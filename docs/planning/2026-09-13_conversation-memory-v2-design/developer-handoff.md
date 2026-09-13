# 开发交接契约

> 2026-09-13 最新实施取舍见 [step-back.md](step-back.md)。本文的数据一致性规则仍作参考，但不再要求为旧协议、旧录制包或旧流程断言增加兼容实现。

2026-09-13。本文补齐实现时必须一致的执行规则；均为待实现设计，不代表业务测试已通过。领域字段以 [data-contracts.md](data-contracts.md) 为准，任务与验收分别见 [implementation-plan.md](implementation-plan.md)、[acceptance.md](acceptance.md)。

## 1. 先做的最小闭环

先用固定理解结果打通：创建会话 → 收到问题 → 出步骤卡 → 问“为什么” → 原卡仍有效 → 反馈无效 → 刷新。随后在接收、业务提交、事件持久化三个位置注入故障，验证无重复输入/反馈。此闭环通过后再接真实模型、诊断和长历史摘要。

保留现有产品目录、知识适配、排查计划、凭证核对和 ModelRouter。新增领域模块各自以一个接口承担实际职责，不引入通用事件总线、工具 Agent、Mem0、web 搜索或另一套知识存储。本次不顺便开启检索增强开关。

## 2. 单轮提交和恢复

### 稳定标识与版本

| 标识 | 生成/使用规则 |
| --- | --- |
| input_id | 消息由客户端生成；动作规范化为 action_id。ID 相同且 kind/业务载荷不同即冲突。 |
| run_id | reserve_input 首次成功时生成并绑定 input_id；重发返回原 run。 |
| entity/patch/effect ID | 服务端以 session_id + input_id + 类型 + 稳定操作序号派生；模型只引用已给出的 ID，不生成数据库主键。 |
| event_id | effect_id + phase 派生；文本 delta 另加 message_id + chunk_index。UNIQUE(session_id,event_id)，相同 ID 不同载荷是内部一致性错误。 |
| version | sessions 的已发布业务版本，首次 0，每个 run 首次发布 commit_turn 时 +1；无事实变化的解释也发布一次。 |
| checkpoint_id | 内部不可变状态位置；checkpoint step、交付重试均不作为公开版本。 |
| seq | 存储层在会话短锁/同一事务中分配，包含内部事件，公开流允许间隔。 |

修订原“version=checkpoint step+1”：V2 有候选工作状态与输出恢复，若仍取最新 step，未发布候选、输出重试会改变客户端版本。显式发布版本使开发者只需遵循一个 compare-and-swap 条件。

### 执行次序

```text
reserve_input（一个事务）
  sessions.active_run_id + session_inputs + 图片正式行
  run_started + input_received
        |
        v
TurnSnapshot = base_checkpoint_id + events <= input_event_seq
        |
        v
interpret -> validate -> reduce 候选 -> policy -> 按需业务模块
        |                   turn_work：尚未对外发布
        v
commit_turn checkpoint
  issues/facts/pending/risks + last_applied_input_id
  committed_version=base_version+1 + pending_effects/AnswerSpec
        |
        v
publish_commit（一个事务、幂等）
  验证 active_run_id/base_version/input_id
  sessions.version/published_checkpoint_id/last_state_commit_seq
  state_committed + session_inputs.state_commit_version
        |
        v
持久化卡片/状态事件 -> 生成回答 -> delta 先落库后发送
        |
        v
最后的收尾事务：done + 输入终态 + 释放 active_run_id
```

