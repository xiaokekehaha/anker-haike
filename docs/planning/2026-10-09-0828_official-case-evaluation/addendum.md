# 测评补充与勘误

## 2026-10-09 新增十个官方案例

- 用户要求继续抽取十个不同案例，选择T5/T7/T18/T23/T35/T46/T48/T53/T56/T61，未与原八单重复。原输入、附件与sheet/行号固定，当前统一英文与交接终点范围沿用。
- 首测5正确、2部分、3错误，10单均无接口错误。T7追加复测正确、首测错误仍保留；T56/T61追加复测仍错误。T48追加官方型号后诚实说明无绿灯知识，未给最终答案，不把知识缺口写成编造。
- 结果与证据在round5-1356/，首轮及round2/3/4记录不覆盖。没有修改应用或推进人工审批后续。

## 2026-10-09 第二次修复及比赛范围

- 固定评审46b1777；运行时HEAD5307876仅增加文档，13个相关文件与容器一致且运行前后未变。139项相关测试、lint、24项证据一致性检查通过；八原样本8/8，13会话无接口错误。
- 上轮四项均按原复现验证修复；规范轴无新增可行动问题。实现说明虽称不处理存储失败，实际单次mutate已通过内存异常回滚及重试验证，不能继续列为未修。
- 用户追问人工审批是否已是比赛结束点。本轮按该范围验收：真实转人工、完整交接、正确表达办理状态、回答独立物流查询。人工批准/驳回/要求补充后再驱动机器人的流程属于后续范围；额外发现两项P2记入报告，不作为这次比赛阻塞项，不继续扩展实现。
- 原plan.md与运行前criteria.md保留。范围说明及完整证据见 round4-1342/report.md。

## 2026-10-09 13:15 Claude 修复复核

- 用户要求检查修复及其他案例是否受影响。规范和需求分轴审查，固定基线 a1a8798；过程中修复被 Claude 提交为 e18fefe，保存 diff 与最终范围内差异一致，测试前后文件哈希不变。
- 9 个相关文件 134 测试通过，Ruff 通过；13 个真实会话无接口错误，八原样本8/8业务通过。T9 三次均完成物流答复与真实人工入队，其他七单关键业务行为保持。
- 独立 HTTP 边界验证复现4个通用缺陷：请求改变被去重吞掉、交接部分写入失败后重试不补齐、选人工后仍推进非查询任务、人工决定后任务仍等待。原八单通过不能等同其他流程完全不受影响。
- 新结果写入 round3-1315/，保留首轮及round2历史；本次未修改应用实现、未提交 Git。

## 2026-10-09 首轮后的补充验证

首轮八单均完成 HTTP 调用，无接口错误。追加验证不替换首轮样本、不混入八单分母。

- T1 首轮把未收到货理解为故障。追加两个独立会话原文复测，检查是否稳定复现。
- T55 附件实际为订单截图，白底清晰；首轮按现有前端默认 purpose=fault 上传，触发 too_bright 并要求补拍。核对前端 Composer：普通首问默认 fault，仅待上传凭证阶段切换 receipt。因此这代表默认上传路径的问题，但不能据此判定后续排障知识错误。
- 在原 T55 会话选择 skip_retake，继续文本排障，直至请求必要证据。另开 purpose=receipt 的诊断性对照，仅改变附件用途，记录区别。该对照不是普通首问 UI 的等价输入。
- 初始记录的观测轨迹可能只包含已完成批量落库的前几轮。结束后重新读取所有会话 journey，以补齐记录；逐轮 SSE 原始事件已经完整保存。
- 容器运行日期按 T51 回答可核对为 2026-10-09。读取 printenv 的部分变量未设置导致退出码 1，不属于服务运行错误。服务通道 domestic；实际模型调用在 journey 中可证实。
- T1 两次原文复测均正确，故报告描述为 3 次观测中 1 次误判，不能描述为必现。
- T55 跳过补拍与 receipt 对照均命中 bp-0102 三步。默认故障用途路径只追 SN，凭证用途对照追故障图片/视频及 SN；只确认文案/待补清单差异，未测试补齐 SN 后的最终授权检查。
- 综合判定包含语言可用性：T13 业务正确但语言不符，计部分正确。综合正确 4/8，业务方向及事实符合 5/8，两种口径分别披露。

## 2026-10-09 11:46 修改后复测

