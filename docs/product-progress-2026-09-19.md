# 海科智能售后服务 Agent：进程、核心功能与算法原理

整理日期：2026-09-19。依据：仓库代码（`orchestrator/app`、`frontend/src`、`config/`、`contracts/`）、117 次提交记录（2026-09-12 至 2026-09-19）、`docs/planning/` 下 70 余份规划与复盘文档。本文只陈述代码里已有的东西；「演示数据」「默认关闭」等状态按代码与配置如实标注。

---

## 1. 一句话定位

面向 Anker 售后（扫地机 / 充电 / 音频 / 安防 / 母婴等品类）的对话式服务 Agent：用户用文字和照片描述故障，系统完成情绪识别、产品消歧、多模态故障定位、分步排障、保修判定与人工升级；每一步都有来源、可回放、可观测。

设计原则贯穿全部模块：**模型只做「理解」和「排序」，业务决策由确定性代码 + 配置做出**；所有给用户的操作必须来自预写计划库并带证据引用；「宁可说不知道，不可说错」。

---

## 2. 进程时间线

| 日期 | 里程碑 | 提交数 |
| --- | --- | --- |
| 09-12 | 仓库初始化；契约（事件 / 动作 / 快照）、Compose 骨架、SSE 会话流、动作幂等与会话锁、图片上传、凭证收集与 OCR、HTTPS / 限速 / 密钥隔离、CI / 发布 / 回滚骨架、数据库迁移与备份 | 25 |
| 09-13 | 会话记忆 V2 主链路；管理员观测台；有界 Agentic RAG；模型 bake-off 与三家厂商链冻结；回放包 A1–A3；巡检脚本；进程内告警；数据保留与脱敏 | 13 |
| 09-14 | L3 闭环设计（19 篇）：动作层、政策引擎、案件与人工介入、五难点深化、任务归属、执行恢复 | — |
| 09-15 | 读图从「一次模型调用」重构为「一次可信的测量」（像素画质门控 + 铭牌复看交叉核对）；R7 误升级三例修复；证据驱动下一动作 | 10 |
| 09-16 | 步骤观察驱动排障闭环（统一下一动作与结束原因）；安全词否定语义；问诊不再复读；锚点主引用与回复引用归因 | 15 |
| 09-17 | 多品类支持对齐官网五大产品线（57 SKU / 20 品类）；定向采集 11 篇官方支持文章；按公开售后政策重建保修规则；上下文预算按任务管理 | 18 |
| 09-18 | 候选池与最终证据分离、充分性驱动一次补查；观察卡片；判别提问优先于步骤；诊断回退方案试验后整体回滚（决策留痕）；7 个发布版本 | 29 |
| 09-19 | 观测台按角色重组（工作台 / 看板 / 会话 / 诊断）；观察越出已记录范围先澄清一次；服务台布局方案 A 落地 | 7 |

规模快照（2026-09-19）：后端 Python 约 3.35 万行、单测 792 个；前端 26 个测试文件 222 个用例；发布清单 23 版；知识库 kb_manual 40 篇（8 篇人工手册 + 7 份 FAQ + 25 篇官方文章）、kb_tickets 380 条演示工单；预写计划 57 条。

---

## 3. 系统架构

```
 用户端（React 19 + Vite）                      管理端（同一前端包 /desk /board /sessions /lab）
   Composer / Timeline / 卡片(产品·步骤·观察·凭证·摘要·方案·执行) / 证据抽屉 / 服务记录
        │  POST /sessions/{id}/messages · /actions  +  SSE 事件流（Last-Event-ID 续接、断连不中止 run）
        ▼
 编排服务（FastAPI + LangGraph，Python 3.12）
   ┌──────────────────────────────────────────────────────────────────────┐
   │ 会话层：幂等 input_id · pg_advisory_lock 会话锁 · 409 附完整快照      │
   │        · run deadline 25 s / ping 5 s · 取消 · 孤儿 run 收尾          │
   │ 图节点（每次输入一次 START→understand→…→commit_issue→END，无跨轮中断）│
   │   understand → disambiguate / clarify / out_of_scope / prepare_card   │
   │   → vision → retrieve → reply / guide → ask_observation / reassess    │
   │   → escalate → prepare_receipt → receipt_extract → summarize / close  │
   │   L3：service_context → propose → authorize → execute → track         │
   │       await_human / apply_human_decision / consult / reopen_case      │
   │ 语义层：interpret_turn 一次抽取意图·事实·答案·操作信号 → reduce 校验落库│
   │ 决策层：decide_symptoms / decide_next / PolicyEngine / rules 检查点    │
   │ 模型层：ModelRouter（任务→模型链，降级 / 重试 / 预算 / 有界并发）      │
   └──────────────────────────────────────────────────────────────────────┘
        │                      │                       │
   PostgreSQL(pgvector)     Redis                 WeKnora v0.8.0
   checkpoint · 会话投影 ·   会话锁 · 限速          kb_manual / kb_tickets
   案件 · analytics 事实表                          hybrid(BM25+向量) 父子分块 800/200
        │
   厂商模型：DeepSeek / 通义(dashscope) / 智谱；海外通道 Anthropic / Google
```

