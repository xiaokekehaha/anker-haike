# 任务计划：观测台修改与重构方案

## 目标
审计观测台前后端现状，按使用者角色给出修改 / 重构方案与分层落地路径，供用户决策；本轮不动代码。

## 阶段
1. 通读 `frontend/src/admin/**`、`orchestrator/app/admin/**`、`analytics` schema / derive / queries；对照 9/13 设计与范围文档 — complete
2. 5174 走查五个页面，抓真实接口数字 — complete
3. findings.md（S / K / A / J 四组问题 + 数据可得性）与 plan.md（P0 / P1 / P2 + E1–E8）— complete
4. 用户选定 P0 + P1，已落地并通过类型检查与全部前端测试 — complete（取舍见 addendum.md）

## 边界
- 不改代码、不改契约、不提交。
- 不触碰其他会话的未提交改动。

## 下一步
P2（source 列、queue join、导出、契约化）等用户排期；本次改动未提交。