- `reserve_input()`/`publish_commit()`/`append_event_once()`/`finish_input()` 接收事务 conn 或自行完整拥有事务；router 不拼接几次各自提交的方法来冒充原子操作。
- LangGraph 中间节点只更新 turn_work；commit_turn 才更新权威领域字段。TurnSnapshot 从账本的 base_checkpoint_id 取输入前状态，不能取另一次运行的最新 checkpoint。
- 卡片和摘要 effect 的正文/稳定 ID 在 commit_turn 中固定；摘要润色若启用，应在提交前完成或失败后保留确定性正文。恢复重发同一 revision，不再生成不同正文占用同一 card_id。
- 模块得到 IssueExecutionView，只返回产品/症状/图像观察/当前证据/计划/反馈等白名单候选；校验 input_id、issue_id、device_ref_id、basis revision 后再提交。迟到结果只作归档，不能直接更新当前 issue。
- 同一部署首期一个活动 RunManager 所有者；现有 subscribe/cancel 依赖进程内 handle。CM-11 明确单 worker，重启恢复在开放入口前完成；水平扩容与跨进程任务接管不属于本次。短数据库锁仍覆盖请求/快照/清理；锁内不得调用模型或等待 cancel 完成。
- 已提交状态到发布完成之间，接收和快照先对账；对账失败返回 503 recovering，不返回混合版本快照。数据库不可用时保持 active run 占位，恢复完成前不接收下一轮。
- 高危预检可以在 commit_turn 前发固定条件性提示，但不能发可执行排障步骤。未完成 run 的危险候选来源保留在输入事件；下一轮 policy 重新检查尚未裁定的候选，取消回复不等于解除风险。

### 故障点决策表

| 故障时刻 | 恢复动作 | 业务状态 |
| --- | --- | --- |
| reserve_input 事务未提交 | 回滚；同 ID 可重新接收 | 无输入/图片/运行残留 |
| 已接收，未有 commit_turn | 不重调模型自动重跑；补齐 aborted/error/done，释放运行 | 回到 base_checkpoint；原始输入保留并标处理失败 |
| commit_turn 已存，publish_commit 未完成 | 按 checkpoint 幂等发布，再交付确定性 effect | patch/反馈只应用一次 |
| effect 已落库，客户端没收到 | 按原 event_id/seq 重放，不新增事件 | version 不变 |
| 文字未开始或只有部分 delta | 重启时不调用模型续写；已有半句标 aborted，输出确定性中断说明 | 保留已提交事实/pending；done(error) |
| message_end(completed) 已存，done 未存 | 补齐剩余确定性 effect 与 done | 完整回答不改成 aborted |
| 用户取消 | commit_turn 前按未提交处理；之后保留已提交状态，停止未完成生成 | done(cancelled)，pending 由已提交状态决定 |

一次 run 只有一个终态 done。pending_effects 在下一轮已对账后可压缩；已交付判据是事件唯一键，不额外维护一份可漂移的 delivered 状态。失败/取消的同 ID 仅重放结果；用户继续会话使用新 input_id，并基于最新快照继续，避免自动重计已提交反馈。

## 3. HTTP、事件与快照

### 输入和冲突

`reserve_input(request) -> accepted | replay | conflict`；accepted/replay 沿用 SSE 响应，不另增成功 JSON 接口。已完成重放允许返回已结束 run 的原事件。

| 情况 | 响应 / 客户端行为 |
| --- | --- |
| 相同 ID + 相同载荷 | 订阅/重放原 run，忽略本次 expected_version；不重复乐观用户气泡 |
| 同 ID 不同载荷 | 409 input_id_conflict；保留草稿，不自动替用户换 ID 重发 |
| 新 ID + 旧 version | 409 stale_version + snapshot；刷新后可用原 ID重试尚未接收的相同内容 |
| 卡片/token/issue 不匹配 | 409 stale_card / wrong_issue；刷新并提示卡片已变化，不自动消费新卡 |
| 新普通输入遇 active run | 409 run_active；不入账、不清草稿 |
| request_human 遇 active run | 先查幂等；显式目标 issue 校验后，锁外取消并等待。未结束返回 409 run_active，尚未接收的新 ID可稍后重试；结束后重新加锁复查并接收 |
| 输入/附件/枚举格式非法 | 422/现有图片拒绝码；无账本行 |
| 已删除/到期 | 404 not_found；仅清当前无效会话引用与对应最近列表项 |
| 发布恢复未完成 | 503 recovering；稍后读快照，不新开第二个 run |

