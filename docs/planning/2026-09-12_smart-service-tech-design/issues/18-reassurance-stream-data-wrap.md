# 18: 安抚句流式先出与 <data> 包裹

**What to build:** 情绪为焦急 / 愤怒时，第一段可见文本是安抚句并先于任何卡片到达；angry 时后续步骤每步不超两句。所有外部文本（用户输入、检索片段、OCR）进入 Prompt 时包在 data 段并声明非指令。

**Blocked by:** 13（stream 入口与 message 事件）、17（intake 结构化抽取与情绪识别）

**Status:** ready-for-agent

- [ ] A2 话术下安抚句 delta 先于 progress(diagnose) 到达
- [ ] Prompt 模板文件化到 prompts 目录并带版本号
- [ ] 注入「忽略以上指令」类文本不改变模型输出结构（测试用例）

**设计依据：** 05 §6；07 §15；03 §4
