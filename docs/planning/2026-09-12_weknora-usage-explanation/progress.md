# 进度

- 本地模型建议完成：核对 Qwen3-Embedding-0.6B/Ollama 和 BGE-small-zh-v1.5 官方规格，优先建议符合现有 1024 维约定的 0.6B，补充本地检索/云端回答数据流与重建要求。没有安装或下载模型，也没有修改知识库。

- 本地 Embedding 追问：只读查看本机架构/内存及 WeKnora Ollama 适配，开始对比官方轻量模型规格；用户意图为解释和选项建议，本轮不安装、不下载模型、不迁移知识库。

- Embedding 追问完成：只读确认三个库均绑定本机 8099 测试桩；核对百炼目标模型、北京区输入 Token 价格和跨模型重建要求，产出 embedding-explanation.md。未调用付费推理、未更改库/模型配置，未修改业务代码。

- Embedding 追问：已核对目标模型和本地导入记录，继续通过只读 API 验证服务绑定，并核查云端计费与模型切换规则。

- 文件/分块/检索追问完成：核对 v0.8.0 官方文档、界面源码和 RRF/父子分块实现，产出 ingest-chunk-search.md。说明 RRF 与 Rerank 的区别、界面与 API 配置边界、当前未利用父块正文。仅更新说明文档，未写入任何服务数据，未修改业务代码。

- 用户继续追问文件格式、切片/分块的界面操作、关键词与语义多路融合；恢复计划，已核对固定版本文件支持表，继续阅读分块与检索融合实现。

- 本轮核查完成：沿 ingest → adapter → graph.retrieve → graph.reply 验证分工，确认 FAQ 未接当前在线检索、Rerank 配置未用于直接搜索链、图谱/多模态关闭；记录本地 Embedding 桩限制。产出 role-explanation.md 并给旧 usage-guide.md 添加状态提示。本轮未改业务代码、未执行服务写入，文档说明无需运行业务测试。

- 2026-09-12 本轮追问：解释为什么选 WeKnora、项目实际功能与平台定位。恢复既有计划，发现历史“未入库”说明已落后于实现；已读取官方 v0.8.0 README，继续核查代码。

- 2026-09-12：读取 AGENTS.md、research 与 planning-with-files 技能；定位第 26 项，开始核对本地部署和官方 v0.8.0。
- 本地核查完成：后端 healthy / HTTP 200，UI 未启动；未调用任何数据写入 API，未访问数据库。确认票 26 为设计待实现。
- 官方核查完成：工作空间 / API Key、普通 CSV 与 FAQ 入库、父子分块字符计量、模型登记机制、Rerank 接口差异均已有固定版本源码来源。
- 产出 usage-guide.md、official-research.md；记录 gte-rerank 下线、模型环境变量仅占位、CSV 须业务侧逐条映射等集成差异。仅新增本任务目录文档，没有更改既有设计或代码。
- 用户追问使用方法和页面链接：执行 docker compose --profile ui up -d --no-deps weknora-ui，管理界面已启动。GET localhost:8081/login 返回200且标题WeKnora，后端/health返回200；提交在Codex打开登录页的请求。仅启动UI，没有重建后端、创建账号或导入知识。