契约由 `contracts/haike_contracts/` 的 Pydantic 模型单一来源导出 JSON Schema 与前端 TypeScript 类型（`make contracts`），CI 做漂移检测。当前 26 种事件类型、13 种用户动作、1 个会话快照结构；等待用户输入是持久化的业务状态 `pending_card`，不是图的 interrupt，所以服务重启、断连、重放都不丢位置。

## 4. 核心功能

### 4.1 情绪识别与安抚策略

- **输入**：intake 任务一次结构化抽取 `emotion_level ∈ {calm, anxious, angry}`、产品线索、症状短语、`wants_human`。
- **落地**：`app/emotion/policy.py` 把模型判定与规则词表合并成四级 `calm(0) < dissatisfied(1) < angry(2) < complaint_risk(3)`，再按 `config/emotion_policy.yaml` 的有序规则映射到五种策略（normal / reassure_first / reassure_and_shorten / direct_resolution / de_escalate_and_offer_human）。策略只改变**语气与动作集合**（如 `shorten_steps`、`prefer_proposal_over_more_steps`、`offer_human`），不改变业务事实。
- **关键约束**：模型给的情绪必须能在原文里引到依据（cues），引不到的 calm 视为「无信号」而不是「平静」；规则词表命中可以抬高级别但不能压低。

### 4.2 产品消歧

- 目录 `config/products.yaml` 57 个 SKU、20 个品类，含别名；`product_state ∈ {unknown, category_only, confirmed_sku}` 三分。
- 「S1 Pro」同时命中吸奶器与扫地机 → 出产品卡让用户点选；只知道品类且该品类知识不按型号分化 → 不问型号直接进症状问诊（spec 2026-09-19-0810 的三档判定 T0/T1/T2）。
- 照片里认出品类特有部件（滚刷 / 插脚 / 充电盒 / 镜头 / 喇叭罩）只作为**待确认**线索，不静默锁定；铭牌读出的型号必须通过复看核对（见 §5.6）。
- 范围外产品走 R8 子流程；用户改口范围内品类即切换。

### 4.3 多模态故障定位

- **文字路径**：受控症状词表（`symptom_taxonomy.yaml`）把口语归一成症状码，否定前缀「不是 / 没有 / 并非」不算命中；症状码决定可用计划集合。
- **图片路径**：像素层画质门控 → 视觉模型 describe-first 输出（observations → findings[part, phenomenon, cell] → model_hint）→ 铭牌裁剪复看 → `(部件, 现象)` 签名映射到计划（`vision_vocab.yaml.signatures`），照片签名写成症状事实进候选集。
- **知识路径**：两个 WeKnora 库并发 hybrid 检索 + 本地 FAQ 索引 + 故障卡，候选池与最终证据分离，充分性评估驱动至多一次补查（§5.1–5.3）。
- **综合**：`diagnose.synthesize` 在**允许的计划枚举内**输出至多 3 个假设，每个假设必须引用真实存在的 evidence_id，否则丢弃并留痕。

### 4.4 症状问诊（判别树）

品类内的故障族候选集从全集开始，每答一题按 yes/no 切分缩小；没有可用判别题时直接让用户多选；连续 2 次无进展或总计 8 次回答仍未收敛 → 如实结束（R7）。首问在故障族 ≤ 6 时直接多选（2026-09-19 新增）。算法见 §5.4。

### 4.5 分步排障与观察闭环

