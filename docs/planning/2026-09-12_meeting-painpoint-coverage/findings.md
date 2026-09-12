# 发现

- 当前项目为 FastAPI + LangGraph 编排、React 前端、WeKnora 知识服务、PostgreSQL 与 Redis。
- 工作树存在大量未提交和新增实现；旧差距分析中步骤、凭证占位结论可能过时，必须重读代码。
- README 定位为扫地机器人售后；会议范围涵盖多产品、人工工作台和业务执行。

## 首轮代码核查
- 设计明确仅中文（F12）、模拟订单（F13），只支持扫地机主线，凭证核对不输出质保资格。
- SummaryCard 与 EvidenceDrawer 已实现，但前者是摘要复制、后者展示知识片段，不是原文译文对齐的人工证据工作台。
- 新代码已包含凭证 OCR / 字段确认 / 模拟核对，旧记录的凭证占位已过时。
- graph.py guide_entry 仍占位并直达 END；apply_action 无 step_feedback；rediagnose 路由仍拒绝。guide/verify 独立文件存在不能视为已接线。
- 当前动作协议无客服选方案、审批、发送与业务执行动作，summarize 后 END。

## 能力与验证
- KnowledgeScope 只含 product_state/category/sku，缺少购买地、服务地、政策生效时间与优先级；ReceiptLookup 明确只核对模拟事实。
- ModelRouter 首个成功结果直接返回，是失败降级而非双模型审核。
- VisionObservation 仅 observations/visible_parts，缺少清晰度与所需证据状态；读图失败目前继续按文本处理。
- Knowledge ingest 为批量导入和版本更新，未发现工单候选知识/人工审批/发布工作流；chunking_config.enable_multimodal=False，步骤模型也无媒体字段。
- metrics 现有首可见与首卡延迟 P50/P95；业务准确率、客服耗时、CSAT 的完整采集和基线尚未发现。评测票 42 在其他任务处理中，不能据此宣称已达标。
- 验证：定向后端 123 passed / 2 deselected（排除真实 WeKnora 与独立 schema）；前端 3 文件 8 tests passed。测试以假模型、内存状态、模拟数据验证行为，不证明真实业务准确率或线上 SLA。
- 摘要问题字段取首条用户原文，后续补充进入 observations；可选 polish 只允许空白标点整理并校验原句，已有保留原话的基础，但没有原文译文对照与来源定位。

## 最终复核更正（优先于前文）
- 核查期间主图发生并行更新：新增 guide 节点并进入 await_input；apply_action 新增 step_feedback 和 _apply_step_feedback，推进到下一卡、done 或升级。此前“占位未接线”判断已失效。
- verify 是 apply_action 内的判定，不要求独立图节点；不能再用“图无 verify 节点”推断缺能力。
- 同组后端重新验证为 118 passed / 5 failed / 2 deselected（8.60s）。此前 123 passed 仅属于旧工作树。
