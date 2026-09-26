# 进度

## 2026-09-25 14:13

- 从 `feat/candidate-relaxation@0bd81e2` 新建分支 `feat/service-plan-p0`。
- 写 plan.md / task_plan.md。开始 T1a。

## 2026-09-25 T1 执行结果不明与执行中断（完成）

- `backends/protocol.py`：`ServiceOrderRequest` / `ServiceOrder` 加 `client_ref`；`BackendClient` 加 `find_service_order`。
- `backends/mock.py`：Memory / Postgres 两个实现记录 `client_ref` 并支持查询；新故障模式 `created_then_timeout`（先建单再超时，`check_committed`）。
- 迁移 `0008_service_order_client_ref`：`service_orders_mock.client_ref` + 唯一索引；`test_db_migrations.py` HEAD 改 0008；`test_l3_postgres.py` 夹具套用 0007、0008。
- `actions/store.py`：第二次接管仍过期抛 `ExecutionNeedsReview`（`ExecutionBusy` 子类）。
- `actions/executor.py`：写操作从第 2 次尝试起先 `find_service_order(幂等键)`，查到即按成功返回；查询失败抛 `OutcomeUnverified` → 不可重试、`needs_review`；超时写 `outcome_unknown`。
- `sessions/l3.py` `execute`：`ExecutionNeedsReview` 与 `needs_review` 结果都转案件 `awaiting_approval`（原因「执行结果待人工核实」）并进 `await_human`；并发执行中仍回「相同申请仍在处理」。
- 测试：`test_l3_backends_actions.py` 新增 4 项（建单后超时可查到、超时后重试不重复建单、建单前超时重试只建一次、查询失败转核实），租约测试收紧为 `ExecutionNeedsReview`；`test_conversation_l3.py` 新增 2 项（图内重试只发一次建单请求、需核实进人工队列）。
- 结果：相关 4 个测试文件 89 passed；`make lint` 通过。首次合跑出现一次 `test_a4_consult_fast_path_and_missing_param` 失败（该轮 105 s，明显异常慢），单跑与两文件合跑均通过，未复现。
- 未验证：本机 Docker 未运行，Postgres 路径（`MockBackend` 的 `client_ref` 插入与查询、0008 迁移）只在 CI / ci-local 可测。
- 未做：演示配置 `backends_mock.yaml` 没有加 `created_then_timeout` 订单（DEMO-FAIL-001 购买地非 US，走不到自动执行），需要演示时再加。

## 2026-09-25 T2 已批准 / 待审批时客户改诉求（完成）

- 复现：案件 `approved`（人工改了费用、等客户重新确认）或 `awaiting_approval` 时客户说「改成退款」，只回「案件正在等待处理」，待确认的方案卡仍有效。测试先红后绿。
- `cases/service.py` 新增 `request_changed`：`approved → awaiting_approval`，清掉客户同意与已选方案，记 `request_changed` 事件（input_id / 原话 / 新诉求），同一输入幂等。
- `sessions/l3.py`：`changed_request` 判断本轮消息的诉求是否不在当前审批覆盖范围内（以最近一次人工决定之后的变更记录、已选方案为准）；`propose` 守卫前调用 `_pause_for_changed_request`：作废待确认卡（`pending_changed`, reason=`request_changed`）、推送案件变化、告知客户已暂停原方案并交人工重审，保留新的 `requested_remedy`。
- 测试：`test_conversation_l3.py::test_changed_request_pauses_pending_approval_and_its_card`（两种状态参数化）：案件回到待审批、事件记录原话、旧卡 409、重复同一诉求不重复记录、不建单。
- 结果：L3 相关 5 个测试文件 88 passed；`make lint` 通过。
- 未做：收货地址字段本身（仓库没有地址字段，改地址目前只触发暂停与人工重审）。

## 2026-09-25 T3 情绪策略接线（完成）

- `prompts/system.py`：`emotion_layer` 全部读 `config/emotion_policy.yaml`，删掉写死的 `EMOTION_LAYERS`（含与配置矛盾的「承诺尽快解决」）；函数内导入改为顶层导入；`PROMPT_VERSION` 升 `2026-09-25.1`。回放包 `replay/*/manifest.json` 记录的是 `system=2026-09-14.1`、`interpret=2026-09-14.8`，早已与当前版本不一致，这次升级不引入新的回放失配。
- `conversation/reply.py`：策略动作含 `offer_human` 且本轮观察到情绪、回复里没提人工时，末尾追加固定文案 `OFFER_HUMAN`（只说可以转人工并整理情况，不宣称已接通）。
- `sessions/clarify.py` `differentiated_candidates`：`skip_optional_clarify` 时不出可选的型号卡。
- `emotion/policy.py` 新增 `complaint_flagged`：按策略动作 `flag_complaint_risk` 或级别 `complaint_risk` 判定；`l3.service_context` 开案、`await_human`、`commit_issue` 三处改用它（此前漏掉「愤怒且上升」规则）。
- `frontend/src/admin/pages/Board.tsx`：过滤值改为后端实际输出的「(未知)」（原来写成「(未识别)」，无情绪会话被算成非平静）；说明改为「最近一轮」。
- 测试：`test_intake.py` 两处断言改为配置文案；`test_l3_experience.py` 新增 4 项（全部策略文案来自配置、offer_human 固定出口与去重、投诉标记跟随动作、skip_optional_clarify 跳过型号卡）；`pages.test.tsx` 新增「(未知)」不计入。
- 结果：后端相关 9 个文件 125 passed；前端 pages.test 5 passed，typecheck 通过；`make lint` 通过。
- 未做：`suggest_compensation_review`（需要契约里的新来源值，放 T8）；看板浏览器走查（本机后端未起）。