- 预写计划库 `config/plans.yaml`：每条计划声明 `applies_to`（品类 / SKU）、`symptom_codes`、步骤、`next_on[feedback]` 转移、`requires_observations` / `excluded_by_observations` 观察门。指令原文 `instruction_src` 必须指向 evidence 段登记的证据（doc_id#chunk_id）。
- 每步出卡后用户三态反馈（solved / not_solved / cannot_do）+ 观察选项；「无法操作」只记阻碍不消耗计划；连续跳过 3 次或执行达上限进入人工出口。
- `decide_next` 按固定优先级选下一动作：风险 → 用户意愿 → 已恢复 → 暂停/投诉 → 资源阻碍 → 缺失观察 → 可发布步骤 → 人工出口（§5.5）。

### 4.6 升级、凭证与保修判定

- 升级原因 R1–R8 枚举（步数上限 / 计划耗尽 / 用户要求 / 安全风险 / 无可用计划 / 退换诉求 / 信息不足 / 范围外），摘要卡不调模型即可从图状态渲染，`card_id = uuid5(session, reason)` 保证重跑幂等。
- 常规升级先收凭证：上传 → `warranty.receipt_ocr` 逐字段置信度（<0.7 标黄）→ 用户确认 / 修改 → 订单与经销商名录核对（L1–L6）→ 摘要。
- `PolicyEngine`（§5.8）按公开售后政策（US 站三个品牌页，逐条带原文 quote）判保修期与处置阶梯；非 US 区域没有采集到来源，一律 `no_policy_matched` 转人工，不把美国月数按到别的区域。

### 4.7 L3 业务闭环（案件 / 动作 / 人工审批）

会话事实（区域、渠道、订单号、地址）持久化并带来源；物流 / 订单 / 换货 / 退款等业务查询走动作层（`config/actions.yaml`，后端 mock 可换真实）；换货等处置需人工审批，坐席工作台 `/desk` 提供队列、SLA 着色、判定表与决定表单；案件生命周期与未解决案件重开有专门状态机。

### 4.8 可观测与工程化

- 管理端：工作台 / 看板（解决率、降级率、检索无命中率、五难点指标）/ 会话旅程（复用聊天端只读渲染、五难点证据 tab）/ 诊断实验室（流程图、模型表、复盘库）。
- 回放包 A1–A8（录制真实模型与知识库结果，离线零网络重放并校验 prompt / 模型 / kb / 规则版本）、巡检脚本 `make inspect`、模型 bake-off 报告、检索评测报告、进程内告警（模型链失败 / 检索为空率 / 队列拒绝 / 健康检查，5 分钟冷却）、分类 TTL 数据保留（图片 1 h、会话状态 24 h、trace 7 d）与地址脱敏。
- 发布：`make release` 冻结 prompt / models / rules / policy / taxonomy / kb 版本与 config 快照，`make rollback REL=` 5 分钟内回退。

---

## 5. 算法与原理

### 5.1 检索：多变体 RRF 融合与跨库交错

**问题**：两个知识库（手册 kb_manual、工单 kb_tickets）加本地 FAQ、重排模型的分值量纲互不可比（WeKnora 内部 RRF ≈ 0.016、FAQ Dice 相似度 0.3–1、rerank relevance 0–1），不能按原始分混排。

**方案**：一律用名次而不是分值。

同库多查询变体融合（`knowledge/search.py::rrf_merge`）。设变体集合 Q，文档 d 在变体 q 结果里的名次为 rank_q(d)：

```
score(d) = Σ_{q ∈ Q, d ∈ R_q} 1 / (k + rank_q(d)),   k = 60（retrieval.yaml multi_query.rrf_k）
```

同一 evidence_id 取并集并记录 `source_queries`；排序键 `(counter_evidence, -score)`，即反证工单永远排在正证之后。状态合并：任一变体 ok → ok；全部或部分 unavailable → unavailable（部分故障不算「正常无命中」）；否则 no_match。

跨库交错（`interleave_kbs`）：每库内部按名次给 `1/(k+rank)`，同名次按 `kb_manual(0) > kb_faq(1) > kb_tickets(2)` 破平，仍把 counter_evidence 放最后。同一函数同时用于图内进 synthesize 的顺序与评测 top-k，保证「评测跑的就是线上链路」。

**查询变体的产生（S0，不调模型）**：`diagnose/expand.py` 只用 `retrieval.yaml` 里已审核的同义词表把口语替换为规范词（「不吸」→「吸力下降」），单点替换各一条 + 全替换一条，去重后 ≤ `max_variants`；断言变体不引入原 query 没有的型号 / 数字。请求数上限 `变体数 × 库数 ≤ max_requests_per_round(6)`。

