# 发现

- 管理页面从 GET /admin/api/sessions/{id}/journey 读取旅程；开发代理指向 127.0.0.1:8000。
- 此任务没有报告确定的故障，diagnosing-bugs 的故障复现、修复及回归阶段不适用；采用只读历史记录追踪。

## 实际链路

会话：42e7fb2c85d347e8b3281b6a95a92562，2026-10-12 13:40:53—13:41:42（Asia/Shanghai）。读取管理 API、页面及 PostgreSQL checkpoint（节点执行后持久化的会话状态），未重跑模型。

1. 首轮 understand 使用 dashscope/qwen3.7-flash 提取现象 Water tray will not empty，及已清洁、软管未压扁、污水箱下方连接器未下陷、污水箱为空等事实。disambiguate 确认 T2351。
2. knowledge.search 用 Water tray will not empty 和 water tray will not empty robot vacuum 两个检索词，在 116 条允许知识范围内检索；最终显示 15 条证据，包含 rv-0270、rv-0254。命中排名本身不直接决定方案。
3. diagnose.synthesize 使用 deepseek/deepseek-flash，最终待澄清候选为 qa_rv_0254，confidence=0.62，reason=needs_confirmation，missing_fact=Check whether the door latch of the dirty water tank is fastened。plans_ranked 为空，plan_cursor 为空。
4. clarify 直接使用诊断任务返回的 question，输出 Is the door latch of the dirty water tank fastened securely?；本轮没有 guide、没有 step_card，也没有额外的回复模型调用。
5. 用户回复 yes。understand 将其记为门扣已扣紧的 action_taken，同时 precondition_answers 绑定原方案、原问句、missing_fact 和 yes。
6. 再检索 Water tray will not empty，再由 diagnose.synthesize 选定 qa_rv_0254，confidence=0.62。模型保存的简短依据是“门扣已确认扣紧，脏水箱空，符合污水抽排异常；需查清洗盘浮标/格栅。”这是模型说明，不等于官方原文包含浮标检查；实际卡片严格取 rv-0254。
7. guide 内调用 guide.step 做事实核对（deepseek/deepseek-flash），生效结果仅 s1=done、quote=yes、skip=true。prepare_step 跳过 s1，发布 s2。
8. s2 正文为检查清洁盘格栅是否被泥沙/异物堵塞，并清洗清洁盘。引用锚点 rv-0254#s2；图片和视频来自同条 Q&A 的第 2 段；rewritten=false。context 使用固定模板说明门扣已经确认，无需重复。
9. 用户点 not_solved，按 next_on:s3 进入第 3 步，要求压住污水箱盖、在 App 触发清洗拖布，并按结果检查密封圈。该轮无检索、无模型调用。再点 solved 后结案并显示评价卡。

## 内容与代码来源

- 官方数据：data/official/qa.yaml:5091，rv-0254 的 3 个编号段落及各自媒体链接。
- Q&A 拆段、移出媒体链接：orchestrator/app/official/qa_index.py 的 split_steps、build_guide、media_of。
- 生成 qa_rv_0254、s1/s2/s3、预期结果固定文案、next_on：orchestrator/app/plans/qa.py:104。
- 模型输出 needs_confirmation 及 clarification_question：orchestrator/app/diagnose/synthesize.py:41、:379；服务端核对与排序在 filter_hypotheses。
- 检索证据映射候选计划：orchestrator/app/sessions/graph.py:2331；无可执行方案但有待澄清候选时转 clarify：:2423；直接发布问句：:301。
- yes 绑定待确认前提：orchestrator/app/sessions/graph.py:1198。
- 步骤事实核对：orchestrator/app/guide/fact_check.py:235；已审核原文、证据、媒体装入卡片：orchestrator/app/guide/steps.py:260。
- 前端 StepCard.tsx:94 展示后端字段；已反馈的历史卡在 :36 折叠为标题和反馈，所以管理页面现在看不到完整卡片。

## 流程判断

1. 首问有官方依据，但将排障动作当成了方案入口前提。rv-0254 第 1 步本来就是检查门扣，门扣未扣紧同样应能进入该排障方案。当前诊断提示词明确区分入口前提与待查原因，但本次持久化结果仍是 needs_confirmation；不能把本次结果描述为确定性设计要求。
2. 清洁信息部分丢失：事实仍保留 cleaned it，subject=it；基于对象和动作的规则不能用不明确对象覆盖复合检查步骤。生效的模型核对只标记 s1，没有 s2 的 done/partial，因而全段原文照发。已有 partial 支持，本次未生效，不能描述为系统完全不支持部分完成。
3. 如后续修复，目标应是保持检查门扣的依据，将其作为方案内步骤；对第 2 步注明用户已清洁，本轮重点补查格栅。当前任务仅分析，未修改业务代码。

## 验证边界

- 此结论基于原会话 4 轮执行记录及对应 checkpoint；未新建会话、未调用真实模型。
- 未取得厂商原始完整模型响应，模型决策以服务端校验后持久化字段为准；置信度 0.62 为模型自报分数，不能解释为真实故障概率。
- 同时段已有 T29 评测目录的版本记录显示关键 synthesize、fact_check、steps 的本地与容器文件哈希一致；本次分析以原会话记录为主，不将其他会话评测当作此会话结果。
