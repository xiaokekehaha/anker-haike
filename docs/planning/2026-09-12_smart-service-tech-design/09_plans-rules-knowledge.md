# 排障计划、规则检查点、产品适用性与知识状态

整理日期：2026-09-12。响应评审 R1、R2、R3、R7、R8、R11。本文补充 03 详细设计中 disambiguate / diagnose / guide / verify / escalate 的规则层，03 中与此冲突的描述以本文为准。

## 1. 每轮规则检查点（R1）

规则服务在三个固定位置被调用，不再只在 verify：

| 检查点 | 时机 | 输入 | 命中后 |
| --- | --- | --- | --- |
| CP-in | 每条用户文本、每张图片的观察结果、每个动作进入图之后、任何模型调用之前 | 文本、observations、动作 | 写 `safety_flags`；R3 / R4 命中直接跳 escalate |
| CP-pre-step | prepare_card(step) 生成卡片之后、await_input 之前 | 待下发步骤 + safety_flags | R4 命中丢弃该步骤转 escalate；步骤含高危动作而知识来源无 caution → 丢弃并取下一步 |
| CP-verify | apply_action(step_feedback) 之后 | 计划游标、计数器 | R1 / R2 / R5 判定升级或继续 |

安全升级的摘要可以在没有凭证时直接生成；凭证在摘要之后作为可选补充，见第 5 节。`request_human` 在任何时刻可用，不受 pending_input 限制（08 §4）。

新增症状 / 照片 / 纠正的入口：`rediagnose` 动作（08 §4）。在 guide / verify 阶段用户通过 Composer 发送自由文本或图片时，前端提示「补充信息将重新判断故障」，提交即为 rediagnose；后端把新输入过 CP-in，然后回到 diagnose 并保留 steps_executed。

安全关键词字典 `config/rules/safety_terms.yaml`：冒烟、烧焦味、异味、电池鼓包、发热变形、漏液、电击、火花；图片观察项同样匹配（如 `observations` 含 "smoke"、"deformed battery"）。

### 1.1 路由不确定与用户纠正

| 后端判断 | 行为 |
| --- | --- |
| 必要信息齐全、与已确认状态一致、当前阶段允许 | 进入对应业务节点；按钮按已校验 kind 路由 |
| 缺少产品 / 具体症状、指代不明或信息冲突 | 先问一个具体问题，不发新排障步骤；产品问题复用 disambiguate，其余复用 intake / 当前节点的文字澄清 |
| request_human / R3、R4，或两次澄清后仍无法确定 | 进入既有升级分支；R7 摘要说明未知项与澄清经过 |

- `clarification={reason: product|symptom|conflict, attempts: int}` 是 checkpoint 内部状态。每次实际发出澄清问题加一；收到第二次回答后仍不明才触发 R7，不因用户尚未回复而升级。信息补齐并可进入合法流程后清零；同一未决问题换措辞、换模型或换 run 不重置。与排障 counters 分开计数。
- 品类明确、型号未知但允许通用品类计划时，可继续 category_only，不为确认具体 SKU 无限追问。未知品类仍按 §2.1 的既有 R7 路径处理。
- 澄清用现有 message_start / message / message_end 与 done(completed) 结束当前 run；这里 completed 不代表问题已解决。没有有效待反馈步骤时清空 pending_card / pending_input，保留可接收下一条消息的 intake / disambiguate 阶段。前端据最新快照禁用已失效卡片，不新增卡片或 awaiting_input kind。
- 「这个又不行了」有明确上文时承接；对象或现象不明时问「是吸力变弱，还是无法启动？」。不能凭模型自报高置信度强行选流程；检查必要字段、冲突、当前阶段，也保留用户纠正入口。
- 型号纠正通过版本 / 幂等校验后，由会话单写者暂停旧计划、使旧 pending_card 失效，再进入消歧；明确新产品前不继续旧步骤。旧证据和执行历史保留供追溯，但新计划按新 scope 重新校验。active run 期间普通补充仍返回 409，不绕过 08 的取消 / 动作协议。
- 合法按钮映射错误属于代码缺陷，用路由表与端到端用例发现；不增加模型判断来修复。动作不存在、阶段不允许或卡片过期按 08 §4 拒绝，不计入语义澄清次数。

## 2. 产品适用性（R2）

### 2.1 消歧状态三分

| product_state | 含义 | 允许进入 |
| --- | --- | --- |
| confirmed_sku | SKU 唯一确认 | diagnose、guide，全部知识 |
| category_only | 品类确定（扫地机），型号未知 | diagnose、guide，仅允许 `scope=category_generic` 的知识 |
| unknown | 品类未定 | 只允许追问（最多 2 次）或 escalate（R7 新增：品类不明） |

