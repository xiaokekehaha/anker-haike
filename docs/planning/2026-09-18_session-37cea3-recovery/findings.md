# 证据记录

管理页面显示七轮消息、零个步骤，最终原因 R2（适用步骤耗尽）。

对话：用户说 A1289 给自身充电慢；助手询问连接设备后的屏幕状态。用户先说设备不在身边，再补充“连接笔记本时显示 UVP／屏幕显示异常”。助手只询问设备是否在身边；用户说“已在”后直接生成无适用路径摘要；再次补充相同观察仍生成摘要。

后续已核验底层状态：device=true；steps_executed、step_attempts、exhausted_plans 都为空；有效症状码仍只有 pb_no_input（自身充电问题）；观察 pb_737_display=laptop_uvp。

decide_next 的观察解锁候选先调用 allowed_for(symptom_codes=codes)，UVP 计划只声明 pb_no_output / pb_indicator_abnormal / pb_port_damage，因此被旧症状码过滤。剩余 output_check / display_reset 又被 laptop_uvp 观察排除，最后误报 knowledge_coverage_missing。

离线重放真实 checkpoint：handoff_offer / knowledge_coverage_missing。只在内存增加既有 UVP 候选：step / pb_737_laptop_uvp。数据库和业务代码均未改动。

match_reply 对“连接笔记本时显示 UVP／屏幕显示异常”返回 laptop_uvp；代码在多个选项命中时按命中文本长度选一个。answered 的 observation_request 不再进入普通回答匹配，改选依赖独立 corrections 路径。

已有 34 项相关后端测试通过（操作条件、事实归约、问题生命周期、待办流程）。这些通过不代表本次交叉状态路径正确；专门的诊断断言仍失败。
