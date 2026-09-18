# 独立观察题出卡（observation_card）

## 现状

计划级的判别问题（`plans.yaml` 的 `diagnostic_observations`）走的是纯文本问答，与步骤内观察题
（`TroubleshootStep.observations`）用同一份定义，却没有同一套 UI。

```
decide_next → kind="ask"            diagnose/decision.py:571
  question = {observation_id, question, options[{option_id,label,kind}], plan_id, attempt}
ask_observation                      sessions/graph.py:1011
  只发 message_start / message / message_end，不设 pending_card
  出边固定 ask_observation → commit_issue          sessions/graph.py:2759
前端                                  components/AssistantBubble.tsx
  普通助手气泡，Markdown 渲染
```

四个后果：

1. 没有可点选项。同一个 `pb_737_display` 定义挂在步骤上时，前端是有单选的
   （`components/StepCard.tsx:73`）。
2. 文案把问题、5 个选项、兜底说明拼成一个段落，用 `／` 分隔（`sessions/graph.py:1008`）：

   ```python
   return f"{question['question']}请直接回复其中一项：{labels}。这个结果会决定后续排查路径。"
   ```

   单段落无换行，`kind=unknown` 的兜底项（「设备不在身边或无法判断」）和 4 个 finding 选项
   混在同一行，用户分不出哪个是「我答不上来」。
3. 答案只能靠字面匹配 `match_reply`（`diagnose/observations.py:166`）：只接受唯一命中，
   回「2」「第二个」「就第一种」都匹配不上。`spec_observation_deadlock_20260918.md` 的「未做」
   里已经记过一条同源缺陷：unknown 选项的标签本身不参与匹配。
4. 匹配失败的代价不是重问一次。`MAX_OBSERVATION_ASKS = 2`（`diagnose/decision.py:373`），
   两轮没解析出来就把该观察记进 `unavailable`（`diagnose/decision.py:545`），
   `requires_observations: pb_737_display` 的三个 A1289 计划永远解锁不了，只剩 handoff。

## 设计

出卡，并保留自由文本，两条路都通。

- 新 pending kind `answer_observation` + 事件 `observation_card` + 动作 `answer_observation`。
  卡片载荷就是 `next_action.question`，字段与契约 `StepObservation` 同形，不另造结构。
- 选项一击提交，照 `components/ProductCard.tsx` 的候选按钮组；不加二次确认的提交按钮，
  一张卡只有一个问题，两步是多余的。
- `kind=unknown` 的选项单独渲染为次级按钮，与现象选项在视觉与语义上都分开。
- 消息文本只留问题本身，不再罗列选项；排版交给卡片。没有卡片的 `operation_blocker` 分支文案不变。
- 输入框不禁用（`components/Composer.tsx:70` 的 `cardOnly` 恒为 false），自由文本与 `match_reply`
  原样保留；点选走 `option_id` 直达 `record_observations`，完全绕开字面匹配。
- 已回答的卡片折叠成一行，照 `components/StepCard.tsx:37` 的 `stepCollapsed`。

### 不变量

- 点选不消耗追问次数：`_asks_for` 数的是 `observation_requests` 条数，点选只把请求置 `answered`，
  不新增条目，`MAX_OBSERVATION_ASKS` 逻辑不动。
- 点 unknown 选项 = 现有文本命中 unknown 的语义：不写观察事实，只把请求置 `status="unknown"`，
  `decide_next` 不再追问该观察。必须在后端显式处理，否则点了没有任何效果。
- 用户改用文本回答同一个问题时，`_accept_observation_reply` 写完事实后要作废这张卡：
  `pending_card=None` + `pending_changed(status="consumed", reason="answered_in_text")`，
  否则卡片挂着一个已经答过的问题。
- 选项只接受本卡声明过的 `observation_id` / `option_id`，与 `_apply_step_feedback` 的
  `declared` 校验同口径；越界选项在路由层返回 409 `invalid_selection`。

## 契约变更

改 Pydantic 模型后跑 `make contracts`，`contracts/schema/*.json`、
`frontend/src/types/{events,actions,snapshot}.ts`、`frontend/src/api/events-schema.ts`
的 diff 随改动一并提交。

| 文件 | 改动 |
| --- | --- |
| `contracts/haike_contracts/common.py` | `PendingKind` 增加 `answer_observation`；`StepObservation` / `ObservationOption` / `ObservationAnswer` 复用 |
| `contracts/haike_contracts/events.py` | 新增 `ObservationCard(_Card)`：`observation: StepObservation`、`plan_id: str`、`attempt: int`；并入 `ServerEvent` |
| `contracts/haike_contracts/actions.py` | `ActionKind` 增加 `answer_observation`；`AnswerObservationPayload{observation_id, option_id}`；`AnswerObservationAction(_CardAction)`；并入 `ActionRequest` |
| `contracts/haike_contracts/snapshot.py` | 新增 `ObservationCardItem`（卡片字段 + `chosen_option_id: str \| None`）；并入 `TimelineItem` |

## 后端变更

