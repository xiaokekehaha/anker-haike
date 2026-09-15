# 第一步：范围、演示用例与验收口径

## 1. 目标（对齐赛题）

| 编号 | 目标 | 可验证口径 |
| --- | --- | --- |
| G5 办成 | 简单咨询直接办结；排障失败后按政策给方案、用户确认后自主办理并出回执 | A4 一轮内出物流状态；A5 从 EXHAUSTED 到回执卡 ≤ 3 次用户交互 |
| G6 不乱办 | 政策不允许 / 证据不足 / 超权限时诚实说明并转人工审批；越权执行率 = 0 | A6 与授权评测集 0 次越权；每次拒绝带条款引用 |
| G7 分对 | 一句多诉求拆成有序任务；购买地 / 渠道 / 平台差异影响方案 | A7 两个任务都被处理且顺序被告知；A6 跨区域触发 needs_human |
| G8 接稳 | 四级情绪 + 轨迹驱动不同策略，而非同一套话术 | A8 日志可见 level / trend / strategy 三元组与对应动作 |
| G9 看懂 | 图片产出结构化故障定位，直接对应计划；模糊图触发补拍 | A9 定位字段命中金标；补拍卡出现且可跳过 |
| G10 可度量 | 托管率 / 意图准确率 / NSS 在管理台可见 | Dashboard 三项指标有数、有分母说明 |

## 2. 范围

### 2.1 纳入（P0）
- 业务动作三项（D-L3-9）：`logistics.query`、`warranty.check`（只读）、`replacement.create`（写）。
- 服务上下文：购买地 / 使用地 / 渠道 / 平台四字段，来源为凭证核对事实或用户确认卡。
- 政策引擎：扫地机品类 × 2 个区域（示例 CN、EU）× 3 类渠道（官方 / 平台 / 授权经销商 / 非授权）× 3 类故障定性（quality / user_damage / safety）× 保内保外 的演示规则。
- 案件对象、最小人工审批回路、执行回执、结案与重开、满意度采集。
- 情绪四级与策略矩阵；看图结构化定位与补拍卡；多意图任务队列；简单咨询快路径。
- 三项 KPI 指标与五难点评测集骨架。

### 2.2 P1 / P2（设计到位，不在 P0 实现）
- `refund.create`、`address.update`、`rma.dispatch`；补偿一致性账本。
- 多品类目录 / 故障卡 / 计划生成管线；真实脱敏工单清洗入库；经销商真实名录；SOP → 规则编译审核流。
- 多语言（zh / en）；Bedrock 通道 bake-off；多模型交叉审核；六个检索开关按评测启用；Step Functions 案件级定时。

### 2.3 不做
- 真实支付 / 退款打款、真实物流 API、真实客服系统对接；跨会话用户级记忆；语音。

## 3. 演示用例（A4–A9，接续 A1–A3）

| 用例 | 脚本 | 期望链路 | 验收断言 |
| --- | --- | --- | --- |
| A4 查物流 | 「我的换货单 DEMO-X10-001 到哪了」 | understand(intent=logistics_query) → consult → `logistics.query` → 回答 + 来源 | 一轮完成；tool_call 事件 started/finished；回答含状态与时间；无检索、无排障 |
| A5 方案与自主办理 | A1 走到 EXHAUSTED（或用户说「修不好，我要换」）；凭证已 order_verified；购买地 CN、官方渠道、购买 200 天 | escalate(R2/R6) → service_context(已齐) → propose(policy: replace eligible, auto_allowed) → ProposalCard → confirm_proposal → authorize 通过 → execute `replacement.create` → ExecutionCard(service_order_no) → case tracking → 用户确认 → close → RatingCard | 方案卡含 ≥1 条条款引用；回执卡含单号与幂等键；case 状态到 closed；越权计数 0 |
| A6 越权不乱办 | 同 A5，但购买地 UK、使用地 DE（或渠道在名录但 authorized=false） | propose(policy: cross_region → needs_human) → 诚实说明 + 转人工审批 → await_human → admin 批准（可改方案） → human_decision 输入 → execute → 回执 | 用户端出现「等待人工审核」卡；admin 队列出现案件；批准后自动执行；拒绝则解释 + 备选 |
| A7 多诉求 | 「扫地机不吸了，另外上周的换货单发出去了吗」 | understand(primary=report_problem, secondary=[logistics_query]) → 任务队列 → 告知顺序 → 排障主链 → close 时自动 consult → 物流答案 | 两个任务都有终态；顺序告知消息存在；物流任务不打断排障等待 |
| A8 情绪接稳 | 三轮：不满 → 愤怒 → 「再不解决我投诉」 | emotion 轨迹 dissatisfied → angry → complaint_risk；策略 direct_resolution → de_escalate_and_offer_human；案件标 complaint_risk；主动进入 propose | 日志三元组；第三轮回复不再追问排障步骤；HITL 队列优先级 high |
| A9 看图定位 | 上传滚刷底部照片；再上传一张模糊图 | vision → FaultLocalization(part=滚刷, phenomenon=毛发缠绕, severity=medium) → 直接命中 rv_suction_hair_wrap；模糊图 → image_quality.usable=false → RetakeCard | 定位字段命中金标；补拍卡可跳过并继续文字流程 |

A1–A3 保持通过（回归）。

## 4. 非功能增量

| 类别 | 指标 |
| --- | --- |
| 延迟 | consult run 首可见 ≤ 2 s、完成 ≤ 8 s；propose 卡 ≤ 10 s；execute（模拟）≤ 5 s；HITL 恢复 run ≤ 8 s |
| 正确性 | 授权门未通过绝不调用写动作；同一 case 同一 remedy 只执行一次（幂等键）；政策判定可离线重放得到相同 decision |
| 可解释 | 每次 propose / authorize / execute 事件带 policy_version、clause ids、gate 检查项结果 |
| 恢复 | 执行中断后重跑同一 idempotency_key 返回同一回执；案件状态从 DB 恢复 |
| 隐私 | 外发 / 日志中订单号、单号沿用 privacy.sanitize |
| 演示 | A4–A9 可录制为回放包；模拟后端支持故障注入（超时 / 失败）演示降级 |

## 5. KPI 口径（D-L3-14）

| 指标 | 分子 | 分母 | 说明 |
| --- | --- | --- | --- |
| 独立托管率 | episode 终态 ∈ {resolved, executed_closed, consult_answered} | 终态 ∈ 上述 ∪ {escalated_human, abandoned} | 剔除 errored、replay、smoke；abandoned 按 analytics 现有 `after_hours` 判定 |
| 意图识别准确率 | primary_intent 与金标一致 | 评测集样本数 | 离线 `scripts/eval_conversation.py` 扩展意图集；在线由管理台抽样标注（复用 LabelDialog） |
| NSS | %(评分 4–5) − %(评分 1–2) | 有评分的 episode | 5 分制 RatingCard；同时展示评分覆盖率 |

## 6. 验收清单（P0 整体）
- [ ] A1–A9 回放包全部通过；巡检脚本新增越权、幂等、HITL 拒绝、模拟后端超时四类场景
- [ ] 授权评测集（≥ 20 条）越权率 0；政策决策表 pytest 全绿
- [ ] 契约 `make contracts` 前后端 Schema 一致；前端全量测试通过
- [ ] Dashboard 三项 KPI 有数据；五难点评测集各 ≥ 20 条且有基线报告
- [ ] 文档：RELEASE 增加 policy_version / actions 版本；runbook 增加模拟后端 seed 与故障注入
