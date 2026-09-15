# 76: refund.create 动作与补偿一致性账本生效

**What to build:** `actions.yaml` 增 `refund.create`（write，`auto_allowed` 永为 false → 必经 HITL；参数 amount / currency 来自订单表，不可由用户或模型改写；幂等键 `{case_id}:refund.create:{option_id}`）；模拟后端 `create_refund / get_refund`；`case.commitments[]` 账本正式落表 `case_commitments(case_id, kind: remedy|amount|eta|fee, value, unit, source: clause|receipt|human, at)`；reply / propose 措辞生成前注入 `<data kind=commitments>`，生成后确定性检查：出现的金额 / 天数 / 币种必须 ∈ 账本值，否则整句替换为模板；HITL 修改金额必须填 override_reason 并写入账本（source=human）。

**Blocked by:** P0 57, 60；P1 74

**Status:** todo

**Owner:** —

- [ ] 退款方案 auto_allowed=false 断言；gate 直接 await_human
- [ ] 承诺一致性评测 `data/eval/commitments/cases.yaml` ≥ 10 组多轮：违规句数 0
- [ ] 人工改金额 → 账本新条目 → 后续回复只出现新值
- [ ] 前端 ProposalCard / ExecutionCard 支持金额 / 币种展示

**设计依据：** 03 §2；06 §5 第 3 道；00 D-L3-9
