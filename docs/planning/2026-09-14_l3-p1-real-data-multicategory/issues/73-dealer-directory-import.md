# 73: 授权经销商真实名录导入

**What to build:** `haike-seed dealers --file <名录> --mapping`：字段映射（名称 / 区域 / 平台 / 授权状态 / 政策备注 / 有效期）、名称归一（沿用 `warranty.key`）与别名表、去重报告、版本号；`Dealer` 模型增 `platform`, `valid_from/to`, `aliases`；L5 匹配增加别名与平台维度；政策引擎 `dealer_authorized` 与 `channel` 从名录推导（`authorized_dealer / unauthorized_dealer`）。演示名录保留为独立 seed 文件供回放。

**Blocked by:** 真实名录到手；P0 54

**Status:** todo

**Owner:** —

- [ ] 重复 / 冲突（同名不同授权）报告并拒绝入库
- [ ] A6 用真实名录中的一条未授权经销商复现 needs_human
- [ ] 回放包仍用演示名录，版本清单区分

**设计依据：** 07 §1「经销商名录」；04 §2
