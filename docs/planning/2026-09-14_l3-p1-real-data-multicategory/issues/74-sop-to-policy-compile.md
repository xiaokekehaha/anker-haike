# 74: SOP → 政策规则编译与审核流

**What to build:** `haike-policy draft --sop <文档>`：LLM 辅助把 SOP 文本抽成 policies / clauses 草稿（每条规则带原文段落引用与页码 / 章节），输出到 `config/policy/drafts/`；人工审核清单（适用范围、保修期、补救项条件、排除项、跨区域、费用承担）→ 合并进正式 YAML 并 `lint`；`explain --case data/eval/policy/cases.yaml` 对照业务确认；决策表补真实场景 ≥ 40 组并全绿后冻结 `policy_version`；RELEASE 记录 SOP 文档版本 ↔ policy_version 映射；`source: demo` 标记移除。

**Blocked by:** 真实 SOP 到手；P0 54

**Status:** todo

**Owner:** —

- [ ] 草稿每条有原文引用；无引用条目 lint 拒绝
- [ ] 审核记录（审核人 / 日期 / 修改）随 YAML 提交
- [ ] 决策表全绿；`auto_allowed` 项经业务书面确认清单

**设计依据：** 04 §3、§7；00 D-L3-6