**作用域过滤先于检索**（`knowledge/adapter.py::allowed_entries`）：

| product_state | 允许的知识条目 |
| --- | --- |
| confirmed_sku | `sku_list ∋ sku` ∪ (`scope=category_generic` ∧ 同品类) |
| category_only | 仅 `scope=category_generic` ∧ 同品类 |
| unknown | 空集，不发请求（空 knowledge_ids 在 WeKnora 等于不过滤，禁止退化为整库搜索） |

标签修正：`scope=sku` 但 `sku_list` 覆盖该品类全部在范围 SKU 的条目按品类通用处理。

当前默认：multi_query / rerank / faq / query_rewrite / grade 全部 `enabled: false`，行为退化为「原 query 两库各一次」；每一项都要凭评测报告单独开启（`docs/planning/2026-09-13_bounded-agentic-rag`）。

### 5.2 本地 FAQ 匹配：字符二元组 Dice + 子串加分

**问题**：WeKnora v0.8.0 对 FAQ 库的检索接口实测返回空；FAQ 条目少且全部品类通用。

**方案**（`knowledge/faq.py::similarity`）：先去标点、去产品词与口语虚词（「扫地机器人」「怎么办」「了」等只会稀释症状相似度），再算：

```
若 s ⊂ q 或 q ⊂ s：  sim = 0.85 + 0.15 · min(|q|,|s|) / max(|q|,|s|)
否则：                sim = Dice(B(q), B(s)) = 2·|B(q) ∩ B(s)| / (|B(q)| + |B(s)|)
其中 B(t) 为 t 的字符二元组集合
```

阈值 0.3 以下不返回，避免「无知识」样例泄漏；命中形状与 WeKnora Hit 一致（source=kb_faq），只在会话品类内匹配。

### 5.3 证据充分性评估与有界补查

**问题**：单轮检索可能命中不足或不相关；无界的 Agentic RAG 会不停改写重查，延迟与幻觉都不可控。

**方案**：两层预算 + 一次受控补查。

候选到证据的选择（`knowledge/context.py`）：
- `select_hits`：按 (轮次, 来源) 分组后 `zip_longest` 交错，来源优先级 `kb_manual < kb_faq < fault_card < kb_tickets`；反证至少保留 1 个代表；**不按一次 grade 的 irrelevant 判定删除证据**。
- `pack_hits`：字符预算 `context_chars=5000`，先为后续所有条目的标题预留空间，再对第 i 条平均分配

```
allowance_i = min(item_chars, (max_chars − 已用 − Σ_{j≥i} header_j) / (n − i))
```

正文按锚点 `context_window` 居中截取，超长记入 `shortened_ids`，被挤掉的记 `excluded[reason ∈ {item_limit, char_limit, empty_content}]`。

充分性评估（`diagnose/grade.py`，轻量模型，默认关闭）：对 ≤12 条代表证据逐条判 `relevant / irrelevant / unsure`，整体 `coverage ∈ {sufficient, insufficient, none}`，并从「有效症状」里**逐字选择**未覆盖项 `missing_symptoms`（不得新增原因或部件）。两条保守规则：coverage=sufficient 但没有任何 relevant → 降为 insufficient；只有反证工单被判 relevant 也不算 sufficient。评分只**标记**质量，不删候选。

受控改写（`diagnose/rewrite.py`，默认关闭）：Schema 仅 `{query}`；校验拒绝空 / 超长 / 与原 query 相同 / 改变否定数量 / 新增型号、错误码、数值、未出现的部件或原因词（已审核同义映射放行）。校验失败不再调裁判模型。第二轮受 `second_round_budget_ms=3000` 与「剩余 < 3 s 跳过」约束。

### 5.4 症状问诊：最小分裂判别树

**问题**：用户口语常映射不到唯一故障族（「充不进电」既可能是输出也可能是自身回充），模型自由追问会复读、跑题、无限循环。

**方案**（`conversation/taxonomy.py`）：确定性判别树，问题来自配置而非模型。

候选集 C 初始为该品类全部故障族。可用判别题 D 须满足 `C ⊆ yes(D) ∪ no(D)` 且两侧都非空。选题准则为最大化最坏情况的缩小量：

```
D* = argmax_D  min( |C ∩ yes(D)|, |C ∩ no(D)| )
```

即选把候选切得最均匀的题（等价于最大化一次二分的最小信息量下界）。回答后 `C ← C ∩ splits[answer]`。

