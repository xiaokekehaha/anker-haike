# 输入与锚点

## 需求输入
- 赛题解析文档要点：[hackathon-brief-gap-analysis/findings.md](../2026-09-14_hackathon-brief-gap-analysis/findings.md)——L1/L2/L3 框架、五难点、三项基线（托管率 70–80%、意图 ≥90%、NSS ≥60%）、技术边界（脱敏工单 / 知识库 / 经销商名录 / SOP；AWS 能力；不套 Bedrock KB）。
- 差距结论：[gap-analysis.md](../2026-09-14_hackathon-brief-gap-analysis/gap-analysis.md)——L3 零覆盖；分流与接稳最薄；看图停在观察层；幻觉约束只覆盖排障域。
- 既有分析：[service-flow-gap-analysis](../2026-09-12_service-flow-gap-analysis/comparison.md)（自主办理 / 人工审批 / 结案三段属新增）、[meeting-painpoint-coverage](../2026-09-12_meeting-painpoint-coverage/coverage-analysis.md)（跨地区政策、补偿一致性、真实业务动作未覆盖）、[service-quality-loop/design.md](../2026-09-13_service-quality-loop/design.md)（反馈 / 案例 / 资产的质量闭环对象模型，本设计的 KPI 采集与其对齐）。
- 预赛材料 9/27 截止（[budget-materials](../2026-09-12_budget-materials/findings.md)）；决赛现场演示日期未知。

## 代码锚点（2026-09-14 工作树）
| 锚点 | 现状 | 对设计的约束 |
| --- | --- | --- |
| [common.py](../../../contracts/haike_contracts/common.py) | `Stage` 8 值；`PendingKind` 4 值；`EmotionLevel` 3 值；`EscalationSummary` 含 product / problem / observations / hypotheses / steps / reason / emotion / receipt / model_trace | 新阶段、卡片、情绪级别都要改 Literal 并重新生成 TS（`make contracts`） |
| [actions.py](../../../contracts/haike_contracts/actions.py) | `ActionKind` 7 值；卡片动作必须带 input_token + card_id | 新动作沿用 `_CardAction` 校验 |
| [events.py](../../../contracts/haike_contracts/events.py) | 卡片事件 product_card / step_card / receipt_card / escalation_summary；`handoff_status` 已有 prepared / requested / accepted / failed / cancelled | 新卡片事件继承 `_Card`；人工接手状态可复用 handoff_status |
| [graph.py](../../../orchestrator/app/sessions/graph.py) | `route_entry` 按 turn_decision 分流；`escalate → route_escalate → prepare_receipt / receipt_extract / summarize → commit_issue → END`；`apply_action` 按 kind 分支；`await_input` 按 pending kind 发卡 | 新节点接在 `route_after_apply` / `route_escalate` / `route_after_guide`；卡片走 `prepare_* → await_input` 三段式 |
| [reduce.py](../../../orchestrator/app/conversation/reduce.py) | `turn_decision` 含 primary_intent / secondary_intents / reply_mode / escalation_trigger / allowed_operations；`issues[issue_id]` 持久化 | 任务队列与情绪轨迹挂在 issue 上；secondary_intents 目前无消费者 |
| [interpret.py](../../../orchestrator/app/conversation/interpret.py) | 14 类 Intent；emotion_level 3 级；facts / corrections / pending_answer / history_request | 新增业务意图与 4 级情绪在此扩展，一次语义调用不加次数 |
| [rules/service.py](../../../orchestrator/app/rules/service.py) | `check_in(text, observations, action_kind, action_note)` → CheckpointResult；R6 为 flag | R6 从「进凭证子流程」改为「进方案决策」，安全规则不动 |
| [warranty/service.py](../../../orchestrator/app/warranty/service.py) | L1–L6 只核事实；`Dealer.region` 未用；`orders_mock` / dealers 表（迁移 0003） | 政策引擎消费 ReceiptOutcome + Dealer.authorized/region；订单表补 region_purchase / platform |
| [admin/router.py](../../../orchestrator/app/admin/router.py) | graph / sessions / journey / metrics / cases（标注） | 审批 API 与案件队列加在同一 router；页面加在 `frontend/src/admin/pages` |
| [migrations](../../../orchestrator/migrations/versions) | 0001–0005 | 新迁移 0006 |
| [models.yaml](../../../config/models.yaml) | providers 5 家，lanes domestic / overseas / zhipu，10 个 task | 新 provider bedrock + lane aws；新 task 只加轻量档 |
| [ingest.py](../../../orchestrator/app/knowledge/ingest.py) | front-matter 必填 doc_id / title / scope / category / doc_version；custom_metadata 只收标量 | 政策条款、区域元数据以标量串存 |
| [Timeline.tsx](../../../frontend/src/components/Timeline.tsx) / [reducer.ts](../../../frontend/src/state/reducer.ts) | 按 kind 分发卡片；upsert 保留用户结果字段 | 新卡片各加一个 case 分支 + 结果字段 |

## 开发核查
- 当前尚无 L3 代码；现有契约采用 Strict + discriminated union，新增卡片必须同时接入 Python、生成 TS、实时 reducer 与快照折叠。
- 输入接收使用 session_inputs 幂等与发布 checkpoint，人工审批须复用该路径。
- 文档内 57/59 的依赖环按先案件服务、后执行图处理。

- 实际 graph 的 diagnose_outcome 是 {mode,plan_id} 对象，并非设计文档简写字符串；fault_class 使用实际结构。
- orders_mock 原 ReferenceData 为 extra=forbid；迁移新增列后旧加载改为显式投影四列，保留 A3 原订单。
- 全量回归已有 20 个基线失败，使用 HEAD 导出代码确认。
- 设计票 57 的 executing_failed 与票 51 CaseStatus 枚举不一致；暂用 awaiting_approval 承接可恢复执行失败，后续收口明确状态。
