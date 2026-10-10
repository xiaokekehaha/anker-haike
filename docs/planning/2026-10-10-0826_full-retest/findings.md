# 初始证据

- 当前分支 codex/official-63-ten-rounds，HEAD eefc1a4，上一轮未提交改动仍在。不能仅凭 HEAD 相同断定文件未变，待生产指纹比较。
- 08:25 本机服务健康：数据库、Redis、WeKnora、domestic 模型配置正常。海外模型未配置，不属于本轮路线。
- 上轮最后评测为 round-10，已知残留包括 T23 风险误判、T41 适用性、T35/T53 统计粒度、混合节点及部分重复。不因本轮偶然不复现就关闭。
- 使用相同客户策略与相同评测脚本，测试集是开发中反复使用的官方 63 单，不是独立留出集。
- 初始指纹确认：与昨日 round-10 的生产文件及运行容器完全一致，当前工作区与容器无差异。因此本次是同版本独立重跑，行为变化不归因于新修复。
- 已阅 T1–T19：物流、真实人工边界等主要行为保持；T12 长段混合、T16 重复安装检查仍有。T19 本次从故障排查变成 product_question 普通文本回答，需结合后续统计核查。
- 已阅 T20–T33：T23 本次按官方 E41 更新/重启，没有误报物理安全事件；无代码变化，不能关闭昨日缺陷。T29 本次停在清洁盘浮标位置问句，未覆盖三步跳过问题；T31 再次要求擦充电触点，T26 问句/操作混卡、T32 长段仍有。
- 全部 63 单已阅。T40 实际命中 qa_rv_0371，guide_trace=source_reference_missing/knowledge_source_gap，真实 awaiting_approval；这是资料缺口防护实测证据。
- SQL 与 checkpoint：T19 产品咨询 answered、consult_answered=false，实际 in_progress；T35 本次纯说明为 consult_answered。证明缺陷取决于入口，不能因 T35 正常就关闭。
- T53 replacement_request=done、report_problem=active，stage=guide；实际 SQL closed_unresolved，仍把部分业务案件终点覆盖整个问题。本次分支选择还重复已知无法开机的信息。
- T41 保留 report_problem + logistics_query，先问实际报码；T45 烫伤真实安全交接。T23/T41 旧严重错误本次未复现，没有产品修复，仍在残留清单。
- 统一反馈下实际收到 57 张操作卡和 2 张问题卡。整案采证耗时中位数 6.93 秒、P95 11.72 秒、最大 18.79 秒，包含自动反馈和采证等待，不是首字延迟。

## 责任复评补充

- T48 新证据：补充型号后的 product_question.question 与实际 retrieval_calls.query 均只有型号说明，丢失“绿灯含义”；第二轮 primary_intent=product_question，product_questions.py 在该分支重建问题。应归系统需修，而非仅知识不足。最后不编造答案的防护成立，但不抵消上游缺陷；绿灯答案是否存在仍待查。
- T60 checkpoint：未确认型号，泛化抱怨直接作检索，knowledge_status=no_match；还不能确认是源库缺口，需评估先澄清。T61 checkpoint：保留提前两小时/无记录的查询，有候选但无适用计划，knowledge_status=ok 不是检索语义准确的证明。
- 源文复核：rv-0371 缺引用已确认；同主题 rv-0073 有链接。bp-0111 确有 speaker cover，但其正误仍需产品核实。未取得官方故意设坑的证据。
- 责任台账每案单列主要去向、多选并存因素；T50 的输入歧义不豁免引导性追问，T53 的保修限制不豁免整体终点错误。合理人工边界之后的办理不纳入本轮 agent 评分。
