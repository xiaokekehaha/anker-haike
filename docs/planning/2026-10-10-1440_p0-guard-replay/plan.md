# P0 约束真实回放验证（2026-10-10 14:40）

## 目标

验证 spec_2026-10-10-1427_official-63-p0-guards.md 的三处约束在真实模型下生效：T53/B15/R05 不出退款任务；T50/B10 首问不预设右侧或反转左侧；T36/T53 卡片不出现换机承诺或索地址。

## 方法

1. `docker compose up -d --build orchestrator` 后确认运行指纹与工作区一致。
2. T36、T50、T53 用 1938 轮长路径驱动（`evaluate_long.py` 原样副本）：原文首发，动作卡固定未解决，只在被问型号时补官方产品列。
3. B10、B15、R05 用 1321 轮分层驱动（`evaluate.py` 原样副本，`scenarios.json` 只保留这三条，模拟答复不变）。
4. 判据只看本次三项：任务队列与对客文字是否含 refund；首问是否含 right / 反转左侧；客户可见文字与卡片是否含 replacement unit / shipping address / we will send|replace。

## 约束

- 6 个会话，不代表 63 单整体比例；单次结果不证明稳定性。
- 只写本目录；不改驱动逻辑与历史报告。
