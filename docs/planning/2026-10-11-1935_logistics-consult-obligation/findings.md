# 发现

- required_reads 按答案字段选工具；consult 的物流强制读取和方案分支都要求字段全集属于 LOGISTICS_FIELDS，导致背景字段能抑制物流任务。
- ORDER_FIELD_WORDS 是关键词出现检测，不能证明用户明确询问订单字段。
- tasks.enqueue 已按各意图拆分队列中的查询字段；当前 turn_decision 仍可能包含合并字段，consult 需保留真实附加查询。
- 现有未提交 l3.py 补丁仅为关键词过滤，本次会替换为语义明确的执行约束。
- graph.py 在主诉求为查询且存在 answer_request 时合并并列查询，不单独入任务队列；测试应验证没有重复查询任务及只回答一次金额，不能要求队列必有两项。
- 物流摘要没有展示 service_order_no 和 updated_at；这两个字段不应因回复去重而丢失。
