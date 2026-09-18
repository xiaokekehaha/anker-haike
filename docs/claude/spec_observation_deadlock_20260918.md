# 观察题回答丢失导致会话死锁（会话 0f8809b0）

## 现象

会话 `0f8809b03ae44e52bccf89153ae924c6`，8 轮用户消息，`steps_executed = 0`，后 5 轮 `next_action`
全是 `pause / operation_conditions_unavailable`，助手逐字重复同一句暂停文案。

```
08:38:05 助手  737 连接设备时，屏幕显示更接近下面哪种情况？(5 选项)
08:38:05 用户  设备不在身边                       ← 选项「设备不在身边或无法判断」的截断说法
08:38:05 助手  已记下设备不在身边，先不安排…拿到设备后告诉我
08:38:25 用户  连接笔记本时显示 UVP／屏幕显示异常    ← 逐字就是选项标签
08:38:34 助手  已记下设备不在身边…                 ← 同一句
08:38:52 用户  连接笔记本时显示 UVP／屏幕显示异常
08:39:01 助手  已记下设备不在身边…
08:39:11 用户  拿到了，连接笔记本时显示 UVP／屏幕显示异常
08:39:19 助手  已记下设备不在身边…
08:40:51 用户  已经拿到了
08:40:55 助手  已记下设备不在身边…
```

## 原因

一句话同时走了两条互不知情的路径：

```
"设备不在身边"
   ├─ interpret.py  explicit_operation_reply 短路 → device_missing → resources["device"] = False
   │     gate `state.get("operation_conditions")` 恒为真（reduce 每轮写回完整 dump），模型没看到这句
   └─ reduce.py     _accept_observation_reply → match_reply 返回 None → 请求置为 "unparsed"
```

四个可验证的事实：

1. `match_reply` 只匹配 `kind == "finding"` 的选项标签，unknown 选项的标签本身不参与匹配；
   「不在身边」也不在 `UNKNOWN_REPLIES` 里，所以这句既不是 finding 也不是 unknown。
2. `PlanStep.required_resources` / `StepObservation.required_resources` 默认 `["device"]`，
   `resources["device"] = False` 之后所有步骤与所有观察都不可用：观察不再追问
   （`decision.py` 的 `unavailable` 分支），三个 A1289 计划都 `requires_observations: pb_737_display`
   因而无可发布步骤，只剩 `pause`。
3. `_accept_observation_reply` 只受理 `status == "asked"`，所以第 5 轮逐字给出的选项标签
   （`match_reply` 认得，是 `laptop_uvp`）被整条丢弃。
4. 「拿到了 / 已经拿到了」既不在 `explicit_operation_reply` 的精确短语表里，模型四轮也都返回
   `operation_update: null`——而暂停文案恰恰写着「拿到设备后告诉我」，系统承诺了一个自己听不懂的入口。

## 修改

| 文件 | 改动 |
| --- | --- |
| `conversation/reduce.py` | `OPEN_OBSERVATION_STATUS = {asked, unparsed, unknown}`：请求在写出观察事实之前一直可以被回答接住；非匹配文本只在 `asked` 那一轮记未解析，不再逐轮改写记录 |
| `conversation/interpret.py` | 操作条件短语移到待答问题受理之后；gate 换成 `has_operation_context`；提示词补一条「resources 中为 false 的资源本轮到位必须给 *_ready 信号」；`INTERPRET_PROMPT_VERSION` → `2026-09-18.2` |
| `conversation/operation_conditions.py` | 新增 `has_operation_context`、`resource_recheck` / `RESOURCE_RECHECK`、`OperationConditions.resource_asks`；资源恢复时清掉追问记录；`explicit_operation_reply` 纳入「拿到了」等到位说法；`pause_text` 给出真的认得的解除说法 |
| `diagnose/decision.py` | 资源缺失导致暂停时先发一次复核追问（`operation_conditions_recheck`），没有可追问的才 `pause` |
| `sessions/graph.py` | `ask_observation` 记录该资源已追问过 |

复核追问的约束：声明当轮先如实答复（那一轮 `resource_sources` 就是当前 `input_id`），之后才追问；
同一次缺失只追问一次；来源未知的历史状态不追问。

修完后的序列：

```
"设备不在身边"        → 观察记未解析 + device=False → 暂停文案（明确给出解除说法）
"连接笔记本时显示 UVP" → 观察接住并写成事实 → 只差设备 → 「设备现在在身边了吗？」
"设备现在在身边"       → device=True → 直接按已收下的观察发 pb_737_laptop_uvp 的步骤
```

## 测试

`orchestrator/tests/test_conversation_observation_deadlock.py`，5 个用例。把
`OPEN_OBSERVATION_STATUS` 临时改回 `{asked}` 时，其中 2 个（含端到端那个）失败。

## 未做

- `match_reply` 仍不匹配 `kind != "finding"` 的选项标签：照着「设备不在身边或无法判断」回答只能靠
  `UNKNOWN_REPLIES` 里的「无法判断」命中，答成截断的前半句仍然认不出。
- 第 3 轮用户已说明「给充电宝本身充电很慢」，却收到以笔记本 UVP / USB-A 为选项的读屏问题，
  观察题与已知现象的相关性未处理。
- `analytics.session_facts` 的 `model_calls / tokens / total_latency_ms` 是逐轮覆盖写，会话页与
  经营面板显示的是最后一轮而非会话合计（实测 overview 191 calls vs `analytics.model_calls` 559）。
