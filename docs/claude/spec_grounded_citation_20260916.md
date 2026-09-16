# 可审计引用（Grounded Citation）：外部方案评估与本项目落地建议

日期：2026-09-16　状态：评估稿，未实施　范围：diagnose 检索链路 → 用户可见回复 → 前端来源展示 → 离线评测

来源：Sumanth（@Sumanth_077）2026-09-15 长文 *How to Build a Grounded Document Agent*，
配套开源项目 [grounded_document_agent](https://github.com/Sumanth077/Hands-On-AI-Engineering/tree/main/ai_agents/grounded_document_agent)。
注意该文是 LlamaIndex 的合作稿（文末含 LlamaParse 促销），**技术论证可用，选型结论需打折扣**。

---

## 0. 结论先行

| 问题 | 结论 |
| --- | --- |
| 这套「有据可查」的思路对我们有用吗 | **有用，但要重映射**。原文是「PDF 文档问答」，我们是「排障对话 + 预写计划下发」。四层里只有引用层与验证层可直接借鉴 |
| 我们已经做到哪一层 | **卡片级引用**已完备：`step_card.evidence_ids`、`synthesize` 强制每个假设至少引一条 evidence_id、前端 `EvidenceDrawer` 联动高亮。比原文项目更严的是我们还有**证据不足即拒答**（四态 + R5 升级） |
| 最大的缺口是什么 | **自由文本回复（`reply.stream`）零引用**。检索片段进了提示词，但既不要求模型标注引用，也不做回执校验。R7 样本第 4 轮「模型自行给出三步排查」就是这条路径 |
| 第二大缺口 | **引用粒度退化到文档级**。`plans.yaml` 里 `instruction_src: evidence:manual_rv_v1#c12` 已经写死了精确锚点，但 `guide/steps.py:_evidence_for` 只取 `#` 前的 doc_id，锚点被丢弃 |
| 要不要换技术栈（LlamaParse / LlamaIndex / Ollama） | **不要**。见 §6 |
| 建议动作 | G1（回复引用锚点）+ G2（主引用）为 P0，G3（失败归因字段）为 P1，G4（证据可达性基线）为 P1 |

---

## 1. 原文四层 → 本项目的概念映射

原文的架构是：**云端解析 → 本地嵌入检索 → CitationQueryEngine 编号引用 → 验证 UI**。逐层对照：

| 原文层 | 原文做法 | 本项目对应物 | 是否可借鉴 |
| --- | --- | --- | --- |
| 解析层 | LlamaParse 把 PDF 转布局感知 Markdown，保留页码；文件哈希缓存 | **我们没有 PDF**。知识源本来就是人工维护的带 front-matter Markdown（`data/knowledge/kb_manual/*.md`），由 WeKnora 父子分块 800/200 入库 | 原则可借鉴（见 §2.1），做法不可照搬 |
| 检索层 | 嵌入 + VectorStoreIndex + top-4 | WeKnora 混合检索（BM25 + 向量）+ 百炼 rerank + RRF 多变体融合 + CRAG-lite 相关性评分 | **我们更强**，无需借鉴 |
| 引用层 | CitationQueryEngine 切 512 字符块，强制 `[1][2]` 内联 | 卡片级已有；**自由文本零引用** | **这是主要缺口，见 G1** |
| 验证层 | UI 展示页码、原文、查询词高亮、相关性分数 | `EvidenceDrawer` 展示来源类型 / doc_id / 版本 / 片段 | **缺定位、分数、评分结论，见 G3** |
| 部署切分 | 只有解析上云，其余本地 | 与我们无关：WeKnora 自托管，embedding / rerank / 生成走远程（D17） | 不适用 |

### 1.1 原文最有价值的三条论断，及其在我们这里的形态

1. **「答案质量的上限由解析决定」**（原文：*The quality of the answer is bounded by the quality of the parse*）
   我们不会遇到双栏串读、OCR 失败，但**同构的天花板依然存在**，只是上移到了分块与元数据：
   - 父子分块 800/200（`ingest.py:chunking_config`）按 `\n\n` / `\n` / `。` 切分，**手册第 3 章的指示灯表格、步骤列表有被拦腰切断的风险**；
   - `custom_metadata` 实测有 1/200 的写入丢失（`ingest.py:299-309` 的注释与重试就是为此），元数据丢了 → `KnowledgeScope` 过滤失效 → 范围控制形同虚设。

   这两件事都发生在模型看到内容之前，调 prompt、换模型都救不回来。

2. **「引用粒度是权衡，没有标准答案」**
   原文选 512 字符。我们已经是 small-to-big（child 200 / parent 800，`synthesize._evidence_text` 有正文用父块 ≤800 字、否则子块 ≤300 字），**不应该再引入第三套切分**。我们的粒度问题不在字数，在**挂载关系太松**（见 G2）。

3. **「引用 ≠ 正确」**
   原文的例子是表格数值配错列头。我们有一个更贴切的版本：**步骤文本来自 `plans.yaml` 的已审核原文，不是模型从证据生成的**（`guide/steps.py` 文档注释：「原样发布已审核操作」）。
   所以我们的失效模式不是「模型编造了引用」，而是**「引用挂错了」**——步骤是对的，但挂上去的那几条证据其实不支持它。这类错误比幻觉更隐蔽，因为文本永远读得通。

---

## 2. 现状盘点

### 2.1 已经做到的（不要重复造）

| 能力 | 实现位置 | 说明 |
| --- | --- | --- |
| 证据契约 | `contracts/haike_contracts/common.py:111` `EvidenceItem` | `evidence_id / source / doc_id / doc_version / chunk_id / snippet / score / status` |
| 假设必须有据 | `orchestrator/app/diagnose/synthesize.py:74` `filter_hypotheses` | 越界 evidence_id 剔除；**零证据的假设整条丢弃**（`no_evidence:{pid}`） |
| 步骤引用 | `orchestrator/app/guide/steps.py:42` `_evidence_for` | 步骤引用越界 id → 丢弃该步取下一步 |
| 证据不足即拒答 | `knowledge/adapter.py` 四态 + `HINTS` | `no_match` / `unavailable` 时**不调模型**，走预写计划或 R5 升级，禁止常识补假设。**这正是原文列在「后续可做」里的 abstention，我们已经有了** |
| 相关性评分 | `diagnose/grade.py` | CRAG-lite：逐条 relevant/irrelevant/unsure + coverage，被滤的仍作为「检索到的来源」发 evidence 事件（`graph.py:1600`） |
| 前端来源抽屉 | `frontend/src/components/EvidenceDrawer.tsx` | 折叠列出片段，当前步骤引用的条目高亮联动 |
| 检索可观测 | `knowledge/search.py:_kb_trace`、`retrieval_trace` | 每库每变体的 query / status / hit_ids / scores / latency |
| 离线评测 | `knowledge/eval.py:101` `score_case` | precision@k、first_rank，以及 `chunk_markers()` 的分块级金标 |

### 2.2 缺口

| 编号 | 缺口 | 证据 |
| --- | --- | --- |
| G1 | **自由文本回复无引用** | `prompts/reply.py:16` `REPLY_INSTRUCTION` 只说「只能引用检索片段里出现的操作」，没要求标注；`reply_messages` 把 `[evidence_id[:8]] snippet` 喂进去了但回执不校验；`contracts/events.py:106` `Message` / `:112` `MessageEnd` 无引用字段 |
| G2 | **引用粒度退化到文档级** | `guide/steps.py:52` `doc_id = step.evidence_key.split("#", 1)[0]`，随后 `[eid for eid, e in allowed_evidence.items() if e.get("doc_id") == doc_id]` —— 同一份手册的**所有**允许片段都会挂上去 |
| G3 | **失败无法归因到段** | `EvidenceItem` 无 locator、无 grade；SSE 不带 `score` 以外的判定依据；前端不展示分数。答错时无法区分是分块、检索还是生成的问题 |
| G4 | **证据可达性无基线** | `plans.yaml` 的 `instruction_src` 锚点（如 `manual_rv_v1#c12`）从未被验证「入库后还检索得到」。`ingest.py:403` `verify_metadata` 只查元数据，不查锚点可达 |

---

## 3. G1：自由文本回复的引用锚点（P0）

### 问题
两条回复路径的治理强度差了一个量级：
- **卡片路径**（step_card / plans_ranked）：证据强制、越界丢弃、前端可查。
- **自由文本路径**（`reply.stream`）：检索片段进了提示词，输出不做任何结构校验。

R7 分析里第 4 轮「模型自行给出基站供电 / 触点清洁 / 重新归位三步排查」（`docs/claude/spec_r7_symptom_interview_20260915.md` §一）走的就是后者。那次结论是「模型本可以继续排障」——但从可审计角度看，**那三步没有任何来源**。

### 方案
1. `REPLY_INSTRUCTION` 增加一句：「给出原因或动作时，在句末标注你实际使用的片段编号，格式 `[e1]`；没有片段支撑的句子不要标。」
   引用编号用**局部序号 e1/e2**，不用 evidence_id 前 8 位——序号对模型更稳定，也不会把内部 id 泄露到用户可见文本（与 `reply.py` 现有约束「不向用户展示 issue_id、entry_id、内部字段名」一致）。
2. 代码侧解析回执：抽出 `[eN]` → 映射回 evidence_id → 越界的**从文本里剥掉**（不是丢整条回复），记 `trace: citation_dropped`。
3. `MessageEnd` 增加 `citations: list[str]`（evidence_id 数组，默认空）。前端复用 `EvidenceDrawer` 的 highlight 通道，与 `StepCard` 完全同构。
4. **落地纪律**：`knowledge_status == "ok"` 且回复含操作性内容、但 `citations` 为空 → 记 `ungrounded_reply` 指标。**先只观测，不拦截**，积累一周基线再决定是否加门。

### 明确不做
- 不要求每句都带引用。安抚语（`REASSURANCE_INSTRUCTION`）、澄清提问、历史回顾本来就不该有引用，强加会让语气机械化。
- 不因为缺引用就拒答——拒答的判据仍然是检索四态，不是文本形态。

---

## 4. G2：主引用（primary evidence）（P0，改动极小）

### 问题
`plans.yaml` 的作者已经写明了每一步的精确出处：

```yaml
- {step_id: s1, title: 检查并清理滚刷, instruction_src: evidence:manual_rv_v1#c12, ...}
```

而 `manual_rv_v1.md` 的小节标题就是 `### 1.1 清理滚刷（c12）`——**锚点是人写进正文的，检索片段里原样带着**。
`knowledge/eval.py:68` `chunk_markers()` 已经实现了 `c12 → 「（c12）」` 的匹配，**但只用在离线评测，没用在运行时**。

运行时的 `_evidence_for` 把 `#c12` 丢了，退化成 doc_id 匹配，结果是：一步清理滚刷的操作，会把整份手册里命中的滤网、尘盒、边刷片段一起挂上去。前端显示「来源 5 条」，但真正支撑这一步的只有 1 条。

### 方案
1. `_evidence_for` 保留 doc 级结果作为兜底集合，另外算一个 `primary`：`allowed_evidence` 中 snippet / full_text 含 `（c12）` 标记的那条（复用 `chunk_markers`，把它从 `eval.py` 提到 `knowledge/` 下共用）。
2. `TroubleshootStep` 增加 `primary_evidence_id: str | None`。`EvidenceDrawer` 默认只展开主引用，其余折叠为「其他相关来源 N 条」。
3. **副作用是一个免费的自检**：若某一步的锚点在允许集合里一条都匹配不到，说明这段手册内容**没被检索到**——直接接上 G4 的可达性基线。

### 与原文的分歧（要写清楚）
原文把粒度问题解成「切更小的引用块」（512 字符）。我们不切——我们的锚点是**人工标注的语义单元**，比任何字符切分都准。这是自建语料相对通用 PDF 管线的结构性优势，应该用满。

---

## 5. G3 / G4：让失败可归因（P1）

### G3：证据事件补两个字段
| 字段 | 内容 | 用途 |
| --- | --- | --- |
| `locator` | `doc_id#anchor`（如 `manual_rv_v1#c12`），无锚点时回落 `doc_id#chunk_{index}` | 回答「这句话出自手册哪一节」，等价于原文的页码 |
| `grade` | `relevant / irrelevant / unsure`（`grade.py` 已算出，目前不出 SSE） | 被滤掉的证据仍然发事件（`graph.py:1600`），但前端看不出它是被滤的 |

前端 `EvidenceDrawer` 相应补：分数、locator、被滤标记。原文验证 UI 的四要素（页码 / 原文 / 高亮 / 分数）我们就齐了，只差查询词高亮——**高亮建议不做**，我们的 query 是 `build_query` 拼出来的产品词 + 症状词，高亮出来是噪音，不是信号。

### 归因三问（admin 控制台 `NodeDetail`）
一次答错，按这个顺序问：

1. **解析问题？** 该步骤的 `primary_evidence_id` 是否为空 / locator 是否指向预期锚点 → 内容没入库或被切碎。
2. **检索问题？** `retrieval_trace` 里正确 doc 是否进了 top-k、`grade` 是否把它判成 irrelevant → 召回或精排问题。
3. **生成问题？** 证据齐、评分对，但回复的 `citations` 指向别处或为空 → 模型问题。

这三问才是把黑盒 RAG 变成可调试管道的落点，前两步的字段 G2/G3 已经备齐。

### G4：证据可达性基线（`make kb-verify` 扩展）
在 `knowledge/eval.py` 旁加一个不依赖标注集的确定性检查：

- **A. 锚点可达**：对 `plans.yaml` 里每个 `instruction_src` 锚点，用该步 title 作 query 检索，断言对应片段进 top-k。**这是我们版本的「解析保真度」，对标原文提到的 ParseBench**。
- **B. 分块未截断**：断言手册第 3 章指示灯表格的表头与数据行落在同一个 parent chunk（`chunk_markers` 已有 `第3章表 → "| 现象 | 含义 |"` 的判据）。
- **C. 元数据完整**：`verify_metadata` 结果里 `doc_version` / `sku_list` 缺失数 == 0（已知 1/200 丢失，必须归零）。

A/B/C 全是确定性断言，可进 CI，**不需要人工标注集**——这一点比 §2.1 提到的「50 条标注样例」门槛低得多，应该先做。

---

## 6. 明确不采纳

| 原文做法 | 不采纳理由 |
| --- | --- |
| LlamaParse 解析 PDF | 我们的知识源是自维护 Markdown，不存在解析环节。真要接客户上传的 PDF 是另一个需求，不在本 spec 范围 |
| LlamaIndex + VectorStoreIndex 替换检索 | WeKnora v0.8.0 已锁版本，混合检索 + rerank + RRF + CRAG-lite 比原文的 top-4 相似度检索强，替换纯负收益 |
| Ollama 本地 qwen3:4b 生成 | 与 D17（远程百炼 + 国产链 DeepSeek / GLM）冲突；4b 模型撑不住我们的结构化输出约束 |
| 512 字符 citation chunk | 我们已是 child 200 / parent 800 的 small-to-big；引入第三套切分只会让 `_evidence_text` 的两档逻辑变三档 |
| 「证据太弱时拒答」 | **已经实现且更严格**：四态 + 允许集合为空直接 no_match + R5 升级 + 零证据假设丢弃 |
| 引用点击跳转原文 PDF 页 | 我们没有 PDF。G3 的 `locator` 已是等价能力（跳到 Markdown 小节） |

---

## 7. 落地顺序与验收

| 序 | 改动 | 主要文件 | 验收 | 风险 |
| --- | --- | --- | --- | --- |
| 1 | G4-A/B/C 可达性基线 | `orchestrator/app/knowledge/eval.py`、`ingest.py`、Makefile | 三项断言全绿进 CI | 低。纯只读检查，先跑出当前红黄绿再说 |
| 2 | G2 主引用 | `guide/steps.py`、`plans/models.py`、`contracts`、`EvidenceDrawer.tsx` | 每个 `plans.yaml` 步骤能解析出非空 primary；前端默认展开 1 条 | 低。兜底集合不变，只加排序与字段 |
| 3 | G1 回复引用 | `prompts/reply.py`、`conversation/reply.py`、`contracts/events.py`、前端 | 含操作的回复 `citations` 非空率进指标；越界 id 被剥离且记 trace | 中。**需灰度**：提示词变更会影响所有自由文本回复的语气，要跑 bake-off 对比 |
| 4 | G3 locator + grade 出 SSE | `knowledge/adapter.py:87`、`graph.py`、`contracts`、admin `NodeDetail` | 归因三问在控制台可走通一遍 | 低 |

契约改动都是**新增可选字段**，旧快照与回放 fixture 不受影响；契约改完需重跑 `contracts` 的 codegen 同步前端类型。

---

## 8. 开放问题（需确认）

1. **G1 的引用要不要对用户可见？** 两个选项：(a) 文本里保留 `[1]` 角标，点击展开抽屉——透明但增加阅读噪音；(b) 文本不带角标，引用只进 `MessageEnd.citations` 供抽屉高亮和内部审计。考虑到 C 端用户是求助状态、`REPLY_INSTRUCTION` 现在就限制「最多一个短列表」，**我倾向 (b)**，但如果这套要拿去做黑客松演示的「可信度」卖点，(a) 更有说服力。
2. **`ungrounded_reply` 最终要不要变成硬门？** 建议先观测。真要拦，拦的动作是「降级成不含操作建议的澄清回复」，而不是拒答——但这会改变对话手感，需要单独评估。
3. **G4-A 的锚点检查失败时按什么处理？** CI 红灯挡合并，还是只告警？取决于 `plans.yaml` 与手册的更新频率是否同步——如果手册改版常导致锚点漂移，红灯会变成噪音。

---

## 附：相关文档

- [智能体式 RAG 方案评估](spec_agentic_rag_evaluation.md) —— 本 spec 的检索层现状基线来自此文 §1
- [R7 误升级根因](spec_r7_symptom_interview_20260915.md) —— G1 的问题样本
- [向量库选型](spec_vector_store_decision.md)、[上下文工程经验](spec_context_engineering_lessons.md)
