# Agent-Reach 上游调研

调研日期：2026-09-13。对象：[Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach)。固定源码版本：`da5044d26fc6adddb6554d5679c94ac22e76e428`，提交时间 `2026-09-01T16:09:56+08:00`，包版本 `1.5.0`。源码克隆到 `/tmp/agent-reach-review-20260913`；只读审查，未运行安装器、未安装依赖、未导入凭据、未实测平台搜索。

## 判断

可以借助其上游工具扩展本项目的公开互联网检索，但不能把 `pip install agent-reach` 当成给现有业务 AI 接上搜索。Agent-Reach 的主体是**依赖安装、配置、健康检查和供命令行 Agent 阅读的 Skill**。它本身不是统一搜索 SDK，也没有可供业务后端直接调用的全平台搜索 HTTP 服务。

源码证据：

- [core.py](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/core.py)：`AgentReach` 公开方法只有 `doctor()` / `doctor_report()`，模块和类注释均要求实际搜索/读取直接调用上游工具。
- [MCP server](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/integrations/mcp_server.py)：可以通过 Python 模块启动 **stdio MCP**，但工具列表只含 `get_status`；没有 `search`、`read_url`。不是 Exa MCP 本身。
- [Channel 基类](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/channels/base.py)：通用协议是 `can_handle`、`check`、`ordered_backends`，并无通用搜索/读取契约。所谓多后端路由主要是健康检查选择后端，再让 Agent 按 Skill 调用命令。
- 存在局部 Python 能力，不能笼统说“完全不能 import”：例如 [WebChannel.read](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/channels/web.py)、[V2EXChannel.search](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/channels/v2ex.py)、[雪球 search_stock](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/channels/xueqiu.py)、[transcribe](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/transcribe.py)。这些并未组成统一业务 API。

## 通道及前置条件

下面是固定版本中存在的接入路径，不代表已在本项目服务器实测成功。“无需 Key”也不等于无限配额。

