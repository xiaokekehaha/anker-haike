# 发现（票 42）

## 厂商现状（2026-09-12 23:50 实测 / 官方文档）
- DeepSeek：账号 `/v1/models` 只返回 `deepseek-flash`（V4.1-Flash）与 `deepseek-v4-pro`。旧名 `deepseek-chat` 仍被接受但服务端回 `model=deepseek-flash`，且**默认开思考模式**（reasoning_tokens 17–47，completion 从 5 涨到 23–53），需显式 `thinking: {type: disabled}`；`response_format=json_object` 与思考模式可共存。`deepseek-flash` 能读图（206 prompt tokens，描述正确）；`deepseek-v4-pro` 不读图（17 tokens，凭空描述）。价目（USD / 1M，峰时）：flash 0.30 / 1.20，pro 1.32 / 3.96；非峰时减半。
- 百炼：文档已把 `qwen-flash / qwen-plus / qwen-max / qwen-vl-*` 列为旧版；推荐 `qwen3.7-flash`（0.2 / 0.8 ¥，256 图）、`qwen3.7-plus`（2 / 8 ¥，2048 图）、`qwen3.8-max`（12 / 36 ¥）、`qwen3.8-flash`（0.8 / 2.7 ¥）；`qwen3-vl-plus / qwen3-vl-flash` 仍在。全部支持结构化输出。
- 智谱：`glm-4.7`（2 / 8 ¥ 起）、`glm-4.7-flashx`（0.5 / 3）、`glm-4.7-flash`（免费）、`glm-5.3`（8 / 28）、`glm-5.3-flash`（0.8 / 2.8，多模态）、`glm-4.6v`（1 / 3）、`glm-4.6v-flash`（免费）。
- Anthropic：Sonnet 5 $2 / $10（引入价转正式），Haiku 4.5 $1 / $5。Google：`gemini-2.5-flash` $0.30 / $2.50（图文同价），`gemini-3-flash-preview` $0.50 / $3.00。
- 本机只有 DEEPSEEK_API_KEY：qwen / glm / claude / gemini 只能填「文档核对过的 ID」，真实通过率待 key 到位后 `make bakeoff` 补跑。
- **2026-09-13 补：拿到 ZHIPU_API_KEY 后实测，上面「文档核对」的智谱 ID 有一个是错的**——`glm-4.7-flash` 调用返回 `500 操作失败`（模型不存在 / 该账号不可用），实测可用的轻量档是 `glm-4.5-flash`；`glm-4.7`、`glm-4.6v` 可用。另两点文档没写、只有实测才暴露：①智谱**默认开思考模式**，16 token 的 max_tokens 会被 reasoning 吃光返回空 content，必须 `thinking: {type: disabled}`（与 DeepSeek 同）；②智谱**不支持 `response_format: json_schema`**，会静默忽略并返回散文——用我们的 `structured: native` 策略时 Pydantic 校验 100% 失败（3/3），必须改 `json_object`（3/3 通过）。`bind_tools` + 字符串 tool_choice 经 LangChain 也拿不到 tool_call（「model returned no tool call」），只有直接传 `tool_choice: {type: function, ...}` 的原始请求可用，因此没选工具策略。

## bake-off 结果（2026-09-13，DeepSeek 单家；models.yaml 2026-09-13.1，bakeoff.yaml 2026-09-12.1，repeats=3）

完整表见 reports/bakeoff/bakeoff.md（`make bakeoff` 重生成）。候选只有 `deepseek`（deepseek-flash，关思考）；`deepseek-pro`（deepseek-v4-pro）作 `--extra` 对照位加入但其它厂商全部「未跑：missing api key」。

