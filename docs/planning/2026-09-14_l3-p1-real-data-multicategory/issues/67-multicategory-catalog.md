# 67: 多品类产品目录生成

**What to build:** `haike-catalog build --kb <知识库导出> --review out/catalog_draft.yaml`：从产品技术知识库抽 SKU / 名称 / 别名 / 品类（LLM 辅助抽取，输出带原文引用；人工审核后合并进 `config/products.yaml`）；`in_scope` 由「该品类是否有 ≥ 1 条已审核计划」自动推导（读 plans.yaml），不再手写；同名异类冲突检测（如 S1 Pro）与别名归一（大小写 / 空格 / 连字符）；目录版本号与 RELEASE 绑定。目标 ≥ 2 个品类 in_scope。

**Blocked by:** P0 66（演示收口后再换目录，避免回归干扰）；真实知识库到手

**Status:** todo

**Owner:** —

- [ ] 草稿每条带来源引用；审核后 lint 通过（SKU 唯一、别名不跨品类冲突或显式标注）
- [ ] `in_scope` 推导单测：无计划品类自动 false 并走 R8
- [ ] A2 同名异类回归通过；新增品类的消歧卡片端到端一例

**设计依据：** 07 §1「产品目录」；06 §2 多品类预留
