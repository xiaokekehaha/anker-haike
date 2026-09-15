# 82: 多语言（zh / en）

**What to build:** interpret 输出 `language`（zh / en / other，规则 + 模型）；`session_preferences.language` 持久化，用户可切换；prompt 层：系统提示、情绪层、澄清 / 拒绝 / 顺序告知等确定性模板全部双语（`config/i18n/{zh,en}.yaml`）；知识检索：查询按语言路由到对应语言文档（front-matter `lang`），跨语言时用 embedding 双语能力兜底并标注；政策条款双语文本（clauses.yaml `text_en`）；前端 i18n（卡片按钮、进度条、状态）；ModelRouter 无需改。`other` 语言 → 英文回复 + 人工选项。

**Blocked by:** P0 66；P1 70（lang 元数据）

**Status:** todo

**Owner:** —

- [ ] 英文 A1 / A4 / A5 端到端；中途切语言后后续回复跟随
- [ ] 模板无硬编码中文（脚本扫描 `app/` 中用户可见字符串）
- [ ] 意图评测英文样本 ≥ 20 条，准确率报告

**设计依据：** 差距分析 §4.6；01 §2.2
