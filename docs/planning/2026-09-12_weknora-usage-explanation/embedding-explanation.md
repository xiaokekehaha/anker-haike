# Embedding：当前模型、运行位置、计费与兼容

核查日期：2026-09-12。固定版本 WeKnora v0.8.0。本轮只读 GET /models 和 GET /knowledge-bases/{id}，未执行模型推理、知识导入或任何数据写入；未输出 API Key。

## 当前实际使用

只读接口确认 manual、faq、tickets 三个知识库均绑定 `stub-embedding-1024`，维度 1024。该模型登记的端点主机为 `host.docker.internal`、端口 8099，对应本机开发桩。登记 source=remote 表示通过 HTTP 调用独立服务；provider=openai 表示接口协议，两者都不意味着模型在 OpenAI 或其他云厂商运行。

测试桩按词元哈希生成确定性向量，用于验证入库/查询链路，不是经过训练的语义模型，也不会产生云厂商 Embedding 推理费用。此核查确认了知识库绑定配置，没有用推理请求验证端点当前健康状态。

项目目标配置为阿里云百炼 `text-embedding-v4`，使用 OpenAI-compatible API，输出维度设置 1024。当前三个库尚未绑定该目标模型。

来源：[本地导入记录](../../../data/knowledge/manifest.json)、[测试桩](../../../deploy/dev/embedding_stub.py)、[目标模型登记](../../../deploy/weknora/builtin_models.yaml)、[项目模型表](../../../config/models.yaml)。

## Embedding 在做什么

Embedding 把文本变成一组数字向量，供检索引擎计算相似度。文档切片先生成向量并存储，提问时问题也用相匹配的模型生成向量，再寻找相近的文档切片。返回的片段是普通文本，可以交给独立的聊天模型组织答案。

1024 维表示每段文本输出 1024 个数，不表示输入或输出了 1024 个 Token。Token 是模型把输入文本拆分后的计量单位，不与中文字符数固定一比一对应。向量化不是微调或训练聊天模型。

## 本地与云端

- 云端：WeKnora 把需要向量化的文本通过 API 发给云服务；无需本地运行模型权重，需要配置模型名称、端点、API Key 和维度。项目原设计采用这个方式。
- 自建：在本机或自有服务器部署实际 Embedding 模型，再由 WeKnora 调用兼容服务；可以不付云 API Token 费，但需要承担算力和运维成本。
- 测试桩：仅替代接口用于联调，不能代表真实语义模型效果。

没有本地模型且要使用真实语义向量检索时，需要配置云端或其他已部署模型服务；不会在缺失配置时自动切到某个免费云模型。纯关键词检索本身不依赖 Embedding 计算。

## Token 在何时计费

| 操作 | Embedding 费用 |
| --- | --- |
| 普通文本切分、预览 | 不调用 Embedding，不产生其 Token 费 |
| 首次建立文档向量索引 | 对实际送入模型的切片文本按输入 Token 计费 |
| 更新文档或重建向量 | 对重新计算的文本再次计费 |
| 语义检索 | 对实际送入 Embedding 的问题文本计费；库中文档向量复用 |
| pgvector 相似度计算、BM25、RRF | 不调用模型，不产生模型 Token 费 |
| Rerank 与回答生成 | 属于另外的模型调用及计费项 |

文档重叠切片、标题上下文、查询改写或多次请求会影响实际输入量。不能简单用原文件字数或“问题条数 × 固定一次”代表完整账单。

百炼 text-embedding-v4 北京区当前标价：同步输入 0.5 元/百万 Token；Batch File 输入 0.25 元/百万 Token。100 万实际输入 Token 对应同步 Embedding 费用 0.5 元，10 万对应 0.05 元。示例不含其他模型、存储等费用，未抵扣免费额度，地区与账号优惠以官方和控制台为准。普通同步 API 中一次传入多段文本不自动享受异步 Batch File 价格。

