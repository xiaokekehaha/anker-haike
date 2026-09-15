# 进度

## 2026-09-14
- 锚点核查：contracts（common / actions / events / snapshot）、graph.py（SessionState、route_entry、escalate 路由、prepare_card / await_input / apply_action、build_graph）、reduce.py turn_decision、interpret.py Intent、rules check_in、warranty L1–L6、admin router、迁移 0001–0005、Timeline / reducer 卡片分发、models.yaml、ingest front-matter、service-quality-loop 对象模型。
- 写入设计系列 00–08、issues/README + 票 51–66、task_plan、findings。未修改代码与配置。
- 待用户确认：D-L3-2（AWS 通道）、D-L3-9（演示动作集）；决赛日期与真实数据到手时间。

## 未决 / 风险
- 契约改动（票 51）是关键路径；情绪 `anxious → dissatisfied` 的兼容映射需在票 51 落。
- 视觉新 schema 需重新 bake-off（票 62）；国内视觉模型此前 83% / 77%。
- 真实脱敏数据未到手，P0 全部演示数据。

## 2026-09-14 开发启动
- 用户授权按本目录开始开发；采用默认 P0 三动作，AWS 现场通道不影响开发。
- 已读取设计、依赖与现有契约/前端分发；保留其他任务未提交改动。
- goal 已由 /goal 创建，复用现有 active goal。

- 51：新增契约已生成；首轮校验发现事件数断言需从 19 更新为 25、历史 pending 默认字段断言与现有模型不符，以及 TS 联合类型解构丢失判别关联，已对应修正。

### P0-A 验证与 P0-B 启动
- 票 51：契约 94 tests、前端原有 195 tests、新增六类 reducer 6 tests、typecheck、contracts-check 通过。正式 L3 卡片组件仍在对应业务票中实现。
- 票 54：54 条政策决策金标 + loader/日期边界测试共 60 tests 通过；PolicyEngine 无 IO，CLI lint/explain 可用。
- 票 52/53：Postgres/Memory BackendClient、13 订单/6 运单 seed、0006、动作 registry/gate/executor、lease fencing 已实现，专项共 23 tests 通过；数据库集成待验证。
- 全量后端：616 passed / 20 failed / 24 skipped；在 /tmp/haike-l3-baseline 的 HEAD 导出代码复跑：同样 20 个失败，529 passed / 28 skipped。失败集中既有 intake 拓扑、卡片稳定 ID、旧升级流程断言，需 P0-D 收口。原始报告 /tmp/haike-l3-baseline-tests.log。
- 本机 PostgreSQL:5432 与 Docker daemon 均未启动；用户询问启动服务，已请其启动项目 PostgreSQL/Redis/WeKnora，随后由本任务启动编排与前端并验证。
- 票 59：案件状态、原子事件/审批事务仓储开始实现；未接会话图。

### 数据库与 L3 主链联调
- 用户已启动依赖；0006 迁移成功，seed 13 订单 / 6 运单可重复执行。
- 真实 PostgreSQL 隔离 schema 验证并发幂等、执行进程重启回执复用、审批竞争、结案重开；专项合计 88 tests 通过。
- A4 查询本地当前代码 8002 实际读取 PostgreSQL，返回工具事件、模拟物流来源和完成事件。
- 55–60 主链、审批管理台、六类正式卡片已接入；A5 自动办理、A6 人工批准后恢复 API 测试通过。
- 61–64 正在收口：情绪/视觉/任务接续代码已接；新增 0007 service_episodes 以问题粒度统计，未评分不伪造数值。
- 当前目录未发现真实故障图片评测集，视觉模型 bake-off 验收暂缺真实图片输入；规则/结构测试与真实视觉能力分开报告。

