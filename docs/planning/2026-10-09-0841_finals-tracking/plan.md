# 决赛冲刺跟踪（2026-10-09）

汇总三个来源，作为决赛前的唯一事项清单：

1. `2026-10-07-1543_organizer-materials-replan/remaining_work.md` 的复评（2026-10-09）；
2. 12 单真实链路回放的人工核对（reports/eval/20261009T002859Z_live_tickets.md + 逐条对照 orders.yaml / qa.yaml）；
3. 8 单官方案例文档测评（`2026-10-09-0828_official-case-evaluation/`，判定修正后 5 正确 / 2 部分正确 / 1 错误）。

判断基准：决赛是现场交互演示，评委按 63 单检验 SOP 分支。「演示主线稳」和「评测指标可信」优先，内部工具链与纯清理靠后。

进度勾选写 progress.md；本文开发开始后只追加不改写，勘误写 addendum.md。

## P1 演示主线缺陷（不修则现场出错）

| # | 事项 | 来源与证据 | 状态 |
| --- | --- | --- | --- |
| P1-1 | T55 附件用途：订单截图走默认 purpose=fault 被当故障照片，触发 too_bright 补拍；更严重的是排障失败后该截图被算作「故障图片/视频」证据，证据没收齐换货单照样提交。修复：区分订单凭证与故障证据；订单截图不触发曝光重拍；live_tickets 驱动同步区分附件用途，避免继续掩盖 | 两轮测评均复现；T55 是 D6 主线演示单 | 待做 |
| P1-2 | T55 产品卡重复弹出：排障走完后客户传照片、回 SN 各弹一次产品选择卡（T2080 / T8D04），客户原文已写明 Breast Pump | 12 单回放人工核对 #1 | 待做 |
| P1-3 | T1 物流路由不稳定：「没收到货」4 次里 1 次被判成故障；出错那次意图识别首调 schema_error 重试（T1.json）。修后同一原文重复跑回归 | 8 单测评 + 复测 ×2；12 单回放 | 待做 |
| P1-4 | 客户可见中文与客服口吻残留：重拍提示（config/vision_vocab.yaml:124 retake_guidance）、步骤卡 expected_result「按这一步操作后…」（orchestrator/app/plans/qa.py:19，13 张卡全中）、Q&A 原文 "Have the user shine a flashlight…"（qa.yaml 约 6 处客服话术） | 两轮测评 | 待做 |

## P2 SOP 符合性（评委按分支检验）

| # | 事项 | 来源与证据 | 状态 |
| --- | --- | --- | --- |
| P2-1 | T9 子诉求：客户要求「没发货就先别发」并想咨询其他产品，回复只给了发货日即结束，未回应也未转人工。两轮均复现 | criteria.md 必须项 | 待做 |
| P2-2 | T49 未排障直接转人工：吸奶器开不了机，官方 Q&A 有对应条目（qa.yaml 11687 / 12030 行），SOP 要求先排障 | 12 单回放 #4 | 待做 |
| P2-3 | T5 补发理由描述不准："Tracking doesn't show the package as delivered" 与事实不符（一包已送达），真正理由是另一包 ETA 9/30 已逾期 | 12 单回放 #6 | 待做 |
| P2-4 | T14 未告知硬件故障判定：应说明官方指引判定 4090 为硬件故障可走保修，而不是开口 "I couldn't find an order"（客户未提供过订单号） | 12 单回放 #7 | 待做 |
| P2-5 | 小问题：T7 多余的「按顺序处理」话术；T12 结束语引用被截断的 Q&A 标题 | 12 单回放 #8 | 待做 |

## P3 评测与 CI 可信度