无可用判别题且 |C| > 1 → 直接让用户在剩余现象里多选（`symptom_selection`）；|C| ≤ 6 且用户尚未回答任何问题时首问就多选（一道 4/1 切分的是非题期望信息量接近零且必然再追一问）。

终止预算（`diagnose/decision.py`）：

| 条件 | 结果 |
| --- | --- |
| 连续无进展回答 ≥ 2（MAX_NO_PROGRESS） | 全部为「不知道」→ `answers_unavailable`，否则 `no_progress` → R7 |
| 总回答数 ≥ 8（MAX_INTERVIEW_RESPONSES） | `clarification_budget_exhausted` → R7 |
| 有回答但候选为空 | `evidence_conflict` → 升级 |
| 已回答 yes/no 且剩余候选共享同一组适用计划 | 不再问，直接 `continue`（`common_applicable_plans`） |

「进展」定义为候选集合变化；新增可归一的症状事实会重置连续无进展窗口（`progress_start`），但不重置总预算；归一不到任何故障族的补充记为 `unmapped` 并计入预算，否则「每次补充都清窗口」会让同一问题重复到永远。

规则与模型冲突留痕：`canonical_codes` 以词表规则为准，模型给的码不在词表或与规则不一致时记 `disagreement`，不静默采用。

### 5.5 下一动作决策：证据驱动的候选序列

**问题**：模型自由生成的「下一步」没有来源、可能重复已做步骤、可能在有风险时继续操作。

**方案**（`diagnose/decision.py::decide_next`）：纯函数，不调模型、不写库、不发事件；返回 `NextAction(kind ∈ {ask, step, resolved, handoff_offer, safety_stop, pause}, reason, basis)`。

固定优先级（design §3.3）：

```
1 风险证据 (allowed_operations=false / R4)      → safety_stop
2 用户要求人工 (R3 / request_human)             → handoff_offer
3 上一步反馈 solved                              → resolved
4 用户暂停 / 纯投诉 / 资源缺失待答 / 请求解释    → pause 或 ask
5 候选计划序列：
    ranked   = plans_ranked 中 confidence ≥ 0.3 且未耗尽者（保持模型排序）
    unlocked = 观察门已满足的 requires_observations 计划（症状码不再否决）
    对每个候选按序：
      observation_gate == excluded → 跳过
      observation_gate == missing  → 记第一个可问的观察（同一观察最多问 2 次，requires_execution 的须先执行过步骤）
      有未执行步骤              → 记第一个可发布步骤
      解锁计划与已记录症状码不相交 → 先问一次范围（scope_conflict），答过则 outside_confirmed_scope 跳过
    取序号最小的可行动作：排在前面的步骤不被后面计划的问题抢先，反之亦然
6 有阻碍 / 资源缺失 / 连续跳过 ≥ 3 / 情绪策略要求少步骤 → 资源复核问题或 pause
7 无支持的下一动作 → handoff_offer(reason ∈ {observation_unavailable, no_supported_followup, knowledge_coverage_missing})
```

观察门（`plans/models.py::observation_gate`）：`excluded_by_observations` 命中 → excluded；`requires_observations` 中有未知 → missing；已知但不在允许选项 → excluded。**未观察到不能当作阴性**：只会让计划「缺失」，不会让它「排除」或「满足」。

R1–R8 是对外兼容 / 观测层的规则码映射，真实结束原因在 `next_action.reason`（`escalation/summary.py::NEXT_ACTION_TEXT`）。

### 5.6 读图：一次可信的测量

**问题**：视觉模型无法自知其无知。公开实验里亮度降到 0.15 倍时 VLM 准确率从 0.99 掉到 0.22，而自报置信度仍稳定在 0.87–0.90，错误检测 AUROC ≈ 0.50——最该拦下的图恰好是模型看不出自己看不见的那些。

**方案一：像素层画质门控**（`images/quality.py`，只用 Pillow，不调模型）

| 指标 | 定义 | reject | marginal | 为什么这么定义 |
| --- | --- | --- | --- | --- |
| focus | 长边归一到 1024 → autocontrast → 水平梯度 \|I(x+1)−I(x)\| 的 99.5 分位 | 无 | < 12 | 取高分位而非均值：大片纯色的清晰图均值也低；归一后阈值与分辨率、亮度无关。合成图阈值不迁移，故只做软阈值 |
| luma_p95 | 灰度直方图 95 分位 | < 60 | < 110 | 刻意不用中位数：Anker 设备多为深色机身，正常曝光中位数只有 64 但 p95 有 204；真欠曝两个数一起塌。问的是「画面里还有没有正常曝光的地方」 |
| clipped | 亮度 ≥ 250 的像素占比 | > 0.5 | > 0.3 | 过曝 |
| short_edge | 原图短边像素 | < 300 | < 480 | 拍太远 / 截图裁剪 |

