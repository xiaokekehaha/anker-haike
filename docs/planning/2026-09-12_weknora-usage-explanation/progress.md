# 进度

- 2026-09-12：读取 AGENTS.md、research 与 planning-with-files 技能；定位第 26 项，开始核对本地部署和官方 v0.8.0。
- 本地核查完成：后端 healthy / HTTP 200，UI 未启动；未调用任何数据写入 API，未访问数据库。确认票 26 为设计待实现。
- 官方核查完成：工作空间 / API Key、普通 CSV 与 FAQ 入库、父子分块字符计量、模型登记机制、Rerank 接口差异均已有固定版本源码来源。
- 产出 usage-guide.md、official-research.md；记录 gte-rerank 下线、模型环境变量仅占位、CSV 须业务侧逐条映射等集成差异。仅新增本任务目录文档，没有更改既有设计或代码。
- 用户追问使用方法和页面链接：执行 docker compose --profile ui up -d --no-deps weknora-ui，管理界面已启动。GET localhost:8081/login 返回200且标题WeKnora，后端/health返回200；提交在Codex打开登录页的请求。仅启动UI，没有重建后端、创建账号或导入知识。
