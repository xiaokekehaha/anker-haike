# AWS 本机服务 HTTPS 接入步骤

用一台 EC2 提供公网 HTTPS 入口，前后端、数据库和知识库继续运行在本机。用户没有域名，因此使用固定公网 IP 和受浏览器信任的 IP 地址证书。访问地址为 https://52.221.175.117/，独立访问账号为 viewer，密码读取本机 deploy/tunnel/.env 中的 BASIC_AUTH_PASSWORD；不要把该文件提交或整份发给访问者。

## 资源与访问范围

已部署新加坡 ap-southeast-1 区域、Ubuntu 24.04 LTS x86_64、t3.micro、8 GiB 加密 gp3 根盘、一个 Elastic IP（固定公网 IPv4）。实例只运行 Caddy 和 SSH。资源信息：

| 资源 | 标识 |
| --- | --- |
| EC2 | i-071329930586b100f，haike-public-ingress |
| 固定公网 IP | 52.221.175.117 |
| IP allocation | eipalloc-0d7a7fa902362f03b |
| 安全组 | sg-0df2ecb73362f91a3 |
| 加密根盘 | vol-05d63aa6ec9339151 |

## 费用估算

按每月 730 小时持续运行、不计免费额度计算：

| 项目 | 单价或假设 | 月费用 |
| --- | --- | --- |
| t3.micro 普通 Linux | 控制台显示 0.0132 USD/小时 | 9.64 USD |
| 一个公网 IPv4 | AWS 标准价格 0.005 USD/小时 | 3.65 USD |
| 8 GiB gp3 根盘 | AWS Pricing API 显示 0.096 USD/GiB/月 | 0.77 USD |
| 基础费用 | 不含税费、额外流量、快照和模型调用 | 约 14.05 USD |

此估算不是账单上限；出站流量依实际用量计费。

2026-10-10 控制台 Credits 页面确认：账号有 200 USD 活动抵扣额度，当前已用 0 USD，到期日为 2026-10-31，适用服务包含 Amazon Elastic Compute Cloud、Amazon Virtual Private Cloud 与 AWS Data Transfer。本方案的符合条件服务费用可先由额度自动抵扣；额度耗尽或到期后，继续运行按标准价格计费。额度不是永久免费资源，且余额页面可能有约 24 小时的更新延迟。

## 网络范围

| 端口 | 云端用途 | 入站来源 |
| --- | --- | --- |
| TCP 22 | 本机连接 SSH | 本机出口公网 IP 的 /32 地址 |
| TCP 80 | 证书验证与 HTTPS 跳转 | 公网 |
| TCP 443 | HTTPS 网站与证书验证 | 公网 |
| TCP 15173 | SSH 反向转发的监听端口 | 仅云端 127.0.0.1，不加公网安全组规则 |

