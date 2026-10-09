# addendum

勘误与复评追加于此；plan.md 开发开始后不改写。

## P1-1 根因（2026-10-09）

plan.md 把 P1-1 写成「订单截图走默认 purpose=fault 被当故障照片」。按第一性原理追下去，这不是 T55 的案例缺陷，
而是两个跨全部工单的结构缺陷。两条都按根因改，没有加 `if ticket == T55` 一类分支。

### 根因 1：purpose 被当成「这张图是什么」，但它记的是「上传时系统在等什么」

`ImageRefItem.purpose` 全系统只有一个写入点：前端 `App.tsx:105` 的 `receiptUpload ? 'receipt' : 'fault'`，
即 pendingKind 是不是 `upload_receipt`。它是**上传时机**，不是图片内容。两个消费端却按内容读它：

| 消费点 | 原读法 | 后果 |
| --- | --- | --- |
| `diagnose/vision.py` | `purpose=="fault"` → 送故障读图 | 订单截图被当故障照片做曝光门控 |
| `sessions/evidence.py` | `purpose!="receipt"` → 记 `photo_or_video` | 单据截图充当「故障图片/视频」，凑齐 `gate.py` 换货证据四件套 |

第二条是测评报告里「更严重」的那一半，且与 T55 无关：**任何**客户在非 `upload_receipt` 时机上传的任何
单据截图都会被记成故障证据。缺的是一个从未被测量过的事实——「这张图实际是什么」。

修法：`diagnose.vision` 的输出 schema 加 `content_kinds`（逐图 fault_photo / document / other），
不额外增加模型调用。`localization.normalize` 按定性确定性地丢掉非 fault_photo 图上的 finding
（提示词也要求了，但约束的执行权不该握在被约束者手里）。`evidence.collect` 排除判为 document 的图。

**方向刻意选的是「排除确认不是」而不是「只认确认是」。** 先写成白名单（只认 fault_photo），
`tests/test_conversation_l3.py` 立刻挂了 4 条——`HAIKE_LLM=off` 或视觉链故障时没有任何图能成为证据，
正常换货流程被整个堵死。视觉链故障是运维事件，不该让每一单换货都卡在「无法测量」上；
改成排除式后，读图没跑时退回按上传时机判定，与修复前同行为，只有**确认是单据**时才扣减证据。

### 根因 2：过曝的判据建在与可读性无关的量上

`too_bright` 原定义为「亮度 ≥250 的像素占比 > 0.5」。白底文档天然 80–96%。
实测 `data/official/attachments` 全部 10 张 + 由其中 5 张设备照合成的 50 张退化样本：

```
真实单据 T53   clipped=0.93  focus=148   ← 原判 reject，人眼完全可读
真实单据 T55   clipped=0.96  focus=134   ← 原判 reject，可读
设备照 ×6.0    clipped=0.89  focus=48    ← 判 reject，确实不可读
正常设备照     clipped=0.004 focus=50
```

`clipped` 只数白像素，不看白像素之间还剩不剩结构，所以区分不开「背景是白的」与「细节被烧掉了」。
`focus`（梯度 99.5 分位）恰好看结构，且分离干净、中间有大间隔：文档 133–201 / 真过曝 13–80 / 正常 18–58。
注意文档的 focus **高于**正常照片，所以这不是给文档开后门——「饱和」本来就不蕴含「不可读」。

修法：`too_bright` 的 reject 改为合取（`clipped > 阈值 AND focus < structure.exposure_reject_below`）。
在 35 个判定样本上零误判（5 张真实单据全部从 reject 降为 marginal，25 个真退化样本仍全部硬拦）。

**试过但放弃的路**：加一个像素级的「是不是文档」判别（白点占比 / 彩度 / 墨色占比）。
T14 过曝 6 倍后 chroma 4.45、ink 0.029，与真实文档 T46 的 5.10、0.036 完全重叠——既是 case-when 又不可靠。