## 2026-09-25 T4 人工台补显示（完成）

- `cases/service.py` 新增 `record_handoff`：交接摘要存为案件事件 `handoff_summary`（与上一份相同不重复记）；案件事件不进客户时间线。
- `sessions/l3.py`：`await_human` 与改诉求暂停时用 `build_summary` 生成摘要（不调模型），`handoff_reason` 给出转人工原因：已有具体迁移原因（如「执行结果待人工核实」）优先，其次退款 / 改地址、政策要求人工（附排除条款原文）、授权检查未通过项。
- `actions/store.py`：两种执行存储都加 `for_case`；`admin/l3_router.py` 案件详情改用它（原来只在有 Postgres 连接池时才查、内存模式恒为空），并返回 `handoff_summary`。
- 前端：新组件 `admin/components/CaseRecords.tsx`（`HandoffSummary`：转人工原因、产品、客户诉求、已做排查、观察、建议回复、核对字段表；`CaseRecords`：执行记录标「待人工核实 / 结果不明」、承诺带依据、事件时间线）；`CaseDetail.tsx` 中栏接入；`ProposalCard.tsx` 条款来源显示为 `source_url` 链接；`SummaryCard.tsx` 导出 `FACT_LABELS` 并补订单号、型号、金额、币种、购买地、平台；`l3.ts` 补 `handoff_summary`、`CaseEvent`，`CaseExecution.error` 改为实际的对象结构；`admin.css` 加 `.handoff` 样式。
- 测试：`test_conversation_l3.py::test_case_detail_carries_handoff_summary_and_executions`（摘要原因、产品、推荐方案、金额核对字段、客户时间线不出现摘要、批准执行后详情有执行记录）；改诉求、待核实两个用例补摘要原因断言；新增 `admin/__tests__/CaseDetail.test.tsx` 4 项（此前案件页没有测试）。
- 结果：后端相关 7 个文件 110 passed / 12 skipped；前端 `src/components` + `src/admin` 16 个文件 104 passed，typecheck 通过；`make lint` 通过。
- 未做：浏览器走查（本机后端与数据库未起，案件页依赖 `/admin/api`）；金额与地址的规则检查（地址字段不存在，放后续）。

## 2026-09-25 T5 照片签名跨品类（完成，根因与计划不同）

- 复现：扫地机会话「eufy X9 Pro 回不了座，充不上电」+ 照片（充电触点, 污渍）。照片在品类确定之前读，签名只能映射到耳机计划 `eb_charging_contacts`，写成带 `eb_*` 症状码的图片症状事实。
- 真正的影响在决策层：`diagnose/decision.py` `known_symptom_codes` 只要事实里有码就跳过原文归一，之后才按品类过滤——耳机的码被滤掉，扫地机的原文症状也没归一，得到空集。去掉修复时测试断言 `codes == []`，确认为红。
- 修复：`known_symptom_codes` 先按品类过滤再决定是否退回原文归一；`sessions/graph.py` 写签名事实时，品类已知则只取本品类计划（品类未知时照旧写，由决策层过滤）。
- 测试：`test_vision_graph.py::test_photo_signature_of_another_category_does_not_mask_the_text_symptom`（决策用的码非空且全属扫地机、`symptom_codes` 不含别的品类、无升级摘要）。
- 顺带：本轮新增测试里的函数内导入挪到文件顶部（CLAUDE.md 只用顶层导入）；`test_l3_experience.py` 导入顺序用 `ruff --select I --fix` 整理。
- 结果：受影响的 12 个后端测试文件合跑 217 passed / 13 skipped；`make lint` 通过。
- 流程偏差：一次用 bash 内嵌多行 Python 改测试文件，违反「bash 命令里不嵌多行脚本」，之后改用编辑工具。

## 2026-09-25 T6-L2 铭牌读数作候选（完成，与 plan.md 有偏差）

- 偏差：plan.md 写「无确认、文字无候选时查 model_hint 并出卡」。实测这会在品类已知、排查不按型号分化时多出一张卡（如「扫地机不吸了」），违背 spec 2026-09-19-0810 三档判定「型号不影响处理就不问」。改为只在原本就要问的两处使用读数：
  - 品类不明、原本要开放式追问产品：改为用读数的目录候选出卡（单命中也出卡，不走 `_lookup` 单命中自动确认）；
  - 知识按型号分化、原本要出型号卡：读数对应型号排第一。