### P0-C/D 验证推进
- 新增症状 taxonomy 8 族与 40 条人工金标；情绪 40 条、多意图排序 20 条、授权 12 条、承诺来源 3 条，连同政策 54 条均通过 deterministic_regression。这些分数不是生产意图准确率或真实视觉模型识别率。
- 契约漂移检查 + 94 tests、前端 201 tests、类型检查与生产构建通过。
- 新增七项 L3 inspection 全通过，报告 reports/inspection/l3/；真实 Postgres 指标查询能观察人工结案，避免误算独立托管。
- 当前全量后端 660 passed / 22 failed，含既有 20 项与管理台新增拓扑映射、WeKnora 实时读取超时。已修拓扑映射与无效全连接边，正在针对验证。
- 浏览器已验证聊天物流结果与管理台四张指标卡；本地服务改为真实 domestic 模型通道联调。8000 Docker 旧镜像未替换。
- 回放版本清单扩为六元组；旧包明确失效需重新录制，CLI 已补当前 input_id/expected_version/input_token 字段。尚未声称 A1–A9 回放全部通过，也未生成新冻结镜像或录屏。
- 已向用户询问真实视觉照片集所在目录，继续完成不依赖图片的工作。

### 用户联调反馈：查询短追问
- 真实模型已跑通排障未解决 → 方案确认 → 服务单创建 → 跟踪链路（模拟业务系统）。
- 用户报告 aec68146e409 会话重复索要物流单号；日志确认历史完整、意图正确，根因是查询节点未复用上一轮参数。
- 统一当前问题内的查询对象解析，覆盖短追问、旧检查点恢复、明确新订单覆盖旧标识符、新问题隔离；参数补齐不绕过写操作授权门。
- 先复现 3 个失败场景，再通过 59 项专项测试及真实模型六轮联调；修复已运行在 8002。用户原会话仅做只读检查，可从历史恢复订单号。
- 详见 [query-context-diagnosis.md](query-context-diagnosis.md)。

### 业务上下文架构重构
- 用户确认新反馈来自 4d21bcd66965，并要求从第一性原理解决架构／流程问题，允许重构。已使用 codebase-design，方案见 [10_business-context-refactor.md](10_business-context-refactor.md)。
- 根因涉及业务对象分散、日志充当参数库、模型自由澄清绕过流程、回复漏字段；全量测试另发现回顾 pin 错误跨轮占用理解预算。
- 落地 BusinessContext（accept/bind/observe/projection）、带原话校验的 BusinessReference、一次性旧状态迁移；贯通查询、凭证、执行回执、服务上下文和理解/回复。业务节点不再维护两套查询参数。
- 原序列、10 轮闲聊后再查、历史裁剪 28 条仍查到单号、真实进程重启恢复及管理台显示均通过。专项 89 tests 通过；证据 reports/inspection/l3/business-context-validation.json。
- 本轮全量 701 passed / 12 failed，长会话 pin 失败已修并专项通过。剩余全量失败未掩盖，继续收口。
- 独立真实模型评测模块和语料已新增：意图 40 条、情绪 40 条、多意图 20 条。当前报告 intent 39/40、emotion 38/40、routing 17/20；routing 未达 90%，需看漏识别而非调整金标。前两项报告属于本次重构前 prompt 版本，后续需重跑版本一致的验收。

### 上下文契约与回归收口
- interpret 2026-09-14.3 明确独立诉求抽取与对象引用、后端排序的职责；真实模型重新评测 intent 40/40、emotion 38/40、routing 20/20，报告版本一致。
- 完成旧测试与当前会话协议对齐。转人工空问题来自测试模拟器未提供 facts；未知意图不再模拟为 report_problem。没有修改生产摘要去猜历史消息。
- 回放故障先红（上下文身份、引用映射、A1 断网回放），再引入 ContextMessages 结构化来源与受限引用转换；回放格式 2 明确失效旧包。相关 10 tests 通过。
- 架构扩展测试发现“办理 A 时查 B”会令 A 的执行回执因聊天焦点变化而无法提交。完整 API 先复现 done error，再将 observe 改为按实际请求唯一匹配对象；不挪动当前焦点，不混合不同订单编号。业务与回放专项 36 passed。
- 最新全量后端 **719 passed**（/tmp/haike-l3-regression-final.log），本轮修改 Ruff 与 diff 检查通过。
- 8002 无活动 run 后重启，载入当前代码与 interpret .3；真实模型 16 轮重测通过，合成会话 8f2ea147357f40e6af0a9b693714c67d。旧合成会话 e8a25ba4e87c4923901ee2af6ecb26b8 在重启后继续查到 DEMO-TRACK-001。原用户会话保持只读；证据补入 business-context-validation.json 的 live_current/restart_current。


