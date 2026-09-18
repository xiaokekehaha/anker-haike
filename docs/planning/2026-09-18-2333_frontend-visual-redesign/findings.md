# 现状审计与依据

日期：2026-09-18 深夜。范围：`frontend/src` 客户端（不含 `admin/` 观测台）。方法：通读壳层与全部卡片组件；用本机 5173 dev 服务器加载三个真实会话（`3dc53c04…` 排障中、`7a0077bb…` 愤怒后升级、`910fe4fd…` 三步未解决后提退换），分别在 1024 px 与 375 px 宽度走查；对照仓库设计文档与赛题材料；补四条外部 UX 规范。

## 1. 现状结构

```
HeaderBar   品牌 + 「模型 / 知识库 / 数据库」健康灯 + 刷新                 (HeaderBar.tsx)
welcome     eyebrow + H1「真正听懂，真正解决。」+ 三条承诺（有历史时隐藏）    (App.tsx:55)
workspace   卡片容器
  ├ heading    「智能售后对话」+ 原生 <select> 会话切换 + 新建会话
  ├ ProgressBar 五段等宽进度（随页面滚走）                                 (ProgressBar.module.css:1)
  ├ ChatPane
  │   ├ Timeline  按 timeline 顺序平铺：气泡 / 卡片 / 工具行 / 来源抽屉 / 系统行
  │   ├ uiState   一行灰字：「请在上方卡片中选择」等                         (App.tsx:84)
  │   └ Composer  3 行 textarea（min-height 100px）+ 照片 / 请求人工 / 发送    (Composer.tsx:199, Composer.module.css:7)
  └ footer
```

与 [05_frontend-design.md](../2026-09-12_smart-service-tech-design/05_frontend-design.md) §3 的 11 个组件相比，卡片种类从 4 种扩到 12 种（product / step / observation / receipt / context / proposal / execution / retake / rating / case_changed / escalation_summary / evidence），但壳层与排版模型没有随之调整，仍是「聊天气泡 + 卡片插在流里」。

## 2. 问题清单（带证据）

| 编号 | 问题 | 证据 |
| --- | --- | --- |
| P1 | **「现在该做什么」不显眼**。待反馈卡片留在消息流里，提示文字却在流的末尾说「请在上方卡片中选择」；输入框始终是 100 px 高的大文本域，即使当前期望的是点卡片 | [App.tsx:18](../../../frontend/src/App.tsx:18) `AWAITING_TEXT`；[Composer.module.css:7](../../../frontend/src/components/Composer.module.css:7)。375 px 走查：头部 + 工作区标题 + 进度条占首屏约 42%，第一条消息才出现；步骤卡与输入框无法同屏 |
| P2 | **服务记录直到升级才可见**。产品、问题、已试步骤、依据在过程中散落为折叠行；只在 `SummaryCard` 才聚合 | [Cards.module.css:54](../../../frontend/src/components/Cards.module.css:54) `.stepCollapsed`；`SummaryCard.tsx`。官方受理三个必要条件之一是「公司必须记录买家已执行的排障步骤及结果」（[service-flow-realignment/plan.md](../2026-09-17_service-flow-realignment/plan.md) §1 第 4 条） |
| P3 | **消息流噪音**。每条气泡都带时间戳；工具行「检索知识库 · 命中 23 条来源」和「来源 23 条」抽屉各占一行；`action` 项渲染成无样式 `<div><small>`；「新问题」是裸 `<button>`；后端重复回复被完整气泡放大 | [Timeline.tsx:43](../../../frontend/src/components/Timeline.tsx:43)、[Timeline.tsx:49](../../../frontend/src/components/Timeline.tsx:49)；[AssistantBubble.tsx:23](../../../frontend/src/components/AssistantBubble.tsx:23)。会话 `7a0077bb` 截图：「当前尚未有可下发的排查步骤…」连续出现三次 |
| P4 | **头部信息对客户无意义**。「模型 / 知识库 / 数据库」健康灯是运维信息；手机端占两行 | [HeaderBar.tsx:19](../../../frontend/src/components/HeaderBar.tsx:19)；375 px 截图头部高约 300 设备像素 |
| P5 | **卡片形态不统一**。判别卡自带标题「选择最接近的情况」，与上一条消息里的问题重复；选项是独立卡片而不是紧贴问题的快捷回复；`ProposalCard` / `ContextCard` 复用 `.feedbackButtons` 但按钮语义（确认 / 拒绝 / 转人工）无主次 | [ObservationCard.tsx:34](../../../frontend/src/components/ObservationCard.tsx:34)；`ProposalCard.tsx` 四个同级按钮 |
| P6 | **情绪分级与策略在界面上不可感知**。四级情绪 + 五种策略是「接稳」难点的核心实现，但客户端只在摘要文本里出现原始枚举 `【情绪】angry / direct_resolution` | [SummaryCard.tsx:45](../../../frontend/src/components/SummaryCard.tsx:45)；策略矩阵见 [06_five-difficulties.md](../2026-09-14_l3-closed-loop-design/06_five-difficulties.md) §4 |
| P7 | **会话与问题切换用原生控件**。`<select>` 标签长而被截断；多问题切换也是 `<select>` | [SessionSwitcher.tsx:37](../../../frontend/src/components/SessionSwitcher.tsx:37)；[Timeline.tsx:39](../../../frontend/src/components/Timeline.tsx:39) |
| P8 | **进度条随页面滚走**，中途看不到阶段；五段等宽在手机端只剩 10 px 字 | [ProgressBar.module.css:12](../../../frontend/src/components/ProgressBar.module.css:12) |

