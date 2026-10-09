# 官方 63 案例修复第二批规格：知识节点类型与卡片协议（I4 I5）

状态：开发规格，尚未实施。承接第一批（a32a1f3）与总规格 `spec_2026-10-09-1633_official-63-remediation.md` §8。D2 已定：事实问句卡为选项加短答。

术语：步骤类型（step kind）= 官方 Q&A 一个编号段落对用户意味着什么：要回答、要操作、只需知道、要提供材料、还是要交人工。

## 0. 问题与证据

- T46 对照 bp-0123：原文「Step 1: Identify the Problem / 1. Is the noise continuous or intermittent? / 4. Please record a short video」全部被编号成操作步骤，页面给每段配「解决了 / 还没解决」。标题点「未解决」还会增加已操作计数。
- T19/T24/T28/T38：「If … hardware malfunction」结论被当成第二个可执行步骤，用户必须点「未解决」才能进质保。
- T26：清洁液事实问题与条件操作混在同一张卡。T40：照片收集混进操作卡。
- T27/T36/T37：用户自述已清洁 / 已换滤网 / 水箱已满，系统仍从第一步重放。第一批已抽出 `action_taken` 事实，但 `prepare_step` 还不消费它。

代码：`official/qa_index.py:53,129` 按编号拆段，`Step` 无类型；`plans/qa.py:52` 给每段同样的三条反馈边；契约 `TroubleshootStep`、`StepFeedbackPayload` 只有三种反馈；`guide/verify.py:94` 对 not_solved 一律 `executed+1`；`StepCard.tsx` 固定三按钮。

## 1. 离线分类（`official/qa_index.py`）

### 1.1 分布（2026-10-09 对 875 条、1364 段扫描）

| kind | 数量 | 说明 |
|---|---|---|
| action | 1172 | 维持现状 |
| action_with_heading | 67 | 「Placement and Appearance Inspection / - Place the pump …」标题加操作正文：按 action 处理，标题进 title，正文进 instruction |
| statement | 107 | 条件说明、机制说明、功能列表（rv-0088 的四种清扫模式、rv-0064 的低温保护） |
| material_request | 9 | 录视频、拍照、提供 SN |
| handoff | 6 | 「please contact us to continue the warranty process」 |
| question | 3 | bp-0032 漏奶位置、bp-0123 两问 |

非 action 段落不到 11%，其中大半是 statement。规则分类够用，少数条目用覆写文件修正；不做模型分类。

### 1.2 规则

`Step` 增加 `kind: StepKind` 与 `options: tuple[str, ...]`，`StepKind = Literal["action", "question", "statement", "material_request", "handoff"]`。分类在 `build_guide` 时按段落首行判定，顺序：

1. 首行以 `?` 结尾且长度 < 200 → question。括号或斜杠列出的选项（「upon startup / During breast pumping / Only at high speed」）拆成 options。
2. 首句含 record / send / provide / upload / share / attach / take + photo / picture / image / video / audio / clip / screenshot → material_request。
3. 首行形如「If … persists, please contact us / contact support」且正文无动作动词 → handoff。
4. 首行是纯标题（`Step N:` 或 首字母大写、≤60 字、无动作动词）：正文有动作动词 → action（标题进 title）；正文无动作动词 → statement。
5. 首行以 If / When / This / It is normal / The robot|device|app / Note / During / After 开头且无动作动词 → statement。
6. 其余 action。

动作动词表与扫描脚本一致（check / clean / remove / press / restart / replace / ensure / fill / wipe / install / update / … 约 50 个），放在 `qa_index.py` 常量。

### 1.3 覆写文件 `data/official/qa_overrides.yaml`

```yaml
# 对官方 Q&A 段落的人工审核结果。只改执行方式，原文不动。
- qa_id: bp-0123
  steps:
    - no: 1        # Identify the Problem
      kind: statement
    - no: 2        # When does it occur?
      kind: question
      options: ["Upon startup", "During pumping", "Only at high speed"]
    - no: 8        # Tubing and Connections
      disabled: true
      reason: "S1 Pro 为一体可穿戴结构，无外接软管（7.1 复核）"
    - no: 10       # Replacement Test（含 hoses）
      disabled: true
      reason: "同上"
    - no: 11
      kind: handoff
- qa_id: bp-0032
  steps:
    - no: 1
      kind: question
      options: ["Breast shield opening", "Bottle connection"]
      branches: {"Breast shield opening": 2, "Bottle connection": 3}
```

`QAIndex.build` 读覆写并应用；`disabled` 段不生成计划步骤但保留在 `Guide.steps` 供证据展示。覆写文件不是生成文件，可手改；加 `tests/test_qa_overrides.py` 校验每条 qa_id / no 存在。

## 2. 计划模型（`plans/models.py`、`plans/qa.py`）

`PlanStep` 增加：

```python
kind: StepKind = "action"
options: list[str] = Field(default_factory=list)
branches: dict[str, str] = Field(default_factory=dict)   # option → step_id；未列出的 option 走 next_on.not_solved
```

`plan_of`：

- action：不变。
- question：`expected_result` 改为 `"Pick the option that matches, or describe it in a few words."`；`next_on` 三条边都指向下一步（反馈语义不适用，由 branches 决定）。
- statement：`next_on` 三条边指向下一步；`expected_result` 为空串由契约允许。
- material_request：`expected_result` 改为 `"Upload it here if you have it, or tell me you don't have it right now."`；`next_on` 指向下一步。
- handoff：`next_on.not_solved = "EXHAUSTED"`，其余同；`plan_of` 把 handoff 段标 `warranty=True` 的现有语义保留（进质保流程）。
- `disabled` 段跳过，step_id 仍按位置编号（s1…sN 不重排，避免 card_id 漂移）。

