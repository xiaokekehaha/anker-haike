# 隔离复现说明

不启动生产服务，不调用真实模型或知识库。复用项目已有 fixtures：`tests.conftest.mem_runtime`、`tests.test_conversation_l3.l3_runtime`，HTTP 客户端使用 `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`。测试文件命名为 `test_conversation_*.py`，避免 mem_runtime 的旧业务场景兜底分类器介入。

临时测试可放 `/tmp/test_conversation_round4_spec.py`。运行入口：

```bash
cd /Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator
PYTHONPATH=/Users/xiaoke.zhou/Documents/workspace/anker-haike/orchestrator uv run --env-file ../.env pytest -c pyproject.toml -q /tmp/test_conversation_round4_spec.py
```

顶层导入上述 fixtures，以及 `tests.test_conversation_l3` 中的 `interpret_as`、`send`、`act`、`events`、`said`、`state_of`。`interpret_as` 只替换模型语义输入，实际路由、节点、存储和 HTTP 仍走项目实现。初始订单及物流来自现有测试用官方数据。`tests/__init__.py` 关闭模型和知识库，`l3_runtime` 使用内存案件及订单工具。

每个独立场景先 `POST /sessions`。客户输入通过 `send(client, sid, text)`，它会读取版本并使用新 input_id；原始 SSE 用 `events(response)` 解析。后台案件从 `GET /admin/api/cases/{case_id}` 读取，case_id 来自 `await state_of(sid)`。

人工决定使用 `POST /admin/api/cases/{case_id}/decision`，JSON 包含随机 `decision_id`、刚读取的 `expected_revision`、`decision` 和 `note`。若批准换货，加 `option_id: "replace"`。等待响应中的 run_id 不再满足 `app.state.run_manager.is_live(run_id)`，再读取图状态及案件。

## 要求补充后普通查询误送审

用 `interpret_as` 注入两条确定性语义，均 `device_relation="current"`：

| 输入 | primary_intent | secondary_intents |
| --- | --- | --- |
| If you have not shipped Anker008, hold it and tell me its shipping date. | order_change | logistics_query |
| Please tell me the shipping date of Anker008 again. | logistics_query | 空 |

1. 新会话发送第一条，确认 order_change=waiting_human、logistics_query=done。
2. 人工决定 request_info，note 为 `Please confirm which item you want held before I can review the request.`。
3. 确认案件 awaiting_confirmation、改单任务 pending。
4. 发送第二条，实际回复追加 `Next up: order change` 和已交接话术，案件回 awaiting_approval。预期仍等待客户回答暂停哪个商品，只有物流答复。

对照：第 4 步换成 `Only hold the main vacuum, not the filter, for Anker008.`，注入 supplement，实际能够带着补充信息重新交接。

## 批准后闸门拒绝却提前办结

新会话，注入如下语义：

- `左侧吸奶器没有吸力，订单 Anker016，我要换货，顺便帮我排查一下`：replacement_request，secondary_intents=[report_problem]，device_relation=current。
- `SN: T8D04121ABCD`：supplement，facts=[{kind: context, context_field: serial_number, value: T8D04121ABCD, quote: SN: T8D04121ABCD}]。
- `The heating part burned me.`：report_problem，device_relation=current，device_safety_assertion=reported，device_safety_quote 为完整输入。

1. 发送首条，再 `send(..., "照片", images=1)`，再发送 SN。图片是现有测试 helper 的生成图片，仅为隔离流程准备证据，不用作官方原样本测评。
2. 通过 `act(..., "decline_proposal", {"reason": "request_human"})` 选择人工，确认换货任务 waiting_human，排障 pending，阶段 awaiting_human。
3. 发送烫伤消息，然后后台 approve，option_id=replace。
4. 读取案件 gate_result：safety=false、fallback=await_human；create_calls 未增加，案件 awaiting_approval，换货任务却 done。预期该任务仍等待人工，不应标记已办结。

## 原四项复核

- 改口：第一场景第 1 步后发送 `Actually cancel my whole Anker008 order instead of holding it.`，注入 order_change，检查 request_changed、摘要 reason.text 及等待任务 quote 都含新原话。
- 原子交接：新会话发送第一条前，monkeypatch `app.sessions.l3.build_summary` 同步抛出 `RuntimeError("round4 injected summary failure")`。案件从 store.queue 找到：仍 open，events 仅 order_identified；客户没有已转交话术。恢复原函数，以新 input_id 重发，案件、review_requested 与摘要完整写入。
- 停止排障：第二场景第 2 步即原复现点，不应出现 Next up 或 step_card。
- 驳回收尾：改单等待人工后后台 reject，检查对应 task=done、case=rejected。

本轮临时采证脚本已删除，证据保存在 spec-repro.json。未测试真实 Postgres 中断或会话 checkpoint 恢复。
