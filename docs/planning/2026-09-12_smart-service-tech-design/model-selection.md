# 难点、业内方案与模型选型

整理日期：2026-09-12。补充 tech-stack-survey.md 中「模型」一行：每个难点业内怎么解、可用哪些模型、是否需要多模态，以及远程多模型适配层如何设计。

## 0. 部署形态结论

2026-09-12 用户决定：不考虑本机部署模型，全部远程调用。本机 M5 / 16 GB 的可行性分析保留在文末附录仅作参考。设计重点转为「一套适配层接多家模型 API，按环节路由」。

## 1. 逐难点分析

### 1.1 情绪识别与安抚

- 业内做法：不单独训分类器，用 LLM 在意图抽取时顺带输出情绪标签（平静 / 焦急 / 愤怒）和触发线索，写入会话状态，再由系统提示切换语气与步骤粒度。低情绪分或连续两轮愤怒直接触发转人工，这是各家客服平台的共同兜底规则。
- 可选模型：任何指令模型都能做三级分类；不需要专门的情感模型。
- 远程：任一厂商轻量档即可（haiku-4-5 / qwen flash / deepseek）。
- 多模态：不需要。
- 注意点：中文口语里的反讽和表情符号（「谢谢😡」）轻量模型容易误判；演示脚本里的用户话术先用强模型跑一遍校验标签，再决定 intake 用轻量档还是中档。

### 1.2 产品消歧

- 业内做法（Adobe、Elastic、Flippi 电商助手的共同模式）：
  1. 先做产品意图抽取，把用户话里的型号、别名、品类线索抽成结构化字段。
  2. 用「精确匹配 + 别名表 + BM25 + 向量」混合检索缩小候选，型号和 SKU 这类实体靠关键词兜住，向量只做泛化。
  3. 候选唯一直接通过；多命中且证据接近时才追问，追问以卡片形式给 2–3 个选项，不让用户自由输入。
  4. 用会话历史做独立问句重写，解决「第二个」「那个」这类指代。
- 可选模型：任一文本模型 + 中英双语 embedding。产品目录小，重点是别名表和 BM25，不是模型大小。
- 远程：轻量档即可。
- 多模态：可选。若用户直接拍产品或机身铭牌，用视觉模型读型号可以省一轮追问，是演示加分点。

### 1.3 故障定位（多模态）

- 业内做法：视觉模型只负责「看图说观察」，输出结构化描述（指示灯颜色、屏幕报错码、部件状态），不直接下结论；文本模型把观察 + 用户描述拼成查询，走知识库和历史工单混合检索，再汇总成带置信度和依据的假设列表。分两步是为了可解释，也为了视觉模型能换。
- 可选模型：闭源里 Claude 文档 / 图表理解领先，Gemini 多图强；国产 API 里 Qwen-VL 静态图与 OCR 最强，GLM-V 偏视频与界面操作。
- 远程：海外通道 claude-opus-5 文档与图表理解最强；国内通道 qwen-vl-plus 中文 OCR 强且单图成本极低。独立测评显示不同视觉任务领先者不同，按任务路由比单一模型准确率高 5–15%。
- 多模态：这是唯一必须多模态的环节。
- 注意点：Ollama 对新视觉模型支持滞后，Qwen3.5 / 3.6 的视觉部分到 2026 年 7 月仍未接通，锁定 `qwen3-vl:8b` 或 `gemma4` 系列，不追最新。

### 1.4 排障引导

- 业内做法：显式状态机约束「当前阶段允许做什么」，LLM 只在阶段内做理解和生成。排障步骤来自知识库中预写好的排障树，LLM 把树节点改写成用户能执行的一句话，并根据用户反馈选择下一节点。这与 GaussMaster 的「诊断树驱动工具编排」和 metacto 的状态机设计建议一致：规则定路径，模型定表达。
- 可选模型：需要稳定的结构化输出。Claude、Qwen3-Max、GLM 均有原生 JSON Schema 输出；DeepSeek 只有 json_object 模式，需要 schema 提示加校验。
- 远程：中档模型（sonnet-5 / qwen3-max）。
- 多模态：不需要，除非用户中途再传图确认状态。
- 注意点：无论哪家，编排层都做 Pydantic 校验和一次重试，不信任裸输出。

