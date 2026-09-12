# 发现

- 上轮票 02 已完成；Claude 的新改动集中在 contracts/haike_contracts/，票 03 尚未标记完成。
- 票 04 依赖票 03，前端生成流水线可以独立编写，最终须用真实 Python 导出的 Schema 验收。
- 契约 §9 约定 events.schema.json、actions.schema.json、snapshot.schema.json 及共享 contracts/fixtures/*.json。
- AGENTS.md / CLAUDE.md 新增「只查询数据库」，本票无需访问数据库。
- 当前导出位置实际为 contracts/schema/（与设计文档少一层 schema 的示例不同）；build_schemas() 可成功生成三份 draft-2020-12 Schema，保留现有实现路径。
- events 使用 discriminator.type + oneOf + $defs（25 个定义）；actions 另含未被根类型引用的 ActionResult / ActionConflict，生成时需保留不可达定义。
- 官方工具参考：Zod https://zod.dev/json-schema 提供 fromJSONSchema（实验 API，需锁版本并用真实契约回归）；json-schema-to-typescript https://github.com/bcherny/json-schema-to-typescript 支持类型生成与 unreachableDefinitions。