| 场景 | 实际能力来源 | 条件与边界 | 一手证据 |
|---|---|---|---|
| 全网搜索 | `mcporter call exa.web_search_exa` → 远程 Exa MCP | 匿名免费入口存在；有免费层限流。Exa 官方建议生产使用自己的 API Key。Agent-Reach 没有实现搜索方法，也没有统一缓存、限流、结果模型。 | [Agent-Reach 搜索命令](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/skill/references/search.md)、[Exa 官方 MCP 文档](https://exa.ai/docs/reference/exa-mcp) |
| 网页正文 | `curl https://r.jina.ai/URL`，局部 `WebChannel.read()` 也是此路由 | 公共页面可匿名读；Jina 当前公开限额为无 Key 20 RPM、有免费 Key 500 RPM。登录墙、反爬和网络仍会失败；Python helper 固定 30 秒超时、5 MiB 响应上限，不加 API Key。 | [web.py](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/channels/web.py)、[Jina 当前额度](https://jina.ai/zh-CN/reader/)、[Jina Reader 官方源码说明](https://github.com/jina-ai/reader) |
| YouTube 搜索、元数据、字幕 | `yt-dlp`；字幕失败时 Skill 指导 OpenCLI → 音频转写 | 不要求 YouTube Data API Key；依赖支持的 Node/Deno JS runtime。具体视频可能触发 bot 校验或没有字幕。Whisper 兜底需 Groq/OpenAI Key 及 ffmpeg/ffprobe；不是永久免费无条件。 | [youtube.py](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/channels/youtube.py)、[视频操作说明](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/skill/references/video.md) |
| B站搜索、元数据 | `bili-cli` → OpenCLI → B站搜索 API | 其说明将搜索/详情列为无需登录；字幕靠桌面 Chrome/OpenCLI。源码注释称 bili-cli 自 2026-03 停更、yt-dlp 已退出 B站路线，这是维护者观察，非本次实测。 | [bilibili.py](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/channels/bilibili.py)、[视频操作说明](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/skill/references/video.md) |
| Reddit 帖子、评论、搜索 | 桌面 OpenCLI 或 rdt-cli + Cookie | 当前路线必须有登录态；没有 Agent-Reach 零配置匿名搜索路径。rdt-cli 用固定 Git commit 安装；Doctor 不执行可能自动刷新 Cookie 的状态命令。上游说明中国大陆需要代理。 | [reddit.py](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/channels/reddit.py) |
| Twitter、小红书、Facebook、Instagram | 专用 CLI、OpenCLI 或平台 MCP | 深度搜索依赖 Cookie 或已有浏览器登录会话；不适合默认作为无人值守业务请求依赖。实际 Cookie/会话必须单独管理。 | [社交平台命令](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/skill/references/social.md) |
| GitHub、RSS | `gh`、`feedparser` | 工具必须在执行环境存在；GitHub 完整 API 能力受认证与配额约束；RSS 是解析器，仍需目标 Feed 可达。 | [GitHub 命令](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/skill/references/dev.md)、[网页/RSS 命令](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/skill/references/web.md) |

Exa 官方同时提供网页全文获取工具 `web_fetch_exa` 及带域名/日期等控制的 `web_search_advanced_exa`。因此一期甚至可以直接对接 Exa 搜索+阅读，而非为了两条 HTTP/MCP 能力引入整个 Agent-Reach 工具安装栈；最终应按目标网站命中率、正文完整度、延迟和费用选择。[Exa 工具列表](https://exa.ai/docs/reference/exa-mcp)

## 安装器确实会修改哪些地方

[cli.py](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/cli.py) 的 `_cmd_install` 将不带 `--system` 的安装设为检查模式，使用只读 Config；`--dry-run` 仅展示。检查模式仍会运行各通道检查，可能触网，不能理解为纯静态解析。

显式 `--system` 会按环境与缺失项进行以下操作，作用域以用户机器为主，**不局限在本仓库**：

1. 创建 `~/.agent-reach/tools`，保存明确指定的代理等配置。
2. 通过现有 Homebrew 或 apt-get 安装缺失的 gh、Node.js/npm；通过 npm 全局安装 undici、mcporter；写 yt-dlp 的 JS runtime 配置。
3. 用 `mcporter config add ... --scope home` 注册 Exa MCP。
4. 按 `--channels` 安装额外 CLI；服务器模式跳过仅支持桌面的 OpenCLI 类通道。
5. 向所有已存在的 `~/.agents/skills`、`~/.config/opencode/skills`、`~/.openclaw/skills`、`~/.claude/skills` 复制 Skill；若均不存在，默认创建 `~/.agents/skills/agent-reach`。不是只给当前工程开启一个工具。
6. 安装流程不自动读取浏览器 Cookie；登录态需单独配置。Twitter、小红书路线有明确的手工 Cookie / 已有会话约束。

此外，自带 [SKILL.md](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/skill/SKILL.md) 对所有 URL/搜索声明广泛强制触发，会改变读取该 Skill 的编码 Agent 行为；不能等同业务 LangGraph 自动增加工具。项目若只需售后资料检索，应写窄范围适配器，避免原样全局注册造成无关平台路由。

## 依赖、成熟度和生产限制

- [pyproject.toml](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/pyproject.toml) 声明 Python ≥3.10、Beta；基础依赖为 requests、feedparser、python-dotenv、loguru、pyyaml、rich、`yt-dlp[default]>=2026.07.04`，浏览器/MCP 为可选附加依赖。仅为搜索引入它会同时带入媒体工具依赖。
- 存在 [constraints.txt](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/constraints.txt) 测试依赖基线，但 pyproject 使用范围依赖，系统安装还有未固定版本的 npm/CLI；部署需自己固定依赖版本和镜像。[依赖锁定说明](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/docs/dependency-locking.md)
- MCP 模块报错提示安装 `agent-reach[mcp]`，但 pyproject 实际没有 `mcp` extra，只有 `all` 包含 `mcp[cli]`。这是文档/实现不一致的具体例子；不能照抄提示假设装完可用。[MCP 源码](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/integrations/mcp_server.py)
- “doctor 可用”不能当作目标查询验收：网页 `check()` 不触网即返回 ok；Exa 只查配置并返回 warn；YouTube 只验证二进制和 JS runtime；OpenCLI 桥接 ready 不证明登录和具体站点工具可用。[web.py](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/channels/web.py)、[exa_search.py](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/channels/exa_search.py)、[youtube.py](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/agent_reach/channels/youtube.py)
- [LICENSE](https://github.com/Panniantong/Agent-Reach/blob/da5044d26fc6adddb6554d5679c94ac22e76e428/LICENSE) 为 MIT，允许修改、分发和商业用途，要求保留版权和许可声明，并无服务保证。此许可仅说明本仓库代码条件，不代替外部服务配额、各上游工具许可或目标平台条款。

## 对 anker-haike 的接入建议（工程推断）

1. **业务在线检索：**复用项目检索适配器边界，新增受控 Exa HTTP/MCP provider，视正文质量增加 Jina reader。返回结构化 `title/url/content/provider/retrieved_at`，沿用现有引用与检索结果模型。无需安装 Agent-Reach，也不需让业务 LLM 执行任意 Shell。
2. **来源优先级：**内部知识库优先；公开 Anker/产品支持站、手册和官方 FAQ 作为联网补充；社区讨论只作为线索，答案清楚区分官方依据与用户经验。
3. **上线需要项目自己补齐：**凭据配置、目标域名控制、超时与限流、结果缓存、来源留存、外部文本不可信处理、失败时返回内部知识库结果。不能从 Agent-Reach 的“多平台”宣传推导已有这些业务保证。
4. **视频/社区：**更适合作为独立资料采集任务，拿到实际字幕/正文、保留来源、经审核后入库。登录态通道不放在客服问答的同步必经路径。
5. **验收：**在真实部署网络用代表性型号/问题测试查询、命中、正文、引用、空结果、429、超时；这次只完成静态调研，不声称“渠道已打通”。