三档：reject 直接发补拍卡（一次模型都不调）；marginal 交模型再看，两边都说不行才判不可用；多图取最好的一张。

**方案二：describe-first 结构化输出**（`diagnose/vision.py::VisionObservation`）：字段顺序即生成顺序，先写 ≤5 条只描述可见事实的 observations，再据此填受控枚举 findings[part, phenomenon, severity, cell]。跳过感知阶段直接填终态枚举会显著增加编造（VDGD 等工作报告两段式在视觉推理上有 2%–33% 提升）。词表区分「其他」（看清了但不在表内）与「不可辨」（根本看不出），两者合并会把「未知」当成「已知的异常」。

**方案三：铭牌裁剪复看与交叉核对**（`_reread_nameplate`）：只要模型给出型号 `model_hint`，就按它指认的九宫格 cell 裁出放大再读一次。触发条件是「有型号」而不是「读不清」——实测某模型在 14px 铭牌上给出格式完全合理的假型号 `T2351`，校验开关不能握在被校验者手里。

```
两次一致（忽略空白、大小写，? 占位不参与）→ verified=True，可自动锁 SKU
两次不一致                              → 取像素更多的裁剪结果，verified=False，让用户确认
裁剪图读不出（单图）                    → 全图那次的自信答案不可信，清空回到「不知道」
无法复看（无 cell / 多图 / 预算不足）   → 保留原值，verified=False
```

效果（reports/bakeoff-stage1）：三家模型铭牌读出率 67% → 100/100/67，deepseek 综合 65% → 93%，编造路径被堵死。

**方案四：图文冲突由代码比对**：视觉调用看不到用户文字（避免被文字误导），`text_aliases` 把用户说法映射回词表后在两个独立结论之间比对，冲突先澄清再检索。

### 5.7 安全规则与否定语义

**问题**：视觉模型会把「没看到危险」也写成观察项：「未见冒烟烧焦鼓包漏液火花」。子串匹配读不出否定，正常的滚刷缠绕照片因此被判 R4 安全风险、排障中断（三次复现一次）。

**方案**（`rules/service.py::_mask_negated`）：只承认**一种**否定形态——否定词后紧跟一串安全词，词与词之间只允许连接词（「明显」「任何」「、」「或」…）。跨过标点或任何实义字符就当成新陈述继续按命中处理：「无线充电座冒烟」的「无」不是否定，「未见冒烟，滚刷烧焦」只遮住前半句。安全判定宁可误报不可漏报，所以判否定的条件比判命中严得多。规则词表 `config/rules/safety_terms.yaml` 按 mtime 热加载；R3 / R4 / R6 检查点作用于用户文本、图片观察、动作与备注四个来源。

### 5.8 保修政策引擎

**问题**：保修判定要可解释、可追溯到条款原文，并且不在没有依据的区域外推。

**方案**（`policy/engine.py`，纯函数，无 IO）：

```
输入 PolicyInput{category, sku, series, region_purchase, region_use, channel, purchase_date, today, fault_class, prior_remedies, dealer_authorized}
1 别名归一（美国→US、Amazon→platform_store …）
2 缺任一必填 → needs_human(missing_inputs)
3 三级匹配：applies_to 同时满足 品类 ∧ 购买区域 ∧ 渠道 ∧ 系列子串 ∧ 部件类 的规则
   取 priority 最大者：品类兜底 10 < 系列 20 < 部件 / 系列例外 30
   无匹配 → needs_human(no_policy_matched)
4 warranty_end = purchase_date + months（按月加、日期夹到月末）；lifetime 无到期日；none 恒不在保
   within_warranty = purchase_date ≤ today ≤ warranty_end
5 exclusions / cross_region：每条 when 的全部条件满足即命中，效果 no_free_remedy 或 needs_human，附条款引用
6 remedies 阶梯：eligible = 条件全满足 ∧ ¬(no_free_remedy ∧ cost_bearer=company)
   auto_allowed = eligible ∧ 规则允许自动 ∧ ¬needs_human
7 trace_id = sha256(规则 + 条款 + 输入)[:24]，同输入同结果
```

