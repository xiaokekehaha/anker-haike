# 第 26 项：WeKnora 使用与入库说明

> 这是早期使用说明，其中“待实现”“缺少模型配置挂载”等状态已过时。当前接入范围与已实现功能请见 [WeKnora 在本项目中的作用](./role-explanation.md)。

核查日期：2026-09-12。框架基线：本项目 Docker 镜像 WeKnora v0.8.0。

## 当前项目状态

WeKnora 后端和 docreader 已运行，`GET http://localhost:8080/health` 返回 200。用户追问页面链接后，已启动 Compose 的 `ui` profile 中的 weknora-ui；`GET http://localhost:8081/login` 返回 200，页面标题为 WeKnora。第 26 项状态仍为 `ready-for-agent`，两类知识库导入和模型配置仍待实现。

管理界面的启动方式（已执行，仅启动 UI）：

```bash
docker compose --profile ui up -d --no-deps weknora-ui
```

启动后访问 http://localhost:8081。http://localhost:8000 是项目自己的售后前端，http://localhost:8080 是 WeKnora API。

| 页面 | 本机链接 |
| --- | --- |
| 登录 / 注册入口 | http://localhost:8081/login |
| 知识库列表 | http://localhost:8081/platform/knowledge-bases |
| 模型管理 | http://localhost:8081/platform/settings?section=models |
| 设置 | http://localhost:8081/platform/settings |

内部页面需要先登录；路径已按 v0.8.0 前端路由核对。

WeKnora 自带管理界面，可创建知识库、登记模型、上传文件 / 网页 / 在线文本、查看解析状态、预览或编辑切片，以及做知识问答。tenant 在界面里叫「工作空间」，用于隔离项目资料和权限。操作顺序为：登录 → 进入或创建项目工作空间 → 在模型管理登记远程模型 → 创建知识库并绑定 Embedding、配置切片 → 导入文件并等待处理完成 → 检索验证。在「空间设置 → API Key」创建服务端访问密钥；编排服务用它调用 WeKnora。

来源：[固定版快速上手](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/website-docs/01-getting-started/03-quickstart.md)、[空间与权限](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/website-docs/03-features/01-tenant-auth.md)。

来源：[README](../../../README.md)、[部署配置](../../../docker-compose.yml)、[第 26 项](../2026-09-12_smart-service-tech-design/issues/26-weknora-tenant-seed-ingest.md)。

## 第 26 项要落地的内容

项目设计为一个独立 tenant 配置访问凭证，在其中准备两类知识：

| 知识库 | 数据 | 导入目标 |
| --- | --- | --- |
| kb_manual | 2 份说明书 PDF、约 50 条 FAQ、1 份排障手册 | 可追溯的产品说明及标准排障依据 |
| kb_tickets | 约 200 条历史工单 CSV | 每条工单可单独检索，保留型号、症状、原因、步骤、结果 |

文档 / 工单须关联 `scope`、`sku_list`、`category`、`doc_version`，工单再加 `result`。这些字段用于区分适用型号与通用知识；未解决工单只能作为反证。

导入脚本需要处理清洗、字段映射、去重、调用导入 API、等待索引完成以及记录导入清单和版本。快照与回滚也属于票面待实现工作。不能仅凭框架能上传文件就认为这些业务要求已经满足。

PDF 可直接走文档上传；FAQ 按现有设计整理为 Markdown 放入 kb_manual，或另建框架原生 FAQ 类型知识库（标准问 / 相似问 / 答案），这是两种不同组织方式。工单 CSV 要由脚本逐行映射为独立知识条目，并关联 metadata。上游普通 CSV 上传会把整张表转成 Markdown 再通用分块，不会自动让每行拥有独立 knowledge_id 和业务元数据。

