# 进度

## 2026-10-10 14:16

- 已完整读取 Makefile、现有 Nginx 代理模板及生产 Compose 覆盖文件。
- 已确认用户没有域名。
- 已核对 IP 地址证书和公网 IPv4 的官方说明；正在确认代理实现和服务器费用。
- 尚未创建或修改 AWS 云资源。

## 配置准备

- 新增 deploy/tunnel/Caddyfile、空值 env 模板和 deployment.md。
- 配置包含公网访问认证、IP 证书自动续期、回环端口转发、SSE / WebSocket 透传；公网管理页面返回 403。
- 原有前后端配置未修改。

## 创建前核对

- 新加坡 EC2 列表显示没有实例，创建向导可用。
- 控制台确认 t3.micro 普通 Linux 0.0132 USD/小时，选中普通 Ubuntu 24.04 镜像；尚未点击启动。
- 官方 Caddy 2.11.7 镜像的配置解析通过，验证容器禁止网络连接。
- 部署方案包含约 15 USD/月基础费用估算、端口范围与验收步骤；公网实际验证待创建后进行。
- 已发出具体资源创建确认请求，等待用户答复；未创建云资源。
- 用户同意部署后追问账号额度；先核对 Billing / Credits / Free Tier，尚未创建收费资源。
- Credits 已确认 200 USD 余额、2026-10-31 到期及 EC2 / VPC / Data Transfer 适用范围；已向用户说明抵扣和到期后的费用，继续已批准的部署。
- 创建表单已配置 HTTP/HTTPS、SSH 当前公网 IP /32、8 GiB gp3 加密根盘和 Standard CPU credit。使用 cloud-init 注入现有 SSH 公钥，未传输私钥。
- 浏览器与本机出口公网 IP 一致；正在核对创建参数，尚未启动实例。
- 已成功启动 i-071329930586b100f；实例详情验证 AMI 为 Ubuntu 24.04 ami-03acbba64aef9bf5c。临时公网 IP 为 13.229.204.196，接下来关联固定 IP。
- SSH 登录与 cloud-init 完成已验证，代理和 bootstrap 脚本已上传。固定 IP 管理页未加载，改用同账号的官方 CloudShell 查询和关联。
- Elastic IP 52.221.175.117 已关联实例，关联 ID eipassoc-0cfb07301767a60c3。
- AWS Pricing API 确认 gp3 0.096 USD/GiB/月，基础费用合计约 14.05 USD/月。
- 官方 Caddy checksum 使用 SHA-512；首次校验未通过格式检查，安装前已停止并修正算法，没有跳过校验。
- Caddy 2.11.7 安装并启动，Let's Encrypt IP 证书成功签发。
- 官方 systemd 单元的 --environ 将访问凭据写入日志；已关闭环境输出、移除云端明文密码并轮换独立访问密码。实际凭据只在本机 deploy/tunnel/.env，权限 600；云端 env 仅保留散列。
- 关闭 Caddy JSON 配置持久化，避免环境展开后的访问散列生成新的配置副本。
- 补充 default_sni 以支持 AWS 公私网 IP 映射与不发送 SNI 的客户端。公网 HTTPS 返回 401，证书校验为 0。
- CloudShell 已确认实际加密 8 GiB gp3、standard CPU credit 与安全组入站规则。
- 正在执行跨越 60 秒的模拟 POST SSE 流测试，不调用真实模型或知识库。

## 验收完成

- 模拟 POST SSE 的三个事件分别在 0.3 / 32.3 / 64.3 秒到达；Authorization 未转发到本机，Host 正确重写，测试响应器与临时隧道已停止。
- macOS 拒绝 launchd shell 读取 Documents 下脚本，改为 LaunchAgent 直接启动 /usr/bin/ssh，未更改系统隐私权限。
- 本机 com.haike.aws-tunnel 已运行，配置 RunAtLoad / KeepAlive 自动重连；云端 15173 仅监听 127.0.0.1。
- 公网未认证首页 401；认证后首页、/health、/@vite/client 均 200；/admin 与 /admin/api/health 均 403，所有 HTTPS 证书校验结果为 0。
- 本机首页、/health、/admin 仍为 200。未执行真实模型、知识库、图片上传或数据库修改。
- shell 语法与 LaunchAgent XML 校验通过；未修改应用前后端代码，未提交 Git。

## 公网 502 修复

- 用户报告公网 502。只读 HTTPS 检查稳定复现首页 502，证书校验为 0；本机首页和健康检查仍为 200。
- 本机网络路由经过 utun4，出口 IP 从 103.167.140.181 变为 188.253.120.162；SSH 连接超时。
- CloudShell 确认 SSH 规则 sgr-0789c6cda4f7121ec 仍允许旧地址 103.167.140.181/32。
- 将该规则替换为当前地址 188.253.120.162/32，仍只允许一个当前网络地址访问 TCP 22；重启本机 LaunchAgent 隧道。
- 原 HTTPS 复现脚本已转为通过：首页和 /health 均 200，证书校验为 0。不调用模型、知识库或数据库。
- 用户确认电脑是否影响可用性：当前应用仍运行在本机，关机、休眠或停止本机服务时公网不可用；持续独立运行需要完整云端部署。