条款库 `config/policy/clauses.yaml` 每条带 source_url、采集日期与原文 quote；系列（GaNPrime / Prime / MagGo → 24 个月）按产品名子串认，因为系列在目录里没有独立字段。

### 5.9 上下文预算

**问题**：多轮会话把历史、事实、证据全塞进提示词会超窗或挤掉当前输入；不同任务的输入预算不同。

**方案**（`context/builder.py`、`context/budget.py`）：

```
tokens(text) = ceil( |tiktoken o200k_base 编码| × 1.25 )      （跨厂商估算，显式留余量）
message_tokens = tokens + 8                                     （消息封装开销）
预算 B(task) = conversation.yaml input_budgets[task]（intake 16000）或 max_input_tokens 8000
             − 256 − tokens(输出 schema JSON) − tokens(附加指令)  （context_input_budget）
used = system + authority(状态投影) + current(当前消息) + history(召回历史)
```

超预算时按序让步：先丢历史摘录缓存 → 再对当前长文本头尾各留、中间省略（不低于 200 字符）→ 仍超则抛 `ContextBudgetExceeded`，区分「必要内容本身超预算」与「请求的历史超预算」并记录分块统计。路由前再做一次 `budget_error`：文本 + 每图预留 16k + 输出 tokens 不得超过模型 context_window。给模型的状态投影只含模型该看的字段（`_model_authority`），身份、证据、业务状态留在存储。

### 5.10 模型路由、降级与容量

**方案**（`models/router.py`，`config/models.yaml`）：每个任务一条模型链（如 `diagnose.synthesize: [deepseek, qwen-max, glm-v]`），按模型 `structured` 能力选结构化方法（native json_schema / json_object + schema 提示 / 工具调用），统一 Pydantic 校验。

| 失败类型 | 处理 |
| --- | --- |
| 超时 / 5xx / schema 校验失败 | 同模型重试 1 次（schema 失败带错误提示），再失败换下一家 |
| 429 | 同模型最多 3 次，退避 1 / 2 / 4 s + [0, 0.5) s 抖动 |
| 拒答 / 内容过滤 | 不重试，直接换下一家 |
| 能力不匹配（需视觉而无视觉）/ 别名未配置 | 路由前跳过，记 skipped |
| 预算 | 单次超时 = min(模型 timeout, 剩余预算)；剩余不足以再调一次即停止 |

全局有界门 `max_in_flight=50`：满则立即抛 `CapacityExceeded`，映射为契约 `error(recoverable=true, retry_with_same_action=true)`，不排队堆积。用户可见流（reply.stream）主模型中途失败 → 降级模型用简化模式变体从头生成并以新 message_id + replaces 替换。

### 5.11 模型选型 bake-off 裁决

**方案**（`bakeoff/runner.py::judge`）：先过硬门（如铭牌不编造率），再过 schema 通过率 / 准确率 / P50 延迟门槛；达标者按

```
key = latency_p50 / latency_cap + cost_cny_per_call × 100
```

最小者为主模型；备用模型必须来自另一家厂商，且 `schema_pass ≥ 备用门槛 ∧ accuracy ≥ 主 − Δ ∧ latency ≤ 主 × ratio`。准确率只作门槛不参与排序，因为聚合准确率会抹平「失效方式」的差别。评分函数 `bakeoff/scoring.py` 按任务对 expect 规则逐项打 0–1 分（如 synthesize 要求 top1 命中且每个假设都有 evidence_ids；stream 禁止出现「可保 / 免费维修」等资格结论词）。

### 5.12 评测口径

- 检索（`knowledge/eval.py`）：`hit@k`（expected_doc_ids 任一出现在 top-k）、`precision@k`、`leak`（无知识样例却返回命中）、`scope_leak`（命中当前作用域不该看见的文档）；按 tag 分组。
- 语义（`evaluation/semantic.py`）：独立文本金标经与线上相同的 `interpret_turn`，逐字段准确率（primary_intent / intents / order / emotion_level），金标绝不进入解释器状态或提示词。
- 会话结局（`analytics/derive.py`）：只看 checkpoint 权威状态 + done.reason，不看事件文本；升级原因分为系统失败 {R1, R1b, R1c, R2, R5, R7} 与用户 / 政策决定 {R3, R4, R8}，解决率只把前者算失败。

---

## 6. 当前状态与边界