「两次未选中 → 通用扫地机」的降级删除。用户两次不选：若 product_hints 含扫地机品类词 → category_only；否则 → escalate(R7)。

选中 `in_scope=false` 的候选（如 S1 Pro 吸奶器）→ 进入 `out_of_scope` 子流程：说明本期仅支持扫地机排障，生成简短摘要并 escalate(R8：范围外产品)。

### 2.2 知识条目的适用范围元数据

每份文档 / 每条工单入库时带：

```
scope: sku | category_generic
sku_list: [..]          # scope=sku 时必填
category: robot_vacuum
doc_version: 2026-09-12.1
result: solved | unsolved | escalated   # 仅工单
```

### 2.3 检索过滤映射到 WeKnora

`KnowledgeAdapter.hybrid_search(kb, query, top_k, allow: KnowledgeScope)`，其中 `KnowledgeScope = {sku?: str, category: str, product_state}`。

适配器把 scope 映射为 WeKnora 请求：

- 启动时从 WeKnora 拉取知识库内全部 knowledge 的元数据，按 `(scope, sku_list, category)` 建索引 `knowledge_ids_by_scope`。
- confirmed_sku → 允许集合 = `sku_list ∋ sku` ∪ `scope=category_generic ∧ category 匹配`。
- category_only → 允许集合 = `scope=category_generic ∧ category 匹配`。
- 允许集合为空 → **直接返回 `no_match`，不发请求**，禁止退化为整库搜索。
- 请求携带 `knowledge_ids=允许集合`（WeKnora knowledge-search 接口参数）。实际参数名与是否支持在锁定镜像版本后核对，作为集成验证项 IV-1；若不支持则由适配器对返回结果按 `knowledge_id` 做后过滤并把 top_k 放大 3 倍。

### 2.4 工单的用法

- `result=solved` 的工单步骤可作为候选动作来源。
- `result ∈ {unsolved, escalated}` 的工单只作为反证：其步骤若与候选步骤相同，候选步骤优先级下调并在 evidence 中标 `counter_evidence=true`；不得改写成推荐动作。

### 2.5 进入 guide 前校验

prepare_card(step) 时校验步骤的 `evidence_ids` 所指条目全部在当前允许集合内；不满足则丢弃该步骤。

## 3. 有限排障计划（R3）

### 3.1 计划模型

```
plan:
  plan_id: rv_suction_hair_wrap
  version: 1
  fault: 滚刷毛发缠绕导致吸力下降
  applies_to: {scope: category_generic, category: robot_vacuum}   # 或 sku_list
  steps:
    - step_id: s1
      title: 检查并清理滚刷
      instruction_src: evidence:manual_rv_v1#c12
      expected_result: 滚刷无缠绕物，转动顺畅
      caution: null
      next_on: {solved: DONE, not_solved: s2, cannot_do: s2}
    - step_id: s2
      title: 取出并清洁滤网
      instruction_src: evidence:manual_rv_v1#c15
      expected_result: 滤网无堵塞
      next_on: {solved: DONE, not_solved: s3, cannot_do: EXHAUSTED}
    - step_id: s3
      title: 检查吸口是否有异物
      instruction_src: evidence:faq_rv#q7
      next_on: {solved: DONE, not_solved: EXHAUSTED, cannot_do: EXHAUSTED}
```

本期预写计划：`rv_suction_hair_wrap`、`rv_suction_filter_clog`、`rv_suction_dustbin_full`、`rv_suction_side_brush`、`rv_suction_motor_fault`（后者只有一步「确认异响或过热」，next 全为 EXHAUSTED，走升级）。

### 3.2 LLM 与规则的分工

- diagnose.synthesize 输出的假设列表中，每个假设必须引用一个 `plan_id`（枚举由当前允许集合决定）；无对应计划的假设丢弃。这替代原「first_step_hint」。
- guide.step 的 LLM 任务变为：给定 `step` 的 instruction_src 原文、用户情绪策略、产品名，改写成用户能执行的一句话 + 预期结果，**不得增删动作**；输出经 CP-pre-step 校验。
- 下一步由规则按 `next_on[feedback]` 决定，LLM 不参与。

### 3.3 会话状态字段（替换 02 §5 中 steps_executed / step_count）

