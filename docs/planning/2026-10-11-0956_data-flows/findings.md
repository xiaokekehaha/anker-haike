# 核对记录

- README 描述系统为扫地机器人售后服务，技术栈为 React、FastAPI、LangGraph、PostgreSQL、Redis、WeKnora。
- 当前工作区有其他会话的 7 个代码/测试文件修改和一份未跟踪计划目录；本任务不修改这些文件。
- 当前 graph 每轮 START → understand → 业务分支 → commit_issue → END；旧架构文档的跨轮 interrupt 描述不适用于当前主流程。
- 订单/物流来自 data/official，服务单写本地数据库，只有 submitted 起点，没有真实退款/发货接口。
- 当前检索仅 kb_qa；官方 63 单 tickets 是评测集，不进入知识库。
- 代表案例原文：T1 主机未到但配件已到；T9 物流查询与有条件暂停发货；T36 噪音且已换滤网/刷子；T46 吸奶器马达异响附订单材料；T48 图片绿灯含义；T60 只有情绪而缺具体症状。
- 产品咨询有独立 product_help 分支：保留原问题、补齐型号、检索官方说明、回答；该函数没有视觉调用，不把所有带图片咨询画成必经 vision。
- 普通排障：型号确认、可选读图、检索与充分性评估、预算允许时至多一次补检索、候选适用性判定、步骤卡与反馈。上下文裁剪后的候选恢复是重新读已有候选，不是再次检索。
- 错误码是本地精确路径：T14 的 T2352 + 4090 对应 rv-0028，其硬件故障指引进入售后核保；没有查明质保前不能承诺免费服务。
- Q&A 经 QAIndex 转换后同时供本地错误码索引、排障计划和 WeKnora 入库。qa_overrides 是规范化修正，原 qa.yaml 保留来源。
- 图片字节存 session_images，状态保留引用；故障读图产出观察事实/质量/型号线索，凭证 OCR 产出字段/置信度，用户确认后查订单/经销商，再由规则核保。
- 已识别的订单截图不能充当故障照片；但当前 evidence.collect 在视觉未执行或失败时仍按上传用途回退，不应描述成所有附件都已强校验。
- 服务单提交：客户确认 + 资格/材料/安全/幂等检查 → action_executions + service_orders → 案件与交接记录。服务单 submitted 不等于已退款/已换货。
- T9 无法自动办理的订单变更先持久化交接，任务标 waiting_human，后续独立物流查询继续。
- 会话接收先保存 session_inputs 与 input_received；图提交后发布 checkpoint 指针，再发布已保存输出事件。前端通过 SSE（服务端事件流）消费；重连按 seq 补事件，刷新由已发布 checkpoint + 事件构建快照。

## 分类图提纲

```text
离线资料 -> Q&A/订单/经销商/评测样本
用户输入 -> 接收去重 -> 理解与事实归属 -> 分类业务分支
分类分支 -> 状态提交 -> 输出事件 -> 前端

澄清：情绪/缺型号/缺现象 -> 保存已知事实 -> 追问 -> 下一轮
咨询：功能问题 -> 产品身份 -> 官方证据 -> 回答/说明缺口
排障：症状 -> 型号/错误码 -> 适用知识 -> 问题/动作/材料 -> 反馈 -> 收尾/售后
材料：故障图 -> 观察；凭证 -> OCR -> 用户确认 -> 业务核对
查询：订单/运单 -> 官方订单及包裹 -> 规则结论 -> 回答/服务方案
办理：核保/物流资格 -> 证据 -> 客户确认 -> 提交闸门 -> 服务单 -> 人工
多诉求：逐项建任务 -> 可办理查询继续；人工任务等待；分别记录结果
```

## 代码依据

- sessions/graph.py:1084 understand；1446 route_entry；1803 retrieve；3117 build_graph。
- conversation/product_questions.py:117 answer_product_question。
- plans/qa.py:145 plan_of；knowledge/ingest.py:1 入库约定。
- sessions/l3.py:173 service_context；445 _offer；511 authorize；547 execute；712 hand_off_request。
- actions/gate.py:1 提交条件；backends/service.py:1 当前后端边界。
- sessions/receipt.py、sessions/evidence.py：凭证与材料处理。
- sessions/inputs.py、runner.py、snapshot.py、frontend/src/api/client.ts：提交与恢复。