**已闭环**：文字 + 图片 → 消歧 → 问诊 → 检索 / 综合 → 分步排障 → 观察 → 升级 / 凭证 / 保修 → 摘要，全链路 SSE 可续接、动作幂等、可回放、可观测；三家国产厂商 + 两家海外厂商模型链冻结并有 bake-off 依据；发布 / 回滚 / 备份 / 巡检 / 告警齐备。

**演示数据**：手册与 FAQ 以人工演示样本为主（25 篇官方文章除外）；380 条工单为合成数据；业务后端（订单 / 物流 / 经销商名录）为 mock；保修政策只覆盖 US 站公开页。

**默认关闭、待评测开启**（`config/retrieval.yaml` 各有独立开关；依据 `docs/planning/2026-09-13_bounded-agentic-rag/{findings,switches}.md` 与 09-18 链路 B 附记）

共同前提：评测集 56 条人工标注 0/56，规划定了硬约束「未标注样例的数字只能做回归对比，不能作开启依据」；手册库仅 13 个子块，top-5 覆盖大半份手册，hit@5 各组均 96%，检索层指标饱和，收益只能在模型侧（synthesize 的 plan 命中率）上量；换 config 后必须发真实会话验活（曾出现配置与镜像不成对的静默故障）。

| 开关 | 技术 | 成本 | 评测证据（56 条，未标注） | 当前结论 |
| --- | --- | --- | --- | --- |
| 多查询变体 `multi_query` | 不调模型。已审核同义词表把口语替换为说明书用语生成 ≤ 2 个变体，变体 × 两库并发，同库 RRF 合并 | 0 次模型调用，p50 +50 ms | 与 FAQ、父块扩展一起开：plan 命中 40/43 → 41/43，outcome 49/51 → 50/51 | 有小幅正收益，建议标注后与 FAQ 一起开 |
| 本地 FAQ 索引 `faq` | WeKnora v0.8.0 的 FAQ 检索接口实测返回空，改为适配器侧字符二元组 Dice + 子串加分，阈值 0.3 | 0 次模型调用，≈ 0 ms | precision@5 61% → 47%，但逐条核对 45 条 FAQ 命中多数正确，只是金标未登记 FAQ；挤掉的是工单不是手册 | 指标失真源于金标缺 FAQ，建议补标注后开 |
| 重排 `rerank` | WeKnora hybrid-search 只做 RRF 不重排，适配器自己调百炼 gte-rerank-v2 对每库 top 命中重排 | 1 次 HTTP，p50 281 → 750 ms | 106 次调用全部成功，文档级 hit 无增益；一例把指示灯表格块顶到正文段前 | 只加延迟不加收益，不建议开 |
| 充分性评估 `grade` | 轻量模型逐条判 relevant / irrelevant / unsure 并给整体 coverage 与缺口症状；只标记不删候选，不足时驱动一次补查 | 1 次模型调用，p50 +1.6 s | plan 命中 41/43 → 39/43，两条回归都是金标段落被判 irrelevant；单独探针判得对，但本期语料首轮噪声本来就少，收益抵不过误剔 | 当前语料净负收益，不建议开；语料扩大后重评 |
| 查询改写 `query_rewrite` | 证据不足时调模型改写一次 query，Schema 仅 `{query}`，代码侧拒绝新增型号 / 错误码 / 数字 / 部件 / 原因词或改变否定 | 触发时 1 次模型调用 | 本语料 0/56 触发：条件是两库都 no_match，而混合检索对任何 query 都返回 ≈ 0.016 的命中；bake-off 校验修正后 qwen-flash 0% → 100% | 当前语料下触发不了；链路 B 已改为「先评估充分性、不足再补查」，同样等真实金标 |

开启顺序（switches.md）：补标注 → 重跑 A / C_nograde 两组确认 plan / outcome 不降 → 一次性开 multi_query + faq + parent_expand 并验活 → rerank / grade / query_rewrite 维持关闭待重评。回滚只需改回 `enabled: false` 重启，无数据迁移、无契约变更。

**部分实现**：处置动作只有 `replace` 可经授权门自动执行（配件 / 付费维修待放开）；转人工状态停在 `prepared`，未接真实转接服务；坐席队列尚未在服务端 join 会话事实。

**已知缺口**（见各 planning addendum）：headphones 等品类无通用卡，不知型号只能 R5；看图可用率无聚合查询；观测台尚未显示 `next_action.reason`；情绪轨迹契约待扩。