### 1.5 升级与后续处理（质保、渠道判断）

- 业内做法：完全走规则引擎，LLM 只做两件事：从会话状态生成转人工摘要；把用户口述的购买信息抽成结构化字段交给规则。质保路径、经销商名录匹配不让模型判断。
- 可选模型：文本模型即可。
- 远程：轻量档即可。
- 多模态：可选。读购买凭证、发票照片需要视觉模型，若把「购买凭证」作为核心难点则必须。

## 2. 检索层模型（WeKnora 配置，全部远程）

按 D7 全远程决策修订：Embedding 与 Rerank 不在容器内运行，WeKnora 配置为远程 API。

| 组件 | 首选（domestic） | 备选 | 说明 |
| --- | --- | --- | --- |
| Embedding | 阿里百炼 text-embedding-v4（OpenAI 兼容接口） | 智谱 embedding-3；overseas：OpenAI text-embedding-3-large | 中英双语；维度与 WeKnora pgvector 配置一致（1024），切换模型需重建索引，因此 kb_ver 与 embedding 模型绑定 |
| Rerank | 阿里百炼 gte-rerank | 腾讯云 LKEAP Rerank（WeKnora 原生支持）；智谱 rerank | WeKnora 通过配置接远程 rerank；不可用时退化为不 rerank，检索状态仍为 ok 并记录 |
| 图谱抽取 | 关闭 | — | 小数据集收益有限 |

模型别名 `embed-primary`、`rerank-primary` 也纳入 models.yaml，具体 ID 联调前核对。

## 3. 远程多模型适配层设计

### 3.1 目标

- 每个环节（task）独立选模型，不同环节可以用不同厂商。
- 主模型失败或不支持某能力时，按链路自动降级到下一家。
- 换模型只改配置，不改业务代码；模型名、参数、能力声明全部集中在一个文件。
- 每次调用记录实际命中的模型，便于复盘和成本核算。

### 3.2 两条通道

Anker 团队与评委在国内，Anthropic / Google / OpenAI 直连有网络与合规不确定性。配置里分两条通道，用环境变量 `MODEL_LANE=overseas|domestic` 切换，也可以逐环节混用。

| 通道 | 厂商 | 接入方式 | 适用 |
| --- | --- | --- | --- |
| overseas | Anthropic Claude、Google Gemini、OpenAI | 官方 SDK 或 LangChain 官方集成 | 图片理解、复杂推理质量上限最高 |
| domestic | 阿里百炼 Qwen、DeepSeek、智谱 GLM、火山方舟豆包、Moonshot Kimi | 均提供 OpenAI 兼容接口，用 `openai` 协议 + `base_url` 接入 | 延迟低、价格低、中文口语与国内发票理解好 |

### 3.3 模型能力矩阵（配置文件维护，随版本更新）

| 模型 | 视觉 | 原生结构化输出 | 工具调用 | 单请求图片数 | 价格档 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| claude-opus-5 | 是 | 是 | 是 | 20 | 高 | 文档 / 图表理解最强，故障图首选 |
| claude-sonnet-5 | 是 | 是 | 是 | 20 | 中 | 综合首选 |
| claude-haiku-4-5 | 是 | 是 | 是 | 20 | 低 | 情绪 / 抽取 / 摘要 |
| gemini-3.x-flash | 是 | 是 | 是 | 多 | 低 | 多图与视频强，海外通道降级位 |
| qwen3-vl-plus / qwen3.x 多模态 | 是 | 是（json_object + schema 提示） | 是 | 10 | 极低 | 单图约 $0.0003，中文 OCR、发票强，国内通道读图首选 |
| qwen3-max / qwen3.x-plus | 否 | 是 | 是 | — | 中 | 国内通道文本主力 |
| deepseek-v3.x / v4 | 否 | json_object | 是 | — | 极低 | 缓存命中价极低，做抽取和摘要 |
| glm-5.x / glm-v | 是（V 系列） | 是 | 是 | — | 低 | 工具调用口碑好，备用 |
| doubao seed | 是 | 是 | 是 | — | 低 | 火山方舟延迟低，备用 |

