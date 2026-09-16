# 可审计引用（Grounded Citation）：外部方案评估与本项目落地建议

日期：2026-09-16　状态：评估稿 **v2（同日复评）**，未实施　范围：diagnose 检索链路 → 用户可见回复 → 前端来源展示 → 离线评测

来源：Sumanth（@Sumanth_077）2026-09-15 X 长文 *How to Build a Grounded Document Agent*
（<https://x.com/Sumanth_077/status/2099865807136428489>，正文已于 9/16 复评时逐段核对），
配套开源项目 [grounded_document_agent](https://github.com/Sumanth077/Hands-On-AI-Engineering/tree/main/ai_agents/grounded_document_agent)。
该文是 LlamaIndex 的合作稿（文末含 LlamaParse 促销），**技术论证可用，选型结论需打折扣**。

---

## 0. 结论先行

| 问题 | 结论 |
| --- | --- |
| 这套「有据可查」的思路对我们有用吗 | **有用，但要重映射**。原文是「PDF 文档问答」，我们是「排障对话 + 预写计划下发」。四层里只有引用层与验证层可直接借鉴 |
| 我们已经做到哪一层 | **卡片级引用**已完备：`step_card.evidence_ids`、`synthesize` 强制每个假设至少引一条 evidence_id、前端 `EvidenceDrawer` 联动高亮；9/15 起每个步骤还会额外发布一条精确到锚点的 `approved_plan` 证据。比原文项目更严的是我们还有**证据不足即拒答**（四态 + R5 升级） |
| 原文项目本身的短板 | 它的 `[1][2]` 是**模型自述、无校验**（`query.py` 只把 `source_nodes` 按序编号，不检查模型标了什么）。我们卡片路径的文本是已审核原文、引用越界即丢步，比原文强一档；差的是自由文本路径 |
| 最大的缺口是什么 | **自由文本回复零引用**。两条模型生成路径（`reply.stream`、`reply_to_turn`）检索片段都进了提示词，但都不要求标注、不做回执校验。R7 样本第 4 轮「模型自行给出三步排查」就是这条路径 |
| 第二大缺口 | **主引用有了但没标出来**。`steps.py:141` 已按 `instruction_src` 的精确锚点发布 `approved_plan` 证据，但同 doc 的全部命中片段仍一并挂上，前端分不清哪条是「这一步真正的出处」；且该证据永不与检索命中去重（v1 说「锚点被丢弃」是过时判断，见 §0.1） |
| 要不要换技术栈（LlamaParse / LlamaIndex / Ollama） | **不要**。见 §6 |
| 建议动作 | G2′（主引用标记，改动极小）→ G1a（回复事后归因，不改提示词）为 P0；G4（可达性基线）、G3（失败归因字段）为 P1；G1b（模型自标引用）**待 G1a 基线出来再决定** |

### 0.1 复评勘误（相对 v1）

1. **G2 判断过时**。v1 说 `_evidence_for` 丢掉 `#c12` 锚点、「退化到文档级」。实际 `steps.py:141-163`（commit 1b4e72c，9/15，比 v1 早一天）已用 `evidence_key` 的 `doc_id#chunk_id` 发布一条 `source=approved_plan, score=1.0` 的证据，前端也有 `approved_plan → 预写排障资料` 的标签。锚点没丢，问题变成三件更小的事，见 §4。
2. **「1/200 元数据写入丢失」是误读**。`ingest.py:300` 的注释原文是：批量导入后**立即 list** 有 1/200 读到空，属列表视图滞后，稍后 get 单条已存在；代码因此改用 get 回读「避免把滞后误判成丢失」。所以 §1.1 的「元数据丢了 → 范围控制失效」是一个**尚未被观察到**的风险，不是已知缺陷。G4-C 相应改写。
3. **原文引用机制的定位要说准**。原文的 CitationQueryEngine 是「把检索块编号喂给模型 + 让模型在句末写 `[n]`」，仓库代码对模型输出的 `[n]` **不做任何校验**。它的可信度来自 UI 把源文本摊开给人看，不来自系统保证。这正好反过来提醒我们：G1 若照搬「让模型标 `[n]`」，等于把可审计性建立在模型合规上——所以 G1 拆成 a/b 两步（§3）。
4. v1 漏了第二条自由文本路径：`owns_diagnostic_reply(state)` 为真时走 `conversation/reply.py:reply_to_turn`（R7 修复引入），同样调模型、同样无引用。G1 覆盖范围补上。

---

## 1. 原文四层 → 本项目的概念映射

原文的架构是：**云端解析 → 本地嵌入检索 → CitationQueryEngine 编号引用 → 验证 UI**。逐层对照：

| 原文层 | 原文做法 | 本项目对应物 | 是否可借鉴 |
| --- | --- | --- | --- |
| 解析层 | LlamaParse 把 PDF 转布局感知 Markdown，保留页码；文件哈希缓存 | **我们没有 PDF**。知识源本来就是人工维护的带 front-matter Markdown（`data/knowledge/kb_manual/*.md`），由 WeKnora 父子分块 800/200 入库 | 原则可借鉴（见 §1.1），做法不可照搬 |
| 检索层 | 嵌入 + VectorStoreIndex + top-4 | WeKnora 混合检索（BM25 + 向量）+ 百炼 rerank + RRF 多变体融合 + CRAG-lite 相关性评分 | **我们更强**，无需借鉴 |
| 引用层 | CitationQueryEngine 切 512 字符块，让模型内联 `[1][2]`，**不校验** | 卡片级已有且校验越界；**自由文本零引用** | **这是主要缺口，见 G1** |
| 验证层 | UI 展示页码、原文、查询词高亮、相关性分数 | `EvidenceDrawer` 展示来源类型 / doc_id / 版本 / 片段 | **缺定位、分数、评分结论，见 G3** |
| 部署切分 | 只有解析上云，其余本地 | 与我们无关：WeKnora 自托管，embedding / rerank / 生成走远程（D17） | 不适用 |

### 1.1 原文最有价值的三条论断，及其在我们这里的形态

1. **「答案质量的上限由解析决定」**（原文：*The quality of the answer is bounded by the quality of the parse*）
   我们不会遇到双栏串读、OCR 失败，但**同构的天花板依然存在**，只是上移到了分块与元数据：
   - 父子分块 800/200（`ingest.py:chunking_config`）按 `\n\n` / `\n` / `。` 切分。手册的锚点写在小节标题行（`### 1.1 清理滚刷（c12）`），**标题行与正文段是否落在同一子块，取决于切分器如何处理单行标题**——这直接决定 §4 的锚点匹配能否命中，目前没有验证过；第 3 章指示灯表格同样有被拦腰切断的风险；
   - `custom_metadata` 靠 `verify_metadata` 用 get 单条回读保证（`ingest.py:300`），目前**没有观察到真实丢失**。但一旦丢，`KnowledgeScope` 过滤就失效，所以它值得进 CI 常态断言（G4-C），而不是当已知 bug 修。

   这两件事都发生在模型看到内容之前，调 prompt、换模型都救不回来。

2. **「引用粒度是权衡，没有标准答案」**
   原文选 512 字符。我们已经是 small-to-big（child 200 / parent 800，`synthesize._evidence_text` 有正文用父块 ≤800 字、否则子块 ≤300 字），**不应该再引入第三套切分**。我们的粒度问题不在字数，在**挂载关系太松**（见 G2）。

3. **「引用 ≠ 正确」**
   原文的例子是表格数值配错列头。我们有一个更贴切的版本：**步骤文本来自 `plans.yaml` 的已审核原文，不是模型从证据生成的**（`guide/steps.py` 文档注释：「原样发布已审核操作」）。
   所以我们的失效模式不是「模型编造了引用」，而是**「引用挂错了」**——步骤是对的，但挂上去的那几条证据其实不支持它。这类错误比幻觉更隐蔽，因为文本永远读得通。

   原文还有一句值得直接搬来当验收口号：*The difference is that the failure is visible*——答错不可怕，答错了说不清是解析、检索还是生成的锅才可怕。§5 的「归因三问」就是这句话的工程化。

---

## 2. 现状盘点

### 2.1 已经做到的（不要重复造）

| 能力 | 实现位置 | 说明 |
| --- | --- | --- |
| 证据契约 | `contracts/haike_contracts/common.py:111` `EvidenceItem` | `evidence_id / source / doc_id / doc_version / chunk_id / snippet / score / status` |
| 假设必须有据 | `orchestrator/app/diagnose/synthesize.py:74` `filter_hypotheses` | 越界 evidence_id 剔除；**零证据的假设整条丢弃**（`no_evidence:{pid}`） |
| 步骤引用（宽集合） | `orchestrator/app/guide/steps.py:42` `_evidence_for` | 同 doc 允许条目 + 命中该计划的故障卡 + diagnose 给的 ids；越界 → 丢弃该步取下一步 |
| 步骤引用（精确锚点） | `orchestrator/app/guide/steps.py:141-163` | 按 `instruction_src` 的 `doc_id#chunk_id` 发布 `approved_plan` 证据，snippet 取 `plans.yaml` evidence 段的已审核文本，score 1.0；检索挂了也能看 |
| 证据不足即拒答 | `knowledge/adapter.py` 四态 + `HINTS` | `no_match` / `unavailable` 时**不调模型**，走预写计划或 R5 升级，禁止常识补假设。**这正是原文列在「后续可做」里的 abstention（*refuse to answer when retrieved evidence is too weak*），我们已经有了** |
| 相关性评分 | `diagnose/grade.py` | CRAG-lite：逐条 relevant/irrelevant/unsure + coverage，被滤的仍作为「检索到的来源」发 evidence 事件（`sessions/graph.py:1758`） |
| 前端来源抽屉 | `frontend/src/components/EvidenceDrawer.tsx` | 折叠列出片段，当前步骤引用的条目高亮联动；已识别 `approved_plan` 来源标签 |
| 检索可观测 | `knowledge/search.py:_kb_trace`、`retrieval_trace` | 每库每变体的 query / status / hit_ids / scores / latency |
| 离线评测 | `knowledge/eval.py:101` `score_case` | precision@k、first_rank，以及 `chunk_markers()` 的分块级金标 |

### 2.2 缺口

| 编号 | 缺口 | 证据 |
| --- | --- | --- |
| G1 | **自由文本回复无引用**（两条路径） | `prompts/reply.py:16` `REPLY_INSTRUCTION` 只说「只能引用检索片段里出现的操作」，没要求标注；`reply_messages` 把 `[evidence_id[:8]] snippet` 喂进去但 `sessions/graph.py:2320` 之后对 `out.text` 不做任何解析；`conversation/reply.py:reply_to_turn` 同理；`contracts/events.py:106` `Message` / `:112` `MessageEnd` 无引用字段 |
| G2′ | **主引用未标记、宽集合未降级、`approved_plan` 永不去重** | `_evidence_for` 仍把同 doc 所有允许片段挂上；`steps.py:146` 的去重条件要求 `chunk_id` 相等，但检索命中的 `chunk_id` 是 WeKnora 的 chunk UUID（`adapter.py:350`），`plans.yaml` 的是 `c12`，**永不相等** → 每步都多发一条与检索片段内容重叠的证据；`TroubleshootStep` 无 `primary_evidence_id` |
| G3 | **失败无法归因到段** | `EvidenceItem` 无 locator；`Hit.grade` 已算（`adapter.py:85`）但 `as_evidence_item` 不带出（`:87-98`）；前端不展示分数 |
| G4 | **证据可达性无基线** | `plans.yaml` 的 `instruction_src` 锚点从未被验证「入库后还检索得到」；`approved_plan` 的存在**不能**当作证明——它的 snippet 来自 `plans.yaml`，不来自 WeKnora，检索完全没命中该段时它照样发布 |

---

## 3. G1：自由文本回复的引用（P0，分两步）

### 问题
两条回复路径的治理强度差了一个量级：
- **卡片路径**（step_card / plans_ranked）：证据强制、越界丢弃、前端可查。
- **自由文本路径**（`reply.stream` 与 `reply_to_turn`）：检索片段进了提示词，输出不做任何结构校验。

R7 分析里第 4 轮「模型自行给出基站供电 / 触点清洁 / 重新归位三步排查」（`spec_r7_symptom_interview_20260915.md` §一）走的就是后者。那次结论是「模型本可以继续排障」——但从可审计角度看，**那三步没有任何来源**。

### 为什么不直接照搬「让模型标 `[n]`」
原文项目的引用就是这么做的，而且**不校验**。我们若照搬，会同时承担两个成本：提示词改动影响所有自由文本的语气（要 bake-off）；引用质量取决于 DeepSeek / GLM 对中文句末标注的合规率，而这个数字我们现在没有。更稳的顺序是先不动模型，用确定性方法量出「回复到底有多少内容能对上片段」。

### G1a：事后归因（不改提示词，P0）
1. 回复流结束后（`stream_to_writer` 返回 `out.text`），把 `out.text` 按句切分，对每句与本轮 `evidence_items[:len(kept)]` 的 snippet 做**字面重叠匹配**（字符 n-gram 或 `difflib` 最长公共子串占句长比例），超过阈值即判该句「有据」，记下对应 evidence_id。
2. `MessageEnd` 增加可选 `citations: list[str]`（evidence_id 数组，默认空）。前端复用 `EvidenceDrawer` 的 highlight 通道，与 `StepCard` 完全同构。
3. 指标：`knowledge_status == "ok"` 且回复含操作性句子（含「请 / 先 / 检查 / 清理 / 重启」等动词模式）、但 `citations` 为空 → 记 `ungrounded_reply`。**只观测，不拦截**，积累一周基线。
4. 两条路径共用同一段归因代码：`reply.stream` 结束处与 `reply_to_turn` 结束处各插一次调用。

字面匹配的局限要认：模型换了说法（「把滚刷拆下来」vs「取出滚刷」）会漏判。但漏判方向是**把有据判成无据**，指标偏保守，作为基线可接受；且它是 0 模型成本、可离线重放的。

### G1b：模型自标引用（视 G1a 基线决定）
若 G1a 显示 `ungrounded_reply` 占比高到不能接受，再上：
1. `REPLY_INSTRUCTION` 增加一句：「给出原因或动作时，在句末标注你实际使用的片段编号，格式 `[e1]`；没有片段支撑的句子不要标。」编号用**局部序号 e1/e2**，不用 evidence_id 前 8 位——序号对模型更稳定，也不会把内部 id 泄露到用户可见文本（与 `reply.py` 现有约束一致）。
2. 代码侧解析回执：抽出 `[eN]` → 映射回 evidence_id → 越界的**从文本里剥掉**（不是丢整条回复），记 `trace: citation_dropped`；再与 G1a 的字面归因取并集。
3. 需灰度 + bake-off（`bakeoff/tasks.py:128` 已有 `reply_messages` 的评测入口，可直接加用例）。

### 明确不做
- 不要求每句都带引用。安抚语（`REASSURANCE_INSTRUCTION`）、澄清提问、历史回顾本来就不该有引用。
- 不因为缺引用就拒答——拒答的判据仍然是检索四态，不是文本形态。

---

## 4. G2′：把已有的主引用标出来（P0，改动极小）

### 现状
`plans.yaml` 的作者已经写明每一步的精确出处：

```yaml
- {step_id: s1, title: 检查并清理滚刷, instruction_src: evidence:manual_rv_v1#c12, ...}
```

`steps.py:141-163` 已经据此发布一条 `approved_plan` 证据（`chunk_id=c12`、snippet 为 evidence 段的审核文本）。这条**就是主引用**，只是没被标成主引用。三个具体缺陷：

1. **宽集合仍在**。`_evidence_for` 把同 doc 的所有允许片段都挂上：清理滚刷这一步，会连带滤网、尘盒、边刷的命中一起显示「来源 5 条」，真正支撑它的只有 1 条。
2. **去重永不生效**。`steps.py:146` 用 `doc_id + chunk_id + snippet` 三者相等判重，但检索命中的 `chunk_id` 是 WeKnora UUID，永远不等于 `c12`；snippet 也是 200 字子块 vs 一句审核文本，永远不等。结果每步都多发一条与某个检索片段内容重叠的证据。
3. **看不出检索是否真的命中了该段**。`approved_plan` 是本地发布的，检索没召回 c12 所在片段时它照样出现，前端与审计都无法区分「检索到了」和「靠本地兜底」。

### 方案
1. `TroubleshootStep` 增加 `primary_evidence_id: str | None`。
2. `_evidence_for` 之后新增一步 `_primary_for`：在 `allowed_evidence` 中找 snippet 含该步锚点标记（`（c12）`）的检索命中——复用 `eval.py:70` `chunk_markers`，把它提到 `knowledge/` 下共用。命中 → 它是 primary，**并且不再发布 `approved_plan`**（这才是去重该有的语义）；未命中 → `approved_plan` 那条是 primary，同时记 `trace: anchor_not_retrieved`。
3. 同 doc 宽集合降级：保留在 `evidence_ids` 里（越界校验与回放不变），但前端 `EvidenceDrawer` 默认只展开 primary，其余折叠为「其他相关来源 N 条」。
4. **副作用是一个免费的运行时自检**：`anchor_not_retrieved` 的出现频率就是 G4-A 的线上版本。

### 一个必须先验证的前提
`（c12）` 标记在手册里写在**标题行**，正文在下一行。运行时 `state["evidence"]` 只有子块 snippet（`as_evidence_item`，无 `full_text`），若切分器把标题行单独切成一块，正文片段里就没有标记，第 2 步会系统性落到「未命中」。**在动 `_primary_for` 之前，先跑 G4-B 确认标题与正文同块**；若不同块，改为匹配 `plans.yaml` evidence 段的审核 snippet 前 20 字（它就是正文首句，见 `manual_rv_v1.md:15`）。

### 与原文的分歧
原文把粒度问题解成「切更小的引用块」（512 字符）。我们不切——我们的锚点是**人工标注的语义单元**，比任何字符切分都准。这是自建语料相对通用 PDF 管线的结构性优势，应该用满。

---

## 5. G3 / G4：让失败可归因（P1）

### G3：证据事件补两个字段
| 字段 | 内容 | 用途 |
| --- | --- | --- |
| `locator` | `doc_id#anchor`（如 `manual_rv_v1#c12`），无锚点时回落 `doc_id#chunk_{index}` | 回答「这句话出自手册哪一节」，等价于原文的页码 |
| `grade` | `relevant / irrelevant / unsure`（`Hit.grade` 已算，`as_evidence_item` 目前不带出） | 被滤掉的证据仍然发事件（`graph.py:1758`），但前端看不出它是被滤的 |

前端 `EvidenceDrawer` 相应补：分数、locator、被滤标记。原文验证 UI 的四要素（页码 / 原文 / 高亮 / 分数）我们就齐了，只差查询词高亮——**高亮建议不做**，我们的 query 是 `build_query` 拼出来的产品词 + 症状词，高亮出来是噪音，不是信号。

### 归因三问（admin 控制台 `NodeDetail`）
原文的说法是 *see whether the problem came from parsing, retrieval, or generation*。我们多一类「挂载」，一次答错按这个顺序问：

1. **分块 / 元数据问题？** 该步骤 `primary_evidence_id` 指向 `approved_plan`（即 `anchor_not_retrieved`）且 `retrieval_trace` 里该 doc 有命中 → 内容入库了但被切碎或标记丢失。
2. **检索问题？** `retrieval_trace` 里正确 doc 是否进了 top-k、`grade` 是否把它判成 irrelevant → 召回或精排问题。
3. **挂载问题？** 步骤卡 primary 正确，但 `evidence_ids` 宽集合里混入了不相关片段被用户/评审当成依据 → `_evidence_for` 的同 doc 规则太松。
4. **生成问题？** 证据齐、评分对，但自由文本回复的 `citations` 为空或指向别处 → 模型问题。

### G4：证据可达性基线（`make kb-verify` 扩展）
在 `knowledge/eval.py` 旁加一个不依赖标注集的确定性检查：

- **A. 锚点可达**：对 `plans.yaml` 里每个 `instruction_src` 锚点，用该步 title 作 query 检索，断言对应片段进 top-k。这是我们版本的「解析保真度」，对标原文提到的 ParseBench。
- **B. 分块未截断**：断言 (i) 每个带 `（cNN）` 标记的标题行与其正文首句落在同一子块；(ii) 手册第 3 章指示灯表格的表头与数据行落在同一父块（`chunk_markers` 已有 `第3章表 → "| 现象 | 含义 |"` 判据）。**(i) 是 G2′ 的前提，先做。**
- **C. 元数据完整**：`verify_metadata`（get 单条回读）结果里 `doc_version` / `sku_list` 缺失数 == 0。目前预期为绿，进 CI 是为了防回归，不是修 bug。

A/B/C 全是确定性断言，可进 CI，**不需要人工标注集**——比「50 条标注样例」门槛低得多，应该先做。

---

## 6. 明确不采纳

| 原文做法 | 不采纳理由 |
| --- | --- |
| LlamaParse 解析 PDF | 我们的知识源是自维护 Markdown，不存在解析环节。真要接客户上传的 PDF 是另一个需求，不在本 spec 范围 |
| LlamaIndex + VectorStoreIndex 替换检索 | WeKnora v0.8.0 已锁版本，混合检索 + rerank + RRF + CRAG-lite 比原文的 top-4 相似度检索强，替换纯负收益 |
| Ollama 本地 qwen3:4b 生成 | 与 D17（远程百炼 + 国产链 DeepSeek / GLM）冲突；4b 模型撑不住我们的结构化输出约束 |
| 512 字符 citation chunk | 我们已是 child 200 / parent 800 的 small-to-big；引入第三套切分只会让 `_evidence_text` 的两档逻辑变三档 |
| 模型自标 `[n]` 且不校验 | 原文项目的现状。我们即便上 G1b 也必须校验并剥离越界引用 |
| 「证据太弱时拒答」 | **已经实现且更严格**：四态 + 允许集合为空直接 no_match + R5 升级 + 零证据假设丢弃 |
| 引用点击跳转原文 PDF 页 | 我们没有 PDF。G3 的 `locator` 已是等价能力（跳到 Markdown 小节） |
| 解析结果按文件哈希缓存 | 我们的等价物是 `status: replay` 的回放证据与 fixture，已有 |

---

## 7. 落地顺序与验收

| 序 | 改动 | 主要文件 | 验收 | 风险 |
| --- | --- | --- | --- | --- |
| 1 | G4-B(i) 标题正文同块检查 | `knowledge/eval.py` | 跑出当前红绿；决定 G2′ 用标记还是首句匹配 | 低。只读，半天 |
| 2 | G2′ 主引用标记 + 去重修正 + 宽集合降级 | `guide/steps.py`、`contracts/common.py`、`EvidenceDrawer.tsx` | 每个 `plans.yaml` 步骤 primary 非空；检索命中时不再多发 `approved_plan`；前端默认展开 1 条 | 低。越界校验逻辑不动 |
| 3 | G1a 事后归因 + `MessageEnd.citations` + `ungrounded_reply` 指标 | `sessions/graph.py:2320` 附近、`conversation/reply.py`、`contracts/events.py`、前端 | 两条路径都产出 citations；指标进控制台 | 低。不改提示词，不改语气 |
| 4 | G4-A/C 进 CI | `knowledge/eval.py`、Makefile | 三项断言全绿 | 低 |
| 5 | G3 locator + grade 出 SSE | `knowledge/adapter.py:87`、`contracts`、admin `NodeDetail` | 归因四问在控制台可走通一遍 | 低 |
| 6 | G1b 模型自标引用 | `prompts/reply.py`、`bakeoff/tasks.py` | 仅当 G1a 基线不可接受时启动；bake-off 通过后灰度 | 中 |

黑客松预赛材料 9/27 截止：1–3 三项加起来约两天，且 2、3 直接改善演示里「来源」抽屉的可读性，建议这三项进预赛前；4–6 放预赛后。
契约改动都是**新增可选字段**，旧快照与回放 fixture 不受影响；契约改完需重跑 `contracts` 的 codegen 同步前端类型。

---

## 8. 开放问题（需确认）

1. **G1 的引用要不要对用户可见？** G1a 天然不产生角标，只进 `MessageEnd.citations` 供抽屉高亮与审计，即 v1 的选项 (b)，**默认就这样**。若黑客松演示要把「每句都有出处」当卖点，(a) 可见角标只能靠 G1b 实现——这会把 G1b 从「视基线而定」提前到预赛前，需要你拍板。
2. **`ungrounded_reply` 最终要不要变成硬门？** 建议先观测。真要拦，拦的动作是「降级成不含操作建议的澄清回复」，而不是拒答——但这会改变对话手感，需要单独评估。
3. **G4-A 锚点检查失败时按什么处理？** CI 红灯挡合并，还是只告警？取决于 `plans.yaml` 与手册的更新频率是否同步——如果手册改版常导致锚点漂移，红灯会变成噪音。
4. **（新）G2′ 检索命中时不再发布 `approved_plan`，会不会影响「检索挂了也能看」的初衷？** 不会：`unavailable` 时 `allowed_evidence` 里没有检索命中，仍会走本地发布分支。但要在 `test_steps` 里补这条边界用例。

---

## 附：相关文档

- [智能体式 RAG 方案评估](spec_agentic_rag_evaluation.md) —— 本 spec 的检索层现状基线来自此文 §1
- [R7 误升级根因](spec_r7_symptom_interview_20260915.md) —— G1 的问题样本
- [向量库选型](spec_vector_store_decision.md)、[上下文工程经验](spec_context_engineering_lessons.md)

---

## 9. 实施记录（2026-09-16，分支 feat/grounded-citation）

本节追加，不改上文。上文是动工前的评估，这里记录实际做出来之后的事实与三处与评估不符的地方。

### 9.1 已落地

| 序 | 内容 | 位置 |
| --- | --- | --- |
| 1 | G4-A/B/C 可达性基线，`make kb-anchors`，非零退出即红 | `knowledge/reachability.py`、`knowledge/cli.py`、Makefile |
| 2 | 锚点匹配三档（精确 chunk / 人工标记 / 已审核原文） | `knowledge/anchors.py` |
| 3 | G2′ 主引用、去重修正、`anchor` 归因 trace | `guide/steps.py`、`sessions/graph.py` |
| 4 | `TroubleshootStep.primary_evidence_id`、`MessageEnd.citations` | `contracts/haike_contracts/` |
| 5 | 前端主引用直接展开、其余折叠一层 | `EvidenceDrawer.tsx`、`Timeline.tsx`、`Cards.module.css` |
| 6 | G1a 事后字面归因与 `reply_grounding` 指标 | `conversation/citations.py`、`sessions/streaming.py`、`sessions/graph.py`、`conversation/reply.py` |

验证：后端 892 passed（新增 `test_anchors.py` 8 例、`test_citations.py` 8 例）、前端 214 passed、
`make contracts-check` 通过、`make lint` 通过、`make kb-anchors` 三项全绿。

### 9.2 与评估不符的三处

1. **G4-B(i) 的担心没有发生，但 G4-A 暴露了另一件事。**
   §4 担心「（c12）标记写在标题行，可能与正文被切到不同子块」。实测五个手册锚点全部 `same_chunk`，
   标记可用。真正拦路的是 **scope**：`manual_rv_v1` 是 `scope: sku` 文档，而引用它的计划全是
   `applies_to.scope: category_generic`。所以 category_only 会话根本看不见这份手册，锚点必然认不出，
   每一步都退回本地发布。这不是分块问题也不是检索问题，是**语料 scope 与计划 scope 不对齐**，
   §5 的归因三问里没有这一类。可达性检查因此必须按「锚点所属文档可见的最小 scope」去测，
   否则测的是范围控制而不是可达性。是否要把手册降为 category_generic，或给计划补 sku 版本，
   留作开放问题 5。

2. **四个 FAQ 锚点当前永远认不出。** `config/retrieval.yaml` 里 `faq.enabled: false`
   （WeKnora v0.8.0 的 FAQ 接口返回空）。所以 `faq_rv#q7/q9/q12/q15` 这四步固定走本地发布。
   基线把它记为 `skipped_faq_off` 而不是红，但这意味着**四步排障的来源抽屉里只有预写资料、
   没有检索命中**，演示时值得知道。

3. **§0.1 第 4 条关于 `reply_to_turn` 的说法要修正。** 它的模型分支条件是
   `not owns_diagnostic_reply(state)`——排障回合根本不走模型，走的是模板。该路径的提示词明确
   禁止「生成新的排障动作」。所以它不是「第二条排障自由文本路径」，G1a 在那里的正确用法不是
   挂引用，而是**用空证据集合跑归因**：凡出现动作句就全部落进 `ungrounded`，正好当这条禁令的
   观测口。已按此实现。

### 9.3 实现中确认的两件事

- **去重永不生效已证实**。`steps.py` 旧去重比对 `chunk_id`，而检索侧是 WeKnora UUID、FAQ 侧是
  `faq_rv#q7`、`plans.yaml` 侧是 `c12`，三者互不相等。两个既有测试断言里都带着那条多余的
  `plan:manual_rv_v1#c12:...`，等于把这个 bug 当成期望行为钉住了，本次一并改正。
- **字面归因的偏差方向**符合预期：R7 样本那种「检查基站供电 / 清洁触点 / 重新归位」三步全部被判
  `ungrounded`，而改写过的正确步骤也会被漏判。分母还有一层保守——动作句按关键词认，口语说法
  认不出。这些都只影响基线高低，不影响「先观测不拦截」的结论。

### 9.4 下一步

§7 的 4–6 项未做：G4-A/C 进 CI、G3 的 locator + grade 出 SSE、G1b 模型自标引用。
G1b 仍建议等 `reply_grounding` 跑出一周基线再决定。

### 9.5 新增开放问题

5. **手册 scope 与计划 scope 不对齐怎么处理？** 三个选项：把 `manual_rv_v1` 降为
   `category_generic`（放宽范围控制）、给计划补 sku 维度（配置翻倍）、或接受 category_only
   会话固定走本地发布（现状，来源抽屉里看不到检索命中）。这件事影响演示时「来源」的说服力，
   需要你拍板。