## 2026-09-14：统一事实问答（用户要求第一性原理、功能优先）

停止扩大测试矩阵，转向 `11_conversation-facts-and-answers.md`。共性根因是事实未按对象持久化、回答模板未覆盖所问字段、聊天焦点与办理对象混用。实现业务事实存储与统一读取/回答模块，解释器 .6 使用唯一对象引用入口，卡片与服务上下文按案件订单绑定。跨订单案件隔离、管理台空筛选修正已完成；案件队列可显示订单号及全部状态。

真实模型八轮会话 `80ca105b74784abab1c17721bf14ab5c` 覆盖订单 A 查询/退款、订单 B 查询/德国使用、回查 A 中国使用、B 物流、闲聊和多字段追问。全部无事件错误，已知编号未重填。新增 2 项接口测试，相关检查 33 passed，Ruff 与 diff 空白检查通过。证据：`reports/inspection/l3/conversation-facts-validation.json`。

原 P0 目标继续保持 active：A4–A9 最新版回放、真实照片评估和发布演示仍未完成；旧 .4 A4 包不再作为 .6 的验收证据。用户已要求以功能推进为主，不为更新测试数量重复全量评测。

最后已将最新版重新加载至 8002，并在同一合成会话追加两轮：退款案件 A 的使用地/状态返回中国与 awaiting_approval；随后聊天焦点 B 的物流编号仍为 DEMO-TRACK-003，无重复任务提示。服务重启后事实和对象绑定保持正确。

## 2026-09-14：继续 P0 办理流程

核查票 55/57 后，补齐可恢复执行失败的用户重试路径：新增 executing_failed 案件状态、重试原申请卡、同幂等键重试和政策依据变化时重新确认。一次接口贯通已证明超时后跨订单插话再重试仍只办理原案件。服务信息卡新增区域/渠道候选，已知项直接展示，只填写缺项。正在完成相关契约和实际页面检查，原目标保持进行中。

本轮最终结果：确认卡片命令优先于自由文本路由，页面实测填写 DE 后直接进入审核，不再重复索要；相关命令/凭证检查 29 passed。A5 一次完整录制后发现离线时间字段未归一化，修正 ExecutedStep.ts 并升级格式 3；再次录制暴露 context_budget，去除当前事实/已做步骤在索引和视图中的重复投影，保留原事实与安全记录。最终 A5 真实模型录制与离线重放均通过：model_hits=8、model_misses=[]、knowledge_misses=[]、errors=[]，最终 case=closed。证据见 `reports/inspection/l3/execution-recovery-validation.json` 与 `replay/a5_replacement/`。

原目标仍 active。接下来完成 A4/A6/A7/A8 最新版回放、P0 未核查细项和发布收口；A9 真实照片数据仍待提供。不要把旧 A4 格式 2 包当作当前已通过。避免扩展无用测试矩阵，优先实际功能。
# 2026-09-14：多任务对象归属

按用户要求继续检查通用架构：发现任务只有意图、没有对象，导致跨订单插话误完成旧任务、恢复时取当前焦点。新增 BusinessContext 引用接口；任务按对象去重与完成，显式/自动恢复绑定原对象，保留原排障卡片，清除前一问题的字段请求。旧任务无法确定对象时澄清。

相关检查 52 passed，随后收口检查 3 passed，Ruff 通过。真实五轮会话验证 A → B → 恢复 A → 追问渠道和单号通过。验证还暴露多任务排障自由回复虚构转人工安排，已让调度流程统一说明任务安排、排障只下发当前步骤。文档见 13_task-ownership.md，证据见 reports/inspection/l3/task-ownership-validation.json。8002 已重启加载改动，原用户会话未修改。
# 2026-09-14：方案、审批与指标保留

补齐换货方案的动作配置时效和来源；管理台可编辑费用承担，编辑后的方案强制用户重新确认。人工审核保留待核实候选，未知故障与安全限制在审批入口即阻止批准。指标匿名化复用看板的最终计算投影，保留晚到人工结案与意图标注，原文仍清除。