表中「视觉」「结构化输出」两列决定路由时能否跳过该模型：任务要求 `needs_vision` 而模型不支持，直接跳到下一家，不发请求。

### 3.4 分环节路由表

路由表唯一来源是 3.7 的 models.yaml，展示表由 `make route-table` 生成于第 4 节。此处不再手工维护。

### 3.5 适配层接口

放在编排层，LangGraph 节点只认 task 名，不认模型名。

```
class ModelRouter:
    async def invoke(task, messages, schema: type[T], *, budget_ms: int) -> ModelResult[T]
        # 结构化调用；tag=internal；返回 {parsed, model_used, lane, latency_ms, usage, attempts[]}
    def stream(task, messages, *, budget_ms: int, message_id: str) -> AsyncIterator[StreamEvent]
        # 用户可见文本；tag=user_visible；产出 delta / aborted / switched(model_tier) / end
```
两个入口分开（评审建议）：结构化输出不流式；文本流有明确的中断与切换事件，API 层据此发 message_end(aborted) 与 message_start(replaces)。budget_ms 由节点按 08 §8 计算；ModelRouter 是唯一重试层，SDK max_retries=0。

实现要点：

- 底层用 LangChain `init_chat_model("provider:model")` 建模型实例，Claude / Gemini / OpenAI 用官方集成包，国内厂商用 `openai` provider 加 `base_url`。LangGraph 本身依赖 LangChain，不引新框架。
- 结构化输出按模型能力选方法：原生支持的用 `with_structured_output(schema, method="json_schema")`；只有 json_object 的用 json 模式加 schema 提示；都没有的用工具调用兜底。所有分支输出都再过一次 Pydantic 校验，失败带错误信息重试一次。
- 图片统一转成 base64 JPEG，长边 1600 px 以内，进入各家 SDK 前再按厂商格式封装；超过该模型单请求图片上限时只保留最新几张。
- Claude 系列传 `output_config.effort`，其他厂商传 temperature 0–0.3；参数映射写在 provider 适配里，路由表只写抽象的 low / medium / high。
- 每次调用带 `metadata={task, session_id, lane}` 写入 Langfuse，`model_used` 一并落到会话状态，摘要页可展示。
- 回放按 case_id + 版本清单命中录制包；非回放响应缓存键为 sha256(task, prompt_ver, schema_ver, model_id, input_text, image_sha256s, kb_ver)（09 §6）。

### 3.6 降级触发与顺序

| 触发 | 处理 |
| --- | --- |
| 超时（模型 timeout_s 与 task 剩余预算取小）、429、5xx | 同模型重试 1 次（退避 1 s + 抖动），再失败跳下一家；总耗时不超过 budget_ms |
| 内容拒答（Claude `stop_reason=refusal` 或厂商安全拦截） | 不重试，直接跳下一家 |
| Schema 校验失败 | 同模型带错误重试 1 次，再失败跳下一家 |
| 模型不支持任务所需能力（视觉、结构化） | 路由前跳过，不计入重试 |
| 整条链失败 | 发 error 事件，走该模块的业务降级（见 03_detailed-design.md 各模块「降级」） |

链上最多尝试 3 家；`attempts[]` 记录每次的模型、原因和耗时。预算耗尽时立即停止并返回最后错误，不再尝试剩余模型。

### 3.7 配置文件（config/models.yaml，唯一路由表来源）

