# Spec

独立需求审查发现 4 项缺口，均已通过隔离 HTTP 会话复现。使用确定性意图、项目内存案件存储和假依赖，不调用真实模型或知识库。证据：[spec-repro.json](spec-repro.json)。

1. **[P1] 去重吞掉已变更的客户要求。** `orchestrator/app/sessions/l3.py:638`。需求要求“保留对象范围、条件和客户原话”“不同请求不能复用同一幂等编号”。先请求暂停，再改成取消整单，两次都映射 order_change，第二次直接跳过记录；客服仍说已交接，人工摘要和任务原话却仍是暂停请求。这是新增交接分支的缺陷。
2. **[P1] 摘要写入失败后重试无法补全交接。** `orchestrator/app/sessions/l3.py:643`。需求明确“三项写入收敛到一次 store.mutate”。先建立问题，再注入摘要写入失败，案件已进入队列；客户重复请求时，代码因状态和意图相同跳过写入，回复已交接，但 handoff_summary=null。现有三次独立事务及新增去重共同导致，不能视为可选复杂度。
3. **[P2] 请求人工后仍自动推进非查询任务。** `orchestrator/app/sessions/l3.py:609`。需求规定“第一阶段只让……独立只读查询继续”。换货并带后续排障任务，客户在方案卡选择 request_human 后，系统仍回复 Next up: device troubleshooting，排障变 active，阶段从 awaiting_human 覆盖为 context。这是本次出口改动引入的回归；未发现实际发出危险步骤，不能据此声称安全闸门被绕过。
4. **[P2] 新等待状态没有人工决定后的出口。** `orchestrator/app/sessions/l3.py:623`。需求要求“人工批准或驳回只更新关联请求”。后台驳回成功后案件为 rejected、会话为 done，关联任务仍为 waiting_human；既有 apply_human_decision 未适配新状态。

Spec 合计：4 项，其中 2 项 P1、2 项 P2；该轴最高优先级问题是变更请求丢失和不完整交接重试仍报成功。P1 表示应优先修复，P2 表示需要修复的流程或状态问题。
