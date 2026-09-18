# 工作记录

## 2026-09-18 深夜
- 通读 `App` / `ChatPane` / `Timeline` / `Composer` / `HeaderBar` / `ProgressBar` 与全部 12 种卡片；对照 05_frontend-design、spec_frontend_shell_redesign、composer-discoverability、16_progress-presentation。
- 通过 `/admin/api/sessions` 挑出三个真实会话（`3dc53c04` 排障中、`7a0077bb` 愤怒后升级、`910fe4fd` 三步未解决后提退换），在 5173 用 `sessionStorage` 切入，1024 / 375 px 走查并记录问题 P1–P8（findings §2）。
- 核对记录面板所需字段在快照里的可得性：除逐轮情绪外均可从 timeline 派生（findings §4）。
- 抓取外部依据：NN/g 启发式、NN/g 聊天机器人研究（2018）、NN/g 进度指示（2014）、WCAG 2.2 SC 2.5.8、Apple HIG Layout；Material chips 页为脚本渲染，未能抓到正文，弃用。
- 写 findings.md、plan.md（共用底座 + A 服务台 / B 向导 / C 精修对话 + 对比 + 建议 + D1–D8）。
- 写原型 `frontend/prototype/visual-redesign.html`：三案用同一份真实会话数据渲染，container query 实现手机框，`?observe=1` 评审视图，深色主题；在 5173 逐个变体桌面 / 手机 / 深色截图核对，无控制台错误。修正两处：方案 A 路线副标换行、方案 B 手机端头部换行。
- 未做：截图未存盘（浏览器工具不落盘）；未改任何生产代码；未提交。

## 2026-09-19 凌晨：方案 A 落地
- 用户以 `/goal` 选定方案 A；plan.md 不动，取舍记入 addendum.md。
- 阶段 0 底座：`tokens.css` 加 `--task` 系列；`base.css` 改全屏应用（html/body 100%、正文 15 px）；`Cards.module.css` 重写（系统行、时间分隔、待办蓝边、chip、卡片解剖）；`Composer` 改单行自增高胶囊；`ChatPane` 改 intake；`AssistantBubble` 加 `cont` 合并头像；`UserBubble` / `AssistantBubble` / `SummaryCard` 去时间戳；`ObservationCard` 改 chip；`StepCard` 角标改「依据 n」并标 `data-pending`；`ToolRow` / `CaseStatus` 走系统行；删除 `ProgressBar`、`MessageTime`。
- 阶段 1：`App.tsx` 重写为 header + 记录条（手机）+ grid（对话流 + dock | 记录面板）+ 手机浮层；`Timeline` 拆出 `PendingCard` 与流内指针行，来源不进流；新增 `state/record.ts`（`deriveRecord`）与 `RecordPanel`；`HeaderBar` 精简为 48 px + 状态弹层，接受 children 放会话切换。
- 验证：typecheck 通过；`npm test` 26 文件 222 用例通过（改 4 处断言，见 addendum）。本会话自己的 dev 服务器 5174 走查：空态、排障中（3dc53c04）、升级后（7a0077bb）三种状态，1280 双栏、375 记录条 + 浮层均正常。
- 修正：记录面板依据按 `evidence_id` 去重（同一条随每次检索重复下发，曾触发 React 重复 key 报错）；记录条无产品时退回问题文本；待办 eyebrow 去掉悬挂的「·」。
