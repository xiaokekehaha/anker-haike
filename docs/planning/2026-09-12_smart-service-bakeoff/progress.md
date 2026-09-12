# 进度（票 42）

- 2026-09-12 23:45 认领。先做票 44 时发现 Codex 已在并行实现（`app/observability/`），让出并改认领 42。
- 23:50 DeepSeek 实测：模型清单、deepseek-chat 别名映射、思考模式默认开、flash 可读图、流式 include_usage 有 usage。价目与各厂商 ID 文档核对写入 findings。
- 2026-09-13 00:15 评测包 `app/bakeoff/`（config / samples / synth / recording / scoring / tasks / runner / cli）、`config/bakeoff.yaml`、9 个 task 的金标（文本 88 条、视觉 30 张合成图）、`haike-bakeoff` CLI 与 `make bakeoff`。13 项单测；全量 385 通过。
- 首次真实跑暴露两处：① langchain-openai 1.6 把连接失败包成 `OpenAIConnectionError`，router 只认 `APIConnectionError` → 归为 error 不重试，3/22 样本因瞬时断连直接失败；改为 `ConnectionError` 模糊匹配 + 回归测试。② `ModelSpec` 新增 `params`（openai 协议进 extra_body），DeepSeek 关思考。
- DeepSeek 单家实测（repeats=1）：intake 100/100/857ms、clarify 100/100/1120ms、synthesize 100/92/1046ms、guide 100/97/828ms、reply.stream 100/100/964ms（首字节）、summary 100/90/960ms、rewrite 100/12（候选被 validate_rewrite 全拒，属票 32 词表问题，非模型问题）。一次 A1 对话 ¥0.0098。
- models.yaml 冻结为 2026-09-13.1：TBD 0；deepseek → deepseek-flash（vision: true、关思考）、新增 deepseek-pro 对照位；qwen3.7-flash / qwen3.7-plus / qwen3.8-max / qwen3-vl-plus / glm-4.7 / glm-4.7-flash / glm-4.6v / gemini-2.5-flash 按官方文档填；每条链保证含 deepseek 可用位。`haike-model-probe intake` 927 ms OK。
- 2026-09-13 00:40 全量 3 遍实测（deepseek + deepseek-pro 对照）：文本 7 task 与 receipt_ocr 全达标，vision 87%（修正否定句误判后），rewrite 0%（票 32 词表过严，非模型问题）；结果与裁决写入 findings「bake-off 结果」。票 42 标 done-with-gap（缺其他厂商 key 的两家对比）。release.sh 增 bake-off 行；model-selection.md 路由表更新为冻结态；implementation task_plan Next Step 更新。
