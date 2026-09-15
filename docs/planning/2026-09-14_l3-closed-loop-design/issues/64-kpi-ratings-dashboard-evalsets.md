# 64: KPI：RatingCard、托管率 / 意图准确率 / NSS 采集与 Dashboard、五难点评测集骨架

**What to build:** `rating_card` 在 `close` 与首次 execute 后发出（可稍后），`rate_satisfaction` → `satisfaction_ratings`；analytics `classify()` 新终态 `executed_closed / awaiting_human / human_executed / consult_answered`，托管率 = 分子 {resolved, executed_closed, consult_answered} / 分母 终态 ∪ {escalated_human, abandoned}，剔除 replay / smoke（补 smoke 标签）；意图准确率：离线 `scripts/eval_conversation.py` 读扩展 gold 出报告，在线 LabelDialog 加「意图正确？」；NSS = %(4–5) − %(1–2) 与评分覆盖率；Dashboard 新卡四张（托管率 / 意图 / NSS / 越权次数）+ 分母悬浮说明；`haike-eval` CLI 统一跑 `vision|symptom|routing|emotion|policy|authorization|commitments` 评测集并落 `reports/eval/`；各评测集建骨架文件与 schema 校验（条数在各票填充）。

**Blocked by:** 57, 58, 59

**Status:** todo

**Owner:** —

- [ ] 内存 API 冒烟：resolved / executed_closed / escalated_human / consult_answered 四类会话 → Dashboard 托管率数值正确（手算对照）
- [ ] 同一 issue 重复评分幂等（unique）；评分不改变排障 / 案件状态
- [ ] `haike-eval authorization` 越权率 0 进 CI；其余评测集 schema 校验进 CI（条数门槛不阻塞）
- [ ] 前端 `RatingCard.tsx`；Dashboard 卡片测试

**设计依据：** 01 §5；05 §2；07 §3–§4；00 D-L3-14