models.yaml 是路由的唯一可执行来源；第 4 节的展示表由脚本 `make route-table` 从该文件生成，禁止手工维护两份。启动时校验：每个 task 在 default_lane 下有链；链上别名都存在；`needs_vision` 的 task 链上模型均 `vision: true`；embed / rerank 别名存在。

```yaml
version: 2026-09-12.1
default_lane: domestic

providers:
  anthropic: {sdk: anthropic, api_key_env: ANTHROPIC_API_KEY}
  google:    {sdk: google_genai, api_key_env: GOOGLE_API_KEY}
  dashscope: {sdk: openai, base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", api_key_env: DASHSCOPE_API_KEY}
  deepseek:  {sdk: openai, base_url: "https://api.deepseek.com/v1", api_key_env: DEEPSEEK_API_KEY}
  zhipu:     {sdk: openai, base_url: "https://open.bigmodel.cn/api/paas/v4", api_key_env: ZHIPU_API_KEY}

# 别名 → 真实模型 ID（联调前核对后填写，见 RELEASE.md）
models:
  sonnet:      {provider: anthropic, id: TBD, vision: true,  structured: native,      max_images: 20, timeout_s: 20}
  haiku:       {provider: anthropic, id: TBD, vision: true,  structured: native,      max_images: 20, timeout_s: 15}
  gemini-flash: {provider: google,    id: TBD, vision: true,  structured: native,      max_images: 16, timeout_s: 20}
  qwen-flash:  {provider: dashscope, id: TBD, vision: false, structured: json_object, timeout_s: 15}
  qwen-plus:   {provider: dashscope, id: TBD, vision: false, structured: native,      timeout_s: 20}
  qwen-max:    {provider: dashscope, id: TBD, vision: false, structured: native,      timeout_s: 20}
  qwen-vl:     {provider: dashscope, id: TBD, vision: true,  structured: json_object, max_images: 10, timeout_s: 30}
  deepseek:    {provider: deepseek,  id: TBD, vision: false, structured: json_object, timeout_s: 20}
  glm:         {provider: zhipu,     id: TBD, vision: false, structured: native,      timeout_s: 20}
  glm-flash:   {provider: zhipu,     id: TBD, vision: false, structured: native,      timeout_s: 15}
  glm-v:       {provider: zhipu,     id: TBD, vision: true,  structured: native,      max_images: 10, timeout_s: 30}
  embed-primary:  {provider: dashscope, id: TBD, kind: embedding, dim: 1024}
  rerank-primary: {provider: dashscope, id: TBD, kind: rerank}

lanes:
  domestic:
    intake:                {chain: [qwen-flash, deepseek, haiku],   effort: low,    max_tokens: 512}
    disambiguate.clarify:  {chain: [qwen-flash, glm-flash],         effort: low,    max_tokens: 256}
    diagnose.vision:       {chain: [qwen-vl, glm-v, sonnet],        effort: medium, needs_vision: true}
    diagnose.synthesize:   {chain: [qwen-max, deepseek, sonnet],    effort: high}
    guide.step:            {chain: [qwen-max, glm, sonnet],         effort: medium}
    reply.stream:          {chain: [qwen-plus, glm-flash],          effort: low,    stream: true}
    escalate.summary:      {chain: [deepseek, qwen-flash],          effort: low}
    warranty.receipt_ocr:  {chain: [qwen-vl, glm-v, sonnet],        effort: low,    needs_vision: true}
  overseas:
    intake:                {chain: [haiku, sonnet],                 effort: low,    max_tokens: 512}
    disambiguate.clarify:  {chain: [haiku, sonnet],                 effort: low}
    diagnose.vision:       {chain: [sonnet, gemini-flash],          effort: medium, needs_vision: true}
    diagnose.synthesize:   {chain: [sonnet, gemini-flash],          effort: high}
    guide.step:            {chain: [sonnet, haiku],                 effort: medium}
    reply.stream:          {chain: [sonnet, haiku],                 effort: low,    stream: true}
    escalate.summary:      {chain: [haiku, sonnet],                 effort: low}
    warranty.receipt_ocr:  {chain: [sonnet, gemini-flash],          effort: low,    needs_vision: true}

retry: {same_model_max: 1, chain_max: 3, sdk_max_retries: 0}
```