- 用户要求继续测试最新修改。沿用八个原始案例、原附件及停止条件，结果写入 round2-1146/，原 plan.md、criteria.md 与首轮证据保留。
- 官方工作簿 SHA-256 未变。当前容器镜像 a5c5551c71b4b6e337b61d1dd503fdb7b004db88d34eebc5d4bb97cfc82f047a，启动时间 2026-10-09 11:25:02（北京时间）。核对 interpret、logistics、l3、vision、quality、evidence 及 models、vision_vocab 共八个文件，容器哈希与当前工作区全部一致。
- 语言口径勘误：在 docs/planning/2026-10-09-0841_finals-tracking/addendum.md 的 DD1 决策中，项目已选择统一英文。故本轮按统一英文验收，T13 不因英语回复扣分。首轮同口径应为 5 正确、2 部分、1 错误；原始 4/3/1 作为历史记录保留。报告将分离真实行为改善与评分口径调整。
- 不采用最新 run_case 的跨工单替换故障照片与合成 SN 策略，本轮只用原案例证据，并在缺材料处停止，保持前后可比。
- 11:48–11:49 复测完成，本轮 7 正确、1 错误。T1 五次均正确，T55 原图不再被要求补拍，排障失败后原图和 receipt 对照都要求故障照片/视频及 SN。
- T9 三次均声称已转交，但 11:52 案件 API 复核仍 open、无交接摘要，只记录订单识别；物流任务仍 pending。中途“没有工单”的表述不准确，现勘误为“已创建案件，但没有实际转人工”。
- service_context 的不可执行诉求早退分支直接 commit_issue，跳过 await_human 与 advance_tasks。现有自动判分只匹配 passed your request to 文案，会把这三次误判成转人工终点；报告采用实际状态和完整诉求覆盖判定失败。
- 新报告与全部新证据在 round2-1146/，仅为此次运行版本的抽样结论，不代表完整服务执行或整体正确率。

## 2026-10-09 口径勘误：语言不再作为判据（DD1）

criteria.md 是运行前固定的判定标准，不改写；勘误记在此处。

- criteria.md 第 11 行 T13 的「回应荷兰语客户」与第 25 行「客户语言加中文译文是项目约定」
  都是 D2 旧口径。D2 已于 2026-10-08 改为**客户可见输出一律英文**
  （见 ../2026-10-07-1543_organizer-materials-replan/addendum.md 两节）。
- 按现行口径，T13 的荷兰语客户收到英文回复不算缺陷。该单业务事实与处理方向本就正确
  （正确记录「官方知识库未收录 5116」、准备人工交接、没有挪用相邻码步骤），
  因此判定由「部分正确：业务正确，语言不符」改为**正确**。
- 本轮综合判定随之从「4 正确 / 3 部分正确 / 1 错误」改为 **5 正确 / 2 部分正确 / 1 错误**
  ——与 report.md 开头「仅看业务事实与处理方向，T13 也符合标准，为 5/8」的说明一致，
  现在这就是唯一口径，不再并列两个数字。
- 仍未变的两单部分正确：T9（子诉求被丢弃）、T55（附件用途混淆）。两者已在
  ../2026-10-09-0841_finals-tracking/ 的 P2-1、P1-1 中修复并经真实链路验证。

## 2026-10-09 round5 三单根因与方案（T7 / T56 / T61）

证据：round5-1356/ 首测与 followups/ 补测原文，容器日志 intake 阶段的模型输出（dashscope/qwen3.7-flash，六次运行均一次成功，没有走关键词降级路径）。三单根因各不相同，只有 T7 主要是模型读错。

### T7 物流追踪号查不到 → 被引到设备排障

- 现象：首测回「I'll handle your requests in this order: device troubleshooting → delivery status」并追问型号；补测直接要订单号/运单号。
- 模型输出：首测 `primary_intent=report_problem, secondary=[logistics_query]`，把「it is not working」（追踪号查不到）读成设备故障；补测同一句给 `logistics_query`。同一输入两次不同，是模型对这句判定不稳定。
- 代码护栏没覆盖：`orchestrator/app/conversation/interpret.py` 的 `logistics_correction` 只纠两种情况——主意图 order_query 且原话有配送词、原话出现「从未收到」。T7 两者都不满足，report_problem 按 `tasks.py` 的优先级 2 排到 logistics_query 的 3 前面并播报顺序。
- 方案：在 `logistics_correction` 补一条客观约束——原话是「用追踪号 / 订单号查不到」（tracking number … not working / can't track / lookup fails 等）且没有设备现象词时，report_problem 不可能成立，降为 logistics_query 并去掉 symptom 事实。与 NEVER_ARRIVED 同一类「物理上不可能」的约束，放代码不放提示词。

### T56 摄像头离线问保修 → 回「涉及多个订单」

