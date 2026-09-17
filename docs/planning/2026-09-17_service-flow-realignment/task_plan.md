# 流水记录

## 2026-09-17 本轮（只出方案，不动代码）

用户要求：固定流程与模板按实际公司业务流程来做；先体验线上流程，再定改哪里。
用户在中途确认：政策以主办方 SOP 优先、授权跑一遍线上 Live Chat、本轮只出方案文档。随后离线，授权自行决策至方案完成。

### 已完成

1. [x] 走查 `service.anker.com` 受理入口与五类分流
2. [x] 走查质保受理表单（`anker.com` / `soundcore.com/exchange`，同一套模板）三段字段
3. [x] 采集三站政策：`anker.com/policies/refund-policy`、`us.eufy.com/policies/refund-policy`、`soundcore.com/policies/refund-policy`
4. [x] 确认中国区无公开消费者售后政策页（`anker.com.cn/pages/after-sales` 404）
5. [x] 打开 Live Chat 组件，记录准入门槛与开场白；**未进入会话**（见下）
6. [x] 核对仓库现状：`config/policy/*`、`config/actions.yaml`、`config/plans.yaml`、`app/policy/{loader,engine,models}.py`、`app/sessions/l3.py`、`app/prompts/*`
7. [x] 写 [findings.md](findings.md)（实测证据）与 [plan.md](plan.md)（方案与决策）

### 未做与原因

- **Live Chat 未进入会话**：组件要求填真实邮箱与姓名才能 Start，会在 Anker 生产客服系统产生一条实名会话记录。用户已离线，无法就这条实名动作逐项确认，因此停在门口。门槛与开场白本身已产出可用结论（身份先于对话、首轮要求「型号 + 问题」一次说清、会话录制显式同意），记在 findings.md §3。若需要完整对话流程，下次由用户在场时再跑。
- **`portable_power_station` 独立政策页未采集**：`anker.com/anker-portable-power-station-warranty-policy`，本轮未取。
- **未改任何代码**：本轮范围就是方案。

## 2026-09-17 第二轮：P0 实施完成

用户设 `/goal 开始开发和修复` 后离线，授权自行决策。主办方 SOP 仍未到手（repo 内无），
按 D-SR-1 用公开站政策作过渡数据层，schema 与规则形状与数据源无关，SOP 到位只换 data。

实施中对方案的修正与取舍见 [addendum.md](addendum.md)，以下只记做了什么。

### 已完成（plan.md §4 的 P0 全部七项）

1. [x] contracts：`Remedy` 枚举加 `parts` / `paid_repair`，新增 `REMEDY_LADDER` 常量；
       `Clause` 加 `source_url`，`source_doc` 由默认值改为必填。`make contracts` 重新生成，产物已更新。
2. [x] 政策 schema 三级化：`applies_to` 支持可选 `series_pattern` / `part_class`；
       `warranty_months` 支持 `lifetime` / `none`；交叠检测按 specificity 判定；
       来源白名单 `demo/public_site/sop` + 非 demo 来源逐条强制 `source.url/fetched_at/quote`。
3. [x] 20 个品类真实保修期入表：27 条规则覆盖 16 个品类，4 个无来源品类故意留空走转人工。
4. [x] 区域主键改 US；`clauses.yaml` 十条条款全部带 `source_url`（旧的 CN/EU/UK 虚构条款删除）。
5. [x] `l3.py` 的 `REMEDY_TITLES` 补两档，propose 排序改为按官方阶梯。
6. [x] 清掉三处提示词单品类写死 + 一处过时 docstring。
7. [x] `data/eval/policy/cases.yaml` 按新 schema 重写为 50 条，`warranty_end` 与 `parts_auto` 逐条钉死；
       `app/evaluation/cli.py` 扩输出字段并支持 `reason` 成员断言。

### 连带改动（方案未列，不改就红）

- `config/backends_mock.yaml`：`DEMO-X10-001` / `DEMO-S1-002` 改 US，否则演示主路径全部转人工。
- `data/eval/authorization/cases.yaml`：共享锚点的区域改 US。
- `tests/test_l3_backends_actions.py`、`tests/test_l3_postgres.py`、`tests/test_conversation_l3.py`：
  区域与订单跟着改（见 addendum §5）。

### 与另一个会话的文件避让

开工前 `git status` 确认目标文件全部空闲。另一会话（knowledge-gap-fill）占用
`config/plans.yaml`、`config/fault_cards.yaml`、`config/symptom_taxonomy.yaml`、`data/knowledge/**`、
`docs/runbook/official-knowledge.md`、`reports/knowledge/**` 与
`test_{diagnose,guide,plans,conversation_escalation_summary,conversation_evidence_next_action,knowledge_adapter}.py`，
本轮一个都没碰。

唯一交叉的是 `tests/test_conversation_l3.py`：该文件有对方 1 行未提交改动，我改的是 `seed_issue` 的
区域默认值与 `test_a6_approval_restores_graph` 的订单，与对方改动不在同一处。

第 6 项（提示词写死）原计划在冲突时跳过，实际核查后发现 `test_guide.py` / `test_diagnose.py`
都没有断言这三处文案，不需要改它们，所以正常做了。

### 验收

`make lint` 通过，`make contracts-check` 无漂移，后端 952 passed / 1 skipped，
前端 typecheck 通过、L3 reducer 与 events 测试 46 passed。明细见 addendum「验收结果」。

### 下一步

- P1（未开始）：两条受理路径 `claim_type`、SN 采集、凭证必填化、换货收货地址、不保清单 9 条、受理五分类。
  plan.md §5 第五条验收（30 天非质量退货）依赖 P1 的 `claim_type`，本轮未覆盖。
- P2：`troubleshooting_record` 口径对齐、自助入口对标；
  「六个新品类演示证据换真实官方锚点」由 knowledge-gap-fill 那条线负责。
- 未提交（CLAUDE.md：用户要求才提交）。

### 与其他任务的关系

- `2026-09-17_knowledge-gap-fill`：那条线在补知识库缺口并复核 `plans.yaml` 的固定排障流程，本方案的 P2「六个新品类演示证据换真实锚点」与它是同一件事，不要重复开工。
- `2026-09-14_l3-closed-loop-design`：D-L3-6 已写明「政策规则为 YAML 演示规则，来源标待真实 SOP 替换」，本方案是那条决策的兑现，并额外发现数据模型本身表达力不足（三级保修期、处置阶梯缺配件档）。
