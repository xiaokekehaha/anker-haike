# 未结项盘点（2026-09-12，本轮收尾时快照）

按票内 Status 与未勾验收汇总，存在实现已写但票据未更新的情况；本表不代表所有列出的功能都尚未编码。50 张票中本次快照有 16 张未标 done。

本轮认领并完成 41（凭证核对）。进行中共享工作树的 08/38 已被其他会话标 done；23 原始前后端验收完成，新增 37 联动待完成。34–36 仍登记 Claude A；32 属 Claude B。后续优先收尾 34–36 后推进 37，42 需真实模型评测条件，44 的可观测是 48/50 的前置。

| 票据 | 当前状态 | 负责人 | 未勾验收数 |
| --- | --- | --- | ---: |
| [21: 产品确认卡片 ProductCard 端到端（A2 前半）](../2026-09-12_smart-service-tech-design/issues/21-product-card-select.md) | ready-for-agent | 未单列负责人 | 4 |
| [23: 版本冲突 409 与前端重建](../2026-09-12_smart-service-tech-design/issues/23-action-409-conflicts.md) | in-progress（2026-09-12；原始前后端验收已完成，追加的票 37 纠错联动验收仍待完成） | 未单列负责人 | 3 |
| [25: 范围外产品 R8 与 request_human 全局动作](../2026-09-12_smart-service-tech-design/issues/25-out-of-scope-r8-request-human.md) | backend-done（2026-09-12，A 线接手会话；前端「请求人工」按钮待 Codex 在票 06 之后接入） | 未单列负责人 | 1 |
| [32: 假设汇总 plans_ranked](../2026-09-12_smart-service-tech-design/issues/32-diagnose-synthesize-plans-ranked.md) | in-progress（核心与查询补充大部分完成；读图并行（票 30）、取消 / 晚到结果、人工标注对照报告未做，见逐项） | Claude Code B（2026-09-12 认领；`orchestrator/app/diagnose/`、`config/retrieval.yaml`；graph.py retrieve 节点扩展为 diagnose 流水线；读图（票 30）未做，先走文本路径） | 0 |
| [34: 步骤卡下发 guide.step 与 CP-pre-step](../2026-09-12_smart-service-tech-design/issues/34-guide-step-card.md) | claimed | Claude Code A（2026-09-12 认领；`app/guide/`（步骤改写、CP-pre-step）、graph.py guide 三段式节点；沿用 prepare_card / await_input / apply_action 追加 step 分支） | 5 |
| [35: 反馈推进、计数器与计划切换](../2026-09-12_smart-service-tech-design/issues/35-verify-feedback-cursor.md) | claimed | Claude Code A（2026-09-12 认领；`app/guide/`（游标推进、计数器、计划切换），graph.py verify；无 LLM） | 4 |
| [36: 出口规则 R1 / R1b / R1c / R2 与 A1 完成](../2026-09-12_smart-service-tech-design/issues/36-exit-rules-a1-complete.md) | claimed | Claude Code A（2026-09-12 认领；`app/guide/`（CP-verify R1/R1b/R1c/R2）、solved 结束语与 done(completed)） | 4 |
| [37: rediagnose 中途补充与纠正](../2026-09-12_smart-service-tech-design/issues/37-rediagnose.md) | ready-for-agent | 未单列负责人 | 12 |
| [39: 凭证收集 collect_receipt](../2026-09-12_smart-service-tech-design/issues/39-collect-receipt.md) | backend-done（2026-09-12，A 线接手会话；前端凭证上传态 / 跳过按钮待 Codex 在票 06 之后接入） | 未单列负责人 | 1 |
| [40: 凭证识别与 ReceiptCard 字段确认](../2026-09-12_smart-service-tech-design/issues/40-receipt-ocr-confirm-card.md) | backend-done（2026-09-12，A 线接手会话；ReceiptCard 前端待 Codex；真实订单截图识别待票 42 有视觉模型 key） | 未单列负责人 | 1 |
| [42: bake-off 评测与模型 ID 冻结](../2026-09-12_smart-service-tech-design/issues/42-bake-off-model-freeze.md) | ready-for-agent | 未单列负责人 | 4 |
| [43: 回放模式与录制包](../2026-09-12_smart-service-tech-design/issues/43-replay-mode.md) | ready-for-agent | 未单列负责人 | 4 |
| [44: 可观测：Langfuse profile 与延迟指标](../2026-09-12_smart-service-tech-design/issues/44-observability-langfuse-metrics.md) | ready-for-agent | 未单列负责人 | 4 |
| [45: 故障与边界场景巡检脚本](../2026-09-12_smart-service-tech-design/issues/45-failure-scenario-suite.md) | ready-for-agent | 未单列负责人 | 7 |
| [48: 生产就绪：数据保留与脱敏](../2026-09-12_smart-service-tech-design/issues/48-prod-data-retention-pii.md) | ready-for-agent | 未单列负责人 | 3 |
| [50: 生产就绪：告警与运行手册](../2026-09-12_smart-service-tech-design/issues/50-prod-alerting-runbook.md) | ready-for-agent | 未单列负责人 | 3 |

## 全量回归阻塞

- `config/models.yaml` 的 domestic.guide.step.chain 有 4 项，但 retry.chain_max=3，配置加载拒绝；导致 9 项全量后端测试失败，也阻碍新进程按当前配置启动。
- 全局 lint：app/guide/steps.py 未用 re；app/rules/service.py 前置注解引号；tests/test_sessions_cancel_stream.py 可变类默认值。均不在本轮新增业务范围。
- 本票独立验证：50 后端测试通过、前端全量 97 通过、最终摘要 5 项及构建/契约检查通过。
