#!/bin/sh
# 通过 SSH 在新建的 Ubuntu 公网入口执行；密码仅保存到 env 文件。
set -eu

public_ip=${1:?PUBLIC_IP is required}
caddy_version=2.11.7
task_dir=$(mktemp -d)
trap 'rm -rf "$task_dir"' EXIT HUP INT TERM

cd "$task_dir"
curl -fsSLO "https://github.com/caddyserver/caddy/releases/download/v${caddy_version}/caddy_${caddy_version}_linux_amd64.deb"
curl -fsSLO "https://github.com/caddyserver/caddy/releases/download/v${caddy_version}/caddy_${caddy_version}_checksums.txt"
sha512sum --ignore-missing -c "caddy_${caddy_version}_checksums.txt"
sudo apt-get update -q
sudo apt-get install -y ./"caddy_${caddy_version}_linux_amd64.deb"
sudo systemctl stop caddy

sudo install -d -m 700 /etc/haike
sudo install -d -m 755 /etc/systemd/system/caddy.service.d
sudo install -m 644 /home/ubuntu/Caddyfile /etc/caddy/Caddyfile
sudo install -m 644 /home/ubuntu/sshd-keepalive.conf /etc/ssh/sshd_config.d/30-haike-tunnel-keepalive.conf
sudo /usr/sbin/sshd -t
sudo systemctl reload ssh

if ! sudo test -s /etc/haike/haike.env; then
	umask 077
	basic_password=$(openssl rand -hex 16)
	basic_hash=$(printf '%s\n' "$basic_password" | caddy hash-password)
	sudo install -m 600 /dev/null /etc/haike/haike.env
	{
		printf 'PUBLIC_IP=%s\n' "$public_ip"
		printf 'BASIC_AUTH_USER=viewer\n'
		printf "BASIC_AUTH_HASH='%s'\n" "$basic_hash"
	} | sudo tee /etc/haike/haike.env >/dev/null
	# 首次生成的明文密码仅供管理员安全取回，不进入 Caddy 的进程环境。
	printf 'BASIC_AUTH_PASSWORD=%s\n' "$basic_password" > /home/ubuntu/.env
	chmod 600 /home/ubuntu/.env
fi

printf '[Service]\nEnvironmentFile=/etc/haike/haike.env\nExecStart=\nExecStart=/usr/bin/caddy run --config /etc/caddy/Caddyfile\n' > env.conf
sudo install -m 644 env.conf /etc/systemd/system/caddy.service.d/env.conf
sudo sh -c 'set -a; . /etc/haike/haike.env; set +a; caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null'
sudo systemctl daemon-reload
sudo systemctl enable --now caddy
sudo systemctl is-active caddy