相关检查 71 passed（含 PostgreSQL），收口检查 6 passed，Ruff/契约/前端构建通过。真实管理台验证补充信息、费用编辑、重新确认与证据门阻止。A6 真实模型录制及格式 3 回放通过，7 次模型命中、无模型/知识未命中，动作配置 .2。细节与限制见 14_proposals-approval-metrics.md；当前继续其他回放与发布交付。
# 2026-09-14：情绪与操作分流

A4、A7 在解释器 .6 下录制与回放通过；A8 暴露投诉被当作 request_human、投诉风险被当作设备 R4 风险。新增 complaint 意图与人工请求原话依据，把设备安全字段改为 device_safety_assertion/device_safety_quote，解释器版本 .8。相关检查 44 passed，真实 A8 录制及格式 3 回放通过（模型命中 7、知识命中 2、无未命中）。失败诊断单独保存，不作为成功包。原目标仍未完成，旧解释器包需要统一刷新；详见 15_emotion-and-operation-routing.md。

## 2026-09-14：进度展示与当前上下文复核

统一前端查询、排障、办理阶段与案件状态映射；会话列表和进度条共用规则，只使用当前问题的案件状态，不将前序步骤推断为已完成。构建与既有 11 项检查通过，桌面合成会话已核对等待人工审核状态；见 16_progress-presentation.md。

A1–A3 在解释器 .8 下录制成功（进程退出码均为 0，录制报告 errors 为空），尚未核对本次包的离线回放。用户继续强调从共性架构解决问答问题，当前优先复核原序列与跨对象字段复用，不扩展测试矩阵或宣称整个 P0 已完成。

8002 当前服务七轮实测通过：查 A 物流 → 退货 → 上面的订单 → 物流 ID，直接返回 DEMO-TRACK-001；随后查 B 的渠道/日期 → 闲聊 → 日期/物流 ID，返回 2026-02-26 和 DEMO-TRACK-003。退货只追问尚未提供的使用地，没有重新索要订单编号；七轮无事件错误。证据保存在 reports/inspection/l3/context-current-validation.json，使用独立 smoke 会话，原用户会话未改动。已有长会话、重启和任务恢复证据见 10–13；本次没有重新扩大全量测试。

## 2026-09-14：人工案件生命周期回路

close/reopen 原先只写案件表，现接入内部会话命令、幂等案件事务与持久事件。补齐管理台按钮、旧卡失效和重新确认边界；用户页面可见时发现外部案件变化并恢复事件流。定向后端 9 项、前端生命周期 26 项通过，构建与 Ruff 通过。8002 合成案件已实际点击结案与重开，数据库、用户快照、管理台一致，重开计数 1，无新业务执行。详见 17_manual-case-lifecycle.md；原目标保持进行中。

## 2026-09-14：未解决结果自动重开

分开单步反馈与案件结果，解释器 .9 增加当前未解决报告的原话依据。新增独立重开节点，按原案件恢复、处理跨订单歧义、使旧确认失效，再核实服务信息和方案；输入重试不重复计数，保留既有处理和安全记录。8 项相关检查通过，跨订单收口 2 项通过；8002 真实模型验证只读查状态不重开，明确否认解决后恢复原案件、仅补缺失使用地、无业务执行。详见 18_unresolved-case-reopening.md 与 reports/inspection/l3/case-reopening-validation.json。

下一项功能缺口已定位：故障判别问题只有文案，没有候选与答案的持久闭环，症状码在 reducer 中未保存。优先完成该功能，之后统一更新旧解释器回放包，避免每次改提示词就重复整套录制。

## 2026-09-14：按用户要求完成功能收口

用户明确“Step back 功能开发完成就结束”，覆盖前述继续扩充回放/发布的计划。故障追问现持久化候选、问题与答案，短回答绑定当前问题；症状码贯通事实、检索与计划适用范围。步骤说明统一在校验后出卡，无适用计划明确交接人工。相关后端 67 项通过，Ruff 通过；交付细节见 19_functional-delivery.md。停止扩充测试矩阵、回放与发布工作。

8002 最终真实模型三轮验证通过：设备坏了 → 不能启动 → 没有充电指示，按当前问题绑定两次回答，最终 R5 交接（无适用充电计划），未生成不相关步骤、无事件错误。证据已标记 passed，见 reports/inspection/l3/symptom-interview-validation.json。