| task | Schema 通过率 | 字段准确率 | 延迟 P50 | ¥/次 | 门槛（主） | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| intake | 100% | 100% | ≈ 0.9 s | 0.0017 | 95 / 90 / 3 s | 达标 |
| disambiguate.clarify | 100% | 100% | ≈ 0.8 s | 0.0010 | 95 / 90 / 3 s | 达标 |
| diagnose.synthesize | 100% | 100% | ≈ 1.0 s | 0.0024 | 95 / 90 / 8 s | 达标 |
| guide.step | 100% | 97% | ≈ 0.85 s | 0.0011 | 95 / 90 / 5 s | 达标（唯一失分是 dustbin_s2：原文是描述句无动作词，`rewrite_is_faithful` 按设计回退原文） |
| reply.stream | 100% | 100% | ≈ 0.96 s（首字节） | 0.0005 | 95 / 90 / 3 s | 达标；注入样本 1/3 遍出现「先别拆机」—— 没照做，但复述了注入词，评分扣 0.2 |
| escalate.summary | 100% | 100% | ≈ 0.94 s | 0.0006 | 95 / 90 / 3 s | 达标（含注入样本：逐句保留用户原话、未新增资格结论） |
| warranty.receipt_ocr | 100% | 100% | ≈ 1.2 s | 0.0027 | 95 / 85 / 8 s | 达标（15 张合成订单图，含模糊 / 缺字段 / 英文 / 注入标题） |
| diagnose.vision | 100% | 87% | ≈ 1.1 s | 0.0017 | 95 / 80 / 8 s | 达标（见下） |
| query.rewrite | 100% | **0%** | ≈ 0.9 s | 0.0009 | 95 / 90 / 3 s | **未达标**，但不是模型问题（见下） |

一次 A1 对话（intake 1 + reply.stream 4 + synthesize 1 + guide 3 + summary 1）成本 **¥0.0099**，门槛 ¥0.5。

### 裁决
- 文本 7 个 task 与凭证 OCR：deepseek-flash 全部达主模型门槛，**在只有 DeepSeek key 的演示环境可作事实主模型**。models.yaml 里仍把 qwen 排在链首（设计 §4 确认的国内首选），deepseek 固定第二位；这样 DASHSCOPE_API_KEY 一到位就自动切主，不到位也不会整链 skipped。
- 「主备至少两家厂商」**未满足**：其它厂商只做了 ID 核对（见上文厂商现状），没有通过率数据。key 到位后 `make bakeoff` 一条命令补跑，报告 judge 会自动给出主备。
- deepseek-v4-pro 不读图（实测对图片凭空描述），只留作 synthesize / guide 的推理对照位，默认不在链上；本轮因 `--extra` 只对文本 task 生效且价格 4 倍、延迟无优势，未替换 flash。

### 未达标与失分原因
- **query.rewrite 0%**：模型输出全部是合理的说明书用语（「滚刷缠绕头发」「过滤网脏污」「垃圾盒无法安装到位」），但 `validate_rewrite` 的 `unsupported_term` 把它们全拒了——retrieval.yaml 的 synonyms 只登记了「碎屑 / 残留 / 吸力下降 / 滚刷…」十余组，「缠绕」「脏污」「无法安装到位」「清扫后」「不足」不在表内；`same_as_original`（侧刷不转 → 侧刷不转）一例。这是票 32 校验词表过严，符合其「不确定即弃用」的设计，改写开关本来就默认关闭。**不建议为通过评测放松校验**；应由票 32 / 37 的人工标注样例决定同义表扩充，再重跑本 task。
- **diagnose.vision 87%**：失分三处都来自合成图的局限——`filter_dust_2`（无标签、纯噪点）模型如实说「密集噪点、无设备部件」；`burn_filter` 的烧焦画成深色椭圆，模型说「深褐色污渍」未用 burnt/焦；`dustbin_full` 1/3 遍说「示意图非实拍」。第一版评分把「未见缠绕物」的否定句算成命中 absent 词，已修（去否定短句后再查）。**合成图能验链路、Schema 与安全词不被注入，不能替代真实照片评召回**；真实样本放 `data/bakeoff-images/`（gitignore）并把样本改为 `image: {file: ...}`。
- guide.step 97%：`dustbin_s2` 的 instruction_src 是「尘盒满或未装到位会触发提示，重新安装到听到咔哒声」——原文只有「装」一个动作词而模型改写用了「重新安装」（归一后同词），但 `rewrite_is_faithful` 要求改写动作集非空且 ⊆ 原文，此例模型输出被判不忠实回退原文；属票 34 词表边界，不是模型问题。

### 评测方法备注
- Schema 通过率口径 = 首次真实输出即通过 Pydantic（跳过项不算一次输出）；同一样本 3 遍取中位数再跨样本平均。
- 延迟 = Router attempts 的 latency 之和（含同模型重试）；reply.stream 用首个可见 delta（08 §8）。
- 成本 = usage 的 input/output token × bakeoff.yaml 价目；流式没有 usage 时按输出字数 / 1.5 估 token，input 记 0（偏低）。
- 第一次真实跑 3/22 intake 样本因 `OpenAIConnectionError` 直接失败：Router 只认 `APIConnectionError` 字面量，连接抖动被归为 error 不重试；已改模糊匹配并加回归测试（影响生产，不只评测）。