P3 里的重复回复属于后端问题，不在本轮范围；但前端把每条回复都包成带头像、边框、时间戳的完整气泡，让重复更刺眼。

## 3. 现有设计里要保留的约束

- **进度不是完成度**：`progress.ts` 的注释「A route is a roadmap, not evidence that every earlier step was completed」（[16_progress-presentation.md](../2026-09-14_l3-closed-loop-design/16_progress-presentation.md)）。任何方案里走过的阶段都不能画成「已完成」勾。
- **人工状态如实**：`prepared` 只表示整理好了记录，不能显示成「已接入人工」（[SummaryCard.tsx:11](../../../frontend/src/components/SummaryCard.tsx:11)）。
- **只有 pendingInput 指向的卡片可交互**，其余置为历史（`Timeline.tsx` 顶部注释）。
- **卡片是预注册的固定组件**，模型只提供经校验的字段，不生成 UI（05 §3）。三案都不改这一点。
- **输入框始终可用**：观察题出卡后仍可打字（`Composer.tsx` `OBSERVATION_HINT`）。这条与 NN/g 的结论一致，见 §5。
- 已有的可访问性基线：skip link、`aria-live`、`focus-visible`、减少动效媒体查询、390 px 无横向溢出（[spec_frontend_shell_redesign.md](../../claude/spec_frontend_shell_redesign.md)）。

## 4. 数据可得性（前端能否不改契约就画出来）

| 方案里要展示的 | 数据来源 | 结论 |
| --- | --- | --- |
| 产品名 / SKU / 品类 | `product_card.candidates` + `selected_sku`；或摘要 `summary.product` | 可得，选卡后即有 |
| 问题描述 | 首条 `user_message`；摘要 `summary.problem` | 过程中只有原话，结构化描述要等摘要 |
| 阶段路线 | `state.stage` + `progress.ts` | 可得 |
| 已试步骤与结果 | `step_card.feedback` / `note` / `observation_answers` | 可得 |
| 依据条数与片段 | `evidence.items`、`step.evidence_ids`、`primary_evidence_id` | 可得 |
| 案件状态 / 服务单号 | `case_changed.status` / `external_refs`；`execution_card.receipt` | 可得 |
| 人工接续状态 | `escalation_summary.handoff_status` | 可得 |
| 情绪等级 / 策略 | 仅 `escalation_summary.summary.emotion`；过程事件里没有 | **过程中不可得**，评审视图若要逐轮显示需要后端在 `progress` 事件或新 timeline 项里带出 |
| 规则码 / plan id / 模型 tier | `summary.reason.rule_id`；`step.evidence_ids` 里的 `plan:` 前缀；`assistant_message.model_tier` | 部分可得 |

