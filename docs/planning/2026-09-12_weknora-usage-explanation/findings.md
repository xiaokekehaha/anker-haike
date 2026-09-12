# 本地核查

> 以下早期核查记录保留历史背景。本轮发现知识导入与检索适配器已实现，早期“待实现”和“缺少模型 YAML”的描述不再代表当前代码，详见后续本轮核查。

- 第 26 项状态为 ready-for-agent，验收项均未勾选；包含独立 tenant、两类知识库、幂等导入及快照、父子分块 800/200、百炼远程 Embedding / Rerank。
- README 锁定 WeKnora v0.8.0；API 为 localhost:8080，Web UI 为 localhost:8081，UI 放在可选 compose profile。
- orchestrator 目前有 WeKnora 健康检查和配置字段；检索适配器需继续核查。
- 原有工作区存在 orchestrator/pyproject.toml 和 uv.lock 修改，本任务不改动这些文件。

来源：README.md；docs/planning/2026-09-12_smart-service-tech-design/issues/26-weknora-tenant-seed-ingest.md；orchestrator/app/settings.py。

## 本机运行与设计边界
- docker compose ps：orchestrator、postgres、redis、weknora-app、weknora-docreader 均 healthy；没有 weknora-ui 容器。
- GET http://localhost:8080/health 返回 HTTP 200；localhost:8081 连接失败，与 UI profile 默认不开一致。
- 镜像 v0.8.0 标注源码 revision 1edcd54b43606d9079bb36650efe3f68707a79ea。
- Compose 里 Embedding / Rerank 只有环境变量占位，尚需官方核实模型登记方式；.env.example 模型名留空。
- 03 §3.2：说明书 / FAQ / 排障手册进 kb_manual，CSV 工单每行一条进 kb_tickets；父子 800/200，BM25+向量，图谱关闭。
- 09 §2.2–2.4：条目携带 scope / sku_list / category / doc_version / result；检索先算允许的 knowledge_ids，空集合直接 no_match；未解决工单仅作反证。
- 已有代码以健康探测、模型配置为主，没有第 26 项导入实现；实施计划也将第 26–36 项标为 pending。

## 百炼官方接口核查（2026-09-12）
- text-embedding-v4 支持 1024 维，OpenAI 兼容接口参数名为 dimensions；维度须与 WeKnora 模型配置和索引一致。
  来源：https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api
- 当前官方排序 API 文档明确公告 gte-rerank 于 2026-05-30 下线，推荐 qwen3-rerank；项目 model-selection.md 的首选 gte-rerank 已过时，实现票 26 时需更新并联调。
- qwen3-rerank 使用 compatible-api/v1/reranks，model/query/documents 为顶层字段，响应顶层 results；gte-rerank-v2 使用 api/v1/services/rerank/text-rerank/text-rerank，input / parameters / output 为嵌套结构。不能仅换模型名假设协议相同。
  来源：https://help.aliyun.com/zh/model-studio/text-rerank-api
- 当天官方文档列出的百炼入口有业务空间 ID 和地域信息；具体部署应以对应账号控制台入口为准。本任务未调用付费模型接口，未验证本项目 key 或模型可用性。

## 官方模型登记核查
- 官方后台核查确认：`EMBEDDING_*` / `RERANK_*` 环境变量名为 builtin_models.yaml 示例自定义变量，未挂载该 YAML 时单独传 env 不会自动注册模型。也可从 UI / API 创建模型。现有 Compose 缺少该初始化文件挂载，因此目前只是模型配置占位。
  来源：https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/docs/BUILTIN_MODELS.md

## 父子分块与协议核查
- research 后台代理已确认 chunking_config.enable_parent_child、parent_chunk_size、child_chunk_size 字段；计量单位为 Unicode 字符/rune，非 token。父块保存，子块索引；子重叠固定为 childSize/5。800/200 为项目目标，上游默认4096/384。
- hybrid-search 默认可补 parent_chunk，上层问答 Merge 将相关内容扩为父上下文；skip_enrichment 可关闭补充。
- WeKnora generic rerank 固定附加 /rerank，与百炼新 qwen3-rerank /reranks 不一致；aliyun provider 是嵌套 input/output 协议。仅换模型名不足以保证接入成功。
- 详细源码路径和行号由后台代理写入 official-research.md。

## 本轮角色与功能核查（2026-09-12）
- 当前已有 `orchestrator/app/knowledge/weknora_client.py`、导入模块与会话检索调用；票 26 已补实现记录，需按现有代码确认实际边界。
- 官方 v0.8.0 README 明确涵盖知识管理、RAG 问答、Agent、Wiki、MCP 等能力；不能将框架能力清单等同于本项目已使用功能。
- 当前工作区已有多项其他开发改动，本轮仅更新本说明目录，不更改业务代码，不执行数据库或知识 API 写入。
- `ingest.py:248` 创建三库：manual / faq / tickets；说明书以 Markdown 在线文本入库、CSV 工单逐行导入，FAQ 使用原生批量 replace。
- `ingest.py:36` 配置父子分块 800/200 字符、关闭多模态；manifest 标记图谱关闭、Embedding 维度 1024。
- `graph.py:318` 的 retrieve 节点只检索 kb_manual 与 kb_tickets（每库 top 5）；`adapter.py:234` 使用 HTTP hybrid-search，并传 knowledge_ids。FAQ 入库尚不等于已接入在线检索。
- 范围控制、反证标记、结果截断与证据事件由项目适配器/会话层实现：先用 sku/category 筛选知识 ID，空范围不发请求，再过滤返回结果；失败工单标为 counter_evidence。
- `weknora_client.py` 未封装 WeKnora 问答 / Agent / MCP 会话链路；当前主流程使用自有 LangGraph。
- 本地 manifest 当前记录 `kb_ver=2026-09-12.1+stub-embedding-1024`；这是导入记录，不能等同于已验证真实语义检索效果，也不能单凭该文件断言运行服务此刻模型状态。
- `graph.py:525` 明确 retrieve → reply；reply 通过 ModelRouter 调用模型并传入 evidence，未调用 WeKnora 问答生成。
- 本机保留的官方 v0.8.0 `knowledgebase_search.go` 显示 HybridSearch 执行召回、融合/去重及结果补充，没有独立 Rerank 模型步骤；注释说明聊天管线可后续执行 reranking。
- `deploy/dev/embedding_stub.py` 明确其哈希向量仅用于链路联调，不用于演示/评测。
- 已产出 role-explanation.md，修订 usage-guide.md 的历史状态提示。