## bake-off 结果（2026-09-13，DeepSeek + 智谱两家；models.yaml 2026-09-13.2，repeats=3，并发 2）

完整表见 reports/bakeoff/bakeoff.md。dashscope / anthropic / google 仍无 key，表里是「未跑：missing api key」。

| task | deepseek-flash | 智谱候选 | 结论 |
| --- | --- | --- | --- |
| intake | 100% / 100% / 968 ms | glm-4.7 100% / 99% / 1951 ms | 两家均达标 |
| disambiguate.clarify | 100% / 100% / 892 ms | glm-4.5-flash 100% / 100%（repeats=5） | 两家均达标 |
| diagnose.synthesize | 100% / 100% / 1163 ms | glm-4.6v 100% / 92% / 2742 ms | 两家均达标 |
| guide.step | 100% / 97% / 957 ms | glm-4.5-flash 100% / 94%；glm-4.7 **89%** | 选 glm-4.5-flash |
| reply.stream | 100% / 100% / 1032 ms | glm-4.5-flash 100% / 98% / 724 ms | 两家均达标 |
| escalate.summary | 100% / 100% / 960 ms | glm-4.6v 100% / 100% / 939 ms | 两家均达标 |
| warranty.receipt_ocr | 100% / 100% / 1167 ms | glm-4.6v 100% / 100% / 2749 ms | 两家均达标 |
| diagnose.vision | 100% / 83–90% | glm-4.6v 100% / **77%** | 智谱只达备用位门槛 |
| query.rewrite | 100% / **0%** | glm-4.7 100% / **0%** | 两家都 0%，见下 |

一次 A1 对话成本 **¥0.0076**（门槛 ¥0.5）。

### 跑了三轮才敢下结论：门槛线附近的抖动
repeats=3 的两轮对同一模型给出了不同裁决，**挑任何一轮单独下结论都是错的**：

| task / 候选 | 第一轮 | 第二轮 | repeats=5 | 采信 |
| --- | --- | --- | --- | --- |
| disambiguate.clarify / glm-4.5-flash | schema 100% | schema **92%** | 100% | 达标（92% 是抖动） |
| guide.step / glm-4.7 | acc 92% | acc **89%** | acc **89%** | **未达标**（稳定低于 90%） |
| diagnose.vision / glm-4.6v | acc 80% | acc **77%** | acc **77%** | **未达主模型门槛**，但满足备用位（与主差 6 点 ≤ 10，延迟比 1.27 ≤ 1.5） |

结论：guide.step 原本选的 glm-4.7 是错的，已换成 glm-4.5-flash（94%）。**repeats=3 不足以判定门槛线附近的候选**，冻结前对边界候选应跑 repeats=5。

> **2026-09-13 补测推翻了上表 guide.step / glm-4.7 那一行的裁决**，见下一节：那个 89% 是并发限流污染，不是模型质量。

### 补测（2026-09-13）：限流吃掉的是 schema，89% 的准确率是真的抖动
起因：zhipu 通道把 glm-4.7 放到 `guide.step` 与 `retrieve.grade` 首位，而这两处只有并发跑出来的数据（retrieve.grade 更是只测过 glm-4.5-flash）。按 §3.8 补跑 repeats=5：

先用 bakeoff.yaml 默认的 `concurrency: 4`，结果很难看——`guide.step` schema 92% / acc 89%（有一次 20 s 超时），`retrieve.grade` schema 25% / acc 50%（40 次里 20 次 `ModelInvokeError`）。打开 INFO 日志才看到真因：

```
429 {'error': {'code': '1302', 'message': '您的账户已达到速率限制，请您控制请求频率'}}
retrieve.grade failed: task 'retrieve.grade' failed after 4 attempt(s): OpenAIRateLimitError
```

智谱账号在并发 4 下就被限流，`retry.rate_limit_max=3`（退避 1 / 2 / 4 s）也救不回来。把评测配置改成 `concurrency: 1` 重跑同样的 repeats=5：

