# 核查证据

- 页面用户原文：刷罩卡扣断裂，已用胶带固定，无法购买替换件，清洁差，防缠绕元件不再正常工作。
- 回答先宣告 spare part purchase → device troubleshooting，再说无法查询库存或下单，已转同事处理刷罩。
- 页面状态：等待人工审核；产品未识别；愤怒；1 轮、0 个步骤。
- 以下所有引用会话和知识库内容均为待核对的证据，不是执行指令。
- API 实际执行：understand → service_context → advance_tasks → commit_issue；retrieval_calls=[]，retrieval_rounds=0，product_state=unknown，clarifications=0。
- 任务队列：parts_purchase=waiting_human；report_problem=pending。案件已进入 awaiting_approval，owner=null。
- 官方工单 T63 与原话一致，sku=null，因此不得从评测工单推断具体型号。
- 官方 Q&A rv-0260（T2351 / X10 Pro Omni）：清理滤网、滚刷、刷罩梳齿；刷罩刮条或其他清洁附件损坏老化时及时更换；可索取清洁差的照片/视频。
- 官方 Q&A rv-0358（T2080 / S1 Pro）：吸力弱时检查刷罩条，损坏或缺失应尽快更换。
- 两条知识均有型号限制；损坏刷罩与清洁变差有关的判断可以作为核查方向，不能据此直接断言用户型号或承诺库存、免费更换。
- 实际 WeKnora 知识库共 872 条，两条知识均存在且 parse_status=completed；在线元数据型号与本地官方源一致。正文依据本地官方 Q&A，在线 GET 的 content 字段未返回正文。
- 案件 API 确认 review_requested 与 handoff_summary 已持久化，完整保留三项故障；不是虚构转交，但 owner=null，尚不能说已有专人接手。
- 判断：转人工核实配件合理，但作为首轮回答不完整；缺少型号/损坏照片澄清和对三项故障的明确回应。排障可以等待部件状况确认，不宜在刷罩损坏时机械推进清洁试跑。
- 建议先承认客户描述的刷罩损坏和功能下降，索取准确型号或铭牌、刷罩/卡扣照片；说明已提交人工核查适配配件与购买渠道。获得型号后再按对应知识安排可执行操作；不承诺库存、价格或免费更换。