request_human 是唯一允许忽略 stale version 的新业务命令，但必须携带明确 target_issue_id；没有任何 issue 时才允许为空并由服务端建草稿。它不能因 active issue 已变而转接另一设备。其余卡片动作必填 target_issue_id；普通文本省略时以接收快照的 active issue 为默认，语义解释仍可识别 new/resume。

V2 移除仅为旧 guide 路由服务的外部 rediagnose 动作，统一用 /messages 表达补充/纠正；new_issue/resume_issue 作为显式 UI 动作。自然语言转换的内部命令复用原 input_id，不再向 /actions 发第二个请求或产生第二条用户输入。

new_issue 的 target_issue_id=null、payload={}，创建无设备结论的 draft；resume_issue 的 target_issue_id 必填、payload={}，只接受本会话已有 issue。两者不带 card/token；select_product/step_feedback/confirm_receipt/skip_receipt 均带目标 issue/card/token。空消息只允许附带实际图片；既无文字也无图片返回 422。已有 4000 字符和图片大小/MIME 限制继续由入口验证。

### 最小公开事件增量

| type | 额外业务字段 | 前端用途 |
| --- | --- | --- |
| input_received | input_id、kind、text 或动作 payload、image refs、received_at、target_issue_id | 以 input_id 替换乐观条目；保留原始意图目标 |
| issue_changed | active_issue_id、issues 简表、input_id、resolved_issue_id、version | 反映实际归属与切换；不修改原输入事件 |
| pending_changed | issue_id、pending_id、status、reason、superseded_by、version | 禁用/挂起/消费旧卡，避免仅靠新卡出现来猜状态 |
| awaiting_input | 原 kind/card_id/version + input_token、issue_id | active issue 的可操作待办，解释后可重复声明同一卡 |
| summary_updated | issue_id、summary_id、revision、card_id、previous_card_id、source_through_seq、updated_at | 新摘要正文仍随 escalation_summary；更新旧卡提示和最新摘要投影 |

每个公开事件仍有 event_id/seq/run_id/recorded_at。card/message_start 补 issue_id，message_start 补 reply_to_input_id；stage 沿用 contracts/common.py 的八阶段（含 out_of_scope），不塞新 intent 枚举。解释阶段以 progress.substage 表达。done.version 必须等于已发布业务版本，不能取最后一次技术 checkpoint step。

公开 ServerEvent 与 StoredInternalEvent 分别用判别联合校验；state_committed/私有工具原始结果只进入内部联合。订阅、fixtures、管理员读取均显式处理 visibility，公开事件过滤发生在发送前。SSE 的 `id:` 继续使用 seq，不改为 UUID event_id。

### 一致快照与续接

1. 在会话短锁下先完成必要发布对账；同一数据库读事务读取 sessions 的已发布 checkpoint 指针、version、active_run 和事件水位 Q。
2. 读取该精确 checkpoint 和 `seq <= Q` 的事件，折叠 timeline/pending/latest_summaries；只在删除不能并发破坏读取的情况下释放锁。流式写入只被短暂阻挡，不等待整个 run。
3. 返回 last_event_seq=Q；即使 Q 对应内部事件也可作为水位。历史快照是对指定 Q 的事实视图，不能混入未来归属、卡片反馈或摘要 revision。
4. 客户端原子替换快照后，以 after_seq=Q 续接 active run；服务端先登记订阅再读历史，客户端忽略 seq<=Q 的事件。沿用一个恢复分支，替换当前“快照无水位、从 0 重放”的逻辑。
5. 本地同时切换会话/请求恢复时沿用 AbortController 世代校验，过期响应不能覆盖新会话。流式半句在 snapshot 保留 streaming + 已收到文本，续接只追加 Q 之后的 delta。

## 4. pending、问题与设备

