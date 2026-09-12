# 06: 前端 reducer、SSE 解析与 ProgressBar

**What to build:** 前端用 fetch + ReadableStream 手写 SSE 解析，reducer 处理 run_started / progress / ping / done，驱动 idle ↔ streaming 两态，ProgressBar 随 progress 事件推进。用户发出一条消息后能看到阶段条动起来并回到可输入状态。

**Blocked by:** 04（前端 TS 类型生成、CI 比对与 fixtures 骨架）、05（会话创建与 SSE 基础流）

**Status:** ready-for-agent

- [ ] reducer 为纯函数，对 fixtures 中的事件序列有单元测试
- [ ] Composer 发送文本后进入 streaming，done 后回到 idle
- [ ] ProgressBar 五阶段切换带 300 ms 过渡
- [ ] 15 s 无事件时显示「仍在处理」提示
- [ ] session_id 存 sessionStorage

**设计依据：** 05 §4–§6
