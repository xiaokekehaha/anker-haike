# Round 4 Standards 复核

- 固定评审目标：`46b1777d845d3052b1b010714d2be9af56a5c315`。
- 对比父提交：`502b2f345b7e88a2ebdbec736923d96ed5b9c14b`。
- 固定 diff：`git diff 46b1777^...46b1777`，留存于本目录 `review.diff`。
- 运行时 HEAD：`5307876`；该后续提交仅增加文档，不扩大代码评审范围。
- 规范来源：完整阅读 `AGENTS.md`、`CLAUDE.md`，完整阅读本提交的 8 个变更文件；以仓库规范优先，Fowler 代码异味仅作启发式判断。跳过工具可检出的样式问题和本提交未引入的既有问题。

## Standards 结论

未发现本提交新增的可行动规范问题：硬规则违反 0 项，需要单独整改的启发式问题 0 项。

1. 上轮新增的函数内导入已移至顶层，符合 `AGENTS.md`“只用顶层导入”。这不表示整个仓库的既有函数内导入均已清理。
2. `orchestrator/app/evaluation/live_tickets.py:95` 新增 `SopExpectation`，替代 `sop_passed` 的 `dict[str, Any]`，符合“不用 Any 兜底”。其他未修改的 `Any` 不计为本次新增问题。
3. 启发式层面，原先散落在会话节点内的交接写入和去重，已收拢到 `orchestrator/app/cases/service.py:365` 的 `CaseService.hand_off`。没有新增足以单独提出修改要求的结构问题。

业务状态与后续任务推进的边界问题由 Spec 轴单独报告；Standards 通过不等于所有业务行为均正确。

## 独立故障注入

使用 `CaseService()` 的默认 `MemoryCaseStore`，不访问真实模型、知识库或业务服务。临时脚本先保存为 `/tmp/haike_round4_standards_atomic.py`，再从 `orchestrator` 执行：

```text
PYTHONPATH=. uv run --env-file ../.env python /tmp/haike_round4_standards_atomic.py
```

步骤：

1. 创建一个 `open` 案件，保存调用前的完整记录。
2. 调用 `hand_off`，传入 `order_change`、原话 `hold my order` 和固定输入编号。
3. 在 `summary_of` 回调中断言局部案件已变为 `awaiting_approval`，且已生成 `status_changed`、`review_requested` 两个事件；随后抛出 `RuntimeError("injected summary failure")`。
4. 重新读取持久化案件，与调用前记录逐项比较。
5. 用相同参数和正常摘要回调重试，检查案件状态与事件链。
6. 再次用相同参数调用，摘要回调设置为一旦执行就抛错，检查去重是否在生成摘要前生效。

实际结果：脚本退出码为 0，全部断言通过。

```json
{
  "failure_preserved_original_row": true,
  "status_after_failure": "open",
  "events_after_failure": 0,
  "retry_status": "awaiting_approval",
  "retry_event_types": ["status_changed", "review_requested", "handoff_summary"],
  "duplicate_did_not_generate_summary_or_write_events": true
}
```

结论：摘要生成异常没有留下半份交接；同参重试可以完整入队；再次重试没有新增事件或改变修订号。脚本执行后已删除。

## 存储语义与验证限度

`MemoryCaseStore.mutate`（`orchestrator/app/cases/store.py:48`）先读取副本，只有回调成功后才替换持久化记录，因此本次异常注入可以验证整个交接回滚。

`PostgresCaseStore.mutate`（同文件第 116 行）将案件更新、事件插入和人工决定写入放在同一个显式事务内。源码确认其写入边界一致；本项未进行真实 PostgreSQL 故障注入，不能把内存验证表述为数据库断连验证。