说明：
- 键值对冒号后必须有空格，URL 加引号（评审 R10 复核的解析问题已修正）。
- 每个 task 链在 domestic 与 overseas 两条通道各自完整；跨通道降级通过在 domestic 链尾放 overseas 别名实现（sonnet / haiku），不再另设「允许跨通道」开关。
- 3.4 的展示表已废弃，以第 4 节由本文件生成的表为准。

#### 3.7.1 可选 query.rewrite 路由（已实现）

无命中改写复用 ModelRouter 的结构化 invoke，新增的仅是任务名 `query.rewrite`，不是独立服务。实现时在实际 `config/models.yaml` 的 domestic / overseas 下注册该任务，初始复用各通道 intake 的已配置模型别名链，`effort: low`、`max_tokens: 128`、无需视觉；不在业务节点硬编码厂商。实际配置仍是唯一路由来源，更新后从它生成路由展示表。2026-09-13 已在两通道注册（domestic `[qwen-flash, deepseek, glm]`，`max_tokens` 由 128 提到 512 以容纳输出）。

启用开关放编排配置 `config/retrieval.yaml: query_rewrite.enabled=false`，不混入现有严格校验的 ModelsConfig。开启前校验两通道路由齐全、所选通道有可调用模型；缺配置则保持补救关闭并记录配置问题，不阻断基本排障。输入 / 输出和保守校验见 03 §1.4.2，触发规则见 09 §4.1，invoke 的 3 s 预算包含现有 Router 内重试与降级；不新增重试层。单次 invoke 不等于必然只有一次厂商请求，实际 attempts 仍须记录。

启用评测使用人工标注的口语 → 允许同义表达 → 应命中依据样例，加入否定、错误码、新增故障原因、错型号和原查询相同等反例。比较默认查询与一次改写后的适用证据命中、错误命中、语义漂移、额外成本及端到端延迟；未经验证保持默认关闭。

bake-off 实测（2026-09-13，8 样本 × 3 次）：qwen-flash 100% / 706 ms（主），deepseek 88% / 842 ms，glm 38%。早期 0% 是 `validate_rewrite` 超出 03 §1.4.2 文档意图所致，已修正（见该节实现口径）。开关仍默认关闭：当前语料下两库同时 no_match 的样例为 0，触发条件无法满足，启用门槛不成立。

#### 3.7.2 可选 retrieve.grade 路由（已实现）

命中相关性评分同样只是新增任务名 `retrieve.grade`（03 §1.4.3），不是独立服务。domestic `[qwen-flash, deepseek, glm-flash]`、overseas `[haiku, sonnet]`，`effort: low`、`max_tokens: 512`（256 装不下逐条判定 + coverage）、无需视觉。开关在 `config/retrieval.yaml: grade.enabled=false`，与 ModelsConfig 分离；两通道缺链时按功能不可用处理，不阻断排障（登记在 `OPTIONAL_TASKS`）。

bake-off 实测（2026-09-13，8 样本 × 2 次）：qwen-flash schema 100% / 准确率 98% / 1169 ms（主），deepseek 100% / 100% / 1038 ms（备），glm-flash 受账户限流未跑出有效数据。主备两家厂商满足 §3.8。开关默认关闭：模型侧对照显示当前语料上它反而让 plan 命中下降（见 docs/planning/2026-09-13_bounded-agentic-rag/findings.md）。

### 3.8 选型验证方式（bake-off）

样本：每个 task 20–30 条金标样本，由三个演示案例扩展并人工标注；diagnose.vision 与 warranty.receipt_ocr 各 15 张图（指示灯、屏幕报错、滤网状态；发票、订单截图、收据）。脚本对链上每个候选模型各跑 3 遍取中位数。