每个 issue 最多一个非终态 pending；只有 active issue 的 pending 可操作。`created_seq` 是创建待办的输入来源序号，卡片实际显示顺序取其公开事件 first_seq，避免在 checkpoint 中预猜事件 seq。

| 输入/变化 | pending 处理 | 计数/后续 |
| --- | --- | --- |
| 解释/历史/偏好 | 保持 ID、card_id、token、payload | 不计步骤；仅公开 version 前进 |
| 对唯一 pending 的有效回答 | consumed，清当前 pending；保留事件引用 | 共用卡片命令验证；反馈枚举 solved/not_solved/cannot_do |
| 补充但不改变适用依据 | 保留 | 不仅因 issue_revision 增加就作废 |
| 产品/设备/计划依据改变 | invalidated，原因持久化 | 旧执行历史保留，新计划新卡；原 token 永不复用 |
| 切到其他 issue | suspended，旧 UI 卡禁用 | 旧 issue 的症状/步骤/计数保留 |
| 返回旧 issue | 核对 basis_refs 和风险，创建替代 pending/card/token，旧者 invalidated | 继续同一步，重新展示不增加 executed；依据失效则重新诊断 |
| 请求人工或新增风险阻止操作 | 操作步骤卡 invalidated；按业务需要创建凭证 pending | 历史/解释仍可进行，禁止继续点击旧步骤 |

事实纠正保持同一 DeviceRef，除非用户明确说另一台设备；纠正型号不等于解除设备风险。新 issue 若最终确认仍为同设备同未解决故障，服务端恢复原 issue 账本；模型不能自行决定归零计数。跨 issue 修改只限服务端校验过的目标；一轮多个设备同时要求执行时，先明确本轮活动目标，其余诉求保留原始输入，不并发给两台设备下步骤。

风险预检只产生候选，语义确认和保守策略决定 reported/disputed；已争议的安全来源仍带操作限制。cleared_by_policy 本期没有用户文本可直接触发的入口，保留状态定义供后续可靠核实。

## 5. 语义候选到内部命令

类型落在 `app/conversation/types.py`（新增），Pydantic extra=forbid；StateReducer 只接 ValidatedPatch。模型输入带候选 issue/device/fact/pending IDs 与可引用 source IDs。

| 候选字段 | 最小契约 |
| --- | --- |
| primary_intent / secondary_intents | 使用 design.md §5 枚举；主意图决定回答重点，不能覆盖其他明确事实增量 |
| issue_relation | same/new/resume/ambiguous；target_refs 引用 issue/device/fact/entry 或 null，新实体 ID 由服务端生成 |
| fact_candidates | operation(add/retract/replace)、kind、value、target_fact_id?、source_entry_ids、原文支撑片段；retract/replace 必须有唯一目标 |
| feedback_candidate | pending_id、feedback(solved/not_solved/cannot_do)、source_entry_ids；“做过了”无效果时为空并澄清 |
| pending_answer | pending_id、command_kind、候选 payload、source_entry_ids；选择型号/确认凭证共用动作白名单验证 |
| history_request | mode(recent/first/reference/time_range)、source_entry_ids、issue_ids、time_expression；只能检索本会话截至本轮输入的记录 |
| emotion / session_preferences | emotion 使用现有三级及代码映射策略；偏好首期仅 detail_level=brief/normal/detailed，不能修改风险或知识来源限制 |

混合输入按固定顺序处理：解析目标 → 校验纠正 → 合并独立新事实 → 判定旧 pending 是否仍适用 → 校验明确反馈/请求 → 风险 policy → 选择业务路径 → 回答主问题。若“型号改成 X10，刚才那步没用”，型号可修正，但旧型号步骤反馈不自动用于新计划；说明关联不明并澄清。独立且目标明确的事实可提交，歧义操作保留待确认，不能把整轮所有字段清空。

所有自然语言阶段只调用一次常规 intake 任务，任务输出升级到本 schema；trace 可用 operation=intake.turn，task 仍为注册的 intake。现有 extract_intake/extract_rediagnose 不能再各调用一次。JSON 校验/引用白名单失败进入明确降级，保留有效事实/pending；Router 自身已有的 schema 重试须计入该调用总预算。