`Plan._steps_consistent` 校验 branches 目标存在。

## 3. 契约（`contracts/haike_contracts/`）

`common.py`：

```python
StepKind = Literal["action", "question", "statement", "material_request", "handoff"]

class TroubleshootStep(Strict):
    ...
    kind: StepKind = "action"
    options: list[str] = Field(default_factory=list)
```

`actions.py`：

```python
class StepAnswer(Strict):
    option: str | None = None     # question：选项原文
    text: str | None = None       # question 短答 / material_request 的说明
    unavailable: bool = False     # material_request：暂时没有

class StepFeedbackPayload(Strict):
    feedback: Feedback | None = None   # action 必填；其他 kind 必须为 None
    note: str | None = None
    answer: StepAnswer | None = None   # question / material_request 必填；statement 可省（确认已读）
```

`snapshot.py` `StepCardItem` 增加 `answer: StepAnswer | None`。`PendingKind` 不新增，复用 `step_feedback`。`make contracts` 后提交产物。`contracts/tests/samples.py` 增加 question / material_request 两个合法样例与「question 带 feedback」非法样例。

## 4. 后端

### 4.1 路由校验（`sessions/router.py`）

`step_feedback` 动作按卡片 kind 校验 payload：action 必须有 feedback 且无 answer；question 必须有 answer.option 或 answer.text，option 须在卡片 options 内；material_request 必须有 answer（text 或 unavailable）或本轮附图；statement 允许空 payload；handoff 不出卡。违反 → `InputConflict("invalid_selection")`。

### 4.2 反馈处理（`guide/verify.py`、`sessions/graph.py _apply_step_feedback`）

`apply_feedback` 增加 `answer` 入参：

- action：现状不变。
- question：不计 executed / skipped；attempt 记 `{"kind": "question", "answer": ...}`；`next` 步为 `branches.get(option)` 或 `next_on.not_solved`。回答写成一条 observation fact：`value = f"{step.title}: {option or text}"`，`subject` 取问题里的名词短语，`source = user_statement`，`polarity = affirmed`。事实进入 issue.facts，synthesize 下一次评估时可见。
- statement：不计 executed；直接 next。
- material_request：不计 executed；`unavailable=True` → 在 issue.observations 追加「待补材料：{title}」并 next；有附图 → 图片进 `_new_fault_images` 走 vision；有 text → observation fact。
- handoff：不出卡，`prepare_step` 遇到即返回 `exhausted` 并记 `dropped: handoff_step`，让 decide_next 走 R2 / 质保。

`_apply_step_feedback` 把 answer 透传，`card_results[card_id]` 增加 answer。

### 4.3 已做操作跳步（`guide/steps.py`）

`prepare_step` 增加 `user_reported_done(step, facts)`：步骤 instruction 与某条 `action_taken` 事实的 value 满足「同部件 + 同动作」（部件词表：filter / brush / roller / tank / contacts / valve / shield / mop / sensor / base / dock；动作词表：clean / wipe / replace / change / restart / reset / refill / fill / reinstall / remove）→ 跳过，记 `step_dropped: user_reported`。整条计划因此耗尽时，`decide_next` 的 `no_supported_followup` 文案改为「you've already done the official checks for this」。

### 4.4 评测驱动器（`evaluation/live_tickets.py`）

- question 卡：停止（criteria 规定不代填事实）。
- statement 卡：发空 payload 继续。
- material_request 卡：发 `answer.unavailable=True` 继续。
- 新增 forbid：`question_as_action`（question 卡收到 feedback）与 `statement_counted`（statement 后 executed 增加）。

## 5. 前端

- `StepCard.tsx` 按 `item.step.kind` 渲染：
  - question：选项按钮（options）加短答输入；提交 `answer: {option}` 或 `{text}`；无 options 时只有输入框。
  - statement：无反馈按钮，一个「知道了」按钮提交空 payload。
  - material_request：「上传」（打开 Composer 附图，purpose=fault）与「暂时没有」（`answer.unavailable=true`）。
  - action：现状。
- `Timeline.tsx` POINTER：question → 「请回答：{title}」；statement → 「请查看：{title}」；material_request → 「请提供：{title}」。
- `Composer.tsx`：pendingKind 为 step_feedback 且卡 kind 为 material_request 时，附图发送附带 `answer.text`。
- 已答卡折叠行显示答案而不是反馈标签。
- `Cards.test.tsx` / `StepCard.test.tsx` 覆盖四种 kind。

## 6. 测试

- `tests/test_qa_index.py`：分类分布断言（action ≥ 1150、question ≤ 10 等粗界）；bp-0123 各段 kind；覆写生效与 disabled。
- `tests/test_plans_qa.py`：question 的 branches、statement 的 next_on、disabled 跳过且 step_id 不重排。
- `tests/test_guide_steps_kinds.py`：question 回答写 observation fact；statement 不计 executed；material unavailable 记待补；handoff 段 exhausted；user_reported 跳步（T27 / T36 / T37 三条 action_taken）。
- `tests/test_conversation_official_tickets.py`：T46 首卡 kind=question 且 options 含 intermittent；T19 第二卡不是 handoff 结论而是直接进质保；T40 照片请求卡 kind=material_request。
- 契约与前端测试见 §3 §5。

## 7. 验收

- 第一批门槛不回退。
- I4 的 7 单：T46 首卡事实问句；T19/T24/T28/T38 结论不需点「未解决」；T26 问句与操作分卡；T40 照片请求保持待补状态。
- I5 的 3 单：T27/T36/T37 不重放用户已做的步骤，且交接摘要列出「用户自述已做」。

## 8. 不做

通用流程编排器；对 875 条逐条人工复核（只覆写 bp-0123、bp-0032 两条，其余按规则）；模型分类。
