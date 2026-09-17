# 实现记录

日期：2026-09-17。根因与决策见 findings.md。

## 1. 改动

| 文件 | 内容 |
| --- | --- |
| `config/vision_vocab.yaml` | 版本 2026-09-15.6 → 2026-09-17.1；新增 `category_parts: {robot_vacuum: [滚刷, 边刷, 尘盒, 吸口, 基站]}`，只列品类特有部件 |
| `orchestrator/app/diagnose/localization.py` | `signature_matches(localization, faults)`：每条可用 finding 命中的 plan_id 列表，按 finding 归因；`signature_plans` 改为其上去重；`part_categories(localization)`：findings 部件 → 品类线索 |
| `orchestrator/app/sessions/graph.py` vision 节点 | (a) `visual_product` 候选并入 `part_categories`，仍要求唯一品类；(b) 签名命中的 plan 在 `plans.yaml` 声明的 `symptom_codes` 写成 `kind: symptom / source_kind: image_signature` 事实，带 `quote`（如「滚刷缠绕」）、`plan_ids`、`image_ids`，按 value 去重；`issue_revision` / `context_revision` 在只有签名事实时也递增。retrieve 处的内联 `signature_plans` import 收到模块顶部 |

不改：三处 `symptom_codes` 过滤、`_active_facts` 定义、vision 提示词、`rv_suction_motor_fault` 内容。

## 2. 为什么是「症状事实」而不是改过滤

候选集的三处门槛（`decide_symptoms.selected`、retrieve `allowed_ids`、`_synthesize_step.allowed`）都只读
`kind == "symptom"` 事实里的 `symptom_codes`。改任何一处都漏另两处；写成事实则三处自动一致，
而且与 `symptom_taxonomy.yaml` 已把「缠绕 → suction_low」补进文字路径的做法对称——同一条已审核知识，图片和文字两条入口。

副作用是有意的：只发一张滚刷缠绕照片 + 确认品类，`codes = [suction_low]` 即可进检索出步骤，不必再问症状。

## 3. 回归

| 文件 | 用例 | 断言 |
| --- | --- | --- |
| `tests/test_l3_experience.py` | `test_category_parts_are_confirmable_hints_from_known_parts` | `category_parts` 的部件 ⊆ 词表、品类 ∈ 目录、签名 plan ∈ 计划库；完好滚刷 → robot_vacuum；传感器 → 无线索；`signature_matches` 按 finding 归因 |
| `tests/test_conversation_evidence_next_action.py` | `test_photo_signature_joins_candidates_beside_text_symptom` | 9db 序列全路径：首轮问「是扫地机器人吗」且 `product_state` 仍 unknown；签名事实 `(symptom, 滚刷缠绕, [suction_low], [rv_suction_hair_wrap])`；同图重传事实仍一条；「是」后 `codes == {abnormal_noise, suction_low}`、`plans_ranked ⊇ {hair_wrap, motor_fault}`、末轮 awaiting_input |
| 同上 | `test_generic_parts_do_not_hint_a_category_or_symptom` | 只认出传感器：无 `visual_product`、无签名事实 |

相关套件 199 passed（两文件 35 + 相邻十文件 164）；ruff 通过。视觉与模型均为 fake，不花 token。

## 4. 实机（新镜像 2026-09-17 10:55，会话 97f56692c3574b91b916918837e1a1c9）

同一照片、同一 5 轮序列：

| 轮 | 输入 | 回复 / 结果 |
| --- | --- | --- |
| 1 | 纯图 | 「照片中的设备看起来是扫地机器人，请确认是这个品类吗？」（改动前：泛问品类） |
| 2 | 有点问题 + 同图 | 记下并重申确认问句 |
| 3 | 运行异响 | 同上 |
| 4 | x00001 | 同上（见 §5 第 1 条） |
| 5 | 扫地机器人 | `fault_plan_ids = [dustbin_full, filter_clog, hair_wrap, motor_fault, side_brush]`；步骤卡 `rv_suction_hair_wrap s1 检查并清理滚刷`；无 R7 |

改动前同一序列末轮 `fault_plan_ids = [rv_suction_motor_fault]`、步骤是「确认异响后停用等人工」。

## 5. 观察到但未在本轮处理

1. `fixed_question` 里 `expected_category` 分支排在 `unmatched_hints` 之前：用户给了型号 `x00001` 目录零命中时，
   回的是品类确认句而不是「型号暂未匹配」。品类确认确实是更该先问的，但用户提供的型号没有被回应。
2. 视觉模型仍会写出「未见冒烟烧焦鼓包漏液」这类否定清单（9/16 已在规则层处理，本次未触发 R4）。
3. 症状多选 smoke 场景（无图）本次一轮没过：模型没把「效果不好」解析成对判别题的回答而重问。
   与本次改动无关，safety-negation task_plan「Errors」记过同一条断言过严；未在本次放宽原脚本。
4. codes 变成 `[abnormal_noise, suction_low]` 后 suction_low 的四个计划全部进候选，粒度与文字说「缠绕」一致；
   签名指向的具体 plan 仍靠 fault card 排序与 `image_observations` 给模型排序，未另加硬约束。