| 文件 | 改动 |
| --- | --- |
| `app/sessions/graph.py:1011` `ask_observation` | 非 blocker 分支设 `pending_card={kind:"answer_observation", card_id, payload:{observation, plan_id, attempt}}`；`card_id` 由 `stable_id(input_id, "observation", observation_id)` 派生 |
| `app/sessions/graph.py:2759` | 固定边改条件边：有 `pending_card` → `await_input`，否则 → `commit_issue` |
| `app/sessions/graph.py:628` `await_input` | 增加 `answer_observation` 分支，发 `observation_card` 事件 |
| `app/sessions/graph.py:684` `apply_action` | 新分支：校验选项属于本卡 → finding 走 `record_observations(source_kind="observation_card", binding={card_id, plan_id, observation_id})`，unknown 只改请求状态 → 两者都把对应 `observation_requests` 项收口 → `_apply_next_action` 重新决策 |
| `app/sessions/graph.py:1003` `observation_question_text` | 出卡时只返回问题句；attempt≥2 的换措辞文案留给无卡分支 |
| `app/sessions/router.py:187` | `_CARD_KINDS` 增加 `answer_observation`；照 `confirm_proposal` 那行加 `option_id` 白名单校验 |
| `app/sessions/snapshot.py:176` | `observation_card` 并入通用卡片分支；`card_results` 提供 `chosen_option_id` |
| `app/conversation/reduce.py:539` `_accept_observation_reply` | 文本答中时作废对应的 `pending_card`，追加 `pending_changes` |

`route_after_apply` 不用改：`apply_action` 写完事实后由 `_apply_next_action` 落 `_verify`，
既有的 `next / ask / done / escalate` 分支照常分流。

## 前端变更

| 文件 | 改动 |
| --- | --- |
| `src/components/ObservationCard.tsx` | 新增。问题 + finding 选项按钮组 + unknown 次级按钮；已选后 disabled 并显示所选项；折叠态一行 |
| `src/components/Timeline.tsx` | 增加 `observation_card` case；`onAction` 联合类型加 `answer_observation` |
| `src/state/reducer.ts:114` | 事件 → timeline item，`chosen_option_id: null` |
| `src/App.tsx:18` | `AWAITING_TEXT` 增加 `answer_observation: '选一项就行，也可以直接打字描述'` |
| `src/components/Composer.tsx:27` | `answer_observation` 沿用 `REDIAGNOSE_HINT` 一类的提示，明确说明仍可自由输入 |

## 测试

后端（`cd orchestrator && uv run pytest -q tests/...`）：

- `tests/test_diagnostic_next_action.py`：`kind="ask"` 时发出 `observation_card` 且 `pending_input.kind`
  为 `answer_observation`。
- `tests/test_conversation_observation_deadlock.py`：点选 finding → 写出观察事实 → 下一动作是
  `pb_737_laptop_uvp` 的步骤；点选 unknown → 不写事实、请求置 unknown、不再追问；
  越界 `option_id` → 409 `invalid_selection`；文本先答 → 卡片作废；
  既有的纯文本补答用例必须仍通过。

前端：

- `src/components/ObservationCard.test.tsx`：finding 与 unknown 分别提交的载荷；非活动卡不可点；
  已答折叠。
- `src/components/Cards.test.tsx`：timeline 渲染新卡。

提交前 `make lint`、`npm --prefix frontend run typecheck`、`make contracts-check`。

## 不做

- 问诊 yes/no（`app/sessions/clarify.py`）不卡片化，范围不同。
- `match_reply` 对 unknown 选项标签的匹配缺陷不在本次修（出卡后该路径不再是唯一入口，
  但纯文本用户仍受影响）。
- 观察题与已知现象的相关性（`spec_observation_deadlock_20260918.md` 未做项第 2 条）不在本次范围。

## 实施记录

按上表实施完毕，另有三处规格未列出但必须同改的地方：

- 协议样本与漂移测试：`contracts/tests/samples.py`（observation_card 事件、answer_observation 动作各一正一负）、
  `contracts/tests/test_events.py`（26 种事件）、`test_actions.py`（13 种动作）、`test_export.py`（判别器映射计数）、
  `contracts/fixtures/events.valid.json`（前后端共读，新增第 20 条）、`frontend/src/api/events.test.ts`
  与 `frontend/src/state/reducer.test.ts` 的联合类型与计数。
- `copy`、`OPEN_OBSERVATION_STATUS`、`record_observations` 按仓库规范提到 `graph.py` 顶层导入，
  确认 `app.conversation.reduce` 不反向依赖 `app.sessions`，无循环。
- `orchestrator/tests/test_diagnostic_loop.py::test_missing_observation_is_asked_and_free_text_answer_reenters_the_loop`
  原先断言正文里含选项标签、且 `pending_card is None`——两条正是本次要改的行为，改判为
  「正文不含选项标签、选项在 observation_card 上、pending_card.kind == answer_observation」，
  并补断言文本作答后发出 `pending_changed(reason=answered_in_text)`。