**`too_dark` 不加这个条件。** 最初出于对称加了，被 `test_vision_graph.py` 两条用例挡回来，复查后确认对称
不是理由：`too_dark` 的硬阈值是 `luma_p95 < 60`，即整幅画面 95% 的像素接近全黑；白底单据不会这样，
曝光正常的深色机身（p95 ≈ 205）也不会。没有被它误伤的合法输入类别，就不加这个条件。

### 改动清单

- `contracts/haike_contracts/common.py`：新增 `ImageContentKind`；`FaultLocalization.content_kinds`
- `contracts/haike_contracts/snapshot.py`：`ImageRefItem.purpose` 补文档说明它是上传时机
- `config/vision_vocab.yaml`：新增 `structure.exposure_reject_below`，重标曝光阈值注释
- `orchestrator/app/images/quality.py`：`assess` 的 too_bright 改合取；新增 `structure_floor()`
- `orchestrator/app/diagnose/vision.py`：schema 加 `ImageKind`；提示词第二步逐图定性；
  `VisionOutcome.document_image_ids`；`VISION_PROMPT_VERSION` → `2026-10-09.1`
- `orchestrator/app/diagnose/localization.py`：`_content_kinds` 归一；非 fault_photo 图的 finding 丢弃
- `orchestrator/app/sessions/evidence.py`：`photo_or_video` 排除 document
- `orchestrator/app/sessions/graph.py`：`SessionState.document_image_ids` 并累积
- `orchestrator/app/evaluation/live_tickets.py`：`fault_photos` / `DOCUMENT_ATTACHMENTS`（见下节）
- 生成产物：`contracts/schema/*.json`、`frontend/src/types/{events,snapshot}.ts`、`frontend/src/api/events-schema.ts`

`sessions/graph.py:361`（`_new_fault_images`）**保持**按 purpose 选图：它决定「哪些图要送去读」，
而一张传在故障位的单据必须先被读过才能认出是单据。

### 验证

- `orchestrator` 全量 794 passed / 2 skipped；`make lint` 零告警；`npm --prefix frontend run typecheck` 通过
- 新增 `tests/test_vision.py` 8 条，锁真实主办方附件而非合成图（顺带覆盖 plan.md 的 P6-1 意图）
- 真实链路（`make up` 重建镜像后打 localhost:8000）：T55 原文 + 原附件、`purpose=fault`
  → 无补拍卡；读图定性 document；直接进 `qa_bp_0102`；排障失败后待补材料为
  「a photo or video of the fault, product serial number (SN)」。修复前只剩 SN。

### 评测驱动同步修正（plan.md P1-1 的第三句是对的，我先判错了）

plan.md P1-1 写「live_tickets 驱动同步区分附件用途，避免继续掩盖」。我起初判断不需要改驱动，错了。

改完消费端后跑 63 单，T46 与 T55 两单从 `warranty_replace` 掉到 `troubleshoot`（sop 95%）。
查下来不是回归，是驱动在替系统假装证据齐全：`run_case` 在被追问「故障照片」时回传的是**工单原附件**，
而 T46 / T55 的原附件就是订单截图。修复前它被错记成故障证据，于是单子走完；
修复后系统正确拒收，驱动手里没有别的图，`supplied` 标记已补、循环退出，终点停在排障。

所以掉下去的两单恰好是「原附件是单据的 warranty_replace 单」全集，这反过来佐证了修复生效。
驱动改法：首封仍按工单原样发（单据截图走 purpose=fault 正是真实前端默认路径，要让它一直压在回归上），
只有被追问故障照片时改送同品类的真实设备照（`fault_photos`，仍取主办方原始附件：
吸奶器 T48.jpg 外壳裂纹、扫地机 T14.jpg）。评测要测的是「证据齐全后能否提交」，
不是「能否用一张订单截图蒙混过关」。

## DD1 决策（2026-10-09）