来源：[百炼模型价格](https://help.aliyun.com/zh/model-studio/text-embedding-v4)、[百炼 Embedding API](https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api/)。

## 不同模型的兼容性

| 层次 | 结论 |
| --- | --- |
| HTTP/API 协议 | 支持 OpenAI-compatible 协议的服务通常可复用客户端，但仍须检查模型名、认证、输入限制、维度参数与输出结构。不是所有“兼容”服务的可选参数都完全一致 |
| 向量长度 | 必须与检索索引匹配；项目约定 1024 维，换成其他维度需配套调整索引/校验 |
| 向量空间 | 文档和问题应使用同一模型/兼容版本及匹配的处理方式；两模型即使均为 1024 维也不能直接混用向量 |
| 最终聊天模型 | 可独立选择。检索交给它的是文本，因此更换聊天模型不要求重建 Embedding 索引 |

以本项目为例：测试桩文档向量不能配百炼问题向量直接检索。迁移到 text-embedding-v4 需要对已有文档重新生成向量，并让问题向量化采用对应模型。维度同为 1024 只能满足形状匹配，不能证明空间一致。模型名相同但版本、处理参数或实现不同也需验证。

该版本 WeKnora 的直接多库 HybridSearch 还会校验 Embedding 模型身份的一致性，拒绝混合不同模型的多库请求。

来源：[WeKnora OpenAI-compatible 客户端](https://github.com/Tencent/WeKnora/blob/v0.8.0/internal/models/embedding/openai.go)、[多库模型一致性校验](https://github.com/Tencent/WeKnora/blob/v0.8.0/internal/application/service/knowledgebase_search_storegroup.go)。

## 当前迁移边界

本轮仅解释，没有更改配置或导入。项目 `ensure_kb` 复用同名库，`upsert_manual` 跳过 doc_version 相同的条目，因此仅设置百炼 Key 并重跑原导入流程，不保证旧库改绑和旧向量重建。真正迁移需要明确处理库绑定和重建，通常可以建立新模型知识库、重新导入并验证后切换调用方。

来源：[项目导入复用逻辑](../../../orchestrator/app/knowledge/ingest.py)。

## 本地 Embedding 配远程聊天模型

用户后续询问是否可使用简单的本地模型。这个组合可行：文档切片与问题都由同一个本地 Embedding 模型向量化，WeKnora/pgvector 在本地检索，然后把命中的原文片段与问题交给远程聊天模型。原文片段仍会随回答请求发往云端；本地 Embedding 不收云端 Token 费，远程回答按其 API 计费。

优先评估 Ollama 运行 `qwen3-embedding:0.6b`。Qwen 官方规格为 0.6B 参数、支持 1024 维和 100+ 语言；Ollama 官方该标签下载包约 639 MB，下载大小不等于运行内存。与项目现有 1024 维约定匹配，但旧测试桩向量仍须重建。另一轻量中文选项是 `BAAI/bge-small-zh-v1.5`，512 维，需要调整项目维度约定并验证索引配置。

来源：[Qwen 官方模型卡](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)、[Ollama 精确标签](https://ollama.com/library/qwen3-embedding:0.6b)、[BGE 官方模型卡](https://huggingface.co/BAAI/bge-small-zh-v1.5)。

WeKnora v0.8.0 已有原生 Ollama Embedding 适配，也可接兼容接口。只读检查本机为 arm64、16 GiB 内存；据候选模型规模，0.6B 是合理的本机试用起点，但本轮未测实际内存、延迟和召回效果。PATH 中未找到 ollama 命令，不等同于检查了所有安装位置。

安装 Ollama 后，可用 `ollama pull qwen3-embedding:0.6b` 获取指定模型；后续仍需配置 WeKnora 的服务地址/模型/1024 维，建立该模型对应的新索引并验证后切换。不要省略 `:0.6b`，官方库的 latest 当前指向更大的 8b。本文仅给出操作方向，本轮没有安装、下载模型或改写知识库。

来源：[Ollama Embedding 使用说明](https://docs.ollama.com/capabilities/embeddings)、[WeKnora Ollama 适配](https://github.com/Tencent/WeKnora/blob/v0.8.0/internal/models/embedding/ollama.go)。
