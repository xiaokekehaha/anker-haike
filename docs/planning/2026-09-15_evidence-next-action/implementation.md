# 证据与下一动作：实现记录

## 行为变化

1. disambiguate 先消费所属问题尚未处理的故障图片，再判产品和症状。图片引用记录 issue_id，处理过的 ID 存在问题状态中；旧引用通过会话历史恢复所属关系。视觉失败也记录已尝试，避免同一附件每轮重复调用。
2. 纯故障图片是有效输入，不再让文本模型解释空字符串。品类线索来自图片观察并由用户确认；未复核 OCR 保存在 visual_product，不再通过 product_hints 的目录匹配绕过确认。
3. 产品品类事实与计划覆盖分开：category_only 不依赖计划是否存在。未知型号可与已知品类同时保存。
4. 澄清文案改为确定性输出。clarification 保存实际 question、question_id、asked_input_id 和 subject（目标、已知型号/症状/品类线索）；新证据不算一次未进展回答。旧检查点没有实际问题绑定的计数不直接触发 R7。
5. 针对最后实际产品问题的裸型号/品类回答走确定性解析，例如 x00001 不再被误解为订单查询；后来的业务问题和用户明确业务切换不会被旧产品问题抢占。product_answered 路由优先于旧 consult_intent。
6. 手写判别题覆盖不到剩余症状时，直接生成受控选项问题，允许多选。选择必须绑定当前 question_id、有本轮原话、且是合法选项；unknown 携带选中项会被拒绝。两次无法回答仍有有界退出；系统问题覆盖缺失用 R5 表达。
7. 摘要利用已接受问答，后台时间线展示真实原因文本。R2/R5/R7 列表标签与后端含义对齐。确定性澄清退出模型候选评测，保留旧模型配置/提示构建接口用于历史兼容。
8. 已审核的整段停止提醒若作为步骤来源，使用 stop_conditions 显式标识，避免提醒中的风险词导致步骤丢弃及零步骤 R2。仅可信计划库可赋予此标识；模型不能修改。高风险操作检查和用户/图片实际风险检查继续生效。来源正文、触发条件、反馈转移保持原样。

## 原图边界

9db 原图是 324×262 的设备展示图，短边小于当前故障图画质门槛 300。没有上采样或放宽既有视觉质量阈值。未知产品的不可用图片允许改用文字确认品类，不强制走故障部件补拍计数。清晰图产生品类线索的分支另有真实 HTTP 图回归（只替换视觉供应商输出）。

异响计划仍沿用已批准的现有知识。当前仅有 rv_suction_motor_fault，其适用确认和停止条件覆盖较浅；本次修复不宣称扩充了排障知识，也不凭空生成替代操作。

## 验证

- 原始四项回归先失败，再修复通过。
- 新增 test_conversation_evidence_next_action.py，覆盖真实理解/归约/会话图：原输入序列、图片单独输入、品类确认、跨轮图片与问题隔离、未复核 OCR、症状单/多选、unknown 有界退出、答案与订单问题隔离，以及条件性停止提醒不误报 R2。
- 最终后端全量：815 passed（完整最终代码与计划配置）。
- 前端管理员页面：17 passed；typecheck、Vite build 通过。
- 后端 app 与新增测试 Ruff、git diff --check 通过。
- 首次真实模型验收发现裸型号被错误解释为查订单。保留 smoke-first-result.json；完善答案绑定并加强 smoke.py 的验收条件，最终结果见 smoke-result.json。
- 第二次发现停止提醒被预步骤过滤器丢弃，保留 smoke-second-result.json；修复后规则/计划/步骤/新会话相关 65 项通过。
- 最终真实模型与本地数据库验收通过：c94ec80f2ce34aeeb8fec669186b99cf（症状选择）、6ed7de363f484d4e98bec96b36a4e00a（原图/未知型号/补品类），共 9 轮。均进入已配置步骤，无误触 R7、误查订单或零步骤 R2。低分辨率原图经过画质检查后改用文字确认品类，没有声称已读出型号。

## 本地运行

- 使用完整 Dockerfile 构建并仅更新 haike 项目的 orchestrator 服务。
- 当前镜像：sha256:bc0a6d90173521ba10023e0f65119b847d35e90fcbb68eaab2eb4e3b4a46cb04。
- 原镜像保存为 haike/orchestrator:before-evidence-next-action-20260915（sha256:af25d5f275ac63c0b54fc677f62524886f7a3e41560de838ea4d07450d0881b8）。
- 容器 healthy，/health/live 返回 ok。没有 /health/ready 路由，第一次探测该路径的 404 不代表服务不健康。
- config/plans.yaml 更新到 2026-09-15.2，电机计划版本 2，仅添加现有来源的 stop_conditions 声明。原配置保存于 plans-before.yaml，回滚镜像时应一起恢复。未变更数据库结构或历史会话；验收使用新建 evaluation_source=smoke 会话。保留工作区原有视觉测试/文档改动。

复验命令：`orchestrator/.venv/bin/python docs/planning/2026-09-15_evidence-next-action/smoke.py <原图路径>`。
