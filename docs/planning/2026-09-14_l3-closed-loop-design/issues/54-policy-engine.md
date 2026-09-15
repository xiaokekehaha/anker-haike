# 54: 售后政策规则引擎

**What to build:** `app/policy/`：`models.py`（PolicyInput / RemedyDecision / PolicyDecision / Clause）、`loader.py`（`config/policy/warranty_policy.yaml`、`clauses.yaml`、`regions.yaml` 加载 + 校验 + mtime 热加载）、`engine.py`（缺输入 → 匹配 → 排除 → remedy when 评估 → 跨区域 → 汇总；纯函数）、`fault_class.py`（R4 → safety；evidence 命中品质类计划 → quality；用户损坏词表 → user_damage；否则 unknown）。演示规则：CN / EU / UK 三套，refund 一律 `auto_allowed: false`。CLI `haike-policy lint|explain --case`。

**Blocked by:** —

**Status:** done

**Owner:** —

- [ ] 决策表 `data/eval/policy/cases.yaml` ≥ 40 组 pytest 全绿（含 A5 允许换货、A6 UK 购 DE 用 needs_human、非授权渠道 needs_human、user_damage 无免费补救、保外付费维修、已换过不再换）
- [ ] 属性测试：`auto_allowed ⇒ eligible ∧ cost_bearer=company`；`needs_human ⇒ 无 auto_allowed`；缺 region ⇒ missing_inputs 非空
- [ ] loader 负例：条款引用不存在、priority 冲突、auto_allowed 的 refund 报错
- [ ] `explain` 输出每条条件的 expected / actual / met 与条款文本

**设计依据：** 04 全文；00 D-L3-5/6