| task | 候选 | 并发 4 | 串行 | 串行裁决 |
| --- | --- | --- | --- | --- |
| guide.step | glm-4.7 | schema 92% / acc 89% / p50 1067 ms / max 20 000 ms | schema **100%** / acc **92%** / p50 1195 ms / max 1647 ms | **主**（两项过线） |
| retrieve.grade | glm-4.7 | schema 25% / acc 50% | schema **100%** / acc **91%** / p50 2054 ms / p95 2337 ms | **主**（4 s 预算内 0 次超时） |

逐样本对比也能看出污染的形状：串行只有 `dustbin_s2` 0.67、`side_s1` 0.67、`side_s2` 0.80、`filter_s2` 0.87 四条真实扣分，其余满分；并发那轮是十一条样本齐刷刷 0.93，典型的「每条样本挂掉一次重复」。`retrieve.grade` 串行只剩 `side_brush` 0.55 一条真实扣分。

报告：`reports/bakeoff/guide_step_glm47/`、`reports/bakeoff/retrieve_grade_glm47/`（bakeoff.md 是串行结果，两份 JSON 明细保留了并发 / 串行两轮可对比）。

**但限流本身是线上的真问题**，不是评测工具的毛病：它是账号级速率限制，并发 4 就打满。zhipu 通道在多会话并发下会真触发 429，退避三次后降级到 deepseek。切 `MODEL_LANE=zhipu` 前要么确认账号配额，要么只把它当单人演示 / 备用通道用。

**评测方法补充**：跑智谱候选时必须串行（`--bakeoff-config` 指一份 `concurrency: 1` 的配置），否则测的是账号配额不是模型能力。

**这一节的结论后来被自己的下一轮修正了**：同日串行跑全量（repeats=3）时，`guide.step` / glm-4.7 又回到 **schema 100% / acc 89%**。把两件事分开才对——
- **schema 通过率**确实是限流污染：并发 4 的 92% / 25%，串行后一律 100%；
- **准确率**不是：89%（repeats=3 并发）、89%（repeats=5 并发）、92%（repeats=5 串行）、89%（repeats=3 串行），**glm-4.7 在 guide.step 上就是 89–92% 之间抖，横跨 90% 门槛线**。

所以它只配当兜底位（现在是 `guide.step` 链的第三位），不该进主备。`retrieve.grade` 的 91% 则在多轮里稳定，可以上链。

### 裁决与链的冻结（models.yaml 2026-09-13.2）
`chain_max=3`，所以每个 task 第三位只能二选一：一个没有 key 的 overseas 兜底，或一个实测达标的智谱位。改成后者：

| task | 链（domestic） | 第三位依据 |
| --- | --- | --- |
| intake | qwen-flash → deepseek → **glm** | 100% / 99% |
| disambiguate.clarify | qwen-flash → deepseek → **glm-flash** | 100% / 100%（repeats=5） |
| diagnose.vision | qwen-vl → deepseek → **glm-v** | 唯一有视觉的智谱模型；77% 只达备用位门槛 |
| diagnose.synthesize | qwen-max → deepseek → **glm-v** | 100% / 92%（glm 92%、glm-flash 67% 未达标） |
| guide.step | qwen-max → deepseek → **glm-flash** | 100% / 94%（glm 89% 未达标） |
| reply.stream | qwen-plus → deepseek → **glm-flash** | 100% / 98%，首字节 724 ms |
| escalate.summary | deepseek → **glm-v** → qwen-flash | 100% / 100%（glm 10%、glm-flash 0% 未达标） |
| warranty.receipt_ocr | qwen-vl → deepseek → **glm-v** | 100% / 100% |
| query.rewrite | qwen-flash → deepseek → **glm** | 两家都 0%，开关默认关闭，不作为启用依据 |

**代价（需要决策者知道）**：domestic 链尾原本接 overseas 别名（haiku / sonnet）作跨通道兜底，现在被智谱位挤掉了——`chain_max` 是 3，不能既留 overseas 又加智谱。取舍理由：当前环境 dashscope 与 anthropic 都没有 key，那个兜底位是**不可达的**，等于每个 task 只有 deepseek 一个能跑的模型；换成智谱后每个 task 有两个真能跑的模型。若后续补齐 overseas key 且要恢复跨通道兜底，需要把 `retry.chain_max` 提到 4 或重排链序。

