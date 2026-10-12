"""通过真实 Caddy 请求验证认证边界，使用临时凭据和无数据的响应器。"""

import base64
import json
import re
import secrets
import subprocess
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class AccessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Colima 默认共享用户目录，macOS 的 /var/folders 临时目录不能用作容器挂载。
        cache_dir = Path.home() / ".cache" / "haike-access"
        cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        cls.directory = TemporaryDirectory(prefix="haike-access-", dir=cache_dir)
        cls.addClassCleanup(cls.directory.cleanup)
        task_dir = Path(cls.directory.name)
        cls.passwords = {name: secrets.token_hex(16) for name in ("viewer", "admin")}
        env = ["PUBLIC_IP=127.0.0.1"]
        for name, prefix in (("viewer", "BASIC_AUTH"), ("admin", "ADMIN_AUTH")):
            hashed = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-i",
                    "--network",
                    "none",
                    "caddy:2.11.7-alpine",
                    "caddy",
                    "hash-password",
                ],
                input=cls.passwords[name] + "\n",
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            env.extend(
                [
                    f"{prefix}_USER={name}",
                    f"{prefix}_HASH={hashed}",
                    f"{prefix}_PASSWORD={cls.passwords[name]}",
                ]
            )
        env_file = task_dir / ".env"
        env_file.write_text("\n".join(env) + "\n")
        env_file.chmod(0o600)
        adapted = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--env-file",
                str(env_file),
                "-v",
                str(Path(__file__).with_name("Caddyfile")) + ":/etc/caddy/Caddyfile:ro",
                "caddy:2.11.7-alpine",
                "caddy",
                "adapt",
                "--config",
                "/etc/caddy/Caddyfile",
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        config = json.loads(adapted.stdout)
        config["apps"].pop("tls", None)
        for server in config["apps"]["http"]["servers"].values():
            server["listen"] = [":18444"]
            server.pop("tls_connection_policies", None)
            server["automatic_https"] = {"disable": True}
            server["protocols"] = ["h1"]

        def replace_upstream(node):
            if isinstance(node, dict):
                if node.get("handler") == "reverse_proxy":
                    for upstream in node["upstreams"]:
                        upstream["dial"] = "127.0.0.1:18519"
                for child in node.values():
                    replace_upstream(child)
            elif isinstance(node, list):
                for child in node:
                    replace_upstream(child)

        replace_upstream(config)
        # 同一隔离容器内的第二个 HTTP 服务只回显收到的头，不接触应用数据。
        config["apps"]["http"]["servers"]["echo"] = {
            "listen": ["127.0.0.1:18519"],
            "automatic_https": {"disable": True},
            "protocols": ["h1"],
            "routes": [
                {
                    "handle": [
                        {
                            "handler": "static_response",
                            "body": json.dumps(
                                {
                                    "identity": "{http.request.header.X-Authenticated-User}",
                                    "authorization": "{http.request.header.Authorization}",
                                    "host": "{http.request.hostport}",
                                }
                            ),
                        }
                    ]
                }
            ],
        }
        config_path = task_dir / "config.json"
        config_path.write_text(json.dumps(config))
        request_script = task_dir / "request.sh"
        request_script.write_text(
            "#!/bin/sh\n"
            "IFS= read -r authorization\n"
            "IFS= read -r identity\n"
            "IFS= read -r path\n"
            "IFS= read -r method\n"
            'if [ "$method" = POST ]; then set -- --post-data="{}"; else set --; fi\n'
            'wget -S -O - "$@" --header "Authorization: $authorization" '
            '--header "X-Authenticated-User: $identity" "http://127.0.0.1:18444$path"\n'
        )
        cls.container = "haike-access-" + secrets.token_hex(4)
        subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--network",
                "none",
                "--name",
                cls.container,
                "-v",
                str(config_path) + ":/etc/caddy/config.json:ro",
                "-v",
                str(request_script) + ":/etc/caddy/request.sh:ro",
                "caddy:2.11.7-alpine",
                "caddy",
                "run",
                "--config",
                "/etc/caddy/config.json",
            ],
            capture_output=True,
            check=True,
        )
        cls.addClassCleanup(
            subprocess.run,
            ["docker", "rm", "--force", cls.container],
            capture_output=True,
            check=False,
        )
        last_status = None
        for attempt in range(30):
            try:
                last_status = cls.request("/", None)[0]
                if last_status == 401:
                    return
            except (OSError, TimeoutError):
                pass
            time.sleep(0.1)
        logs = subprocess.run(
            ["docker", "logs", cls.container], text=True, capture_output=True, check=False
        )
        for line in (logs.stdout + logs.stderr).splitlines():
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                if line.startswith("Error:"):
                    print(line)
                continue
            if message.get("level") == "error":
                print(message.get("msg", "Caddy fixture error"))
        raise RuntimeError(f"Local Caddy did not become ready; last HTTP status={last_status}")

    @classmethod
    def request(cls, path, account, *, spoof=None, method="GET"):
        authorization = ""
        if account:
            encoded = base64.b64encode(f"{account}:{cls.passwords[account]}".encode()).decode()
            authorization = "Basic " + encoded
        result = subprocess.run(
            ["docker", "exec", "-i", cls.container, "sh", "/etc/caddy/request.sh"],
            input=f"{authorization}\n{spoof or ''}\n{path}\n{method}\n",
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        statuses = re.findall(r"HTTP/\S+ (\d+)", result.stderr)
        if not statuses:
            raise OSError("No HTTP response from isolated Caddy")
        return int(statuses[-1]), result.stdout

    def test_unauthenticated_requests_are_denied(self):
        for path in ("/", "/admin", "/admin/", "/admin/api/graph"):
            with self.subTest(path=path):
                status, _ = self.request(path, None)
                self.assertEqual(status, 401)

    def test_viewer_cannot_reach_admin_even_with_spoofed_identity(self):
        for path in (
            "/admin",
            "/admin/",
            "/admin/api/graph",
            "/%61dmin/api/graph",
            "/admin%2Fapi/graph",
            "/./admin/api/graph",
            "/outside/../admin/api/graph",
            "//admin/api/graph",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, "viewer", spoof="admin")[0], 401)

    def test_public_requests_remove_identity_and_password(self):
        for account in ("viewer", "admin"):
            for path in ("/", "/health", "/src/admin/main.tsx"):
                with self.subTest(account=account, path=path):
                    status, body = self.request(path, account, spoof="admin")
                    self.assertEqual(status, 200)
                    data = json.loads(body)
                    self.assertEqual(data["identity"], "")
                    self.assertFalse(bool(data["authorization"]))
                    self.assertEqual(data["host"], "127.0.0.1:5173")

    def test_admin_requests_use_authenticated_identity(self):
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                status, body = self.request(
                    "/admin/api/echo", "admin", spoof="forged-user", method=method
                )
                self.assertEqual(status, 200)
                data = json.loads(body)
                self.assertEqual(data["identity"], "admin")
                self.assertFalse(bool(data["authorization"]))
                self.assertEqual(data["host"], "127.0.0.1:5173")


if __name__ == "__main__":
    unittest.main(verbosity=2)