- 现象：首测与补测完全相同，会话里没有任何订单却回「This involves more than one order」；离线故障没有产生任何排障步骤。
- 模型输出（两次一致）：`primary=warranty_query, secondary=[complaint]`，把反问句「Is that your warranty?」当成查保修；抽到了 symptom=offline，但 report_problem 不在意图列表里，这条事实在 consult 路径被丢掉。`business_reference.relation=ambiguous`，引用「my SoloCam S340」。
- 提示词枚举缺口：relation 只有 current / other / case / issue / ambiguous，提示词写「无法确定对象用 ambiguous」，而「本轮没有业务对象」没有可选值，模型只能选 ambiguous。
- 代码缺陷：`orchestrator/app/conversation/business.py` `accept` 中 relation=ambiguous 直接置 status=ambiguous、candidate_ids=全部 subjects（此时为空列表）；`bind` 见 ambiguous 就返回 ambiguous，不检查候选是否为空；`l3.py` consult 分支据此回「涉及多个订单」。零候选应等于 missing。
- 方案（三处，前两处必要，第三处可选）：
  1. `business.py`：subjects 为空或 candidate_ids 为空时，ambiguous 退化为 missing；consult 分支只在候选 ≥2 时说「多个订单」。
  2. `interpret.py`：有 symptom 事实但意图列表没有 report_problem 时，按「有故障现象就必须有排障诉求」补 report_problem 进 secondary_intents；由 tasks.py 排序，排障（2）自然在保修（3）前。
  3. 可选：提示词把「Is that your warranty?」这类对质保的反问归 complaint 而非 warranty_query。模型两次一致选错，改提示词收益不确定，先靠第 2 条兜底。

### T61 提前两小时启动 + 清扫记录缺失 → 给「7051 无法启动」步骤，漏第二症状

- 现象：首测与补测都给 rv-0522（7051 任务进行中无法启动定时清扫）的步骤卡；not_solved 后转去要订单号查保修，进入 awaiting_upload_receipt；「cleans not recorded」始终没被覆盖。
- 模型输出正确：首测抽出两条 symptom「schedule not followed, goes off 2 hours early」「cleans not recorded by app」，检索 query 即这两句；补测合成一条。意图 report_problem，型号 T2280 锁定。模型没有读错。
- 知识库无对应条目：Omni C20 范围 93 条 Q&A 没有任何一条讲「提前启动 / 时间偏移」或「清扫记录缺失」。15 条命中分数 0.012–0.016 几乎持平，首测第一名 rv-0551 低电量、补测第一名 rv-0522，都是「定时任务」相邻条目。
- 策略放大偏差：grade/synthesize 仍给 rv-0522 ≥ `SWITCH_CONFIDENCE`(0.3) 并出卡；`decision.py` `MAX_GUIDES = 1`，一步 not_solved 即 guide_exhausted → 人工出口 R1 → 保修核验要订单号。「问保修」是设计路径不是误判，但第二条症状从头到尾无步骤覆盖，且卡片标题就是客户没报过的错误码 7051。
- 方案：
  1. 知识空白要如实说：命中分数全部低于阈值且标题含客户未提及的错误码时，不出步骤卡，直接按「官方知识库未收录此现象」走人工交接，并把两条症状一起写进交接摘要（同 T13 处理 5116 的方式）。需要在 grade 层加「错误码匹配」判据：Q&A 标题带错误码而客户原话没有该码，置信度封顶在 SWITCH_CONFIDENCE 以下。
  2. 多症状覆盖：交接或结案前检查 issue 的 active symptom 是否都被至少一个步骤的 evidence 覆盖；未覆盖的写进交接摘要「以下现象无官方步骤」，不得静默丢弃。
  3. 不改 MAX_GUIDES：单步即交接是 2026-10-09-1153_single-step-guide-diagnosis 的既定决策，这里的问题是不该出那一步，不是步数。
- 换更强模型不会改善这单。

### 结论

| 单 | 模型 | 提示词 | 代码 | 知识库 |
|---|---|---|---|---|
| T7 | 判定不稳定 | — | 护栏缺口 | — |
| T56 | 主意图选错 | relation 枚举缺「无对象」 | 零候选当 ambiguous | — |
| T61 | 正确 | — | 低分仍出卡、第二症状丢失 | 无条目 |

以上为分析与方案，未实施；实施后需在新 round 目录复测，不改本轮分母。

### Codex 复核：方向部分同意，以下约束须修订后再实施