来源：[知识导入 API](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/docs/api/knowledge.md)、[FAQ API](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/docs/api/faq.md)、[CSV 转换源码](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/internal/infrastructure/docparser/builtin_converter.go#L180)。

来源：[详细设计 §3.2](../2026-09-12_smart-service-tech-design/03_detailed-design.md)、[产品适用范围 §2](../2026-09-12_smart-service-tech-design/09_plans-rules-knowledge.md)。

## Embedding 与在线检索的分工

入库的主要过程为：原文件 / 文本 → 解析正文（扫描件视配置使用 OCR / 视觉解析）→ 分块 → 对子块调用 Embedding → 保存片段与向量索引。上传成功之后还需等异步解析和索引任务完成。

项目目标为父子分块，核心配置示例如下（80 是显式选择的父块重叠值，票面只规定 800 / 200）：

```json
{
  "chunking_config": {
    "enable_parent_child": true,
    "parent_chunk_size": 800,
    "child_chunk_size": 200,
    "chunk_overlap": 80
  }
}
```

v0.8.0 这里按 Unicode 字符计数，不是 token。先把文档切成父块，再在每个父块内切子块。父块保存较完整上下文，不做向量索引；子块用于检索。子块重叠量由实现取 `child_chunk_size / 5`，200 对应 40 个字符。800 / 200 是本项目选值，上游默认父 4096 / 子 384。

切片会结合所选策略尽量保留标题、段落、句子、表格行等结构；800 / 200 是尺寸配置，不能理解为每块都精确等长。UI 可预览切片。修改参数后，既有文档需要重新解析 / 重建索引。

例如一个父块包含“滤网堵塞的症状、检查、清洁和复装说明”，其子块分别覆盖这些内容。用户问“吸力小且声音变大”时可先命中症状子块，检索增强返回关联的 `parent_chunk`；上层问答流程再合并父块，取得完整操作上下文。自行调用搜索 API 的适配器需处理这些返回字段；`skip_enrichment=true` 会跳过补充。

源码细节与固定版本链接见 [官方核查记录](official-research.md)。

Embedding 将文本转换为表示语义的数值向量，例如把一个片段转换为 1024 个数字。它服务于相似内容检索，不是训练聊天模型。入库时对知识片段向量化；搜索时用同一模型把用户问题向量化，再比较相似度。

本项目设计使用百炼远程 `text-embedding-v4`，1024 维，存入 PostgreSQL/pgvector。该模型支持 1024 维；调用参数、模型登记信息和向量索引必须一致。更换 embedding 模型，即使维度相同，也需重新生成库内向量；设计要求 `kb_ver` 记录所绑定的模型。

来源：[项目模型设计 §2](../2026-09-12_smart-service-tech-design/model-selection.md)、[百炼官方 Embedding API](https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api)。

BM25 用于字面词语、型号、错误码匹配；向量用于意思接近但措辞不同的匹配；Rerank 对候选资料进一步排序；最后由项目的编排服务结合证据推进排障、生成回复。

## 需要更新的模型配置

当前 Compose 传入 `EMBEDDING_*` / `RERANK_*` 环境变量，还不能让 WeKnora 自动创建模型。v0.8.0 需要通过 UI / API 登记模型，或者用 `builtin_models.yaml` 引用这些变量后挂载该文件；官方示例明确这些变量名由 YAML 自定义。模型登记后再选择 / 绑定给知识库或对应检索会话。

来源：[WeKnora v0.8.0 内建模型说明](https://github.com/Tencent/WeKnora/blob/1edcd54b43606d9079bb36650efe3f68707a79ea/docs/BUILTIN_MODELS.md)。

项目文档首选 `gte-rerank` 已过时：百炼当前文档公告其于 2026-05-30 下线，推荐 `qwen3-rerank`。不同排序接口的请求和响应结构存在差异，实施时需同时核对模型名、地域 / 业务空间 URL、provider 和协议，不能只替换名称。尚未使用本项目凭证调用模型验证。

官方 v0.8.0 的 generic reranker 会在 base_url 后附加 `/rerank`（单数），与百炼 qwen3-rerank 的 `/reranks`（复数）入口不直接一致；aliyun reranker 则用 `input` / `parameters` / `output.results` 协议。`gte-rerank-v2` 的官方协议与后者相符，是可联调的候选；`qwen3-rerank` 需要验证路径映射或适配方案。此处为源码 / 文档对照结论，未作远程调用验收。

来源：[百炼官方 Rerank API](https://help.aliyun.com/zh/model-studio/text-rerank-api)。

## 核查范围

本次读取代码、设计、容器状态和公开文档，新增说明文档，并在用户追问页面使用方式后启动管理 UI；未创建 tenant、导入知识或改动数据库，未修改既有设计或其他正在开发的代码。
