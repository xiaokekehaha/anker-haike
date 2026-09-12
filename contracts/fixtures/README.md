# 共享契约 fixtures

前后端测试共同读取本目录。所有样本使用虚构数据，不保存真实消息、订单、图片或密钥。

- `a1.json`：A1 排障成功的事件序列占位，目前为 `[]`，不表示 A1 已实现或通过。
- `events.valid.json`：每种 ServerEvent 至少一个合法载荷，验证事件字段与嵌套层级；这是独立协议样本集合，不是一轮真实业务流。
- 后续 A2 / A3 与故障场景使用 `a2.json`、`a3.json`、`failure-<场景>.json`，内容统一为事件数组。
- 业务序列中 seq 按会话递增；run_id 区分各轮；本轮最终有 done，卡片反馈轮遵循 awaiting_input / done 配对。完整业务样本由对应票据填充。
- 契约源为 `contracts/haike_contracts/`，Schema 在 `contracts/schema/`；修改后运行 `make contracts`，同时更新受影响样本。
- 前端校验入口：`frontend/src/api/events.ts` 的 `parseServerEvent`；后端入口：`haike_contracts.events.parse_event`。

本目录由票 04 建立，Python 定义与导出器由票 03 维护。两端不得为使样本通过而各自维护不同的协议定义。
