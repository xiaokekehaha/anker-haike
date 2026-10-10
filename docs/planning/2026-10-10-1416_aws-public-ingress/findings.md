# 核对结果

- Vite 监听本机 5173，API 使用同源相对路径，并转发到 127.0.0.1:8000。
- 聊天使用 SSE；代理应透传流式响应和 Vite WebSocket。
- 前端入口包含 /admin，现有代理配置提供基础认证、HTTPS 和 SSE 不缓冲。
- 用户没有可配置 DNS 的域名。
- AWS 默认 us-west-2 区域控制台显示实例数和 Elastic IP 数均为 0；其他区域未确认。
- Let's Encrypt 已于 2026-01-15 公布 IP 地址证书正式可用，证书有效期 160 小时，必须自动续期。
  来源：https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability
- AWS 公网 IPv4 标准价格为每小时 0.005 美元。
  来源：https://aws.amazon.com/vpc/pricing/
- 当前其他会话已有 .gitignore 和若干文档改动，本轮只写自己的新增文件。
- 控制台区域菜单包含新加坡 ap-southeast-1，区域已启用；适合作为本轮报价和接入测试的候选区域，实际链路速度仍需部署后测量。
- 本机 5173 首页和 /health 的只读请求均返回 200。
- Caddy 当前正式版为 2.11.7；已完整读取其 ACME issuer 源码，支持 profile shortlived。该版修复了 POST SSE 被 60 秒超时截断的回归，应采用此版而非 2.11.6。
  来源：https://github.com/caddyserver/caddy/releases/tag/v2.11.7
- Caddy 对 text/event-stream 自动立即刷新响应，并支持 WebSocket；不必额外设置 flush_interval -1，后者会改变客户端断开后的上游取消行为。
  来源：https://caddyserver.com/docs/caddyfile/directives/reverse_proxy
- 新加坡实例列表已加载，明确显示没有实例；已打开创建向导，尚未点击启动。
- 创建向导的 t3.micro 选项显示普通 Linux 按需价格为 0.0132 USD/小时，2 vCPU / 1 GiB；Ubuntu Pro 另有加价，方案使用普通 Ubuntu。
  来源：AWS 新加坡 EC2 控制台创建向导，2026-10-10 核对。
- CertMagic v0.25.6 源码的 ACME PreCheck 明确允许 Let's Encrypt 签发 IP 证书。
  来源：https://github.com/caddyserver/certmagic/blob/v0.25.6/acmeissuer.go
- 官方 Docker 镜像 caddy:2.11.7-alpine 的 adapt 解析成功；验证容器使用 --network none，不申请证书，不访问模型或知识库。
- 控制台已选普通 Ubuntu Server 24.04 x86_64 与 t3.micro，AMI 为 ami-03acbba64aef9bf5c。未创建密钥对、安全组或实例。
- 按 730 小时计算，EC2 与一个 IPv4 合计 13.286 USD/月；8 GiB gp3 暂预留约 1 USD，区域精确单价待创建前复核。约 15 USD/月仅为基础费用估算。
- Billing / Credits 已显示活动抵扣额度 200 USD，已用 0 USD，到期 2026-10-31；完整服务列表包含 EC2、VPC 和 AWS Data Transfer，相关费用可由有效额度抵扣。余额估算约每 24 小时更新。
- i-071329930586b100f 已启动，SSH 公钥登录成功，cloud-init status 为 done，远端实际系统为 Ubuntu 24.04.4 x86_64。
- CloudShell 确认新加坡此前没有 Elastic IP；固定 IP 52.221.175.117 已关联实例，allocation id 为 eipalloc-0d7a7fa902362f03b，association id 为 eipassoc-0cfb07301767a60c3。
- CloudShell 实际资源查询确认：vol-05d63aa6ec9339151 为 8 GiB gp3 加密盘；CPU credit 为 standard；安全组仅开放 80/443 到公网，22 仅允许 103.167.140.181/32。
- AWS Pricing API 确认新加坡 gp3 为 0.096 USD/GiB/月；730 小时的基础费用合计约 14.05 USD/月。
- Let's Encrypt 已签发 IP SAN 为 52.221.175.117 的证书，签发者 YE1，2026-10-16 21:41 UTC 到期；Caddy 管理自动续期。
- HTTPS 无认证请求返回 401，curl ssl_verify_result 为 0；使用 default_sni 适配不发送 SNI 的 IP 客户端。
  来源：https://caddyserver.com/docs/caddyfile/options#default-sni
