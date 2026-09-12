# 37: rediagnose 中途补充与纠正

**What to build:** guide / verify 阶段用户在 Composer 发送自由文本或图片，前端提示「补充信息将重新判断故障」，提交为 rediagnose 动作；后端新输入过 CP-in，复用 intake 一次调用更新情绪与有效症状，使用票 32 的查询函数回到 diagnose 重新汇总，保留 steps_executed 与 counters。明确纠正型号时先回现有 disambiguate，重新确认适用范围。

**上下文补充（2026-09-12，待实现）：** 把已确认产品、有效症状、最近步骤与反馈传入已有抽取入口；增量 fact_patch / needs_clarification 与[连续追问设计 §3](../../2026-09-12_conversation-memory-design/architecture-requirements.md#3-每条追问的处理链路)对齐，复用同一次 intake 调用。否定纠正更新有效症状，未提及 / 空抽取不删除旧事实，用户原话留在已有消息记录。澄清行为复用票 24，实际检索与可选改写仍归票 32。

**Blocked by:** 36（出口规则 R1 / R1b / R1c / R2 与 A1 完成）、23（纠正后旧卡片冲突与前端快照重建）

**Status:** done（2026-09-13，接手会话；后端 + 前端 + 真实 DeepSeek / WeKnora 实测）

**Owner:** Claude Code（接手会话，2026-09-13）

- [x] 排障中补充「其实还有异响」→ plans_ranked 变化 → 新步骤卡（graph.py `rediagnose` 节点：/messages 在 guide / verify 阶段经 route_entry 直达，/actions kind=rediagnose 经 apply_action 作废旧卡后同路；增量抽取 `app/intake/rediagnose.py` → disambiguate → retrieve → synthesize → reply → guide；test_supplement_symptom_…）
- [x] 补充文本含安全词 → R4 升级（CP-in 先于任何模型调用与检索；安全升级直接摘要，摘要 steps 含已执行步骤；test_safety_term_…，真实链路「闻到烧焦味」0.0 s 出 R4 摘要）
- [x] steps_executed 在 rediagnose 后保留并出现在最终摘要（节点只清 plan_cursor / diagnose_outcome / pending_card；counters、exhausted_plans 原样；guide 按 instruction_src 去重不再下发已执行步骤）
- [x] 有 active run 时 rediagnose 被 409（**差异**：按 08 §4 / 票 23 的校验顺序返回 `run_active` 附快照，而非 not_allowed_now；stage ∉ {guide, verify}、等待的是产品 / 凭证卡才返回 not_allowed_now；test_rediagnose_rejected_while_run_active）
- [x] 「还是不吸」承接已确认产品与未解决症状，发给 adapter 的 query 不是孤立的「还是」或「这个」（空增量 = 保持；query 仍为 `eufy X9 Pro 不吸了 滚刷缠头发`；有效症状为空时回退到更早轮次含故障描述的原文；test_deictic_followup_…）
- [x] 「不是吸力小，是有异响」使 symptoms / query / synthesize 输入不再把吸力不足当有效事实；补充「还有异响」则保留原故障（negated_symptoms 只删能对上已知症状的项；原话留在 messages；真实 DeepSeek：removed=['不吸了']；test_negation_replaces_…）
- [x] 用户纠正型号时先完成消歧，新确认前不下发旧 SKU 步骤；新步骤 evidence_ids 均符合新 scope（product_hints 交 disambiguate：单命中重新确认并清空 evidence / knowledge_status，多命中先出产品卡；检索 allow.sku 为新型号，新卡 evidence ⊆ 本轮 evidence；test_product_correction_…）
- [x] 上下文抽取失败不清空已确认产品；按 03 §1.4.1 用原文回退，纠正有歧义则澄清，不凭空补事实（degraded → 产品 / 症状保持，原文含具体故障描述时补为一条症状；test_extraction_failure_…）
- [x] counters 与 steps_executed 都保留；结构化 step_feedback 直接走 verify，R3/R4 升级不先跑知识召回（R4 路径模型 / adapter 调用次数为 0）
- [x] 指代无唯一对象时先澄清，不以模型高置信度推进；连续两次澄清答复仍冲突时 R7 升级，并在摘要说明未知项（后端规则：needs_clarification 且无产品线索 / 新现象，或无任何增量且此前无有效症状 → symptom 澄清，复用票 24 计数；第三次 → R7，observations 记「R7：连续 2 次澄清…」；test_ambiguous_reference_…）
- [x] 型号纠正后旧 pending_card 失效，前端据快照禁用旧按钮；再次点旧卡按校验顺序返回对应 409 与快照，业务计数不变（旧版本 → stale_version，版本对但卡旧 → stale_card，快照 pending 为新卡；counters 不变。注意 step card_id = uuid5(session, plan, step)，若重诊后仍落在同一计划步骤则新卡与旧卡同 id、只是版本更新）
- [x] 路由分流样例至少含模糊输入、S1 Pro 产品歧义、明确纠正、过期按钮、人工请求；未触发检索的分支不调用 query.rewrite（tests/test_sessions_rediagnose.py 14 项覆盖模糊「还是不吸」/「不是那个」、S1 Pro 多命中出卡、X10 单命中纠正、过期按钮 409、R4；request_human 见票 25；R4 / 澄清分支不检索）

**设计依据：** 01 F5b/F5c；03 §1.2、§1.4.1；09 §1.1；08 §4；05 §2；连续追问设计 §3

**实现说明（2026-09-13）：**
- 后端：`app/intake/rediagnose.py`（RediagnoseExtraction 增量 schema + merge_symptoms，复用 intake 任务链，独立 prompt 版本 `2026-09-13.1`，不改动 intake 提示，A1–A3 回放包无需重录）；`graph.py` 新增 `rediagnose` 节点、`in_guide`、`route_entry` / `route_after_apply` / `route_after_rediagnose`；`router.py` 放开 kind=rediagnose（version → 时机 → pending kind → 载荷 / image_ids 归属校验；有 interrupt 用 Command(resume)，否则 entry_action）。动作 run 里补充的消息以运行器上下文的当前 run_id 归入 timeline（修了一次实测发现的错位）。
- 前端：Composer 在 step_feedback 等待期开放文字 / 照片输入，提示「补充信息将重新判断故障…」，useSession.send 放行并走 /messages；App 状态文案同步。
- 验收：后端 406 项（新增 14）、前端 123 项、tsc / vite build、ruff 通过。真实 DeepSeek + WeKnora（uvicorn :8010）：A1 首卡 5.7 s；「其实还有异响」5.4 s（added=['异响']）；「不是吸力小，是有异响」5.8 s（removed=['不吸了']）；/actions rediagnose 5.3 s、同 action_id 重放 replayed=true、旧卡 409 stale_version 附快照；「说错了，我的是 X10」→ disambiguate 重新确认 X10；「闻到烧焦味」0.0 s → R4 摘要含已执行步骤。
- 已知差异：active run 时返回 run_active（契约顺序）；票面原写 not_allowed_now。