四项指标与门槛：

| 指标 | 定义 | 门槛（主模型） | 门槛（降级位） |
| --- | --- | --- | --- |
| Schema 通过率 | 首次输出即通过 Pydantic 校验的比例 | ≥ 95% | ≥ 90% |
| 字段准确率 | 关键字段与金标一致（情绪标签、产品线索、观察项召回、凭证字段） | 文本任务 ≥ 90%；视觉观察召回 ≥ 80%；凭证字段 ≥ 85% | 比主模型低不超过 10 个百分点 |
| 延迟 P50 | 从请求到完整响应 | intake / summary ≤ 3 s；guide ≤ 5 s；vision ≤ 8 s；synthesize ≤ 8 s | 不超过主模型 1.5 倍 |
| 成本 | 单次调用平均费用 | 一次完整对话（A1 案例）≤ ¥0.5 | 记录，不设硬门槛 |

裁决规则：先按通过率与准确率过滤，达标者中延迟与成本综合最低的做主模型；同一 task 的主备至少来自两家厂商。任一 task 无模型达标时降低门槛并在 findings.md 记录原因。

结果写入 findings.md 的「bake-off 结果」小节，作为最终路由表依据；预赛文档「预期效果」中引用该数据，并与「已验证结果」分开表述。

### 3.9 备选：网关方案

如果后期要给多个服务共用模型、做配额和成本看板，可把路由下沉到 LiteLLM Proxy：应用只对一个 OpenAI 兼容地址说话，fallback、重试、按 key 限额在网关配置。当前阶段不引入，理由是多一个组件且 alias 与 fallback 组合有已知边角问题；ModelRouter 的接口设计与之兼容，迁移时把 provider 换成网关地址即可。

## 4. 已确认（2026-09-12 用户答复）

| 事项 | 结论 | 落地 |
| --- | --- | --- |
| 默认通道 | domestic（国内），`MODEL_LANE=domestic` | diagnose.vision 保留可单独切 overseas 的开关 |
| 第一版接入厂商 | 阿里百炼 Qwen、DeepSeek、智谱 GLM、Claude / Gemini 四家全接 | 百炼先接，覆盖文本与视觉；DeepSeek 与 GLM 做降级位；Claude / Gemini 供 overseas 通道与质量对照 |
| 购买凭证识别 | 纳入演示 | warranty.receipt_ocr 转为正式 task，视觉 bake-off 加发票 / 订单截图样本，D2 决策同步修改 |
| 适配层实现 | 编排服务内置 ModelRouter，不引入 LiteLLM | 少一个组件；接口与网关兼容，后续可迁移 |
| 跨通道降级 | 允许：国内链失败后可自动切 Claude / Gemini | 优先保证演示成功率；attempts 记录跨通道次数，摘要页可见 |
| 凭证确认交互 | 先确认字段再查规则 | 识别结果以 receipt_card 展示，用户确认或修改后以 confirm_receipt_fields 提交，再查订单表与经销商名录 |
| 模型 ID 冻结方式 | 先用抽象别名（opus / sonnet / qwen-vl / qwen-max / deepseek / glm-v 等） | 业务代码与路由表只引用别名；具体模型 ID 在联调前从各厂商控制台核对后写入 models.yaml，并记入 RELEASE.md |
| 结构化输出策略 | 统一由 ModelRouter 适配 | 原生 JSON Schema 优先，json_object 加 schema 提示，都不支持时工具调用兜底；所有分支统一 Pydantic 校验与一次重试 |
| bake-off 门槛 | 四项综合评测 | 见 3.8，Schema 通过率、字段准确率、延迟、成本四项都设门槛 |
| 本轮交付 | 只完善设计文档，不写业务代码 | 实现阶段另开 planning 任务 |

第一版默认路由（由 `make route-table` 从 models.yaml 生成，别名见 3.7；2026-09-13 票 42 冻结后的生成结果，真实 ID 见 config/models.yaml）：

