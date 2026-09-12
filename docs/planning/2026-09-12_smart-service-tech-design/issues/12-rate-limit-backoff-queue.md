# 12: 限流退避与全局有界队列

**What to build:** 429 采用 1 / 2 / 4 s 加抖动的指数退避；全局并发队列上限 50，满时立即返回 recoverable error 让用户稍后重试而不是堆积。

**Blocked by:** 11（降级链与 task 预算）

**Status:** ready-for-agent

- [ ] 并发压测下队列满时请求快速失败，返回 error(recoverable=true)
- [ ] 退避时间与抖动范围有单元测试
- [ ] 队列长度、拒绝次数有结构化日志

**设计依据：** 07 §13；04 §1
