# 上下文预算按任务分档与固定开销瘦身

## 问题

会话 d524a2cf（2026-09-17 09:15Z）用户问「我的产品是哪个」，两轮都得到写死文案「当前记录较多，我暂时无法准确理解这句追问」，整轮零模型调用。日志：

```
"context": {"source": "context_budget", "required_tokens": 4841, "max_tokens": 4679}
```

`build_context` 在装入任何历史之前，固定部分就超出了预算（`orchestrator/app/conversation/interpret.py:201-226`）：

| 项 | token（o200k_base × 1.25） |
| --- | ---: |
| `max_input_tokens`（`config/conversation.yaml`，全任务共用） | 8000 |
| 减 `TurnInterpretation` JSON schema（json_object 模式下确实随 system 发送） | -3065 |
| 减固定保留 | -256 |
| 传给 build_context 的上限 | 4679 |
| INSTRUCTION + 60 个症状码候选 | 2437 |
| authority 会话状态 JSON（facts 579 / symptom_interview 437 / decision 302 / steps_executed 279 / issue_index 165） | 2220 |
| 当前输入「？？？」含元数据 | 120 |
| 合计 | 4777–4841 |

这条会话只有 4 轮用户输入、13 条 history。触发条件不是「记录多」，而是走完症状问诊进入 escalate 后状态膨胀，且本轮输入不在 `fallback_interpretation` 的确定性规则里。

同日另一会话的只读核查 `docs/planning/2026-09-17_context-capacity-review/findings.md`（尚未提交）已核对厂商容量并用同一 checkpoint 探测过 16k / 32k 预算，结论一致；本文是其实施方案，不重复核查。

## 三个问题的现状回答

### 模型能处理多大

| 模型（domestic/intake 链顺序） | 厂商声明窗口 | 备注 |
| --- | ---: | --- |
| qwen3.7-flash | 1,000,000 | 非思考最大输入 991,808 |
| deepseek-flash（V4.1-Flash） | 1,000,000 | |
| glm-4.7 | 200,000 | 最大输出 128K |

8000 是应用自设值，不是模型限制。本会话实测：intake 真实输入 4783 token、输出 437 token、5.1 s（延迟主要在输出）；escalate.summary 输入 4877 token、1.8 s。真正的约束是文本轮 25 s deadline、成本（一次 A1 对话约 ¥0.011）、以及长上下文下的理解准确率，后者没有任何实测。

### 有测试和预期吗

已有（离线、假模型，15 passed）：`tests/test_conversation_context.py`（最终预算含 schema/重试/输出）、`test_conversation_history.py`（整轮裁剪、max_tokens=1600）、`test_conversation_reader.py`、`test_conversation_summary_cache.py`、`test_conversation_long_flow.py`（30 轮短闲聊）。验收 `2026-09-13_conversation-memory-v2-design/acceptance.md` 的 A20 / A23 / A39 是要求，不是通过证据。真实语义评测 75/75 时 ContextBundle 只有 1854–1880 token。

缺口：短输入但必需状态超限（本事故）无回归；预算不按 task 分档；估算与真实 usage 无校准；真实模型在 8k / 16k / 32k 输入下的准确率与延迟无数据；用户文案把内部装配失败归因为「记录多」。

### 怎么管理

原始记录存库，每次模型调用只发该任务需要的视图；预算按任务定额并统一计算；固定开销先压下去，再谈扩预算；超限先丢可选块再失败；估算用真实 usage 校准。分四个阶段。

## 方案

### 阶段 0：止血（当天）

1. `ConversationConfig` 增 `input_budgets: dict[str, int]`，key 为 task（`intake` / `reply.stream` / `diagnose.synthesize` / `escalate.summary` / `guide.step` / `default`），`max_input_tokens` 保留为 `default`。新增 `input_budget(task) -> int`，三处调用统一改：
   - `interpret.py:201` 传 `input_budget("intake") - schema - 256`
   - `context/runtime.py:53` 传 `input_budget(task) - reserve - 256`
   - `context/budget.py:budget_error` 增 `task` 参数，第一道检查改用 `input_budget(task)`
   初值：intake 16000，其余 8000（intake 的 16000 已用 d524 checkpoint 离线容纳验证，其余待评测）。
