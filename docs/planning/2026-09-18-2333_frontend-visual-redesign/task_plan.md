# 任务计划：前端可视化重构方案

## 目标
从客服助手的工作方式出发，给出多套结构不同、依据充分的前端样式与交互方案，供用户次日决策。本轮不改生产代码。

## 阶段
1. 审计现状：通读壳层与全部卡片组件，用真实会话在桌面 / 手机走查 — complete
2. 收集依据：仓库设计文档、赛题材料、线上客服实测、外部 UX 规范 — complete
3. 写出三套方案 + 共用底座 + 对比 + 建议 + 待决策 — complete（plan.md）
4. 可点击原型：`frontend/prototype/visual-redesign.html`，`?variant=A|B|C`，评审视图 / 手机框 / 深色 — complete
5. 用户决策（D1–D8）后开票落地 — pending

## 边界
- 不改 `frontend/src`，不改契约；评审视图的逐轮情绪作为可选契约扩展记在 D2。
- 原型是抛弃件，不进构建入口；选定后按 prototype 技能约定推到一次性分支。
- 不触碰其他会话的未提交改动（`RELEASE.md`、`releases/`、`2026-09-18-20_session-reversibility-review/addendum.md`）。

## 下一步
等用户在 D1–D8 上选择；然后按 plan.md §7 拆票，先做阶段 0 底座。