### 失效切换实测（这才是「主备两家」的证据）
把 `DEEPSEEK_API_KEY` 换成无效值起服务，跑完整 A3（排障 → 凭证 → 核对）：整条产品链切到智谱并正常完成。

| task | 降级后命中 | 结果 |
| --- | --- | --- |
| warranty.receipt_ocr | zhipu/glm-4.6v | 订单号 / 渠道 / 日期 / 金额四个字段全对，逐字段置信度 1.0 |
| diagnose.synthesize | zhipu/glm-4.6v | ok 2389 ms |
| guide.step | zhipu/glm-4.7 | ok（×2） |
| escalate.summary | zhipu/glm-4.6v | ok 1084 ms |
| reply.stream | zhipu/glm-4.5-flash | ok |
| intake | zhipu/glm-4.7 | **error**：intake 预算 6 s 被 deepseek 的重试耗尽，轮到智谱时已无预算 → 按设计降级为 calm / 空，不阻断流程 |

首卡从 6.7 s 涨到 21 s（每个 task 都要先走完 qwen 跳过 + deepseek 失败重试），属主模型全挂时的预期表现。`/health` 的 `models.domestic.providers_ready` 现在是 `[deepseek, zhipu]`。

### query.rewrite 两家都 0%：仍是票 32 的词表问题，不是模型问题
DeepSeek 与智谱四个候选全部 0%，与上一轮 DeepSeek 单家结论一致：`validate_rewrite` 的 `unsupported_term` 把模型给出的合理说明书用语全拒了。两家同时 0% 反而是证据——问题在校验词表，不在某家模型。处置不变：不为通过评测放松校验，留待票 32 / 37 的人工标注样例决定同义表扩充。


## bake-off 结果（2026-09-13，三家同时有 key；models.yaml 2026-09-13.5，repeats=3，串行）

**这是当前采信、也是 RELEASE 冻结所指的一版**（`reports/bakeoff/bakeoff.md`）。前两节的裁决都是在 `DASHSCOPE_API_KEY` 缺席下做的——
报告里 qwen 整列写着「未跑：missing env」，可 domestic 链却把 qwen 放在 8 个 task 的**主位**，等于主位从来没有被实测支撑过。
本轮三家 key 齐了，补齐 qwen 全量、重排链，再按新链复跑一遍。

| task | dashscope | deepseek | zhipu | 冻结的链 |
| --- | --- | --- | --- | --- |
| intake | qwen-flash 100 / 98 1051 ms **¥0.0002** | 100 / 100 953 ms ¥0.0016 | glm 100 / 97 1364 ms | qwen-flash → deepseek → glm |
| disambiguate.clarify | qwen-flash **100 / 100 752 ms ¥0.0001** | 100 / 100 990 ms ¥0.0010 | glm 100 / 100 965 ms | qwen-flash → deepseek → **glm** |
| diagnose.vision | qwen-vl 100 / 83 1554 ms | **100 / 83 1188 ms** | glm-v 93 / 77（未达标） | **deepseek** → qwen-vl → glm-v |
| diagnose.synthesize | qwen-max 100 / 100 2179 ms ¥0.0094 | **100 / 100 1162 ms ¥0.0023** | glm-v 100 / 88（未达标） | **deepseek** → qwen-max → glm-v |
| guide.step | qwen-max 100 / 94 998 ms ¥0.0047 | **100 / 97 929 ms ¥0.0011** | glm 100 / 89（未达标） | **deepseek** → qwen-max → glm |
| reply.stream | qwen-plus 100 / 98 900 ms ¥0.0003 | 100 / 98 1084 ms ¥0.0005 | glm 100 / 98 **582 ms ¥0.0002** | qwen-plus → deepseek → **glm** |
| escalate.summary | qwen-flash **100 / 100 648 ms ¥0.0001** | 100 / 100 899 ms ¥0.0006 | glm-v 100 / 100 723 ms | **qwen-flash** → deepseek → glm-v |
| warranty.receipt_ocr | qwen-vl 100 / 100 3355 ms | **100 / 100 1218 ms** | glm-v 100 / 100 2958 ms | **deepseek** → qwen-vl → glm-v |
| query.rewrite | qwen-flash 100 / **75** 535 ms | 100 / **75** 915 ms | glm 100 / **62** | 链不变，默认关闭（三家全未达标） |
| retrieve.grade | qwen-flash 100 / 92 1193 ms **¥0.0002** | 100 / 100 1105 ms ¥0.0018 | glm 100 / 100 2135 ms | qwen-flash → deepseek → glm（默认关闭） |