2. 兜底文案改为如实描述：「这句话我没有理解，请说明是要查询哪项信息，还是继续办理哪一步」。同样处理 `interpret.py:236`、`:262` 两处文案。
3. 回归测试 `tests/test_conversation_interpret_budget.py`：用 d524 形态的 state fixture（含 resolved symptom_interview、2 条 steps_executed、5 条 facts、escalate 阶段 decision，不连 DB）调 `interpret_turn(router=FakeRouter)`，断言 source 不是 `context_budget`，且 `bundle.omitted_entries == 0`。注明本事故会话 ID。
4. 验证：`make lint`；`cd orchestrator && uv run pytest -q tests/test_conversation_interpret_budget.py tests/test_conversation_context.py tests/test_conversation_history.py`。

### 阶段 1：固定开销瘦身（目标：intake 固定部分 ≤ 4000 token，6 轮历史必进）

1. schema 3065 → ≤ 1500：`Intent` 24 个枚举在 primary / secondary 各展开一次，改成共享 `$defs`；四段长 `Field(description=...)` 移入 INSTRUCTION；`FactCandidate` / `HistoryRequest` 的 None 默认字段去 `| None` 双类型（anyOf 展开成本高）。每步用 `estimate_tokens(json.dumps(model_json_schema()))` 度量，写进测试作为上限断言。
2. INSTRUCTION 2437：60 个症状码候选从 system 移到 authority 的 `symptom_candidates`（数据不重复）；品类已知时只给该品类；症状选择那段只在 `pending.kind == symptom_selection` 时拼接。
3. authority 2220：
   - `decision` 只保留 `primary_intent` / `reply_mode` / `clarification` / `target_issue_id` / `pending_changes`
   - `facts` 用 `exclude_none`，`quote == value` 时省 quote，去 `source_entry_ids`（模型不需要）
   - `symptom_interview.response_attempts` 去 `candidates_before` / `candidates_after`
   - `steps_executed` 每条只留 `step_id` / `title` / `outcome` / `at`
   这些字段模型是否使用需对照 INSTRUCTION 与 `decision.py` 逐条确认，删前列清单。
4. 测试：`test_conversation_context.py` 增固定开销上限断言（system + authority 空状态 ≤ 3000，d524 形态 ≤ 4000）。

### 阶段 2：压力触发与观测

1. `build_context` 必需内容超限时，先按顺序丢 `decision` → `issue_index` → `business_subject` 明细 → `historical_excerpts_cache`，每丢一块记 `dropped`；全丢仍超限才 raise。安全相关 `facts` / `risks` / `pending` 不可丢。
2. 摘要触发由 `summary_after_turns` 改为 token 压力：history 估算超过 `input_budget(task)` 的 60% 即生成。
3. 观测：`conversation_turn` 日志的 `context` 增 `blocks: {system, authority, current, history}` 各块 token 与 `dropped`；`model_trace` 记录 `estimated_in` 与 `usage.input_tokens`，用于校准 `token_estimate_margin`。观测台会话页展示这两组数字。
4. 指标：`context_budget` 落地率按 task 统计，目标 0。

### 阶段 3：验收与真实评测（付费，需用户明确同意再跑）

1. 确定性矩阵（假模型）：30 / 100 轮 × 1 / 5 个业务对象 × 4000 字符输入边界 × facts / steps / evidence 密集增长；每档断言必需信息集合不变、降级原因可断言。
2. 真实模型分档评测：输入 8k / 16k / 32k，关键信息置于开头 / 中间 / 末尾，覆盖型号回忆、跨订单查询、否定纠正、已做步骤。门槛：关键金标全通过，普通联合正确率 ≥ 95%；同时报告 P50 / P95 延迟与每轮成本，作为各 task 预算终值依据。
3. 更新 acceptance.md：A20 / A23 / A39 补「生产 schema + json_object + 密集状态」形态的通过证据。

## 可选复杂度（不在本轮范围）

- 把 `issue_index` / `business_subject` 明细改成「清单 + 按需拉取」（沿用 `history_request` → `recall_entry_ids` 通道）。
- 摘要从抽取式改结构化「已排除 / 已拒绝 / 已执行无效」块。抽取式不改写原话是有意取舍，保留。
- 新记忆库或模型工具循环：不需要。

## 涉及文件

`config/conversation.yaml`、`orchestrator/app/context/{config,builder,budget,runtime}.py`、`orchestrator/app/conversation/interpret.py`、`orchestrator/app/models/router.py`（budget_error 调用）、`orchestrator/tests/test_conversation_*.py`、观测日志与观测台会话页。

## 验收

- d524 形态回归通过，`context_budget` 不再出现。
- `make lint` 清零；上述测试文件通过。
- 阶段 1 后 intake 固定部分 ≤ 4000 token（测试断言）。
- 阶段 3 真实评测单独批准后执行，结果写 `addendum.md`。
