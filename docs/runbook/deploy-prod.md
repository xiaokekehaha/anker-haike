# 运行手册：线上 / 对外演示部署（票 46）

整理日期：2026-09-12。决策见 00_decisions D18。发布与回滚见 [release.md](release.md)，数据库见 [database.md](database.md)。

## 1. 密钥管理

- 仓库里只有 `.env.example`（全部密钥项为空）。本机开发用 `.env`（gitignore）。
- 线上：密钥文件放仓库外，默认 `/etc/haike/haike.env`（`chmod 600`，属主为部署账号），内容同 `.env.example` 的键。启动时用 `--env-file` 传给 compose，覆盖文件把 orchestrator 的 `env_file` 换成它，`.env` 不参与。
- 镜像：`.dockerignore` 排除 `.env*`、`releases/`、`data/`、代理证书与口令；Dockerfile 不 COPY 任何 env。
- 校验：`make scan-secrets IMAGE=haike/orchestrator:dev` 扫仓库跟踪文件、`.env` 是否被跟踪、`.env.example` 是否含非空密钥、镜像内是否有 `.env` 或密钥字样；CI（backend.yml）每次提交跑仓库部分。测试里的占位串写成 `sk-test-…` 或行尾加 `scan-secrets:allow`。
- 轮换：改 `/etc/haike/haike.env` 后 `make prod-up`（重建 orchestrator 容器即可，其他服务不动）；WeKnora API key 轮换见票 26 `make kb-bootstrap`。

## 2. HTTPS 反向代理与访问控制

拓扑：外网 → `proxy`（nginx:1.27-alpine，80 → 301 → 443）→ `orchestrator:8000`。覆盖文件把 orchestrator / postgres / weknora-app 的宿主机端口全部收回（`ports: !reset []`），只有 80/443 对外。

| 能力 | 实现 | 配置 |
| --- | --- | --- |
| HTTPS | `deploy/proxy/certs/fullchain.pem` + `privkey.pem`（TLS 1.2/1.3） | 自签：`make proxy-cert HOST=demo.example.com`；正式证书直接放同目录 |
| 访问控制 | 基础认证（bcrypt htpasswd），`/health/live` 例外供探针 | `make proxy-passwd USER=judge`（密码只打印一次）；Authorization 头不透传给应用 |
| 按 IP 限速 | `limit_req` 10 r/s、burst 20，超出 429 | `PROXY_RATE` / `PROXY_BURST` |
| SSE 透传 | `proxy_buffering off`、`proxy_cache off`、HTTP/1.1、读超时 600 s；应用自带 `X-Accel-Buffering: no` | 无需配置 |
| 上传 | `client_max_body_size 6m`（应用侧 5 MB 判定，票 29） | — |

启动 / 停止：

```bash
make proxy-cert HOST=<域名>          # 或放正式证书
make proxy-passwd USER=<账号>
make prod-up HAIKE_ENV_FILE=/etc/haike/haike.env
make prod-down
```

验证清单：`curl -k https://<host>/health` → 401；带账号 → 200；`curl -k -N -u u:p -F text=... https://<host>/sessions/<id>/messages` 首个 `event: run_started` 在 1 s 内到达（不被缓冲）；`ab`/循环 30 次快速请求出现 429；`docker compose ... ps` 只有 proxy 有 `0.0.0.0:443`。

## 3. 已知边界

- 基础认证是「共享口令」级别的访问控制，够演示与内部试用；多用户 / 审计需要真正的登录（前端也要改），不在本票。
- 限速按来源 IP；经 CDN / 公司出口 NAT 时所有人共用一个额度，需调 `PROXY_RATE` 或改成按认证用户限速。
- 自签证书浏览器会告警；对外演示请用正式证书。
- WeKnora UI（8081，profile ui）不在代理后面，线上不要开。