选 a：维持统一英文，改掉「语言一致 100%」的指标口径，演示时主动说明取舍。
需要改的两处（随 P3-2 一起做，尚未改）：
`2026-10-07-1543_organizer-materials-replan/plan.md` §4 的指标、
`2026-10-09-0828_official-case-evaluation/criteria.md` 里要求回应荷兰语客户的那条。
改口径后 T13 的判定从「部分正确」变为「正确」（业务事实与处理方向本就正确）。

## P1-2 根因（2026-10-09）

plan.md 写「T55 产品卡重复弹出：排障走完后客户传照片、回 SN 各弹一次」。
从 12 单回放留下的会话（`75eba490…`）的 journey 复现到了精确位置：
`prepare_card` 在 run 5 与 run 7 各出现一次，而 run 1–4 早已带着已确认的产品走完排障。
两次的形态相同：`understand` 记录 `product_state: confirmed_sku`，紧接着 `disambiguate`
把它改成 `unknown` 并重新出卡。

根因是 `clarify.decide` 里的两处不对称，都与 T55 无关：

### 1. 产品已确认后，仍会拿「只增不减的旧线索」去推翻它

`_lookup(catalog, text, hints)` 在本轮原话查不到型号时回退到 `product_hints`，
而 hints 跨轮累积（`reduce.py:269` 的 `[...旧, ...新]`）。首封的「S1 Pro」是跨品类同名别名，
`lookup_product("S1 Pro")` 返回 `[T2080 扫地机, T8D04 吸奶器]` 两个候选。
于是排障走到一半，客户回一句「Here are photos of the problem.」—— 本轮原话里没有任何型号 ——
旧 hint 被重新查成两个候选，`decide` 的 `len(cands) > 1` 分支把已确认的 T8D04 判成
「提到了别的型号」而作废，产品卡再弹一次。

改法：产品已确认时不再回退到 hints（`[] if confirmed else hints`）。
已确认的产品是更强的证据，推翻它要靠本轮原话里真的出现别的型号，而不是一条旧线索。

### 2. 同名别名的品类消歧只写在「未确认」分支里

`if len(cands) > 1 and category: 取同品类的那一个` 这段原本只在 `else`（未确认）分支。
已确认后反而失去定位能力：客户说「my S1 Pro vacuum broke」，原话两个候选都命中、
品类词 vacuum 已经说明是哪一台，却只能作废产品再弹卡。
改法：把这段提到两条分支之前，对「已确认」与「未确认」一视同仁。这是删特例，不是加特例。

验证：两条都各有一条会在回滚时变红的用例（实测验证过）。
真实链路 T55 走到底 + 追加传照片、回 SN 两轮，产品卡 0 次（修复前 2 次）。

## P1-3 根因（2026-10-09）

plan.md 写「T1 物流路由不稳定：4 次里 1 次被判成故障」。先量化基线：
T1 同一原文跑 8 次，2 次判成 `report_problem`（次诉求 `logistics_query`），
回复是「I'll handle your requests in this order: device troubleshooting → delivery status」，
而这单根本没有故障可排。

根因不是某个模型调用的抖动，是**缺一条客观约束**：
「东西从来没送到」与「这台设备有故障 / 我要换这台设备」在物理上互斥 ——
没到手的机器既不可能有观察到的故障现象，也没有什么可换。
63 单里说「从未收到」的 4 单（T1 T2 T8 T10）金标全部是物流分支，没有一单是排障或换货，
所以这条约束在样例集上零误伤（有一条用例守着这个前提，将来新增反例会先变红）。

提示词里已经写了「逐一识别本轮每个独立诉求」，模型仍有约 25% 概率读错，
所以这条约束放进代码，而不是继续加提示词。实现上复用已有的 `logistics_correction`
（它本来就在纠 `order_query` → `logistics_query` 的同类问题），不新开一条并行通道。

### 修的过程中暴露的两个更深的问题

