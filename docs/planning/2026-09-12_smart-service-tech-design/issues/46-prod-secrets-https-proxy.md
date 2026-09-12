# 46: 生产就绪：密钥管理、HTTPS 反向代理与访问控制

**What to build:** 线上部署前置：所有 API key 与数据库口令从 .env 移到密钥文件或环境注入，不进镜像；前置 Nginx / Caddy 提供 HTTPS 与 SSE 透传（关闭缓冲）；对外接口加最简访问控制（共享 token 或基础认证）与按客户端 IP 的限速。设计文档按演示环境编写，本票超出原范围，需回填决策表。

**Blocked by:** 01（Compose 骨架与 /health 聚合）

**Status:** done（2026-09-12）

**Owner:** Claude Code A（2026-09-12 认领；`deploy/proxy/`（Caddy 或 nginx HTTPS 反代）、compose profile、访问控制与密钥管理文档；不改业务代码）

- [x] 镜像与仓库中扫描不到任何真实密钥（scripts/scan-secrets.sh：跟踪文件正则扫描 + .env 未跟踪 + .env.example 密钥项为空 + 镜像内无 .env / 密钥字样；CI 每次提交跑；.dockerignore 排除 .env*）
- [x] 通过 HTTPS 访问且 SSE 首事件不被代理缓冲（nginx TLS 1.2/1.3；实测 https 发消息首字节 11 ms、总 4.1 s，run_started 立即到达；80 → 301 https）
- [x] 无 token 的请求被 401 拒绝（基础认证 bcrypt htpasswd；实测无认证 401、带认证 200、/health/live 探针免认证 200；按 IP 限速 10 r/s + burst 20：60 并发 → 21×200 / 39×429）
- [x] 决策表新增一条线上部署决策并引用本票（00_decisions D18）

**设计依据：** 00 D8；04 §5；07 §10、§15

**实现记录（2026-09-12，Claude Code A）：** `deploy/proxy/templates/default.conf.template`（nginx 官方镜像 envsubst 渲染；变量 PROXY_SERVER_NAME / PROXY_RATE / PROXY_BURST）、`deploy/prod/docker-compose.prod.yml`（proxy 服务；orchestrator / postgres / weknora-app `ports: !reset []`；orchestrator `env_file: !override` 指向仓库外密钥文件，默认 /etc/haike/haike.env）、`scripts/proxy-cert.sh` / `proxy-passwd.sh` / `scan-secrets.sh`、`.dockerignore`、Makefile prod-up / prod-down / proxy-cert / proxy-passwd / scan-secrets、docs/runbook/deploy-prod.md。实测 prod 组合的 compose config 里只有 proxy 发布宿主机端口。

**踩坑：** 多文件 compose 的相对路径以第一个文件目录为基准，覆盖文件里写 `../proxy` 会指到仓库外并挂进空目录；已改为 `./deploy/proxy/...`。共享 token 方案选了基础认证：前端零改动、SSE 与静态资源天然携带；多用户 / 审计留待真正登录。
