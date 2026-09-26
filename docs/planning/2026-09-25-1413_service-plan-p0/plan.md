# 智能服务方案 P0 迭代：可立即开发的拆解

日期：2026-09-25 14:13。分支 `feat/service-plan-p0`，基于 `0bd81e2`。
依据：[spec_2026-09-25-1336_service-plan-gap-review.md](../../claude/spec_2026-09-25-1336_service-plan-gap-review.md)
与同日四份代码改动图（执行 / 已知信息 / 上传 / 人工台与指标 / 情绪与办理流程）。开发开始后本文件不再改，勘误写 addendum.md。

## 1. 筛选口径

「现在可以开发」= 同时满足：
- 不依赖待决策项 D1–D6（多事项架构、读图是否看文字、AI 复核、演示是否用召回例子、邮件渠道、安全冻结范围）；
- 不依赖外部数据（真实照片、非 US 政策来源、真实业务接口）；
- 有明确落点和可写的回归测试。

排序按契约影响，不按价值：先做不改 `contracts/haike_contracts` 的票；需要改契约的集中成一张票（沿用 D-L3-16），一次 `make contracts`。

## 2. 全量归类

| 类别 | 条目 |
| --- | --- |
| 现在就做（本分支） | T1 执行结果不明 / 中断；T2 已批准后客户改诉求被丢弃；T3 情绪策略接线；T4 人工台补显示；T5 图片签名跨品类写入症状；T6 已知信息表（不改契约的部分） |
| 可做但本分支只规划 | T7 上传即识别凭证；T8 契约批次（观察建议项、补偿评估项、回电选项）；T9 指标补齐 |
| 按建议方案可做，最好先确认 | 带问题读图（D2）；回复前行动风险检查（依赖 T6）；知识缺口模拟与计划按品类拆包 |
| 等决策 | 多事项与客户侧多事项进度（D1 / D4 / D6）；召回（D4）；AI 复核（D3）；邮件渠道（D5） |
| 等外部 | ≥20 张真实故障照片；非 US 保修政策；真实业务系统接口 |

## 3. 本分支票据

每张票：先完整读目标文件 → 写失败测试 → 实现 → 只跑相关测试文件 → `make lint` → 记 progress.md。不跑全量 pytest，不提交（用户要求再提交）。

### T1 执行结果不明与执行中断（方案六·异常表最后一行）　D 依赖：无　契约：无

问题：`ExecutionBusy("执行状态需人工核实")` 被路由到 `commit_issue`（`sessions/l3.py:427-429`），案件卡在 `executing` 且不能手工结案；超时后重试直接再调 `create_service_order`（`actions/store.py:44-52`），不先查原单。模拟后端的故障注入发生在建单之前（`backends/mock.py` `FaultInjection.check`），所以现在的「超时」一定是「没建成」，测不到「建成了但回执丢了」。

- **T1a**：`ExecutionBusy` → 案件 `executing → awaiting_approval`（`cases/service.py` TRANSITIONS 已允许），路由 `await_human`，告知客户已交人工核实。测试放 `tests/test_conversation_l3.py` 重试用例旁。
- **T1b**：先查原单再决定。
  - 协议（`backends/protocol.py`，非契约）：`ServiceOrderRequest` 增加 `client_ref`（取执行幂等键）；`BackendClient` 增加 `find_service_order(client_ref) -> ServiceOrder | None`。这是给真实业务系统预留的形状：幂等键由调用方给，查询按调用方键，不依赖模拟后端的 `uuid5(order_no:type)`。
  - 模拟后端：Memory / Postgres 两个实现都记录 `client_ref` 并实现查询；新增故障模式 `created_then_timeout`（先建单再抛超时）。Postgres 表 `service_orders_mock` 是否需要加列在实现时核实，需要则加迁移 0008。
  - 执行器：写操作超时记为结果不明（错误码区分 `outcome_unknown`）；再次执行同一幂等键前先 `find_service_order`：查到 → 按成功回放；确认不存在 → 按原幂等键重建；查询本身失败 → 交人工。
  - 测试：`tests/test_l3_backends_actions.py`（执行器与幂等）+ `tests/test_conversation_l3.py`（图内重试）。

### T2 已批准 / 待审批时客户改诉求被丢弃（方案六·异常表第 5 行）　D 依赖：无　契约：无

问题（改动图 B1）：案件处于 `approved` 时客户发改诉求消息，`propose` 守卫（`sessions/l3.py:234-245`）只回「案件正在等待处理」；待确认的方案卡仍然有效，客户仍可确认，授权门接受 `approved`（`actions/gate.py:57-58`），原换货照常执行。

- 在 `propose` 守卫处：状态为 `approved` / `awaiting_approval` 且本轮是改诉求（换货 / 退款 / 改地址）时，案件转 `awaiting_approval` 并记录变更；作废待确认方案卡（沿用 `l3.py:792-796` 的 pending_changed 作废模式与 `inactive_case_state`）；告知客户已暂停原方案、交人工重新审核。
- 已有的「人工改方案 → 重新请客户确认」路径（`l3.py:858-880`）承接重审。
- 地址字段本身不在本票（仓库没有收货地址字段，属于 T8 之后）。
- 测试：`tests/test_conversation_l3.py`。

### T3 情绪策略接线（方案五）　D 依赖：无　契约：无

