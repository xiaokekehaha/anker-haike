# 发现

- 观测台：7 轮用户消息，产品 ANKER-A1289，最终需人工处理，原因“适用步骤已耗尽”，执行步骤数为 0。
- 当前工作区已有他人改动：RELEASE.md 与 releases/20260918-8c1cbf6/，不触碰。
- 相关既有文档记录了另一会话的观察题补答/资源恢复缺陷，不能直接套作本会话结论。
- 本会话第 5 轮已接受 `pb_737_display=laptop_uvp`；第 6 轮“已在”被接受为 `device=true`。因此观察丢失、资源无法恢复均不是本会话终止的直接原因。
- 最终 checkpoint：`symptom_codes=[pb_no_input]`；候选为 `pb_737_output_check`、`pb_737_display_reset`，都被 laptop_uvp 观察排除；`next_action=handoff_offer/knowledge_coverage_missing`，`steps_executed=[]`、`exhausted_plans=[]`。
- 计划库实际有 `pb_737_laptop_uvp`，但其症状码不包含 pb_no_input；decide_next 的观察解锁路径仍先按旧症状码过滤。
- 第 7 轮重新 retrieve/synthesize 后重复同样结果；前台回复说资料无适用路径，观测台把 R2 统一显示为步骤耗尽，两者不一致。
- 数据读取使用独立连接并设置 `default_transaction_read_only=on`，未运行图、未调用模型。
- 使用真实最终状态离线调用 decide_next 复现 handoff_offer；只在计划库内存副本放宽 UVP 计划的症状码，便得到 observation_unlocked_plan，确认直接阻塞点。该反事实不是修复建议。
- 现有恢复测试从 pb_no_output 起步，不覆盖“有输出→自身充电慢”的交互；两个相关测试文件合计 57 项通过。
- 已有事实修订、问题恢复、资源恢复、案件重开，但没有统一的修订后候选重建机制；外部服务单接口没有取消或变更协议。
- 计划库、事实来源、确定性授权、持久化基础可保留，首要工作是统一候选适用性和下一动作决策，补足充电方向及问题范围澄清。
- 最终发现、源码位置、实施顺序和验收场景已写入 analysis.md；裁剪证据保存于 evidence.json。
