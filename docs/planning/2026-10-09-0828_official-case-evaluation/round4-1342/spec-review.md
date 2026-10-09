# Spec 复核

固定评审提交：46b1777d845d3052b1b010714d2be9af56a5c315，相对父提交 502b2f345b7e88a2ebdbec736923d96ed5b9c14b。运行期间 HEAD 前进到仅更新说明的 5307876，所测 service.py、tasks.py、l3.py、graph.py、interpret.py 与固定提交无差异。

隔离 HTTP 使用内存会话/案件存储及测试语义输入，关闭模型与知识库；6 个独立会话保存 9 组状态证据。临时采证测试运行成功（1 passed，0.98 秒）；这是采证程序通过，不代表下面两个缺陷通过验收。原始证据：[spec-repro.json](spec-repro.json)。应用及现有测试均未修改。

## 已修复

- 原话由暂停改成取消整单：`request_changed` 与最新交接摘要均保存新要求，等待任务原话同步更新。
- 摘要生成异常：一次 `mutate` 回滚交接，案件停在 open、仅保留之前的 order_identified，没有成功话术。新输入重试后完整进入 awaiting_approval，有 review_requested 与 handoff_summary。本次未覆盖 Postgres 故障或 checkpoint 中断重放。
- 方案卡请求人工：换货任务 waiting_human，排障任务 pending，阶段保持 awaiting_human，无排障步骤卡。
- 人工驳回：对应改单任务变为 done，案件 rejected。未把等待任务遗留为 waiting_human。

实现说明仍称存储中断“不做”，但代码已采用单次 mutate，上述异常注入证实了本地原子回滚。

## [P2] 要求补充的信息未收到，普通查询却把申请重新送审

定位：[l3.py:974](../../../../orchestrator/app/sessions/l3.py#L974)，相关调度在第 1036–1038 行。

复现：暂停主机并查物流 → 人工 request_info，要求确认暂停哪个商品 → 客户只问一次发货日期。人工决定将等待任务设为普通 pending；物流查询结束后调度器选择该任务，使用原来的暂停请求重新交接。回复出现 `Next up: order change`，案件从 awaiting_confirmation 回到 awaiting_approval；客户未补充所需信息。

需求依据：方案“必须成立的约束”第 2、3 项要求区分等待客户与可推进任务；影响约束要求查询结果不能清除等待材料限制。修正应保留不可调度的等待补充状态，只有补充条件满足才重提。

证据键：`request_info_then_readonly_query`。对照 `request_info_then_actual_supplement` 表明实际补充信息后能重新交接。

## [P2] 人工批准后提交仍被阻止，任务已提前标成办结

定位：[l3.py:982](../../../../orchestrator/app/sessions/l3.py#L982)，提前生成 done 的代码在第 974 行。

复现：换货加排障 → 补齐图片/SN → 方案卡选择人工 → 客户补报烫伤 → 人工批准 replace。`apply_human_decision` 先把任务改 done，再调用 authorize；安全闸门拒绝后案件回到 awaiting_approval，但 next_task 只更新 active/pending，无法恢复这个 done 任务。

实测最终案件等待人工、换货任务 done、排障任务 pending。服务单提交次数为 0，安全限制仍有效，不能表述为发生了危险执行。

需求依据：方案“人工批准或驳回只更新关联请求；若批准还需后续动作，继续通过原有授权检查，不把批准自动解释为……整体任务已解决”。应在提交得到确定结果后结算任务，失败或再次等待时保持对应状态。

证据键：`approve_then_gate_blocks`。

## 未列作缺陷的疑点

`settle` 只按 intent 匹配，但队列当前按 issue 保存，普通不同订单会切换 issue；未获得自然 HTTP 复现，不以纯函数构造的跨单队列认定误结单。批准/驳回的并发版本关联未做额外故障注入，结论不覆盖该项。