| 字段 | 说明 |
| --- | --- |
| plans_ranked | `[{plan_id, version, confidence}]`，由 diagnose 给出并按置信度排序 |
| plan_cursor | `{plan_id, step_id}` 当前位置 |
| steps_executed | `[{plan_id, step_id, card_id, feedback, note?, ts}]` |
| counters | `{executed: int, advanced: int, skipped: int, plans_exhausted: int}` |
| exhausted_plans | 已 EXHAUSTED 的 plan_id 列表 |

计数规则：solved → 结束；not_solved → executed+1, advanced+1；cannot_do → skipped+1（不计 executed）。

### 3.4 出口与上限

| 规则 | 条件 | 动作 |
| --- | --- | --- |
| R1 | `executed ≥ 4` | escalate |
| R1b | `skipped ≥ 3` | escalate（用户无法操作） |
| R1c | `executed + skipped ≥ 6` | escalate（硬上限） |
| R2 | 当前计划 EXHAUSTED 且 `plans_ranked` 中下一计划 confidence < 0.3，或无下一计划 | escalate |
| 计划切换 | 当前计划 EXHAUSTED 且下一计划 confidence ≥ 0.3 | plan_cursor 移到下一计划首步，`plans_exhausted+1`；同一 `step_id` 内容若与已执行步骤 instruction_src 相同则跳过 |

confidence 只用于排序与切换门槛，不再作为「步骤耗尽」的单独判据；原「签名降权」（07 §3）保留为跨计划去重的实现细节。

## 4. 知识状态与降级（R8）

`ToolResult.status ∈ {ok, no_match, unavailable, replay}`，替换 03 中的 ok / empty / unavailable。

| 状态 | 含义 | diagnose 行为 | 前端标记 |
| --- | --- | --- | --- |
| ok | 实时检索有命中 | 正常 | 来源可展开 |
| no_match | 实时检索无命中（含允许集合为空） | 先按 §4.1 判断是否允许一次改写补救；未触发 / 补救失败后，若 product_state=confirmed_sku 或 category_only 且有 `applies_to` 匹配的预写计划 → 默认顺序执行（instruction_src 取计划绑定的已审核文本），否则 escalate(R5) | 补救结束后按实际分支显示「未找到匹配知识，按标准排障流程」或升级说明 |
| unavailable | WeKnora 不可达 / 超时 | 不触发查询改写；适用预写计划或 escalate(R5)，不允许 LLM 用常识生成假设 | 按实际分支显示「知识库暂不可用，按标准排障流程」或升级说明 |
| replay | 显式回放模式命中录制 | 正常 | 「演示回放」 |

- 删除「LLM 依据内置常识给假设，confidence 上限 0.5」的降级。
- 回放模式：只在 `REPLAY_CASE_ID` 显式设置时启用，缓存未命中 → `unavailable`，不得借用其他案例的结果。
- 模型全部不可用时：escalate 摘要由 `summary` 结构字段直接渲染（不润色），`model_trace` 标注 `summary_polish=skipped`。

### 4.1 无命中补救的触发与停止

改写开关默认关闭，具体 Schema / 校验见 03 §1.4.2，预算见 08 §8。不得把适配器所有 no_match 都理解成「换句话能搜到」。

| 首轮结果 / 上下文 | 是否改写 | 后续 |
| --- | --- | --- |
| 允许集合非空，实际请求的各库均 no_match；开关开启、信息足够、无图片新增补检索、次数与预算允许 | 一次 | query.rewrite → 校验 → 相同 scope 再检索一轮 |
| 任一库已有适用 hits，即使另一库无命中 / 不可用 | 否 | 使用已有证据，保留各库状态与缺失提示 |
| 开启评分（03 §1.4.3）且 graded 结果无一条 relevant | 一次（同首行条件） | 该库 ok 在**决策时**按 no_match 计，走同一条改写路径；`knowledge_status` 仍按实际检索结果上报，不伪装成无命中 |
| 无 hits 且任一已请求库 unavailable | 否 | 服务降级；不把部分故障归为正常无命中 |
| 所有允许集合为空，或 product_state=unknown | 否 | 前者用适用预写计划或 R5，后者澄清；不扩大范围 |
| 回放、待澄清、取消、预算不足、名额已使用或开关关闭 | 否 | 维持该路径既有行为，不因跳过改写额外升级 |
| 改写无效 / 超时 / 模型不可用，或第二轮仍 no_match / unavailable | 不再改写 | 有适用预写计划则标明来源，否则 R5；知识状态仍反映实际检索结果 |