验证：`make lint`、`make contracts-check`、`make contracts-test`（98 passed）、
`orchestrator` 全量 pytest（1092 passed, 1 skipped）、`npm --prefix frontend run typecheck`、
前端全量 vitest（222 passed）。

未做浏览器端到端验证：本机 orchestrator 跑在三小时前构建的 docker 镜像里，要看到新卡需要 `make up` 重建，
按仓库约定 docker 构建只在要求时跑。

## 预览走查发现的两处缺陷（已修）

1. **卡片排在提问消息之前**。`conversation/effects.py` 的 `PERSISTED` 决定哪些事件跟随状态提交一起发；
   `observation_card` 不在表里，于是走即时通道，seq 比随后落库的 message_start 还小
   （会话 b93a685：card=10、message_start=15）。同时 `emit` 里注入 `issue_id` 的卡片列表也漏了它，
   卡片的 issue_id 为 null。两处都补上 `observation_card`，新会话事件序为
   evidence → message_start/end → pending_changed → observation_card → awaiting_input。
   回归断言写在 `test_missing_observation_is_asked_and_free_text_answer_reenters_the_loop`。

2. **点选后看不到自己选了什么**。时间线的动作行取 `history.ACTION_LABELS`，没有 `answer_observation`
   就落到兜底文案「操作」。改为 `action_text(payload)`：判别问题按 `option_label` 渲染成
   「回答：屏幕显示异常或无法显示剩余电量」。`fold_history` 的卡片类型集合也补上 `observation_card`。

## 走查结果

会话 7eb1857（新构建）：一句话描述 737 故障 → 出判别卡；点「屏幕显示异常或无法显示剩余电量」→
时间线出现「回答：屏幕显示异常或无法显示剩余电量」，卡片折叠成一行带所选项 →
观察解锁 `pb_737_display_reset`，发出步骤卡「按 A1289 官方方法复位」。

## 走查暴露的既有缺陷（不在本次范围）

会话 1db3017 选「连接笔记本时显示 UVP」后直接转人工，原因不在本次改动：
`decision.py` 的观察解锁候选 `library.allowed_for(..., symptom_codes=codes)` 仍按症状码先过滤，
而 `pb_737_laptop_uvp` 的 symptom_codes 是 `[pb_no_output, pb_indicator_abnormal, pb_port_damage]`，
不含该会话的 `pb_no_input`。实测：

```
['pb_no_input']  -> ['pb_737_output_check', 'pb_737_display_reset']
['pb_no_output'] -> [..., 'pb_737_laptop_uvp']
```

观察门槛本身是满足的（`observation_gate({'pb_737_display': 'laptop_uvp'}) == ('ok', [])`）。
`docs/planning/2026-09-18-20_session-reversibility-review/findings.md` 已记录同一条，由该评审处理。

同一会话还暴露：问诊问题同样以纯文本列选项，用户回「1」被原样记成症状描述
（摘要里的 problem 字段就是「…；用户回答：1」）。属于 `clarify` / 问诊路径，与本卡片同源但另作。

## 追加：已满足的观察不再被症状码否决

原提的「解锁路径不用症状码过滤」没有采纳，理由是它把提问面一起放开了：`unlocked` 同时决定
哪些计划可执行、哪些观察题会被问（gate=missing 即 `pending_ask` 来源），而 `decision.py` 里
`ask` 先于 `pending_step` 返回。全放开之后，一个与本次现象无关、只是同品类同 SKU 的门槛计划，
会用它缺的那道题抢在可执行步骤前面提问，与 design §3.4「不能只因 taxonomy 里有这道题就强行补问」相悖。

真正错的只有一件事：问了又不用答案。改成一句规则——

> 观察门槛已满足的计划不受症状码否决；尚缺观察的计划仍要症状码支持。

`app/diagnose/decision.py` 的 `unlocked` 改为在 `allowed_for(category, sku)` 全集上筛选，
条件为 `p.plan_id in by_codes or p.observation_gate(option_ids)[0] == "ok"`，
`by_codes` 仍是原来的症状码过滤结果。不引入新概念：`observation_gate` 紧接着的循环本来就要调。

没有改 `config/plans.yaml`。全库 56 个计划里只有 3 个带 `requires_observations`，都是 A1289、
都挂在同一道 `pb_737_display` 上，只有 `pb_737_laptop_uvp` 少写 `pb_no_input`。补这个码能让该会话通，
但下一个漏写的计划会重现同样的死路——两处只该改规则那一处。

测试：`test_satisfied_observation_unlocks_a_plan_whose_symptom_codes_do_not_match`（把判据退回
`p.plan_id in by_codes` 时该用例失败）、`test_unmatched_codes_do_not_create_new_questions_while_the_observation_is_unknown`
（守住提问面不被放开）。全量 pytest 1094 passed, 1 skipped。

走查（会话 6965a9c）：「我的 Anker 737 充电宝出问题了，充不进电」→ 判别卡 →
点「连接笔记本时显示 UVP」→ 时间线「回答：连接笔记本时显示 UVP」→
步骤卡「使用仅输出的 USB-C2 验证笔记本充电」（pb_737_laptop_uvp），不再转人工。
