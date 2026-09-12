# 本地核查

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
