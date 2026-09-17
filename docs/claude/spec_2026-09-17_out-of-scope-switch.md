# 范围外产品的下一轮：不问症状，用户改口即切换

日期：2026-09-17　范围：`config/products.yaml`、`orchestrator/app/sessions/clarify.py`

## 问题

会话 `cd45df574b044961b9b79d227a37acc6`：

| 轮 | 用户 | 系统 | 内部 |
| --- | --- | --- | --- |
| 1 | 我的充电与移动电源出问题了 | 「本期智能排障仅支持 eufy 扫地机器人…」→ R8 摘要 | `category_hint` → power_bank，`in_scope: false` → out_of_scope 节点 |
| 2 | 我的机器人有问题 | 「设备按电源后能正常启动吗？」 | 「机器人」不是品类关键词 → 沿用 power_bank；进了扫地机的症状判别题；摘要仍写 R8 |

两个独立原因：

1. **关键词漏「机器人」**。`robot_vacuum.keywords` 只有 扫地机 / 扫地机器人 / 扫拖机器人 / 拖地机 / 机器人吸尘器 / robovac，
   单说「机器人」匹配不到，`decide` 回退到 `state.category` 里上一轮的 power_bank。
2. **范围外产品被当成已确认的排障对象**。`out_of_scope` 节点把 `product_confirmed = {移动电源（型号未确认）, in_scope: False}` 写进状态；
   下一轮 `decide` 进 `if confirmed:` 分支，该分支不设 `out_of_scope`，直接落到 `decide_symptoms`；
   品类 ≠ taxonomy 品类 → `clarify(symptom_missing)` → 对一台移动电源问扫地机的判别题。
   卡片里选中范围外 SKU（`_confirm` 写 `in_scope: False`）后再发文字，是同一条路。

## 改动

- `products.yaml` → 2026-09-17.1：`robot_vacuum.keywords` 加「机器人」。目录里只有这一个机器人品类，无歧义；
  `strip_category_words` 按长度降序剥词，「机器人吸尘器」仍先于「机器人」被剥。
- `clarify.decide`：在 `if confirmed:` 之前加一段——`confirmed` 且 `in_scope` 为假时，本轮若给出型号候选或范围内品类，
  作废占位（`product_confirmed = None`）走原有的未确认分支（→ category_only / confirmed_sku）；否则 `out_of_scope = True` 直接
  `continue`，路由回 out_of_scope 节点再说明一次 R8。不进症状问诊。

## 回归

- `tests/test_catalog.py::test_category_hint`：「我的机器人有问题」→ robot_vacuum。
- `tests/test_sessions_clarify.py::test_out_of_scope_product_stays_out_of_scope_until_user_switches`：
  三轮重放——R8 → 「有问题」仍 out_of_scope 且回复不含「启动」 → 「我的机器人有问题」切到 category_only / robot_vacuum、占位清空、无 escalation_summary。
- catalog / clarify / actions / human / model_clarification 五个套件 46 passed；ruff 通过。

## 验证

- `scripts/ci-local.sh` 全绿：ruff / db-check / pytest 896 passed / contracts 94 / 前端 214（含同日「照片先验进候选」改动）。
- `make up` 重建镜像（2026-09-17 11:13），实机新会话 `c5837e3fc9404c54ba2c228a3dbb16e5` 重放三轮：

| 轮 | 用户 | 改动前（cd45df） | 改动后 |
| --- | --- | --- | --- |
| 1 | 我的充电与移动电源出问题了 | R8 说明 | R8 说明（不变） |
| 2 | 有问题 | 「设备按电源后能正常启动吗？」 | 再说明一次「仅支持 eufy 扫地机器人…」，stages 含 out_of_scope，无症状问句 |
| 3 | 我的机器人有问题 | 沿用 power_bank | `category = robot_vacuum`、`product_state = category_only`、`product_confirmed` 清空；进入扫地机判别题 |

- 查 journey 时注意：`session_facts` 投影在 run 结束后异步写入，紧接着查会拿到上一轮的值（首次断言即因此误报 runs=2）。

## 观察

- 会话级 `outcome` 仍显示 `escalated / R8`：第 2 轮升级后第 3 轮继续排障，投影的 outcome 不回退。这是分析口径问题
  （一个会话既升级过又在继续），不在本次范围。

## 未处理

- 「本期只支持扫地机」是设计决策（02 §3、票 25），靠 `in_scope` 配置生效；放开一个品类除了改 `in_scope`，
  还需要该品类的 symptom_taxonomy、plans、fault_cards、vision_vocab 与知识库，以及 `or "robot_vacuum"` 兜底默认值的清理。
- 品类归属仍是关键词子串匹配（设计上不让模型猜产品）；与 9db 的「运行异响推不出品类」同源。