**a. 降级路径绕过了纠正。** 第一版只在模型分支调 `logistics_correction`，重测仍有 1/10 失败。
查 journey 发现那次走的是 `l3_rules_degraded`（模型 schema_error 重试耗尽后的关键词降级），
它直接 return，没有经过纠正。而模型调用失败恰恰是最容易判错的时候。
改法：把纠正挂在 `interpret_turn` 的出口上，两条分支都过。

**b. 降级的关键词表把 T1 读成换货请求。** `config/rules/intent_terms.yaml` 的
`replacement_request` 含 `replacement`，而 T1 原文「Only the replacement parts kit」
是在描述**收到了什么**，不是诉求；`replacement_request` 在 `tasks.PRIORITY` 里还高于物流。
也就是说降级路径下这单会去提议换货。同一条「没到手」约束正好覆盖它，
所以把约束的适用意图从 `report_problem` 扩到 `{report_problem, replacement_request}`，
而不是给关键词表打补丁。

**c. 次诉求也要清。** 写完 b 后测试仍红：降级把 `logistics_query` 放主、
`replacement_request` 留在次诉求里，而第一版只在「主诉求不可能」时才清次诉求。
不可能成立的诉求出现在哪个位置都不该留 —— 留着会让 `tasks.enqueue` 发
「按顺序处理」的多诉求提示，并把一个不存在的换货任务排进队列。

验证：T1 同一原文连跑 16 次，16/16 `logistics_query`，0 次「按顺序处理」提示
（基线 2/8 错；只修模型分支时 2/10 错）。63 单里「从未收到」的 4 单 T1/T2/T8/T10 全部通过。

### 遗留：T9 意图漂移（**未修，非本次改动引入**）

P1-2/P1-3 之后的 63 单回放里 T9 从 `logistics_query` 变成 `product_question`
（终点 `logistics_presale` → `clarify`），复跑 6 次有 5 次如此，不是偶发。
时间上正好卡在这次改动，但已证明与改动无关：

- A/B 实测：把 T9 原文和 5 种主/次诉求组合分别喂给**基线版**与**新版** `logistics_correction`，
  两者输出逐项相同（脚本思路见 progress.md）。
- `NEVER_ARRIVED` 不匹配 T9 原文（T9 说的是 "I only received the filters"，不是「从未收到」）。
- 两处 clarify 改动都要求 `len(cands) > 1`，而 T9 在目录里零候选。
- 容器日志里模型**原始输出**就是 `primary_intent: product_question`，在所有本地代码之前。

真实原因是 T9 本身是多诉求工单：「If you have not shipped, don't and let's first talk about
your other products.」——「想聊别的产品」被模型读成 `product_question`。
这正是 plan.md P2-1 记的那条（子诉求未被处理），只是这次它抢走了主诉求位置。
留给 P2-1 一并处理，不在 P1-3 里顺手改意图优先级：那会把一条真实的多诉求压成单诉求，
掩盖 P2-1 要解决的问题。

另注：一次 T9 复跑里观察到客户可见文字混入中文
（"用户提到 'your other products' 并询问，但未明确…"），属 P1-4 客户可见文本残留，一并记在那条下。

## P1-4 根因（2026-10-09）

plan.md 列了三处。实际扫描「后端下发、直接显示给客户」的固定文案后，范围与 plan 的描述有两处出入：

- **补拍指引**（config/vision_vocab.yaml 的 `retake_guidance`，6 条全中文）——确认，已改英文。
- **步骤卡 expected_result**（`app/plans/qa.py` 的 `EXPECTED`）——确认，已改英文。
- **读图回显**（`localization.echo_findings` 的「从照片里我看到：…」）——plan 未列，同样是客户可见，
  一并改英文。部件 / 现象走 `vision_vocab` 已有的 `english` 映射（`conflict.en()`），不新建第二套词表。