## 文件、分块与融合追问（2026-09-12）
- 官方 v0.8.0 文档解析说明列出 PDF、Word、PPT、Excel、EPUB、XMind、文本/Markdown/CSV/JSON、URL/HTML/MHTML、图片和音频；图片内容理解需视觉模型，音频需 ASR。
- 官方说明支持知识库解析设置、上传批次覆盖以及分块列表编辑；后续核对具体分块策略和融合源码。
- `docs/CHUNKING.md` 与功能说明支持 auto / heading / heuristic / legacy(recursive)，界面有 Chunking 设置和样本文本预览；旧文档改策略后需重新解析，不能仅保存配置即宣称重切完成。
- `knowledgebase_search_fusion.go` 确认两路都有结果时使用加权 RRF：vectorWeight/(k+vectorRank) + keywordWeight/(k+keywordRank)，按 chunk_id 去重；只有一路命中时保留该路分数去重排序。
- RRF 融合排序与调用模型做 Rerank 不同。当前项目的直接 hybrid-search 已包含前者，不包含后者；不应将此前“未使用 Rerank”解释为“未做多路合并排序”。
- 分块界面源码确认策略下拉、分隔符、大小/重叠、父子开关与大小、预览组件；单块编辑会触发索引更新，改变全库切分配置则需重新解析旧文档。
- 项目 `chunking_config()` 未填写 strategy，上游将空值按 legacy/recursive 处理，不能称项目已启用 auto。父块 800、重叠 80，子块 200、子重叠按上游 childSize/5 为 40。
- 上游配置默认 RRF k=60、向量权重 0.7、关键词权重 0.3，参数属于 workspace/tenant retrieval config；这些是源码默认值，未读取运行空间的当前配置。
- 项目适配器只取命中 `content` 并保留 parent_chunk_id，未消费返回的父块正文；因此“父子分块开启”不等于“当前模型已拿到完整父块上下文”。
- RetrievalSettings.vue 界面支持 TopK、关键词/向量阈值和 Rerank 配置，但未暴露 RRF 权重控件；该版本自定义 RRF 权重使用后端检索配置 API。
- 已产出 ingest-chunk-search.md，含文件表、界面操作、分块机制、RRF 流程图与当前项目边界。

## Embedding 模型、计费与兼容追问（2026-09-12）
- 当前 config/models.yaml、builtin_models.yaml 和 CLI 定义目标模型为百炼 text-embedding-v4，OpenAI-compatible 协议、1024 维；本地 manifest 仍记录 stub-embedding-1024，需只读核对服务绑定。
- 百炼官方检索结果明确支持按输入 Token 计费和 OpenAI-compatible Embedding API；继续读取具体计费单位及地区。
- 已通过 GET /models 和 GET /knowledge-bases/{id} 只读确认：manual、faq、tickets 三库均绑定 `stub-embedding-1024`，1024 维；登记 source=remote、provider=openai。未调用 Embedding 推理或任何写入 API，未输出凭证。
- 百炼官方 text-embedding-v4 北京区标价：同步文本输入 0.5 元/百万 Token，Batch File 0.25 元/百万 Token；本次无需推理调用即可核查价格。项目同步请求内批量 input 不等于云厂商异步 Batch File 产品。
- 项目 Ingestor.ensure_kb 会复用同名已存在知识库、upsert_manual 会跳过同 doc_version 文档；仅改环境变量并重跑常规导入不能被保证为完成模型迁移。
- 只读确认当前绑定模型端点为 host.docker.internal:8099，对应本机开发桩；remote 为 HTTP 调用方式、openai 为兼容协议，不代表云端/OpenAI 模型。
- 已核对官方 v0.8.0 OpenAI-compatible 请求结构和多库 Embedding 身份校验：API 兼容、维度匹配、语义向量空间一致性是不同要求。
- 已产出 embedding-explanation.md；当前实际模型状态已从此前仅依据 manifest 提升为只读服务绑定核查，仍未做推理健康验证。

## 轻量本地模型追问（2026-09-12）
- 本机 uname -m=arm64，hw.memsize=17179869184（16 GiB）；command -v ollama 无输出，只能说明 PATH 中未找到 CLI。
- Ollama 官方模型库列出 qwen3-embedding:0.6b，下载包 639 MB；默认 latest 是较大的 8b，推荐命令必须显式指定 0.6b。
- WeKnora v0.8.0 已有原生 Ollama Embedding 适配；项目仍约定 1024 维。
- Qwen 官方卡确认 0.6B 参数、输出支持至 1024 维、100+ 语言；Ollama 下载包大小不代表运行内存。BGE-small-zh-v1.5 为中文轻量备选，512 维会涉及项目维度调整。
- 本地向量化 + 本地检索 + 远程聊天可独立组合；发往远程的是问题和原文片段，因此回答依旧产生云 API 费用。本轮不宣称实测性能。
- 已补充 embedding-explanation.md 本地候选及接入方向，保留必须重建测试桩向量的要求。
