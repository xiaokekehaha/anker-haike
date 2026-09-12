# 17: intake 结构化抽取与情绪识别

**What to build:** intake 节点一次 internal 调用同时输出情绪三级标签 + strategy、product_hints、symptoms、wants_human；strategy 写入状态并注入系统提示三层中的第二层。抽取失败视为 calm、hints 为空。

**Blocked by:** 10（结构化 invoke：三种输出策略与 Pydantic 校验）、15（规则服务骨架与 CP-in 安全升级）

**Status:** ready-for-agent

- [ ] 对 A1 / A2 / A3 演示话术抽取结果与预期一致（fixtures 金标）
- [ ] wants_human=true 等价于 R3 命中
- [ ] 系统提示三层结构：固定角色、每轮情绪策略、每轮状态摘要
- [ ] 抽取失败走降级不阻断流程

**设计依据：** 03 §1.1、§1.2、§4