1. **T7 纠正对象是合理方向，不能宣称物理互斥。** “追踪号不能用”与“设备故障”可以同时出现；没匹配到设备现象词也不能证明不存在设备现象。只能删除被错误绑定到追踪对象的排障诉求及对应事实，不能一律去掉 symptom。需要覆盖“追踪查不到，同时摄像头离线”的对照。
2. **T56 零候选提示多订单是确定的代码缺陷；自动补排障的条件过宽。** 只有候选确实≥2才可说多个订单。未知对象必须继续明确缺参，不能借此自动复用旧订单。新描述的故障也不必然授权立即排障，例如“摄像头离线，但先别排障，只查保修”。应区分当前求助、历史背景、明确拒绝排障，保留真正独立的故障诉求。`business_reference` 本身可为 null，current 也允许没有已知订单，因此“枚举迫使模型只能选 ambiguous”并不成立；提示词应澄清缺参和歧义的区别。
3. **T61 不能使用所提的分数/错误码硬门槛。** 0.012–0.016 是检索排序分，不能当成低正确率；正确的 T35 首条同样约0.01639。用户只描述现象、不知道错误码，是正常输入，文档有错误码不等于该文档不可用。应验证用户现象与条目适用前提是否一致；“提前启动”与“无法启动”不一致时拒绝/澄清，不能只看是否都包含 schedule。
4. **仅修改 grade 不足以改变当前出卡。** 当前 `config/retrieval.yaml` 中 grade 和 query_rewrite 均关闭，真实 T61 没有 retrieve.grade 调用；grade 的输出是相关性/覆盖标记，也不是计划 confidence。需要把适用性判定接到实际出卡入口，不能只加一个未启用的评价条件。
5. **必须保留模型“没有适用计划”的结果。** `synthesize.py:232` 目前把空 hypotheses 恢复成检索候选并赋0.3，刚好可出卡。FakeChatModel 离线复现已确认。业务上的“无适用证据”不能与模型不可用/格式异常共用兜底恢复候选。这一项不是声称 T61 的真实运行必经空列表分支，而是拟议方案需要同时封闭的通路。
6. **支持多症状交接，不要求每条症状都有步骤。** 每个有效症状应有明确去向：有适用操作、待澄清、无资料需人工、或用户已确认解决。没有资料的症状无需硬配步骤；交接摘要必须保留。`MAX_GUIDES=1` 是一条指南上限，不是任意一张卡后立刻转人工；该值本轮可不改。
7. **模型归因需分阶段。** T61 的 intake 理解正确不代表后续 diagnose.synthesize 选择正确；“换更强模型不会改善”缺乏对照证据。更强模型不能补出官方未提供的知识，但可能改善拒绝不适用候选的判断，前提是代码不把拒绝结果覆盖掉。

原始方案保留，上述为追加复核；五单原因及离线验证见 `round5-1356/causes.md`、`round5-1356/cause-probes.json`。只改测评文档，未实施应用修复。

## 2026-10-09 14:36 round6 修复验证（T7 / T56 / T61）

修复内容：`interpret.py` 提示词 2026-10-09.2 + 新模块 `request_constraints.py`（追踪号查不到不是设备故障；有故障求助原话时补 report_problem）；`business.py` 零候选不再算 ambiguous；`answers.py` 文案改为「无法识别是哪笔订单」；`synthesize.py` 假设增加 applicability / supported_symptoms，不支持的方案丢弃，全部丢弃时 plans_ranked 为空而不是退回检索顺序；`escalation/summary.py` 交接摘要列出无步骤覆盖的症状，新增 R5 客户文案。

验证过程：`make lint` 通过；相关单测 5 个文件 60 通过。14:34 `make up` 重建镜像，六个改动文件容器哈希与工作区一致。用 round5 同一驱动 `haike-eval live-tickets --ids T7,T56,T61` 跑三次（T61 只跑第一次），报告在 round6-1436-fix-verify/。

| 单 | 运行 | 意图 | 终点 | 结果 |
|---|---|---|---|---|
| T7 | 3/3 | logistics_query | ask_order | 首句「Please share your order number or tracking number and I'll look it up.」，不再播报排障顺序，不追问型号。round5 首测误判的那条路径三次都没再出现 |
| T56 | 3/3 | report_problem + complaint | troubleshoot，2 张步骤卡 | 不再出现「涉及多个订单」。business_reference 为 null，命中 bp-0186（检查电池电量 → 按 SYNC 键），与 criteria 金标 bp-0151/0186 一致；两步 not_solved 后暂停并提出可整理交接摘要。第 2 次运行模型额外给了 warranty_query 次意图，播报「device troubleshooting → warranty check」，排障在前符合 SOP |
| T61 | 3/3 到 R5 交接；摘要完整 1/3 | report_problem（首次两条症状分开抽到；补跑两次整句一条且被 quote 校验丢弃，见下）| no_guidance，R5 交接 | synthesize 对 15 条命中全部判 not_applicable，返回空假设；不再出 rv-0522「7051」卡。客户收到「I couldn't confirm official troubleshooting guidance for the symptoms you reported」；交接摘要 observations 两条：「尚无适用步骤，待人工核实：going off 2 hours before schedule」「…cleans are not being recorded by app」，第二症状不再丢失 |