- **qa.yaml 客服口吻**：plan 说「约 6 处」，实测全库只有 2 处
  （`Have the user shine a flashlight…`、`The user can press…`）。

边界依据既有决策：replan addendum §D2 写明「转人工摘要、观测台、**前端界面保持中文**」，
所以 `RetakeCard.tsx` 一类界面文字不在本项范围内，只改后端下发的文案。
`receipt.NEXT_STEP` 也保持中文：它进的是转人工摘要，不是客户可见回复。

### qa.yaml 不能手改

`data/official/qa.yaml` 文件头写明「生成文件，勿手改：python -m app.official.build」，
来源是主办方 XLSX（带 sha256）。改它既违反生成文件约定，也会让本地数据与主办方原文悄悄分叉。
所以人称改在**渲染层**（`plans.qa.customer_voice`），只改人称、不动操作内容，
证据里仍是原文。`guide/steps.py` 出卡与 `reply.py` 解释步骤两个出口都过这一道。
有一条用例把全部 875 条 Q&A 渲染一遍，断言渲染后不再有客服口吻。

## P2 根因（2026-10-09）

### P2-3：补发理由与事实相悖（T5）

`SOP_TEXT` 按 verdict 写死，而 `reship_eligible` 有两条互不相同的来路：退回发件人，和
「在途但已过预计送达日」。T5（Anker005）主机包裹 ETA 9/30 逾期未达，同一订单的配件包裹 9/15 已送达，
套用「Tracking doesn't show the item as delivered」就是假话。
改法：新增 `logistics.sop_text(order, as_of)`，理由从包裹状态推出来而不是按 verdict 取。

### P2-2：换货诉求跳过排障（T49）

`route` 里 `intent in REMEDY_INTENTS → service_context` 直接进办理流程。
主办方业务 DOCX 的 SOP 是「保内**排障无效**可换货」——排障是前置条件，不是另一条路。
改法：`_troubleshoot_before_remedy` 四个条件同时成立才先排障（只管换货/退款、本会话没排过、
确实有现象可排、还没进办理流程），避免把客户困在排障里。

### P2-4：没查过订单却说「没查到订单」（T14）

`I couldn't find an order` 写在 else 分支里无条件输出。T14 是 App 自动生成的报障表单，通篇没有订单号，
根本没查过；而且跳过了「为什么现在谈保修」。改法：
`customer_gave_order_no` 区分「查了没找到」与「压根没给」；
`hardware_basis` 由 `diagnose_outcome` 驱动补一句依据（官方 Q&A rv-0028 已把 4090 判为硬件故障），
来路不明时返回 None，不编理由。

### P2-5：两处小问题

- T7「按顺序处理」：查询类诉求（物流/保修/订单）都是从同一张订单读字段，一轮答完，
  不会分轮处理。`announces_order` 只在真要分步时才播报。
- T12 结束语引述被截断的 Q&A 标题：`closing_text` 不再引述以「…」结尾或本身是问句的标题。

### P2-1：T9 的「先别发货」（这一项绕了弯路，记录完整）

63 单里只有 1 单命中「别发货 / 取消订单」，按「按典型场景设计」不该为它加架构。
但失败很严重（对客户说了与诉求相反的话），所以取**最小机制**：复用既有的 `address_update`
那条「本系统办不了 → 如实说明 + 转人工」通路，把它推广成 `NOT_EXECUTABLE` 这一类，
新增 `order_change` 意图归入其中。没有新流程、没有新卡片。

过程中踩了三个坑，都已修并各有用例：

1. **加了意图就过度触发。** 提示词写「要求暂缓发货…都是 order_change」之后，实测 T1
   「Was the vacuum shipped?」、T9 开头的「inquire about the shipping」全被判成 order_change
   （8 单 SOP 掉到 75%）。与 P1-3 同一个教训：提示词约束不住，补确定性守卫
   `ORDER_CHANGE_WORDS`，没有明确原话就退回查询。