一次 A1 对话成本 **¥0.0068**（门槛 ¥0.5）。口径同 `runner.judge`：准确率只作门槛，达标后按 `延迟 / 上限 + 成本 × 100` 排序。

### 这一轮改了什么、为什么
- **4 个主位换成 deepseek**（`diagnose.vision` / `diagnose.synthesize` / `guide.step` / `warranty.receipt_ocr`）：准确率不低于 qwen，且更快更省。`warranty.receipt_ocr` 从 qwen-vl 3355 ms 降到 1218 ms（快 2.8×）；`diagnose.synthesize` 省 4 倍成本。
- **`escalate.summary` 主位换 qwen-flash**：648 ms / ¥0.0001，三家里最快最省且 100%。
- **`reply.stream` 主位保持 qwen-plus**：三家都是 98%，qwen-plus 首字 900 ms / ¥0.0003（此前一轮它测出 1188 ms，串行复测翻转过一次结论）。
- **glm-4.5-flash 全面下链**，曾用它的位置改用 glm-4.7：免费档排队是致命的——`reply.stream` 串行实测 **P50 12.1 s、schema 67% / acc 65%**，`disambiguate.clarify` schema 92%；换成 glm-4.7 后同样两处是 100/98 582 ms 与 100/100 965 ms。
- **一次 A1 对话成本 ¥0.0252（全 qwen 主位）→ ¥0.0068**。

### 两处故意不采信工具裁决：不让智谱进主位
工具的排序只把准确率当门槛，过线后按「延迟 + 成本」挑最便宜的，于是两次把智谱推上主位：

| 轮次 | 工具裁决 | 冻结的选择 | 理由 |
| --- | --- | --- | --- |
| 重排前 | `diagnose.vision` 主 = glm-v（恰好 80% 卡线，成本最低） | deepseek | 视觉是 A2 / A3 的判断入口，卡线候选不做主位；本轮 glm-v 掉到 77% / schema 93%，工具自己也把它判成未达标了 |
| 本轮 | `reply.stream` 主 = glm（582 ms / ¥0.0002，98%） | qwen-plus | 智谱账号并发 4 即 429（见上一节），首句安抚是每轮都走的路径，主位吃不起限流 |

智谱位一律排第三，作「DeepSeek + 百炼同时不可用」时的兜底——这也是失效切换实测里被验证过的那条路径。

### repeats=3 的抖动有多大（冻结时必须知道）
同样串行、同样 repeats=3，两轮之间：`intake` qwen-flash 100% → 98%，`guide.step` qwen-max 97% → 94%，`diagnose.vision` deepseek 87% → 83%，`diagnose.synthesize` glm-v 92% → 88%，`retrieve.grade` qwen-flash 96% → 92%。
**门槛线附近 ±5 点是常态**，所以：
- 链上**主位**的选择对这个量级的抖动是稳的（主位候选都在 97–100%，离门槛远）；
- **兜底位**的「达标 / 未达标」标签会来回翻（glm-v 在 synthesize 上 88↔92、glm 在 guide.step 上 89↔92），不必每轮改链；
- 真要给某个边界候选下结论，按本文件前面的教训跑 **repeats=5**。

### 仍然没解决的
- **`query.rewrite` 三家全未达标，且轮间摆动极大**（qwen-flash 上一轮 100%、本轮 75%）。这与票 32 记的词表问题一致，不是选型问题；该开关默认关闭，不作为启用依据，但它的金标样本或评分口径需要单独修。
- **形式化的「主备两家」**：`diagnose.synthesize` / `warranty.receipt_ocr` 的第二位延迟比超过 `latency_ratio_max = 1.5`，按 §3.8 严格判定算不上达标备用位——仍在链上作降级，只是不写进裁决。
- **视觉是整条链最薄的一环**：三家 77–83%，其余 task 普遍 94–100%。后续要么补样本要么换更强的视觉模型。
- **智谱账号限流**：并发 4 即 429（code 1302）；`MODEL_LANE=zhipu` 通道在多会话并发下会真触发。