| task | 主 | 降级 1 | 降级 2 | 需视觉 |
| --- | --- | --- | --- | --- |
| intake | qwen-flash | deepseek | haiku（overseas） | 否 |
| disambiguate.clarify | qwen-flash | deepseek | glm-flash | 否 |
| diagnose.vision | qwen-vl | deepseek | sonnet（overseas） | 是 |
| diagnose.synthesize | qwen-max | deepseek | sonnet（overseas） | 否 |
| guide.step | qwen-max | deepseek | sonnet（overseas） | 否 |
| reply.stream | qwen-plus | deepseek | glm-flash | 否 |
| escalate.summary | deepseek | qwen-flash | — | 否 |
| warranty.receipt_ocr | qwen-vl | deepseek | sonnet（overseas） | 是 |
| query.rewrite | qwen-flash | deepseek | — | 否 |
| retrieve.grade | qwen-flash | deepseek | — | 否 |
| embedding | embed-primary（百炼） | — | — | — |
| rerank | rerank-primary（百炼） | LKEAP | 不 rerank | — |

冻结说明（票 42，2026-09-13）：每条链第二位固定为 `deepseek`（deepseek-flash，V4.1-Flash，实测可读图、json_object 可用、关思考后 ≈ 0.9 s），保证只有 DeepSeek key 的环境任何 task 都不会整链 skipped；qwen / glm / claude / gemini 的 ID 按厂商官方文档核对填入，其真实通过率与延迟待 key 到位后 `make bakeoff` 补跑并据结果调整主备顺序。评测结果与裁决见 ../2026-09-12_smart-service-bakeoff/findings.md。

## 附录：本机部署可行性（已搁置）

本机 M5 / 16 GB，未装 Ollama。D7 已决定全远程，本附录仅存档：若日后需要断网兜底，文本用 qwen3:8b，视觉用 qwen3-vl:4b，两者不同时驻留。Embedding / Rerank 亦已改为远程（第 2 节）。

## 来源
- https://huggingface.co/blog/daya-shankar/open-source-llm-models-to-run-locally
- https://localaimaster.com/blog/best-ollama-models-for-agents
- https://tinyweights.dev/posts/best-local-vision-language-models-2026/
- https://insiderllm.com/guides/vision-models-locally/
- https://codersera.com/blog/qwen3-vl-4b-vs-qwen3-vl-8b-benchmarks-vram-guide/
- https://www.promptquorum.com/local-llms/best-models-apple-silicon-2026
- https://docs.langchain.com/oss/python/concepts/providers-and-models
- https://reference.langchain.com/python/langchain/chat_models/base/init_chat_model
- https://reference.langchain.com/python/langchain-core/runnables/fallbacks/RunnableWithFallbacks
- https://docs.langchain.com/oss/python/langchain/structured-output
- https://tokenmix.ai/blog/vision-api-comparison
- https://www.getapipulse.com/best-ai-model-for-vision.html
- https://apirank.vip/zh/tutorials/ai-api-visual-understanding-2026/
- https://www.traktoken.com/blog/china-llm-comparison-2026
- https://news.qq.com/rain/a/20260420A04GUB00
- https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models
- https://futureagi.com/blog/best-rerankers-for-rag-2026/
- https://huggingface.co/Qwen/Qwen3-Reranker-0.6B
- https://arxiv.org/pdf/2404.14760 （Adobe 域内问答的产品消歧）
- https://arxiv.org/html/2507.05788v2 （Flippi 电商助手独立问句重写）
- https://www.elastic.co/search-labs/blog/entity-resolution-llm-elasticsearch
- https://arxiv.org/pdf/2506.23322 （GaussMaster 诊断树驱动工具编排）
- https://www.metacto.com/blogs/ai-agent-state-machine-design
- https://chatarmin.com/en/blog/ai-customer-service
- https://www.qiscus.com/en/blog/best-llm-for-customer-support/
