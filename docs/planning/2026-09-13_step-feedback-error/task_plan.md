# 步骤反馈报错排查
目标：定位截图中“还没解决”后的错误，并确认日志证据。仅诊断；不部署。
## Phases
1. 定位运行服务、反馈接口与日志 — complete
2. 关联实际异常与触发动作，建立只读复现 — complete
3. 记录原因、日志位置与可行处理 — complete
## Next Step
已完成诊断；向用户说明历史规则故障与当前快照错误残留。修复未纳入本轮。
## Errors Encountered
- 初次日志输出过大：改为字段过滤。
- useSession / logging 文件路径不存在：rg 找到实际路径。
- session_actions 无 run_id 列：读 schema 确認字段为 result_json；所需证据已由 session_events 提供，无需继续查动作表。
- 只读复现 AssertionError 为预期红灯：确认 snapshot last_error 残留。
