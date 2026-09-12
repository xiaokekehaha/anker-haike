# 发现

- 同一工作树三方并行时，认领信息必须落在票面 `Owner` 行与总计划，且要区分会话名（Claude Code A / B），否则两个 Claude 会话会认为「Claude Code」就是自己。
- LangChain 1.x：`init_chat_model(model, model_provider=...)`，openai 兼容厂商传 `base_url`；`ChatAnthropic` 有显式 `output_config` 字段，`model_kwargs` 里放会告警。
- 本机 macOS 无 `timeout` 命令，用 `perl -e 'alarm N; exec @ARGV'` 代替做启动探测。
- models.yaml 中 TBD 的别名占多数（qwen / glm / gemini / embed / rerank），票 10–11 的真实验证只能用 DeepSeek（json_object 策略）；native json_schema 与 tool calling 策略需等 key / id 到位或用假 provider 覆盖。
- DeepSeek（deepseek-chat，2026-09-12）不支持 `response_format: json_schema`（400 「This response_format type is unavailable now」），只支持 json_object 与 function calling；models.yaml 的 `structured: json_object` 正确。tools 策略 token 用量约为 json_object 的 1.8 倍（439 vs 241），json_object 应保持为 DeepSeek 默认策略。
- WeKnora v0.8.0 本机 `registration_mode=self_serve`，`POST /auth/register` 直接返回 tenant.api_key，可脚本化建独立 tenant；平台 key 访问指定空间需再带 `X-Tenant-ID`。
- v0.8.0 知识库创建字段没有 rerank_model_id：rerank 绑定在问答会话层，`knowledge-search` 不经 rerank，因此「rerank 不可用检索仍有结果」在检索接口上天然成立；票 27 的适配器仍要记录 rerank 状态供 evidence.status。
- 百炼 gte-rerank（v1）已于 2026-05-30 下线；gte-rerank-v2 仍是 aliyun 嵌套协议可直连，qwen3-rerank 用 /compatible-api/v1/reranks 与 WeKnora generic provider 固定拼的 /rerank 不兼容，切换需上游适配或反向代理改写路径。
- 手册的证据引用（plans.yaml evidence 段 doc_id#chunk_id）与 WeKnora 实际 chunk id 无法预先对应；票 27 需要在入库后按 `knowledge_title + chunk_index` 或内容锚点（手册里保留了 c12 / c15 等锚点字样）建立映射。
