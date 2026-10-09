# 订单查询与交接事务保证核对

状态：代码核对与设计说明，未修改实现。用户询问查询订单的事务、原子性与一致性如何保证。

## 术语

- 事务：把一组数据库操作作为一次提交或撤销的工作。
- 原子性：这组写入全部成功或全部失败。
- 业务一致性：订单归属、合法状态迁移等约束成立。
- 读取一致性：拼接出的资料来自一致的数据快照；主要属于事务隔离问题。它不等同于资料一定是此刻最新状态。
- 幂等：同一次操作重试不会重复产生业务结果。它本身不保证多项写入一起提交，也不能用业务意图相同代替请求相同。

## 当前实际实现

1. 订单和物流内容不在实时订单数据库中。OrderBook 初始化时从 OfficialData.orders 加载 data/official/orders.yaml，按订单号建立内存字典；get_order 返回该对象。Order 同时包含 lines、packages。OfficialData 使用 cached_property。正常只读路径使用同一份进程内资料，因此没有外部订单并发变更；也没有实时同步或刷新机制保证最新。
2. 单次查询的执行记录另存 action_executions。consult 使用 session_id、input_id、动作类型和参数哈希构成请求键；执行存储使用事务锁领取执行，成功回执可重用。这个机制用于同次输入重放，不提供跨查询的数据版本保证。
3. BusinessContext.bind 对缺失或多订单歧义先澄清；observe 检查回执标识与请求相符，并按订单对象归档事实。CaseService.bind_order 禁止已绑定案件换成另一订单。这些是应用层业务约束，不依赖大模型自觉维护。
4. PostgresCaseStore.mutate 在 conn.transaction 内锁定案件行 SELECT FOR UPDATE，再更新案件、事件、人工决定；单次 mutate 的这些变更一起提交。传入 expected_revision 时另有版本核对。该保证不自动覆盖多次 mutate、会话 checkpoint 或外部业务系统。
5. hand_off_request 仍分开调用 transition、record_review_request、record_handoff，形成三个提交边界。round3 的隔离 HTTP 验证已复现摘要写入失败、重试跳过补齐的问题。
6. PostgresCaseStore.get/_read 分别读取 cases、case_events、human_decisions。其共享连接池设置 autocommit=True，get 没有包裹统一快照事务。因此并发修改时不能保证返回的案件状态和事件来自同一个时间点；这是静态代码确认的保证缺口，本轮未另做数据库并发复现。
7. consult 在执行器取得查询回执之后，又调用 get_order 渲染事实。当前静态资料下读到同一对象；未来换成实时后端时，回执和二次读取可能不一致，不能将当前行为当成实时系统的一致性保证。

代码位置：app/backends/service.py:55–65、app/official/models.py:110–125、app/actions/executor.py、app/actions/store.py、app/conversation/business.py、app/cases/service.py:151、app/cases/store.py:96–168、app/sessions/runtime.py:29–35、app/sessions/l3.py:626–650 与 736–755。

## 建议的保证边界

- 同一轮回答使用一份完整查询回执，携带订单标识、资料版本或更新时间、查询时间。不要在回复前无版本约束地重读并替换回执内容。
- 同库多表详情可使用单条聚合查询，或只读的一致快照事务；仅包普通事务不能自动假定多条语句同一快照。不要跨模型调用或等待客户期间长期持有数据库锁。
- 交接状态、客户请求、摘要放入一次案件事务，成功后才发送成功反馈。跨案件事务和会话提交用稳定请求编号及可靠重放恢复。
- 如果未来连接真实订单系统，“查询后暂停”必须由订单系统在执行时原子地检查状态/版本并暂停；本地查到尚未发货不代表执行时仍未发货。对方返回冲突时重新查询/交人工，不能声称已暂停。
- 跨系统操作没有默认的共同数据库事务。用请求编号、受理回执和明确的待确认状态衔接；在当前主办方静态数据环境中只能登记人工请求，不能证明外部仓库暂停或退款完成。

本轮仅核对本地实现，不执行数据库写入或重跑模型测评。