每 run 初次检索 + 至多一次补检索；图片观察补检索与改写补检索二选一，已返回的新图片事实优先。不能因某个库无匹配或某个假设缺证据而另开改写循环。召回命中仍须校验产品适用性、来源与计划枚举；**改写文本不是证据，评分结论同样不是证据**。

## 5. 凭证、订单与渠道（R7）

### 5.1 escalate 子流程

```
escalate
 ├─ CP: 是否安全升级(R4) 或用户 request_human ──▶ summarize(receipt.status=not_collected) ──▶ offer_receipt(可选) 
 └─ 常规升级
      ├─ collect_receipt      awaiting_input(kind=upload_receipt)；用户可 skip_receipt
      ├─ extract              warranty.receipt_ocr → fields/confidence/unreadable
      ├─ confirm_fields       receipt_card + awaiting_input(kind=confirm_receipt)；用户改字段或 skip
      ├─ lookup               规则：订单表 → 经销商名录 → 核对
      └─ summarize            escalation_summary → done
```

上传时前端标记图片用途 `purpose=receipt`，与故障图区分；上传到 upload_receipt 之外的位置的图片走 rediagnose。

### 5.2 lookup 规则

输入：`confirmed_fields`（用户确认或修改后）、`confidence`、`edited[]`、`product_confirmed`。

| 步 | 判定 | 输出 receipt.status |
| --- | --- | --- |
| L1 | 无 order_no 且无 channel | `insufficient` |
| L2 | order_no 命中 orders_mock 且 `order.sku == product_confirmed.sku` | `order_verified`，verified_facts = {order.channel, order.purchase_date}（使用订单实际值，不覆盖为「官方」） |
| L3 | order_no 命中但 `order.sku != product_confirmed.sku` | `order_product_mismatch`，conflicts = [sku 不一致] |
| L4 | order_no 命中且 OCR 该字段 confidence < 0.7 且用户未修改 | 在 L2 / L3 基础上加 conflicts = [订单号低置信]，status 降为 `needs_manual_check` |
| L5 | order_no 未命中，channel 匹配 dealers | `channel_in_directory`，verified_facts = {dealer.name, authorized} |
| L6 | 均未命中 | `channel_unknown` |

`next_step` 文案由规则表给出：order_verified → 「资料已核实，转人工办理」；channel_in_directory → 「经销商在名录内，人工确认购买凭证后办理」；mismatch / needs_manual_check → 「凭证与当前设备信息不一致，需人工核实」；insufficient / unknown → 「请准备购买凭证，人工协助核实」。

**不输出**「可走标准质保」「已确认可保」等资格结论；本期只输出已核实事实与下一步。

### 5.3 receipt 状态与前端

`pendingInput.kind` 增加 `upload_receipt`、`confirm_receipt`（05 同步）。ReceiptCard 字段可编辑，confidence < 0.7 标黄，`edited[]` 随 confirm_receipt 提交。

## 6. 回放、fixture 与评测的分离（R11）

| 用途 | 机制 | 键 / 输入 | 说明 |
| --- | --- | --- | --- |
| 演示回放 | ReplayRouter + ReplayKnowledgeAdapter | `case_id` + 版本清单 `{prompt_ver, models_ver, kb_ver, rules_ver}` | 录制包 `replay/<case_id>/manifest.json + events.jsonl`；清单任一项不符 → 启动时报 `replay_incompatible`，不静默降级 |
| 协议 / 规则测试 | 结构化 fixture | `contracts/fixtures/*.json` | 不经模型；测试 reducer、规则服务、事件校验 |
| Prompt / 模型评测 | bake-off 脚本 | 金标输入实际调用 | 通过 model-selection 3.8 门槛后才允许录制新回放包 |

LLM 响应缓存键（非回放）：`sha256(task, prompt_ver, schema_ver, model_id, input_text, image_sha256s, kb_ver)`。

## 7. 对既有文档的修订点

- 02 §3 状态机：escalate 拆为子流程；新增 out_of_scope；product_state 三分；rediagnose 边。
- 02 §5 状态字段：替换 steps_executed / step_count 为 §3.3；新增 product_state、safety_flags、pending_card、receipt。
- 03 §1.3 / 1.4 / 1.5 / 1.6 / 1.7 / 1.8：按本文改写。
- 03 §2.3：ToolResult 四态；filters → KnowledgeScope。
- 04 稳定性表：WeKnora 不可用行改为「按预写计划 / 升级」；回放行改为 case_id + 清单。
- 05：pendingInput.kind、ReceiptCard、rediagnose 入口。
- 07 §3：签名降权降为实现细节，主判据为计划游标。
