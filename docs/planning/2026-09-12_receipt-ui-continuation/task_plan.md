# 票 39/40 凭证前端接续

## Goal
补齐凭证上传/跳过/字段确认/快照恢复，串联已完成的票 41；修复上轮确认的配置和 lint 阻塞。

### Phase 1: 状态核对与认领
**Status:** complete
### Phase 2: 凭证输入与卡片生命周期
**Status:** complete
### Phase 3: 测试、构建与回填
**Status:** complete

## Decisions
- 本轮认领票 39 前端及票 40 前端，真实视觉识别评测留票 42。
- pending_input 决定输入模式；卡片等待阶段禁止普通消息误提交，人工请求保持可用。
- guide.step 保留最多三个模型和当前可用 DeepSeek；不提高全局模型调用上限。
- 保留工作区已有改动，不批量提交或回退。

## Errors Encountered
- 初次批量读取输出截断，后续缩小范围。

## Next Step
凭证前端转交共享工作树中的并行会话；本轮实现计划转至 ../2026-09-12_observability-continuation/。
