# 69: 多品类故障卡与预写计划编写流程

**What to build:** 计划编写工具链：`haike-plans scaffold --category <c> --family <f>` 生成计划模板（步骤 / expected_result / caution / next_on / instruction_src 占位）；`haike-plans lint` 校验 evidence 引用存在于知识库 manifest、next_on 闭合、高危动作步骤必有 caution、signatures 对应词表；`haike-plans coverage` 报告每品类每族的计划覆盖与证据缺口；故障卡按 SKU / category 从计划与知识自动生成草稿（≤ 800 token）供人工校对。目标：新品类 ≥ 5 条计划、每 in_scope SKU 一张故障卡。

**Blocked by:** 67, 68, 70

**Status:** todo

**Owner:** —

- [ ] lint 负例：悬空证据、next_on 指向不存在步骤、拆机步骤无 caution 各报错
- [ ] coverage 报告与 `in_scope` 推导一致
- [ ] 新品类 A1 式排障一例端到端通过（步骤引用真实知识片段）

**设计依据：** 07 §1「故障卡 / 计划」；09 §3（原系列）
