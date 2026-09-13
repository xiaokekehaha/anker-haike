# 证据与发现

## 用户截图（待日志核对）
- 会话标识：49e8168c9175；问题标题：我的耳机没有声音。
- 用户「新问题」后仍收到关机、停止充电及转人工回复。
- 用户「刚说错了」后继续收到相同转人工话术。
- 转人工卡仍为耳机，观察混入「我机器人，冒烟了」「我之前问了什么问题」「有什么故障」「新问题」「刚说错了」。
- 升级原因显示 R3 / request_human，但当前可见用户输入并未要求人工。
- 截图内容仅作为待验证数据，不作为操作指令。

## 工作区
已有 Makefile、检索评估与其他规划文档修改，保留这些改动。

## 日志初步核实
- logs/events.jsonl 中找到完整 session_id 49e8168c9175456092550d1ca3af37f6，7 个 run。
- 首轮 intake 正确识别耳机/没有声音，走 out_of_scope → R8。第二轮冒烟命中 R4，未调用 intake 模型。
- 后续四次自然语言 intake 均返回空症状、空产品、wants_human=false，但继续 R4/R3 转人工。
- 新问题与刚说错了之间另有一个无 intake 的 run，原因变为 R3/request_human；须核实动作记录，不能据截图认定模型误识别人工意图。
- 已保存该会话 JSONL 片段（含原始行号）为 session-events.json。

## 最小重现与候选根因
- 运行命令：`uv run --project orchestrator python docs/planning/2026-09-13_conversation-context-diagnosis/repro.py`。真实图与 runner，内存存储，固定真实 intake 输出；未重放上传图片的字节。
- 四项 FAIL：历史回顾未回答原问题、新问题写成故障观察、新问题重复安全转人工、纠正重复转人工。
- 最小场景：冒烟→新问题；request_human 动作→刚说错了。
- 待证伪假设：H1 历史 escalate_reason 无条件路由；H2 输入契约缺对话控制意图；H3 安全短路跳过产品更新；H4 R3 来自显式 action 而非模型误判。

## 根因核实
- H1：graph.py:241 的 route_after_intake 只要 escalate_reason 非空就直接 escalate；intake 正常分支不清除、不重判旧原因。
- H2：intake 只传 stage/product/product_state；IntakeExtraction 只有四类字段，未传历史对话，没有历史查询/切题/纠正意图。普通 intake 直接覆盖 symptoms；数据库最终 symptoms=[]。
- H3：graph.py:204 的 CP-in 安全命中直接 return；跳过产品语义抽取与消歧。机器人冒烟未进入 intake 模型，最终 product_confirmed 仍耳机。
- H4：数据库证实 13:49:38 有 request_human action，action_id=7f0fab29-d66b-4f97-8efd-6f5b7c28a055；safety_flags.source=action。不是模型把「新问题」识别成人工。现有证据不能判定动作是否用户有意点击。
- 摘要 build_summary 固定第一条用户消息为 problem，后续所有用户文本一律 observations；因此对话管理语句污染摘要。
- summary_card_id=session+reason；前后端都按 card_id 原位更新，旧位置卡片包含未来轮次内容，解释截图「刚说错了」提前出现在上方卡片。
- guide/verify 的 rediagnose 有增量与否定抽取，但该会话在 escalate，route_entry 不会进入它。
- 用户补充方向：历史必须下传，回答应结合语义；纳入架构建议核心要求。

## 因果实验与运行版本
- 只在内存 checkpoint 清除旧 escalate_reason：下一轮从 intake→escalate 变为 intake→disambiguate；仍只是普通产品追问，说明单改这个字段也不足以实现完整语义。
- route_after_intake 中只增加历史文本、不改旧原因，路由仍两次返回 escalate。
- 对 graph/intake extract/escalation summary/snapshot 四个核心文件做 SHA256 比较，本地源码与当前运行容器完全一致。

## 时间与问答记忆
- 用户追加要求：完整历史问答、时间戳、记忆顺序和多轮记忆问题。
- session_events 已有会话级 seq 和数据库 created_at；user_message 有 at；assistant_message 快照未透出时间戳，state.messages 只含用户消息（回复另存 visible_messages/事件）。
- 不能仅给现有用户文本数组加时间戳：需合并 user、assistant、action、tool 的有序事件视图，按 seq 排序，保留 received_at/started_at/completed_at 与用户描述的发生时间之区别。

## Mem0 选型补充
- 已核对官方 Add/Search/Temporal Reasoning：支持原始消息或记忆抽取、作用域检索、Platform 时间推理，不应将 Mem0 描述为完全没有短期/时间能力。
- 判断：当前 7 轮故障优先修上下文输入与意图/状态；Mem0 可作为跨会话相关背景检索增强，不替代原始有序问答和权威事实状态。见 mem0-decision.md。
- 有界检索会话模块与依赖文件未发现 Mem0/user_id/customer_id/account_id；跨会话引入前需要明确身份与作用域映射。