| # | 事项 | 来源与证据 | 状态 |
| --- | --- | --- | --- |
| P3-1 | D2 评测金标清理：data/eval/intent、routing、conversation 仍有 DEMO-X10-001、耳机、充电宝样例；CI `haike-eval all` 在跑过时集。自建评测是展示点（plan G17），金标测不存在的产品会被评委问住 | remaining_work D2 | 待做 |
| P3-2 | 评测口径收紧：live_tickets 分支判定同时接受多种终点（T12 期望解释实走排障、T14/T49 停在追问订单都算对），指标 100% 不能外推为回答正确率。收紧口径或在报告里固定说明 | 12 单回放「关于 100% 的说明」 | 待做 |
| P3-3 | F8 grep 门禁收口：test_analytics、test_escalation_summary、test_context_capacity、test_admin_api 仍有旧 SKU；operation_conditions.py:109「充电宝」（B10 仅剩此处）。最后跑 scripts/ci-local.sh | remaining_work F8 / B10 | 待做 |

## P4 发布与部署链路（决赛部署前必须通）

| # | 事项 | 来源与证据 | 状态 |
| --- | --- | --- | --- |
| P4-1 | release 链路断：scripts/release.sh:37、release-check.sh:34 仍读已删除的 config/plans.yaml；Makefile plans-schema 目标与 seed 帮助文案、pyproject haike-plans-schema 入口指向已删代码 | remaining_work F6 / B11 / F4 残余 | 待做 |
| P4-2 | F7 smoke.py：仍用 kb_manual / rv_suction_hair_wrap，部署冒烟假失败 | remaining_work F7 | 待做 |
| P4-3 | 提交散落的工作区改动：Makefile / README（ui profile）、reports/eval 报告、10-09 测评目录、本目录 | git status | 待做 |

## P5 决赛准备（非代码）

| # | 事项 | 状态 |
| --- | --- | --- |
| P5-1 | 向主办方确认决赛日期与形式（plan.md D8②）、评委是否用 63 单之外的工单（D8④） | 待做 |
| P5-2 | 演示彩排固定 DEMO_TODAY（T5 逾期、T51 过保边界依赖它）；跑一遍 D6 七单演示脚本 | 待做 |

## P6 低成本收尾（顺手做）

| # | 事项 | 状态 |
| --- | --- | --- |
| P6-1 | D7：test_rules 引用的 4 张合成图换 data/official/attachments | 待做 |
| P6-2 | D8：contracts/fixtures/events.valid.json 的 category=charger | 待做 |
| P6-3 | A4 剩余旧快照、F1–F3 文档（README 版本锁定、runbook 改写） | 待做 |
| P6-4 | B13 标完成：R4 对英文步骤生效已由 T45 / T36 回放证实，无需开发 | 待做 |

## 取消项（不再推进）

| 原项 | 理由 |
| --- | --- |
| A10 中文跨语言召回 | 63 单无中文客户，评委用官方工单检验，纯假设场景 |
| A11 SoloCam 漏召回（T57/T59） | 两轮实验无提升（术语改写、rerank），长尾口语描述；97%/98% 下边际收益低。富余时间可捡回 |
| D3 bakeoff 重写 | 内部模型对比工具，决赛不看，10 份 fixture 重写零演示价值 |
| D5 巡检场景按 D6 重写 | 巡检已换官方 PN 与 qa_rv_* 计划，回放 7/7 已覆盖 D6 七单，重写属重复覆盖 |
| E8 候选现象卡、C1/C2/C4/E4 翻译链 | 此前已作废（问诊改开放问题；D2 改统一英文） |

## 待决策

| # | 问题 | 选项 | 建议 |
| --- | --- | --- | --- |
| DD1 | 语言口径矛盾：D2 已改统一英文，但 replan plan.md §4 指标仍写「语言一致 100%」，8 单测评 criteria.md 也要求回应荷兰语客户 | a 维持统一英文，改掉指标口径，演示时主动说明取舍；b 恢复按客户语言回复（约 11 单，需重新引入翻译层） | a：改口径成本接近零；b 增加一次模型调用与事实被改写风险 |

## 执行顺序

1. P1-1 → P1-2 → P1-3（T55 主线与 T1 路由，每修一项用原文重复回放回归）。
2. P1-4 + P2 全部（客户可见文本与 SOP 符合性，多为话术与提示词改动，可并一批）。
3. DD1 决策后改指标口径；P3-1 + P3-2（金标与口径）。
4. P4（release / smoke / 提交），P3-3 收口跑 ci-local。
5. P5 决赛准备与 P6 收尾穿插进行。