- `sessions/clarify.py` `decide`：计算 `photo` 候选（本会话出过卡就不再用）；两处接入。
- `sessions/graph.py` `prepare_card`：候选与读数重合时 note 写「照片铭牌读到「X」，请确认是不是这台设备」；候选同属一个品类时给「不确定」出口并带 `category`（否则选「不确定」会 KeyError）。
- 测试：`test_vision_graph.py` 新增 3 项（替代开放式产品追问、型号卡读数排第一、型号不影响时不多问）；`test_conversation_evidence_next_action.py::test_unverified_ocr_cannot_confirm_catalog_product` 的结果断言由 `clarify` 改为出候选卡，「不能确认产品」的不变量保留。
- 结果：涉及产品卡的 14 个测试文件 235 passed / 12 skipped；无契约变更。

## 2026-09-25 T6-L4 口述购买日期（完成）

- `conversation/interpret.py`：`context_field` 加 `purchase_date`；提示词说明只在能确定到某一天时抽取、用 YYYY-MM-DD；`INTERPRET_PROMPT_VERSION` 升 `2026-09-25.1`。
- `sessions/graph.py`：上下文事实写入 `service_context` 前用 `receipt.stated_purchase_date` 校验（真实日期、不晚于当天）。
- `sessions/receipt.py`：`card_payload(receipt, stated)` 只在 OCR 没读到日期时用口述日期预填，并从 `unreadable` 去掉；`receipt_extract` 传入 `service_context`。
- 边界：口述日期不进 `CONTEXT_FIELDS`，`policy_input` 仍只认凭证 / 订单来源的日期（测试断言 `purchase_date is None`）；客户在凭证卡上确认后才成为凭证字段，与今天手工填写同等。
- 测试：`test_sessions_receipt_card.py` 新增 2 项（只补空缺不覆盖、日期校验）；`test_conversation_l3.py` 新增 1 项（合法日期记为用户来源、未来日期丢弃、不进政策输入）。
- 结果：凭证 / 归并 / 语义相关 7 个文件 78 passed；`make lint` 通过。
- 未做：`business.remember` 未放行 `purchase_date`（预填只读 `service_context`，不需要）；语义金标未补口述日期样例（需真实模型评测）。

## 2026-09-25 本轮汇总验证

- 后端：受影响的 29 个测试文件合跑 429 passed / 17 skipped（跳过项均为本机无 Postgres）。
- 前端：`src/components` + `src/admin` + `src/state` 22 个文件 167 passed；`npm run typecheck` 通过。
- `make lint`、`make scan-secrets` 通过。
- 未跑：全量 pytest、`scripts/ci-local.sh`（需要本机 Postgres，Docker 未运行）；浏览器走查（后端未起）。
- 未提交：等用户要求。T6-L3 的匹配方式待定，见 addendum.md §3。

## 2026-09-25 收尾复核后的修正

- 勘误（T3 记录）：回放包记录的 `system=2026-09-14.1` 与改动前代码一致，失配的只是 `interpret` 等其他项；本次升 `system` 版本会新增一项 system 失配。实际影响不变：回放包拼接后的 `prompt_ver` 本来就对不上，需要重新录制。
- T3 补漏：`offer_human` 原来只接在 `acknowledge_current_turn`，走模型流式回复的对话（`reply_to_turn`）和排障回复节点（`graph.py` `reply`）带不上。新增 `offer_human_after_stream`：流式回复结束且正文未提人工时，另发一条只含固定文案的短消息；`complaint` 意图本来就走固定文案。测试：`test_l3_experience.py::test_offer_human_follows_a_streamed_reply_as_its_own_message`。L3 `say()` 的办理类消息未接（转人工相关的文案本身已提到人工）。
- T2 补漏：退款 / 改地址直接进人工审核、案件没有已选方案，客户再说一遍「我要退款」被误判为变更并暂停。`cases/service.py` 新增 `record_review_request`，`await_human` 进审核时记录客户诉求（`review_requested` 事件）；`changed_request` 以「最近一次人工决定之后的审核诉求或变更」为准。测试：`test_conversation_l3.py::test_repeating_the_request_under_review_is_not_a_change`（先红后绿）。前端事件时间线补 `review_requested` 文案，变更事件显示新诉求。
- 结果：L3 三个测试文件 92 passed；回复相关 5 个文件 84 passed；前端 `src/admin` 29 passed，typecheck 通过；`make lint` 通过。

## 2026-09-26 按票提交

- 用户要求按票提交。顺序按依赖：T3 `e4c1a05` → T4 `4d22356` → T1 `eb35e6c` → T2 `a539357` → T5 `6e6d443` → T6-L2 `5c4dbe9` → T6-L4 `0ae4d00`。T1 的用例断言交接摘要、T2 的暂停复用交接摘要，所以 T4 排在 T1、T2 之前。
- 跨票 hunk 按行拆分暂存；每个提交都在导出的暂存树上跑了 ruff 与相关测试文件，全部通过。
- 前端 `CaseRecords.tsx` 里 `request_changed` / `review_requested` 的事件文案随 T4 提交（T2 的后端先于它不存在也不影响显示）。
- 未跑：`scripts/ci-local.sh`（本机 Docker 未运行，Postgres 路径与迁移 0008 仍只在 CI 验证）。
