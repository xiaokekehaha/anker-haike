# Spec：前端壳重设计为消费电子售后客服场景

日期：2026-09-12　分支：feat/smart-service-impl　范围：frontend/

## 背景
票 02（Codex）交付的前端空壳把欢迎区写成了「扫地机器人 · 售后支持」专属：分区标签、主标题「让清洁回到好状态」、描述文案、meta、扫地机插画。设计文档 05 对这段没有要求。赛题面向 Anker 全线消费电子售后（情绪安抚、S1 Pro 歧义、经销商订单），前端不应把品类写死。

## 目标
1. 页面文案与视觉不绑定单一品类，覆盖扫地机、吸奶器、充电、音频、安防、投影等品类。
2. 工作区从「对话准备中」空态改为真正的客服对话骨架，与 05 §3 组件结构对齐，后续票 05/06/13/20 直接往里接。
3. 保持票 02 已验收项：健康灯、10 s 轮询、深浅色、390 px 无横向溢出、测试与类型检查通过。

## 改动
| 文件 | 说明 |
| --- | --- |
| src/App.tsx / App.module.css | 欢迎区改为紧凑标题 + 三条服务承诺；工作区 = 标题栏（内嵌健康状态 chip）+ ProgressBar + ChatPane + Composer；降级提示条 |
| src/components/ProgressBar.tsx | 五阶段：理解需求 / 确认产品 / 定位故障 / 分步排障 / 处理结果；`stage: Stage | null` 按后端 Stage 枚举映射（intake→0, disambiguate→1, diagnose→2, guide/verify→3, escalate/out_of_scope/done→4）。票 06 只需传入 reducer 中的 stage |
| src/components/ChatPane.tsx | 欢迎态：助手开场白 + 品类 chips（6 类）+ 4 条示例问题（含 S1 Pro 歧义、经销商订单）。点击写入 Composer 草稿。后续消息 timeline 接在同一容器 |
| src/components/Composer.tsx | 文本框、照片按钮、请求人工、发送。`offline` 为 true 时可编辑草稿但不可发送，提示「对话服务接通后即可发送」。票 06 把 `CHAT_OFFLINE` 换成 reducer 的 ui 状态 |
| index.html | meta description 去品类化 |
| src/App.test.tsx | 断言无单品类文案、五阶段渲染、示例问题写入草稿且发送禁用 |

## 不做
- 不接 SSE、不建 reducer（票 05/06）。
- 不做 ProductCard / StepCard / ReceiptCard / SummaryCard（票 21/34/40/16）。
- 品类 chips 目前是前端常量；票 19 产品目录落地后可改为从后端拉取。

## 验证
- `npm run typecheck`、`npm test`（53 通过）、`npm run build`。
- 浏览器：桌面与 375 px 两种宽度截图检查，无横向溢出。