结论：三案的客户可见部分都不需要改契约；「评审视图」里的逐轮情绪需要一次契约扩展（可选）。

## 5. 外部依据

| 来源 | 结论 | 支撑的设计点 |
| --- | --- | --- |
| Nielsen, *10 Usability Heuristics for User Interface Design*（NN/g，1994，2024-01 复核）, https://www.nngroup.com/articles/ten-usability-heuristics/ | #1 系统状态可见；#6 识别优于回忆（把选项和动作摆在眼前）；#8 极简（不放无关或少用的信息） | P1 停靠待办、P4 去健康灯、P6 记录面板 |
| Budiu, *The User Experience of Chatbots*（NN/g，2018-11）, https://www.nngroup.com/articles/chatbots/ | 按钮与自由文本**两者都要有**，只给选项会让用户觉得被限制；明示能力边界；坦白失败并给人工出口会被正面看待 | 快捷回复贴着问题、输入框永不禁用、「请求人工」常驻可见 |
| Sherwin, *Progress Indicators Make a Slow System Less Insufferable*（NN/g，2014-10）, https://www.nngroup.com/articles/progress-indicators/ | 超过约 1 s 的等待要有反馈；能看到进度的用户平均多等 3 倍；确定性指示优于无限转圈 | 检索中的过渡状态行；阶段路线常驻 |
| WCAG 2.2 SC 2.5.8 Target Size (Minimum)（AA）, https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html | 指针目标至少 24×24 CSS px，或间距足够 | 快捷回复 chip ≥ 36 px 高，结果按钮 ≥ 44 px |
| Apple HIG *Layout*, https://developer.apple.com/design/human-interface-guidelines/layout | 触控目标建议 44×44 pt；按重要性分层，次要内容弱化 | 手机端结果按钮 48 px；头部降级 |
| Anker 线上客服实测（[service-flow-realignment/findings.md](../2026-09-17_service-flow-realignment/findings.md)） | 受理第一步是五选一分流；Live Chat 开场白要求「一条消息里同时给型号与问题」；质保表单先验单号、后要凭证与地址 | 首屏 intake 的写法；记录面板的字段口径 |
| 赛题解析（[hackathon-brief-gap-analysis/findings.md](../2026-09-14_hackathon-brief-gap-analysis/findings.md) §5） | 评判看五个难点「处理得有多深、多实」；交付形式是**现场可交互演示** | 评审视图；让「看图 / 问清 / 分流 / 接稳 / 幻觉」的处理在界面上可被看见 |

## 6. 走查截图要点（未存盘，按需在 5173 复现）

- 桌面 1024 px，会话 `7a0077bb`：三张步骤卡都折叠成一行，两份摘要卡各占约 300 px，两份之间夹着四条几乎相同的助手回复。
- 桌面 1024 px，会话 `3dc53c04`：步骤卡「按 A1289 官方方法复位」处于待反馈；卡片下方是 uiState 灰字，再下方是 100 px 高的输入框，三者都在首屏之外。
- 手机 375 px：头部两行（品牌 + 三组健康状态），再是工作区标题与会话切换两行，再是五段进度；第一条用户消息出现在约 800 / 1624 设备像素处。

复现命令：dev 服务器已在 5173（另一个会话启动）；浏览器控制台执行 `sessionStorage.setItem('haike.session_id','<id>'); location.reload()`。