2. **办不了的诉求变成了换货。** `requested_type()` 的兜底 `return "replace"` 把 order_change
   一路变成 `warranty_replace`。这是早就存在的隐患（`address_update` 同样会中招），
   只是之前没有意图触发到它。改法：`service_context` 入口先截住 NOT_EXECUTABLE，
   并给 `requested_type` 加断言，让这类错误以后直接炸出来而不是悄悄发一张换货单。
3. **撇号。** T9 原文是 `don’t`（U+2019），而所有规则只认 `'`，整条漏掉。
   63 单里有 15 处弯撇号——这不是 T9 的特例，是全部带撇号规则的共同前提。
   改法：`logistics_correction` 入口统一归一撇号。

最后一层：模型稳定地把 T9 读成 `product_question`（只读到「想聊别的产品」那半句），
`order_change` 根本不会被它选中。所以守卫做成双向——有明确原话却没识别出来时，
把 `order_change` 补进次诉求队列，不抢主诉求。明确的要求不该取决于模型挑了哪半句。
这同时解释并解决了上一节记的「T9 意图漂移」。

### P2-1 续：另外两个坑（接上）

4. **守卫放错了位置，客户收到空回复。** 把 NOT_EXECUTABLE 的拦截放在 `service_context` 开头提前返回，
   结果 `propose` 读 `state["case_id"]` 抛 `CaseNotFound: None`，整轮异常，客户什么也没收到 ——
   比原来的缺陷更糟。原因是 `service_context` 没有通往 `await_human` 的边，而且 case 还没建。
   改法：拦截点挪到建完 case、`emit_case` 之后，说明文字就地发出，路由走既有的 `commit_issue`。
   教训是：这类「提前返回」要先确认它跳过了哪些必须的副作用。

5. **第二处写死的补发理由。** P2-3 改完 `logistics.SOP_TEXT` 后 T5 实测仍是旧话术 ——
   同一句话在 `l3.TYPE_DETAILS["reship"]` 里还有一份拷贝，方案卡走的是后者。
   改法：删掉这份拷贝，`type_detail()` 统一按包裹状态取，`execute` 里的服务单理由直接沿用
   option 上已经算好的那句，不再第三次重复。

### 评测口径：新增 order_change_human 终点

T9 现在的行为是「答发货日 + 如实说明改不了订单并转人工」，而 `terminal_of` 没有这个终点，
被归成了 `explain`（判错）。这是口径缺项，不是行为错误：
- `terminal_of` 新增 `order_change_human`（客户可见文字出现「passed your request to」时命中）；
- `ACCEPT["logistics_presale"]` 接受它 —— 标注 note 本来就写着「转人工可选」；
- `cases.yaml` 新增可选的 `intent_alt`：T9 一句两诉求，单标签表达不了，
  答发货日（logistics_query）与识别出暂缓发货（order_change）都算对，后者其实更完整。

这一项**放宽了口径**，与 P3-2「收紧口径」方向相反，所以单独说明：
放宽的是「同一句话的两种合理读法」，不是「多种终点都算对」。
T9 原来的失败（只回发货日就结束、完全不提暂缓诉求）在新口径下仍然判错 ——
它的终点会是 `logistics_presale` 且客户可见文字里没有那句说明，不会命中 `order_change_human`。




### 改动清单（P1-2 / P1-3）

- `orchestrator/app/sessions/clarify.py`：`_lookup` 在产品已确认时不回退 hints；
  同名别名的品类消歧提到两条分支之前
- `orchestrator/app/conversation/interpret.py`：`NEVER_ARRIVED` 约束与
  `IMPOSSIBLE_WHEN_NEVER_ARRIVED`；`logistics_correction` 覆盖主/次诉求并清理症状事实；
  降级分支同样走纠正
- 测试：`tests/test_sessions_clarify.py` +3、`tests/test_conversation_official_tickets.py` +6

