# 进度

- 10:12 用户确认 P1 → P2 → P3，P3 选方案 A（条件判定加一次轻量模型调用）。
- 10:20 读 reduce / interpret / commands / synthesize / charging / verify / router 校验。
  调整 P1-2：原提议「mismatch 直接丢弃不追问」与 T52 金标（sop=clarify，先区分盒子自身供电与盒子给泵充电）及 4 个现有测试冲突，
  首次追问是有意行为；改为「同一澄清问过且已答不再问」，覆盖所有模板化澄清。
- 真实会话第二轮的模型语义原文不在 run 文件里，服务容器 10 分钟前重启，日志已不含；"nothing waiting" 只在模型给出 feedback 或 pending_answer 时出现，据此推断两条会话都给了 feedback。
- 10:40 P1 完成（未提交）：
  - verify.step_payload_error：卡片载荷校验一处，router 与文字命令共用；
  - PendingAnswer 增 step_answer，提示词说明问句 / 材料卡的文字回答用它（INTERPRET_PROMPT_VERSION 2026-10-10.1）；
  - commands：问句卡上的 feedback 当文字回答；新增事实（add）不再挡反馈，只有 replace / retract 要确认；
  - reduce.answers_pending_step：本轮在回答当前卡时，新增症状不撤卡；纠正仍撤卡；
  - _diagnose_outcome：上一轮发过的同一澄清（同 reason、同问句）不再发。
  - tests/test_answer_binding.py 7 项（T22 / T46 HTTP 端到端、T52）先红后绿；相关 29 个测试文件 443 项通过；make lint 清零。
- P2 调查：可见 QA 只有 5 条计划 7 个问题步骤；P2 与 P3 都是「步骤 vs 已知事实」核对，合成一个模块、一次模型调用。
- 10:55 P2 + P3 合并实现（未提交）：
  - plans/qa.step_condition：「If <场景>,」拆为 PlanStep.condition；接上一步结果的（still / persists / after …）不算。可见 QA 中 83 计划 107 步；
  - guide/fact_check.check_plan_facts：guide 发卡前对当前计划调用一次 guide.step 判定（问句 answered / 条件 satisfied·negated·unknown），
    服务端校验步骤 id、引文逐字出自本问题的用户原话、选项逐字在卡上；问句答案写 step_attempts(source=fact)，条件写 step_checks；
    否定的条件步骤跳过，兄弟条件成立则其前未知的条件步骤跳过；同一事实修订号每计划只判一次；无用户自述事实、模型失败时不判，照常发首步；
  - operation_conditions.step_unavailable 认 condition_not_met，decide_next 与 prepare_step 共用。
  - 调整 P1-2：只对 *_mismatch（对象 / 时机冲突）去重；needs_confirmation 的前提确认保留 R7 预算内的二次追问（test_diagnosis_recovery 的既有行为）。
  - step_answer 提示压到一行，intake 固定开销回到护栏内（test_context_capacity 4630）。
  - 全量后端 1182 passed / 2 skipped；make lint 清零。
- 10:58 用户问输入预算是否该提高。试改 max_input_tokens 8000→16000、intake 16000→32000：4 个测试把具体数值写成断言
  （reply.stream 8000 字超限、长输入省略到 8000 内、intake==16000、指标里 input_budget==16000），已回退，等用户决定。
- 11:05 预算提高到 16000 / 32000，测试读配置；全量后端 1182 passed / 2 skipped；ci-local 全绿（后端 1182、契约 90、前端 230）。
- 11:10 make up，4 个多轮场景复跑：T22 → s2、T46 → s3、T52 第二轮换对象再问（泵）→ 收紧 P1-2 为同类冲突只问一次；
  再次 make up 复跑 T52：第二轮转人工，不再追问。T48 未改。结果见 addendum.md。临时复跑脚本已删除。
- 11:35 T22 复测不稳定定位与修复（fact_check 对照 + 不得因判定耗尽计划），真实连跑 6 次 5 次正确，1 次为首轮意图误判（另一问题）。见 addendum.md。
- 11:45 一并修首轮带码表单误判 product_question 与错误码跨轮沿用；真实连跑 T22 8/8 正确。
- 11:58 修 T22 首轮物流次诉求（表单元数据行识别）；真实连跑 12 次 0 次提示，但模型这 12 次未产生该次诉求。
