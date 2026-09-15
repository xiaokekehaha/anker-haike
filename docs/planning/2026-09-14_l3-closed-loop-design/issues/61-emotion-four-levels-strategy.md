# 61: 情绪四级、轨迹与策略矩阵

**What to build:** interpret `emotion_level` 四级 + `emotion_cues[]`；`config/rules/complaint_terms.yaml` 规则命中优先给 complaint_risk；「投诉」从 R3 text_terms 移除；`issue.emotion_track`（最近 6 轮）与派生 trend / unresolved_turns；`config/emotion_policy.yaml` 策略矩阵 + `app/emotion/policy.py` 求解；`compose_system_prompt` 情绪层按 tone / pace 模板化；动作落点：`shorten_steps`（已有）、`skip_optional_clarify`（clarify 只问必要项）、`prefer_proposal_over_more_steps`（`route_after_guide`：executed ≥ 2 且 not_solved → R2 进 service_context）、`offer_human`（reply 末尾确定性人工选项）、`flag_complaint_risk`（case.complaint_risk / priority=high）、`suggest_compensation_review`（摘要 recommended_options 加需人工项）。

**Blocked by:** 51

**Status:** todo

**Owner:** —

- [ ] A8：三轮 dissatisfied → angry → complaint_risk；日志三元组 {level, trend, strategy}；第三轮不再出步骤卡而进方案 / 人工
- [ ] 「我要投诉」不再直接 R3 摘要，而是 de_escalate_and_offer_human 策略 + offer_human；「转人工」仍 R3
- [ ] `data/eval/emotion/cases.yaml` ≥ 40 条（含反讽 / emoji / 多轮），level 准确率报告；策略求解单测覆盖矩阵每行
- [ ] 旧 `anxious` 兼容映射测试

**设计依据：** 06 §4；00 D-L3-10
