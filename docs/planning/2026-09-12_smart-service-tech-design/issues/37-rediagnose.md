# 37: rediagnose 中途补充与纠正

**What to build:** guide / verify 阶段用户在 Composer 发送自由文本或图片，前端提示「补充信息将重新判断故障」，提交为 rediagnose 动作；后端新输入过 CP-in，复用 intake 一次调用更新情绪与有效症状，使用票 32 的查询函数回到 diagnose 重新汇总，保留 steps_executed 与 counters。明确纠正型号时先回现有 disambiguate，重新确认适用范围。

**上下文补充（2026-09-12，待实现）：** 把已确认产品、有效症状、最近步骤与反馈传入已有抽取入口；增量 fact_patch / needs_clarification 与[连续追问设计 §3](../../2026-09-12_conversation-memory-design/architecture-requirements.md#3-每条追问的处理链路)对齐，复用同一次 intake 调用。否定纠正更新有效症状，未提及 / 空抽取不删除旧事实，用户原话留在已有消息记录。澄清行为复用票 24，实际检索与可选改写仍归票 32。

**Blocked by:** 36（出口规则 R1 / R1b / R1c / R2 与 A1 完成）、23（纠正后旧卡片冲突与前端快照重建）

**Status:** ready-for-agent

- [ ] 排障中补充「其实还有异响」→ plans_ranked 变化 → 新步骤卡
- [ ] 补充文本含安全词 → R4 升级
- [ ] steps_executed 在 rediagnose 后保留并出现在最终摘要
- [ ] 有 active run 时 rediagnose 被 409 not_allowed_now
- [ ] 「还是不吸」承接已确认产品与未解决症状，发给 adapter 的 query 不是孤立的「还是」或「这个」
- [ ] 「不是吸力小，是有异响」使 symptoms / query / synthesize 输入不再把吸力不足当有效事实；补充「还有异响」则保留原故障
- [ ] 用户纠正型号时先完成消歧，新确认前不下发旧 SKU 步骤；新步骤 evidence_ids 均符合新 scope
- [ ] 上下文抽取失败不清空已确认产品；按 03 §1.4.1 用原文回退，纠正有歧义则澄清，不凭空补事实
- [ ] counters 与 steps_executed 都保留；结构化 step_feedback 直接走 verify，R3/R4 升级不先跑知识召回
- [ ] 指代无唯一对象时先澄清，不以模型高置信度推进；连续两次澄清答复仍冲突时 R7 升级，并在摘要说明未知项
- [ ] 型号纠正后旧 pending_card 失效，前端据快照禁用旧按钮；再次点旧卡按校验顺序返回对应 409 与快照，业务计数不变
- [ ] 路由分流样例至少含模糊输入、S1 Pro 产品歧义、明确纠正、过期按钮、人工请求；未触发检索的分支不调用 query.rewrite

**设计依据：** 01 F5b/F5c；03 §1.2、§1.4.1；09 §1.1；08 §4；05 §2；连续追问设计 §3