网页需要独立的演示访问账号。公网入口的 /admin 与 /admin/* 返回 403；本机管理页面继续使用原地址。数据库、知识库和后端 8000 不配置公网规则。

SSH 反向隧道是由本机主动连接云服务器的端口转发；AWS 收到的网页请求经该连接返回本机。电脑休眠、前端停止或隧道断开时，公网网站不能提供服务。

## 云端配置

1. 用户批准后已创建 EC2 与安全组，配置 SSH 公钥认证，启用根盘加密，实例数为 1。T3 CPU credit 为 Standard，避免额外的 Unlimited CPU credit 费用。
2. 已关联 Elastic IP，访问地址 `https://52.221.175.117/`。
3. 安装官方 Caddy 2.11.7 的 Linux amd64 包。读取该版本发布说明，校验官方 checksum 后安装；该版本修复了 POST SSE 流被 60 秒超时截断的问题。
4. 将 `deploy/tunnel/Caddyfile` 放到 `/etc/caddy/Caddyfile`。
5. `/etc/haike/haike.env` 保存 `PUBLIC_IP`、`BASIC_AUTH_USER` 与 `BASIC_AUTH_HASH`。独立访问密码不复用 AWS 控制台密码；明文仅保存在本机 `deploy/tunnel/.env`，权限 600。密码散列用 `caddy hash-password` 的标准输入生成，避免进入命令参数、历史或日志。
6. `/etc/haike/haike.env` 属主为 root，权限 600。给 Caddy 的 systemd 单元增加以下 drop-in，使服务从该文件读取环境变量：

```ini
[Service]
EnvironmentFile=/etc/haike/haike.env
ExecStart=
ExecStart=/usr/bin/caddy run --config /etc/caddy/Caddyfile
```

7. 覆盖官方服务中的 `--environ` 选项，避免环境变量进入 journal；Caddyfile 设置 `persist_config off`，避免散列展开后产生新的 JSON 配置副本。首次检测到默认日志输出后已轮换访问密码，旧密码失效。
8. 重载 systemd 并启动 Caddy。持久保留服务的证书存储目录；Caddy 按证书续期信息自动续期。设置 `default_sni` 为公网 IP，使不发送 SNI 的客户端能在 AWS 公私网地址映射下选中正确证书。

Let’s Encrypt 的 IP 证书有效期为 160 小时，配置显式选择 `shortlived`。已签发证书的 IP SAN 为 52.221.175.117，签发者 YE1，2026-10-16 21:41 UTC 到期；自动续期由 Caddy 管理。已验证公网证书链，无需添加证书信任或跳过浏览器警告。

## 本机连接

保持原有 frontend-dev 与本机后端运行。本机 launchd（macOS 的后台服务管理器）通过 `~/Library/LaunchAgents/com.haike.aws-tunnel.plist` 直接执行系统 `/usr/bin/ssh`，自动建立反向隧道。macOS 默认限制后台 shell 读取 Documents 下的脚本，直接执行 SSH 避免了该限制，无需修改系统隐私权限。

仓库中的文件供手动连接与凭据查阅使用：

- `deploy/tunnel/connect.sh`
- `deploy/tunnel/.env`

SSH 私钥继续使用已授权的本机密钥，不向云端上传。首次连接时记录了实例在临时 IP 下的主机公钥，`SSH_HOST_KEY_ALIAS` 用该记录校验固定 IP 对应的同一服务器。

后台隧道会在登录时启动，并在连接退出后自动重连。手动连接用于排查问题，命令入口为：

```bash
make -f deploy/tunnel/Makefile connect
```

运行状态与重启入口：

```bash
make -f deploy/tunnel/Makefile status
make -f deploy/tunnel/Makefile restart
```

不要在后台隧道运行时再启动手动连接，同一云端监听端口只能由一个连接占用。SSH 的 `ExitOnForwardFailure` 让监听失败时立即退出；keepalive 让断开的连接及时退出，由 launchd 重新启动。电脑休眠时隧道不能工作。

Caddy 将 HTTP Host 改为 `127.0.0.1:5173`，匹配 Vite 已允许的回环地址；保留正常域名校验。浏览器中的 API 使用同源相对地址，由 Vite 继续代理到本机 8000。

## 验证步骤

已完成：公网未认证首页 401；认证后首页、/health、/@vite/client 均 200；/admin 与 /admin/api/health 均 403；所有 HTTPS 请求的 curl ssl_verify_result 为 0。本机 /admin 仍正常。模拟 POST SSE 事件在 0.3 / 32.3 / 64.3 秒到达，确认跨越 60 秒持续流式返回；测试后已切换为实际 5173 隧道。云端 15173 仅绑定回环地址，LaunchAgent 实际处于 running 状态。

1. 本机 `http://127.0.0.1:5173/` 与 `/health` 返回 200。
2. 云端 `http://127.0.0.1:15173/` 能返回首页。
3. 从外部网络访问 HTTPS 公网 IP，证书链受浏览器信任；未认证时返回 401，认证后首页与 `/health` 返回 200。
4. 使用临时本机响应器发送 0/32/64 秒的 POST SSE 事件，验证代理链路跨越 60 秒持续流式返回，再切换到实际 5173。配置验证不调用模型或知识库；图片上传和真实聊天属于应用演示，不计入本轮只读部署验收。
5. 公网 `/admin` 返回 403；本机 `/admin` 正常。
6. 云端 `ss -lntp` 确认 15173 仅绑定回环地址；后端、数据库和知识库端口不在公网安全组中。

本机出口公网 IP 改变时，SSH 的 /32 来源规则需更新，隧道才能恢复连接；不要把 22 端口改为全网开放。

后台隧道由 launchd 自动重启；需要停用时应卸载该 launchd 服务。停止 EC2 后根盘和已分配的 Elastic IP 仍会收费；结束演示后是否释放资源需另外确认。

## 参考

- [IP 地址证书正式可用](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability)
- [Caddy 2.11.7 发布说明](https://github.com/caddyserver/caddy/releases/tag/v2.11.7)
- [Caddy ACME profile 配置](https://caddyserver.com/docs/caddyfile/directives/tls)
- [Caddy SSE 与 WebSocket 代理](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
- [Caddy default_sni 与配置持久化](https://caddyserver.com/docs/caddyfile/options)
- [AWS 公网 IPv4 费用](https://aws.amazon.com/vpc/pricing/)
- [AWS 根盘费用](https://aws.amazon.com/ebs/pricing/)