history_request 由 HistoryReader 在解释后补取原文，再给回答任务；不为回查重新跑一遍 intake。仅依赖 seq、entry ID、issue、时间范围与分页；不新增历史向量库。查不到或超过预算时明确询问范围，不让模型凭摘要编造原句。

## 6. ContextBuilder 与知识引用

### 输入输出

`build(task, snapshot, budget, history_selection, evidence_refs) -> ContextBundle`。Builder 不调用模型、不改变状态；HistoryReader/EvidenceReader 负责先取所需数据并注入。输出包括 messages、required_source_ids、selected_entry_ids、selected_evidence_ids、omitted_ids/reasons、token_estimate、through_seq、context_revision、issue_revision、policy_version。

一期继续复用已有任务名，消费视图明确如下：

| 任务 | 必须看到的上下文 | 知识输入 |
| --- | --- | --- |
| intake | 最近问答/按钮与卡片内容、产品/症状、当前 pending、纠正候选、时间 | 默认无 RAG 正文，操作指代可带当前步骤原文 |
| reply.stream（历史/解释/普通回答） | 主意图、实际上一轮问答、当前问题、有效事实与风险、必要原文 | 本轮相关片段；解释旧答案可读取旧依据但标历史版本 |
| diagnose.synthesize | 当前有效症状、观察、已做且失败的步骤、产品与允许计划 | 当前 issue 的有效证据，不把所有历史片段传入 |
| guide.step | 当前待下发步骤、来源原文、前一步反馈、风险/情绪 | 只带该步骤的必要依据，沿用不能新增动作约束 |
| escalate.summary | 当前 issue 的有效事实、执行结果、凭证与真实 handoff | 主要是结构化事实及来源 ID，生成器不得根据旧助手猜测补事实 |
| vision / receipt OCR | 当前图片与明确任务、产品/主体引用 | 不塞无关问答和历史凭证；事实关联由服务端验证 |

最近 6 回合定义为最近 6 个已接收 input（消息或按钮）及其关联的已实际输出；当前 input 单独加入一次。问答保留 Human/AI 角色；按钮、卡片、历史工具记录是带标签的数据段，不伪造孤立 ToolMessage 或助手已执行动作。取消/替换片段仅在被引用时带状态进入；主备替换的旧段不作为有效操作。

高权限 system 只放静态政策/任务约束。产品名、用户症状、旧问答、摘要、OCR、RAG、动态时区说明均放有来源的数据段；不能继续把用户可控字符串直接插入 compose_system_prompt 的 system 状态层。

### 知识 ID 与正文

`EvidenceRef`：evidence_id、source_event_seq、issue_id、device_ref_id、product_basis_revision、doc_id、doc_version、chunk_id、source、retrieved_by_input_id、status(current/historical/invalidated)。引用传递不新增知识数据库；短原文继续存原始 evidence 事件，必要时按现有知识适配模块读取。

- 图状态和计划可只带引用，调用模型时必须解析为“ID + 来源/适用范围 + 必要短原文”；只传 ID 不能提供模型未见过的知识内容。
- 新诊断以当轮检索选中集替换 current_evidence_ids，旧来源仍可供历史回顾；不得像当前 reply() 一样取累计 evidence 的前六条。
- 无新检索的解释/步骤反馈可复用当前计划的有效引用；型号、设备或知识版本变化后先重新验证，不能沿用旧适用范围。
- RAG 不追加进永久聊天 messages；按本次任务临时装配。初始沿用诊断每条 300 字/父块 800 字、回复最多 6 条的上界，总预算优先；不得截断关键否定、条件、步骤和警示，片段不足则取完整必要段或停止给操作。
- 历史解释优先用当时持久化的 snippet；版本原文已不可取时注明依据缺失，不能拿最新版冒充当时版本。图片过期只引用已有观察，receipt 不进入一般知识检索。
- AnswerSpec 的引用选择由代码验证：ID 必须在该任务允许集合；历史助手答案、摘要、model_hypothesis 不自动升级为操作依据。保留正常 SSE evidence/前端证据抽屉，不暴露内部全文。

