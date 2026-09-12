# 发现（票 42）

## 厂商现状（2026-09-12 23:50 实测 / 官方文档）
- DeepSeek：账号 `/v1/models` 只返回 `deepseek-flash`（V4.1-Flash）与 `deepseek-v4-pro`。旧名 `deepseek-chat` 仍被接受但服务端回 `model=deepseek-flash`，且**默认开思考模式**（reasoning_tokens 17–47，completion 从 5 涨到 23–53），需显式 `thinking: {type: disabled}`；`response_format=json_object` 与思考模式可共存。`deepseek-flash` 能读图（206 prompt tokens，描述正确）；`deepseek-v4-pro` 不读图（17 tokens，凭空描述）。价目（USD / 1M，峰时）：flash 0.30 / 1.20，pro 1.32 / 3.96；非峰时减半。
- 百炼：文档已把 `qwen-flash / qwen-plus / qwen-max / qwen-vl-*` 列为旧版；推荐 `qwen3.7-flash`（0.2 / 0.8 ¥，256 图）、`qwen3.7-plus`（2 / 8 ¥，2048 图）、`qwen3.8-max`（12 / 36 ¥）、`qwen3.8-flash`（0.8 / 2.7 ¥）；`qwen3-vl-plus / qwen3-vl-flash` 仍在。全部支持结构化输出。
- 智谱：`glm-4.7`（2 / 8 ¥ 起）、`glm-4.7-flashx`（0.5 / 3）、`glm-4.7-flash`（免费）、`glm-5.3`（8 / 28）、`glm-5.3-flash`（0.8 / 2.8，多模态）、`glm-4.6v`（1 / 3）、`glm-4.6v-flash`（免费）。
- Anthropic：Sonnet 5 $2 / $10（引入价转正式），Haiku 4.5 $1 / $5。Google：`gemini-2.5-flash` $0.30 / $2.50（图文同价），`gemini-3-flash-preview` $0.50 / $3.00。
- 本机只有 DEEPSEEK_API_KEY：qwen / glm / claude / gemini 只能填「文档核对过的 ID」，真实通过率待 key 到位后 `make bakeoff` 补跑。

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