说明：
- live-tickets 对 T61 标 SOP ✗，是因为 cases.yaml 标签仍期望 troubleshoot → rv-0551/0522；criteria.md 已写明这两条是相近而非精确问题，「如实升级」在允许范围内，按 criteria 判定为正确。标签是否改为 no_guidance 另议。
- T61 的 escalate.summary 润色模型输出被拒（日志 summary polish rejected），回退为原始拼接文本，不影响内容。
- T61 补跑两次（14:40，报告 20261009T064005Z / 064013Z）：均 report_problem → no_guidance，0 张步骤卡，R5 交接，客户文案与首次相同。但两次的交接摘要 problem 字段都是「（尚未记录具体故障现象）」，observations 为空，两条症状在人工侧全部丢失。
  - 原因：这两次模型把整句抽成一条 symptom，quote 为「omni c20 isn’t following …」（单空格），而工单原文是「omni c20  isn’t」（两个空格）。`reduce.py` 第 221 行用精确子串校验 `candidate.quote not in text`，校验失败整条事实被丢弃；issue 没有 symptom，检索退回原文兜底，synthesize 仍判空走 R5，但摘要无事实可写。
  - 这不是本次修复引入的，是 quote 校验对空白不归一化的既有缺陷，被 T61 原文的双空格触发；round5 补测时模型保留了双空格所以没暴露。
  - 修法：quote 校验改为空白折叠后比较（与 `request_constraints.py` 已做的撇号归一化同类），不放宽其他约束。未实施。
  - 因此 T61 修复验证结论：3 次都不再出 7051 卡并正确走知识空白交接；但交接摘要完整列出两条症状只有 1/3，另外 2/3 需等上面的 quote 修法后复测。
- 三单的 round5 首测结果与分母不变。

## 2026-10-09 15:12 quote 校验空白归一化（T61 摘要丢症状）

改动：新增 `orchestrator/app/conversation/quotes.py`，`quoted(quote, text)` 把两边的连续空白折叠为单空格、弯撇号 ’ʼ 统一为 '，再做子串匹配；其余约束不变，quote 仍须是本轮原话片段。`reduce.py` 的 9 处、`commands.py`、`operation_conditions.py`、`sessions/l3.py`、`sessions/graph.py` 各 1 处精确子串校验全部改为调用它。回归测试 `tests/test_conversation_reduce.py::test_fact_quote_matches_across_whitespace_and_apostrophe_form`：双空格 + 弯撇号原文下两条症状入库，编造的 quote 仍被拒。lint 通过，相关 5 个测试文件全部通过。

验证：15:10 `make up` 重建，quotes.py / reduce.py / graph.py 容器哈希与工作区一致。T61 复跑三次（quote-fix/ 下 20261009T071106Z / 071113Z / 071121Z）：
- 三次 intake 的 symptom quote 都是单空格写法，`patches` 均为 2，两条症状全部入库（修复前 2/3 次为 0）。
- 三次 synthesize 都把 rv-0551 / 0522 / 0542 判 needs_confirmation 而不是 not_applicable，走澄清追问「Does the app show a warning code such as 5015 when the scheduled cleaning starts early?」。这是与本修复同时落到工作区的另一处改动（graph.py / synthesize.py / reply.py / rules/service.py，15:00–15:09，非本会话所改）：needs_confirmation 的假设带 clarification_question，无 supported 假设时先问入口前提，最多 2 次。live-tickets 驱动不回答自由文本追问，所以终点标 explain / applicability，不是 R5。
- 手工接续其中一个会话（bac5816f）：答「无错误码」→ 追问「启动时机器人是否在清扫 / 回充」→ 答「停在基站空闲」→ R5 交接。摘要 problem 四条：提前两小时启动、清扫无记录、无错误码、启动时停在基站空闲；observations 四条「尚无适用步骤，待人工核实」。两条原始症状都在，澄清得到的两条事实也在。

结论：quote 校验缺陷已修，T61 摘要不再丢症状。澄清路径是否算改善另评：对 T61 这类知识空白单，两问之后仍交接，多了两轮但摘要信息更全；criteria.md 允许「澄清时间配置 / 截图或如实升级」，在范围内。