### 预算和摘要

增加 `config/conversation.yaml`（开发时新增）：recent_turns=6、max_input_tokens=8000，另配置 token 估算裕量/历史分页上限；conversation_timezone 的配置只在 Settings 定义，避免两处默认值。每个实际候选模型需要在现有 ModelSpec 补可校验的 context_window；数值按提供商资料核对，不能把所有模型硬写成同一个窗口。

先按本任务主备可用链的共同上界装配同一必要集合；ModelRouter 在 `_prepare()` 增补结构化 schema、重试错误提示之后及 stream 每个备用调用前再计预算。只裁可选历史/重复证据；必要集合放不下则跳过该模型，所有候选均放不下时受限回应。回退提示与原提示必须保留同一 required_source_ids；相关接口改造和测试归 CM-03/09，而非只改 Prompt 模板。

当前 HTTP 文本上限是 4000 字符，V2 保留该接收上限；A23 的超长输入拆成“超限返回 422”与“合法长输入 + 多轮超预算”两种。总 run deadline 首期沿用运行配置，预算含等待、主备重试、取历史、检索和输出，不能把各模型 budget 简单相加。

摘要只压缩已结束回合，首次没有缓存时用近期历史/结构化状态，不在主路径额外等待摘要模型。每会话最多一个摘要任务；记录 source IDs/through_seq/context_revision。新消息仅追加且旧来源仍有效可保留缓存；纠正/归属变化使来源失效则 CAS 拒绝旧结果。历史 as-of 查询直接读截至 Q 的原文及业务提交位置，不能用 Q 之后生成的摘要替换当时视图。

后台提交摘要需要与删除共用会话锁并在事务内验证会话存在、未到期、来源 revision；摘要 expires_at 不得晚于来源会话，写派生缓存不能更新 sessions.updated_at 来续命。会话引用已删除时放弃写入，后台任务不得新建 sessions。

## 7. 前端与生成契约的修改落点

- `Composer.tsx`、`useSession.ts`、`App.tsx` 同步解除等待 select_product/confirm_receipt/upload_receipt 时对普通文本的限制。pending 不等于 busy，streaming/recovering 才阻止普通新请求；卡片操作仍校验最新 version/token。
- 输入凭证模式由实际附件决定：等待上传凭证时允许纯文字追问；等待确认时附图视为替换凭证候选，只有明确新凭证用途且通过业务验证才替换，普通故障图不能被自动 OCR 成订单。
- `useSession` 维护当前提交的 immutable draft/input_id；网络不确定时先查快照按 input_id 找已接收记录，未确认接收才允许同 ID 同内容重试。刷新后服务端历史仍是权威，首期不为保存二进制附件引入 IndexedDB；未接收且文件丢失时要求重新选图。
- timeline reducer 按 input_id/message_id/card_id 和 event_id/seq 幂等，suspended/invalidated 卡禁用；pending_changed、issue_changed、summary_updated 需覆盖 SSE 与刷新两个路径。
- 同版发布后遇 not_found，清 sessionStorage 的 haike.session_id 与 localStorage 的 haike.recent_sessions 对应项；保留其他有效最近会话。
- 契约先改 `contracts/haike_contracts/{actions,common,events,snapshot}.py`，再 `make contracts` 生成 Schema/TS/Zod；multipart 输入另定义 Pydantic 元数据 schema 与请求 fixture，避免表单字段只藏在 router 注解中。内部事件放应用内 typed schema，不导出到浏览器。

完成判据：A33～A44 的契约与实际入口测试可执行；所有新事件在 parse、存储、订阅、快照、前端、管理员/analytics、replay 中有明确处理或明确忽略理由。文档例子不替代真实契约 fixtures。