- YAML 策略文案生效：`prompts/system.py` `emotion_layer` 全部读 `config/emotion_policy.yaml`，删掉写死的 `EMOTION_LAYERS`（含「承诺尽快解决」）；升 `PROMPT_VERSION`；改 `tests/test_intake.py:96,106` 的断言。
- `offer_human`：命中时在 `conversation/reply.py` `acknowledge_current_turn` 末尾追加一句固定文案（不触发 R3，不宣称已转接）。
- `skip_optional_clarify`：命中时跳过可选的型号卡（`sessions/clarify.py:311-316` 已有的跳过条件处）。
- `flag_complaint_risk`：案件高优先级改为按动作判断（现在只按 `level == complaint_risk`，漏掉 `angry + rising` 规则）。
- 看板：`frontend/src/admin/pages/Board.tsx` 过滤 `'(未识别)'` 与后端 `'(未知)'` 不一致导致无情绪会话被算作非平静；说明文字「首轮情绪」改为「最近一轮」。
- `suggest_compensation_review` 不在本票：`ProposalOption.source` 只允许 policy / human，诚实的第三种来源要改契约，放 T8。

### T4 人工台补显示（方案八）　D 依赖：无　契约：无

- `await_human` 生成交接摘要（`escalation/summary.py` `build_summary`，不调模型），作为案件事件存储（仿 `cases/service.py` `record_commitment`），不向客户发 `escalation_summary` 事件。
- `GET /cases/{id}`（`admin/l3_router.py:58-84`）把摘要取出返回；`frontend/src/admin/l3.ts` 手写类型补字段。
- `CaseDetail.tsx` 渲染：交接摘要（问题、已做步骤、推荐方案、建议回复）、执行记录、承诺记录、事件时间线。
- `ProposalCard.tsx` 条款显示 `source_url` 链接。
- 新增 `frontend/src/admin/__tests__/` 下 CaseDetail 测试（现在没有）。

### T5 图片签名跨品类写入症状（疑似 bug）　D 依赖：无　契约：无

改动图发现 `sessions/graph.py:519-522` 收集签名对应计划的症状码时不按品类过滤：扫地机照片的（充电触点, 污渍）会命中耳机计划 `eb_charging_contacts`，把 `eb_charging_failure` 写进扫地机事项。先写测试复现，确认后按当前品类过滤。

### T6 已知信息表（不改契约的部分）（方案二、三、五）　D 依赖：无　契约：无

新模块 `orchestrator/app/diagnose/known.py`（不放 `conversation/`，避免 `history.py:55` 记录的循环导入）。

- **L2 铭牌读数作候选**：`clarify.decide` 在无确认、文字无候选时查 `visual_product.model_hint`，生成候选并走产品卡，用 `note` 说明「照片铭牌读到 X，请确认」。`prepare_card` 必须设 `allow_unknown=True` 与 `payload.category`（否则 `graph.py:808` KeyError）。不得把读数送进 `_lookup`（单命中会自动确认）。
- **L3 口述「已经做过」**：新增 issue 字段 `claimed_steps`，只记录不当作执行；下一步选中被声称做过的步骤时，改为在消息里确认「您提到已经……，结果如何？」，仍用步骤卡承接反馈。绝不写入 `step_attempts` / `steps_executed`。步骤与口述的匹配方式在实现前再定（计划步骤加 `phrases` 做确定性匹配，或把候选步骤给解释器），先写测试钉住行为。
- **L4 口述购买日期**：`interpret.py:56` context_field 加 `purchase_date`，`business.py:177` 放行；只用于凭证卡预填（OCR 为空时）。不进 `l3.py:21` `CONTEXT_FIELDS`（它喂 `PolicyInput`，口述日期不是凭证）。
- **L1 照片回答观察题：本票不做**。内容先有问题：`dock_contacts` 选项是 `clean` / `dirty_cleaned`，照片能看出脏，看不出「已清洁」。需要拆选项（计划版本升级）并给观察卡加 `suggested_option_id`（契约），放 T8。陷阱记录：图片结果不能写成观察事实，`active_observation_facts` 会把任何带 `observation_id` 的事实当成已知而跳过提问。

## 4. 只规划不开发

### T7 上传即识别凭证（方案二·嵌入表第 4 行）
阻塞点：凭证截图按故障照片上传会先被像素门控判 `too_bright` 拒绝（合成凭证 clipped=0.79 > 0.5）；确认凭证后流程固定进升级（`graph.py:771,792`）；一轮 25 s 预算下读图 + OCR 接近上限；需要改两个测试（`test_sessions_receipt.py:179`、`Composer.test.tsx:102`）；OCR 补 SKU 要改 `ReceiptFields`（契约）。方案：视觉输出加 `image_kind`，像素门控按用途放行截图，凭证结果以「未确认」来源存放、后续预填。

### T8 契约批次
观察卡 `suggested_option_id`（配合 L1 与 `dock_contacts` 拆选项）；补偿评估项的来源值；等人工时的回电 / 消息跟进选择卡（PendingKind、ActionKind、事件、时间线项）。一次 `make contracts`。

### T9 指标补齐
人工处理时长（从案件事件与决定时间 SQL 计算，无需迁移）；重复索取、重复步骤次数（`session_facts` 加列，迁移 0008）；情绪轨迹入库。

## 5. 顺序

T1a → T1b → T2 → T3 → T4 → T5 → T6（L2 → L4 → L3）。T1、T2 属执行域正确性，改动面最小；T6 面最大放最后。
