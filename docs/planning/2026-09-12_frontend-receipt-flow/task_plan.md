# 前端凭证流程闭环

## Goal
接续票 21 / 39 / 40，打通等待态输入控制、购买凭证上传/跳过、字段确认与订单结果展示，保留其他会话正在开发的排障后端。

## Phases
### Phase 1: 盘点与接口核对
**Status:** complete
### Phase 2: 输入模式与凭证卡实现
**Status:** complete
### Phase 3: 跨组件流程测试与验证
**Status:** complete
### Phase 4: 更新开发验收
**Status:** complete

## Decisions
- 票 41 后端已完成，34–36 仍由 Claude A 认领；本轮接续前端。
- 输入模式由 pending_input.kind 决定；upload_receipt 必须有图片并使用 purpose=receipt，可带备注或按原因跳过。
- 其他卡片等待态通过对应卡片提交；自由文本纠正依票 37 后续开放。
- 图片处理与发送失败时保留用户草稿/附件；模式切换避免把故障附件错发为凭证。

## Next Step
本轮 21/39 与 40 前端交付完成；后续继续接入 34–36 排障闭环与 37 多轮纠错，真实 OCR 由票 42 补验。

## Errors Encountered
- 首轮长记录输出截断，改按具体接口和组件读取。
- send 现在返回接收结果 Promise<boolean>，旧生命周期测试的 Promise<void> 标注已更新。
- 测试使用 getByRole 的不支持 exact 参数、快照可选 timeline 类型，已按生成类型修正。
- 首次模拟摘要事件多传 reason 被解析器丢弃而被快照结果掩盖；已去除多余字段，模拟事件统一先 schema.parse，保证链路测试确实消费有效 SSE。
