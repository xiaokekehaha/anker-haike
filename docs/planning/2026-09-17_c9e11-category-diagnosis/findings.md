# 发现

- 目标页面可访问，返回前端入口；会话内容需要读取对应 API。
- 初始工作区有未跟踪的 `data/knowledge/sources/` 和 `orchestrator/app/knowledge/official.py`，属于其他工作，不修改。

## 会话证据
- 四轮会话：用户说“我的移动电源出问题了：” → 问输出反应 → 用户说“没有” → 输出接口清理步骤 → cannot_do → 换线换设备步骤 → cannot_do → R2 摘要。
- 每轮有品类字段的节点均为 `power_bank`，产品状态为 `category_only`；检索只查移动电源手册，计划为 `pb_port_debris`。
- 最终摘要产品显示“扫地机器人（型号未确认）”；两个步骤的原始反馈均为 `cannot_do`，结束文案却写“已完成”。
- 首轮 `disambiguate` 判定澄清，随后进入 `clarify`；第一问不是模型单独生成，未发出澄清模型调用。
- 定位到 `escalation/summary.py` 的产品和完成文案回退；准备直接调用真实摘要构造函数作离线复现。

## 已核实实现
- `build_summary` 的 `category_only` 回退直接写“扫地机器人（型号未确认）”，不读 `category`。离线真实函数调用断言失败，与在线摘要一致；git blame 指向 2026-09-12 初始摘要实现，9/17 多品类扩展遗漏此处。
- `polish_summary` 只能改 `problem` 字段，不能改产品；本次品类错误是确定性代码产生。
- `disambiguate` 包含产品、症状、冲突三种澄清；前端 `progress.ts` 固定映射为“确认产品”，未表达实际追问目的。
- 输出反应问题来自 `config/symptom_taxonomy.yaml`，不是这轮模型临时生成。移动电源配置 6 个故障族、2 个二分题；`select_discriminator` 最大化较小分支的候选个数，同分保留配置前项。
- 问“输出反应”把 yes 分到自身充不进电/掉电快/发热/灯异常，把 no 分到无法输出/接口松动。两道题均为 4:2 划分，第一题因配置顺序获选。
- 这类映射把观察和故障族排他地绑定；“不能输出”本身不能证明自身充电、灯异常等其他问题不存在，复合问句也混合了两个不同观察。
- 当前摘要测试在不提供 category 时仍断言“扫地机器人”，把单品类假设固化；缺少多品类 category_only 的不变条件测试。
- 离线反转问题配置顺序，首问改变；原顺序下完整复现 `symptom` 澄清、两个输出候选、`same_applicable_plans` 与 `pb_port_debris`。
- 当前目录 20 个品类，19 个非扫地机品类在相同 category_only 摘要回退路径全部错误。
- 两次真实 cannot_do 输入摘要构造函数，稳定复现“已完成”；计划第二步 cannot_do 直接走 EXHAUSTED，只有 not_solved 才去第三步。
- 既有摘要测试 `3 passed in 0.17s`；本轮只做诊断与方案，不把既有测试通过视为缺陷已修复。
