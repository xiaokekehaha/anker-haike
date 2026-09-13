# WeKnora 内置对话模型与视觉语言模型配置

日期：2026-09-13　范围：`deploy/weknora/builtin_models.yaml`、`docker-compose.yml`（weknora-app）、`.env.example`

## 问题

WeKnora 网页（http://localhost:8081）打开「快速问答」提示 *智能体未就绪，需要配置以下内容：对话模型*。
该 tenant（10001）只登记了 Embedding（text-embedding-v4、stub-embedding-1024）与 Rerank（gte-rerank-v2），
没有任何 `KnowledgeQA` 类型模型——编排服务自己调模型（config/models.yaml），从没给 WeKnora 配过对话模型。

根因有两层：

1. `deploy/weknora/builtin_models.yaml` 顶层键写成 `models:`，WeKnora 只认 `builtin_models:`。
   启动日志一直是 `[builtin-models] applied: 0 upserted, 0 pruned`，即该文件从未生效；
   现有 Embedding / Rerank 模型其实是 `make kb-bootstrap` / `make kb-ingest` 按 tenant 注册的。
2. 文件里本就没有对话模型与视觉模型条目。

## 改动

`builtin_models:` 下登记两个模型（`is_builtin=true` 对所有 tenant 可见，UI 任一空间都能选到）：

| 类型 | 模型 | 通道 | 用途 |
| --- | --- | --- | --- |
| KnowledgeQA | `deepseek-flash` | https://api.deepseek.com/v1 | WeKnora「快速问答 / 智能推理」等内置智能体的对话模型 |
| VLLM | `qwen3-vl-plus` | 百炼 compatible-mode | 视觉理解 / 多模态解析，为后续图片检索准备 |

选型依据 `config/models.yaml`（2026-09-13.5 实测冻结）：deepseek-flash 是 domestic 链 reply.stream / guide.step
首位（首字 ≈ 1 s、成本最低）；qwen3-vl-plus 是 diagnose.vision 备位，单次可收 10 张图（deepseek 只收 4 张）。

配套：`docker-compose.yml` 的 weknora-app 增加 `LLM_*` / `VLM_*` 环境变量，默认值分别复用 `DEEPSEEK_API_KEY`
与 `DASHSCOPE_API_KEY`；`.env.example` 记录换厂商时才需要填的六个变量。

### 两个坑

- WeKnora 的 `${VAR}` 展开按 `${([^}]+)}` 整段当变量名，**不支持** `:-默认值`；默认值只能写在 compose 的
  `environment:` 里（compose 支持嵌套 `${A:-${B:-}}`）。
- Embedding / Rerank 故意不放进本文件：ingest 的 `ensure_embedding_model` 按「名字」挑模型，
  同名两份（builtin 一份 + tenant 一份）会挑到 id 不同的那份，触发知识库 embedding 变更判定（要 `--recreate-kb`）。
  单一来源约定：**向量 / 重排归 CLI，对话 / 视觉归本文件**。

## 验收（2026-09-13 本机）

```
[builtin-models] upserted: id=builtin-llm-default name=deepseek-flash type=KnowledgeQA
[builtin-models] upserted: id=builtin-vlm-default name=qwen3-vl-plus type=VLLM
[builtin-models] applied: 2 upserted, 0 pruned
```

- `GET /api/v1/models` 返回 5 个模型，新增两个 `is_builtin=true / is_default=true / status=active`。
- UI 实跑一次「快速问答」：`chat model ID: builtin-llm-default`，检索 `vector 11 + keywords 4 → 融合 10 块`，
  正常流式作答（weknora-app 日志 `[PIPELINE] stage=SearchParallel ... total_results=10`）。
- 编排服务 `GET /health` 仍为 `ok`（db / redis / weknora 全 ok），主链路不读 `LLM_*` / `VLM_*`。

## 尚未开启：知识库级图片解析

模型已就位，但三个知识库的 `vlm_config.enabled` 仍为 false、`image_processing_config.model_id` 为空
（与 `orchestrator/app/knowledge/ingest.py` 现有「关闭多模态」一致）。要做图片检索还需要：

1. 在 UI 知识库设置里开启多模态 / 图片解析并选 `qwen3-vl-plus`（或 API 更新 KB 的 `vlm_config`）；
2. 对已入库文档重新解析（图片 caption 与 chunk 是解析期产物，开关不回溯）；
3. `ingest.py` 同步打开多模态，并评估 kb_ver 是否要进位。

这三步会改变入库产物，未在本次改动内执行。
