# 证据与发现

- 目标会话：7a0077bb32494ca8b366c8f87e12118c。
- 工作区开始时仅有其他任务的未跟踪文件 docs/planning/2026-09-13_bounded-agentic-rag/addendum.md，不触碰。
- 本报告将以历史事件为事实依据，以当前源码解释实现；若版本不同，单独说明。

## 会话原文初步核对
- 会话共 10 轮运行、7 条用户文本、3 次 cannot_do（无法操作）按钮反馈。
- 首轮“怎么这么难用”识别 dissatisfied，但直接问输出反应，没有安抚。
- “永不了”被保留为无法解析的判别回答，机器人重复相同问题；“没有”后进入 pb_port_debris 通用排障方案。
- 三步清理接口、换线换设备、长按电源键复位均 cannot_do；首次摘要按 R1b（连续无法操作）产生，handoff_status=prepared。
- “我很暴躁”和“我很不开心，你们产品太烂了”各产生两段回复：固定致歉/人工/补偿评估文案，随后“当前尚未有可下发的排查步骤”。“我很不开心”仅收到后一段。
- 最后“永不了啊 我的充电器”后再次检索，按 R2/no_supported_followup 生成摘要；明确尚未接入真实转接。
- 最终情绪 angry/direct_resolution；最新摘要保留 6 个输入的情绪轨迹。
- 检索已包含 A1289 专用复位资料，却下发了通用的长按电源键 10 秒；需要核对计划与证据选用机制。

## 运行日志核对后的结论

- 本次确实做了情绪识别与策略选择，但可见回复没有稳定落实策略；没有证据证明用户情绪被有效缓和。
- “永不了”不能简单归因于错别字识别差：该轮 intake 首次返回不符合结构约束（business_reference.quote 不是字符串），重试超时，最终 source=degraded、intent=unknown，情绪落为默认 calm。耗时 8.518 秒。
- “我很不开心，你们产品太烂了”：模型先判 dissatisfied，关键词“太烂”将结果提升为 angry，趋势 rising，选择 de_escalate_and_offer_human。
- “我很不开心”：正确判 dissatisfied，选择 direct_resolution；实际回复落入诊断固定解释，不含针对情绪的回应。
- 三次不能操作的内部计数为 executed=0、skipped=1/2/3。首次升级由 R1b 触发；末轮为 R2/no_supported_followup，并非情绪减负分支 burden_prefer_proposal。
- 已核对运行容器与本地 graph.py、reply.py、decision.py、emotion/policy.py 的 SHA-256，四个文件一致。当前仓库 HEAD=b907437；历史行为判断仍以本次日志为准。
- 优先优化情绪回复路由、型号资料与步骤一致性、不能操作后的分流、降级时情绪状态保留、人工能力文案。

## 修改方案补充取证

- guide/verify.py 将 cannot_do 追加进 steps_executed，虽然不增加 executed 计数，guide/steps.py 与 diagnose/decision.py 仍将该列表全部用于操作去重。修改不能只调阈值，需要区分操作历史、真实执行和暂时受阻，允许用户条件变化后明确恢复。
- PlanStep 当前没有操作资源前提；AppliesTo 只支持 category_generic/sku 和 sku_list。型号专用优先与执行条件需落到可验证的适用性模型及步骤发布检查。
- StepFeedbackPayload 已有可选 note，但没有不能操作的结构化原因；当前按钮文案为“做不到 / 跳过”，混合不同用户意图。首版可用已有备注和一次文字追问，结构化原因控件属于后续体验改进。
- effects.py 已持久化消息与卡片并去重；统一回复必须复用该机制，不能在事件层按数量丢消息，否则会影响摘要、卡片或业务执行回执。
- reduce.py 的 ISSUE_FIELDS 包含情绪轨迹但没有 emotion 本身，reduce_turn 末尾又从每轮语义默认值重建 emotion；新情绪状态需要单一写入者并按问题保存。
