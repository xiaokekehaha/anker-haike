# 经典软件工程概念在 AI 编程中的复用：Tracer Bullet、Leading Word、Deep Module、Ubiquitous Language

来源：

- Matt Pocock（Grill Me / mattpocock-skills 作者）访谈转述。核心论点：Agent 按层写代码，最后才组装，各层拼不上；解法是从三本老书里取概念写进提示词。
- Matt 的 skills 原文（本机 `~/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.2.3/skills/`）：`codebase-design`、`domain-modeling`、`tdd`、`to-tickets`、`writing-for-agents`、`prototype`、`ask-matt`。下文引用「Matt 的定义」均出自这些文件。
- 三本原著：Thomas & Hunt《程序员修炼之道》（The Pragmatic Programmer，20 周年版）；Ousterhout《软件设计哲学》（A Philosophy of Software Design）；Evans《领域驱动设计》（Domain-Driven Design）。
- 案例取自本仓库（anker-haike）的提交、spec 与代码。

术语约定：下文「Agent」指编码智能体（Claude Code / Codex 之类）；「提示词」包括对话输入、`CLAUDE.md`、skill 文件。

## 0. 总览

| 概念 | 出处 | 解决的问题 | 本仓库对应物 |
| --- | --- | --- | --- |
| Tracer bullet（追踪子弹） | 《程序员修炼之道》Topic 12 | 按层开发，最后组装才发现层间对不上 | 提交 ec7a24a 一次贯穿 contracts → orchestrator → frontend；`make contracts` 流水线 |
| Leading word（引导词） | Matt 自创，见 `writing-for-agents` | 提示词里用一段话描述行为，Agent 执行不稳定 | `CLAUDE.md` 里的 planning-with-files、spec、addendum 等既有词 |
| Deep module（深模块） | 《软件设计哲学》第 4 章 | 接口和实现一样复杂，改一处牵连多处，难测 | `KnowledgeAdapter` Protocol + WeKnora 实现 + 测试替身；`FakeChatModel` |
| Ubiquitous language（统一语言） | 《领域驱动设计》第 2 章 | 同一概念多个叫法，人、代码、提示词各说各话 | `08_session-execution-contract.md` §1 术语表；`symptom_taxonomy.yaml` 的 symptom_code |

四者关系：tracer bullet 决定**切工作的方向**，deep module 决定**切出来的模块长什么形状**，ubiquitous language 决定**给模块和概念起什么名**，leading word 是**把前三者塞进 Agent 脑子的传输手段**。

## 1. 问题：Agent 按层写，最后才组装

Matt 观察到的现象：让 Agent 做一个功能，它先写完数据库层，再写完应用层，最后写前端。每层单看都对，拼起来出问题，因为数据库的设计决定前端能展示什么，这些约束要早对齐才知道合不合理。

本仓库有一个同构的案例，不是 Agent 分层写的，但失败机理一样：**两个模块各自正确、互不知情**。

案例：观察题回答丢失导致会话死锁（`docs/claude/spec_observation_deadlock_20260918.md`）。用户回答「设备不在身边」，一句话同时走两条路：

```
"设备不在身边"
   ├─ interpret.py  短路成 device_missing → resources["device"] = False
   │                （之后所有步骤与观察都不可用，只剩 pause）
   └─ reduce.py     match_reply 匹配不到选项标签 → 请求置为 "unparsed"
                    （之后只受理 status == "asked"，逐字回答也被丢弃）
```

两层各自看都合理：interpret 层负责识别操作条件，reduce 层负责受理观察回答。但没有一条纵向路径把「用户说不在身边 → 稍后说拿到了 → 继续排障」跑通过，于是暂停文案承诺「拿到设备后告诉我」，系统却听不懂「拿到了」。

如果当初用 tracer bullet 的方式做这个功能，第一颗子弹就该是「一句资源缺失的回答，从 HTTP 入口到暂停文案再到恢复」全链路跑通，而不是先把 interpret 写全再把 reduce 写全。

## 2. Tracer Bullet（追踪子弹）

### 2.1 原著定义

《程序员修炼之道》Topic 12。比喻来自机枪的曳光弹：在黑暗里打一发能看见轨迹的弹，看它落在哪，再修正瞄准。对应到软件：**先做一条端到端的窄路径，把所有层都贯穿，跑通后再向两侧扩展**。

书里强调 tracer bullet 与 prototype（原型）的区别：

| | Tracer bullet | Prototype |
| --- | --- | --- |
| 代码去向 | 保留，是最终系统的骨架 | 丢弃，只为回答一个问题 |
| 完整度 | 每层都真的做，但每层只做最窄的一条 | 可以用假数据、跳过错误处理 |
| 目的 | 验证架构与集成可行，给后续开发一个可运行的基线 | 探索某个未知点（状态模型是否合理、UI 长什么样） |

Matt 的 `prototype` skill 与书里的 prototype 定义一致：「throwaway code that answers a question」，无持久化、不写测试、状态全部打印出来。两个概念不要混用。

### 2.2 横向分层 vs 纵向切片

```
横向分层（Agent 的默认倾向）           纵向切片（tracer bullet）

 前端   ░░░░░░░░░░░░░░░░  第 3 步        前端   █░░░░░░░░░░░░░░░
 应用   ░░░░░░░░░░░░░░░░  第 2 步        应用   █░░░░░░░░░░░░░░░
 数据库 ████████████████  第 1 步        数据库 █░░░░░░░░░░░░░░░
                                                ↑
 每层写完才能看到集成问题                 第 1 颗子弹：窄但贯穿；跑通后向右扩展
```

### 2.3 本仓库案例：一次提交贯穿四层

提交 ec7a24a「产品确认三档判定与无症状首问多选」改了 32 个文件，按层分布：

```
contracts/haike_contracts/{actions,events,snapshot}.py     Pydantic 模型（真源）
contracts/schema/*.schema.json                             make contracts 生成
frontend/src/types/{actions,events,snapshot}.ts            make contracts 生成
frontend/src/api/events-schema.ts                          make contracts 生成
orchestrator/app/{conversation,diagnose,knowledge,plans,sessions}/…   后端逻辑
frontend/src/components/ProductCard.tsx, state/reducer.ts  前端展示
orchestrator/tests/test_*.py, frontend/src/components/Cards.test.tsx  两侧测试
```

这是一颗 tracer bullet：一个功能，一次提交，每层都动但每层只动这个功能需要的部分。能这样做的前提是**层间契约的生成成本接近零**：改 Pydantic 模型后 `make contracts` 一条命令把 JSON Schema、TS 类型、Zod 校验器全部重新生成，CI 用 `contracts-check` 拦截漂移。

对照 CLAUDE.md 的规则「生成文件禁止手改，改模型后 `make contracts` 重新生成」：这条规则的价值不只是防漂移，它让纵向切片变得便宜。如果契约要三处手工同步，Agent 会自然退回按层开发。

### 2.4 Matt 的落地方式

`to-tickets` skill 把任何 spec 拆成 tracer-bullet 票，规则原文：

- 每张票纵向切过所有层（schema、API、UI、tests），不是某一层的横切
- 完成的票单独可演示或可验证
- 每张票的大小放得进一个新开的上下文窗口
- 预备性重构先做
- 每张票声明 blocking edges（哪些票必须先完成）

`tdd` skill 把「横向切片」列为反模式：先写完所有测试再写所有实现，测的是想象中的形状，而不是用户可见的行为。正确做法是「一个测试 → 一个实现 → 重复」，每个测试就是一颗 tracer bullet，响应上一轮学到的东西。

**例外：大范围机械重构**。改一个共享符号的类型、重命名一个列，一动就炸几千个调用点，任何纵向切片都不能单独变绿。Matt 的处理是 expand–contract：先加新形式（不删旧的），按爆炸半径分批迁移调用点（每批一张票），最后删旧形式。这和本仓库「除非用户要求，不保留向后兼容」不冲突：expand–contract 的兼容期只存在于一组票之间，contract 票完成时兼容代码必须删除。

### 2.5 怎么写进提示词

Matt 的做法是直接把词写进去：「把这个做成一个 tracer bullet」。他观察到 Agent 开始在推理中自发使用这个词。这就引出第 3 节。

适合本仓库的写法（放 CLAUDE.md 或 planning 目录的 task_plan.md）：

```
拆任务按 tracer bullet：每个子任务贯穿 contracts → orchestrator → frontend → 测试，
单独可验证；先跑通最窄的一条，再扩展。改模型后 make contracts。
```

## 3. Leading Word（引导词）

### 3.1 定义

Matt 在 `writing-for-agents` 里的定义：**一个在模型预训练里已经存在的紧凑概念，Agent 执行文档时用它来思考**。例子：lesson、fog of war、tracer bullets。它作为一个 token 反复出现，而不是作为一句话反复解释，靠模型已有的先验把一整片行为锚定在最少的 token 上。

机理：经典编程书几乎必然在训练数据里。提示词里出现「tracer bullet」，激活的不只是这个词，还有围绕它的整片知识：和 prototype 的区别、为什么要先贯穿、扩展时怎么做。自造词也能用，但要花 token 去定义，而且不带先验。**先找现成的词**。

### 3.2 两处锚定

- **正文里锚定执行**：词每次出现，Agent 复用同一套行为；在平铺的规则列表里，它把注意力聚焦到一类要找的东西上。
- **指针里锚定调用**：同一个词同时出现在提示词、文档、代码里，Agent 把这套共同语言和对应材料关联起来，触达更稳定。这是 skill description 的写法要点：把引导词放最前面。

### 3.3 重构成引导词的例子

Matt 给的两个：

- 「fast, deterministic, low-overhead」三个形容词 → **tight**（a tight loop）
- 「a loop you believe in」这种模糊的门槛 → **red**（这个循环在这个 bug 上变红，或者不变红），把模糊判断变成二值可观察状态

本仓库 CLAUDE.md 里已经在用的引导词：planning-with-files、spec、addendum、scope、ci-local。「plan.md 保持原样；复评、勘误、每轮回顾写 addendum.md」这句话里，addendum 就在替代一段「开发开始后不改原计划，改动记在附录里」的解释。

可以再收的候选：

| 现在的说法 | 候选引导词 | 理由 |
| --- | --- | --- |
| 「大范围修改、审计、或编辑没完整读过的文件之前，先读完整个文件；搜索片段只用来定位」 | **primary source** | Matt 多个 skill 用它指「必须读原文、不能凭摘要判断」 |
| 「只有一个调用点的单行 helper 直接内联」 | **pass-through**、**deletion test** | 见 §4.4，Ousterhout 的词，覆盖面更大 |
| 「模型用 FakeChatModel，知识库用 fake_weknora，HTTP 链路用 conversation_runtime」 | **seam** / **adapter** | 见 §4.2，一句话说清测试替身放哪 |

### 3.4 否定的陷阱

Matt 特别提到：**用禁止来引导，会把被禁止的行为拉进上下文，让它更可得而不是更不可得**。「别想大象」，大象就是全部。否定是弱修饰，强激活的概念会盖过它。所以要正向陈述目标行为（「写单行注释」），让被禁行为根本不出现。禁止只在确实无法正向表达的硬护栏上使用，即便如此也要配一个正向目标。

对照本仓库 CLAUDE.md 的 Git 段：「禁止 `git reset --hard`、`git checkout .`、`git clean -fd`…」是硬护栏，属于 Matt 说的例外。它前面那句「只提交本次会话自己改的文件；`git add` 显式路径」就是配套的正向目标，结构上是对的。其他段落的「不用 any」「不写 `await import()`」可以检查一下是否都有正向说法在旁边。

## 4. Deep Module（深模块）

### 4.1 原著定义与 Matt 的修订

Ousterhout《软件设计哲学》第 4 章「Modules Should Be Deep」：模块的价值在于**接口小、实现多**。接口是使用者必须知道的一切，实现是内部细节。深模块用小接口藏住大量功能；浅模块的接口几乎和实现一样复杂，用它不比自己写省事。

```
深模块（要的）                       浅模块（避免）
┌─────────────────────┐            ┌─────────────────────────────────┐
│   小接口             │            │       大接口                     │
├─────────────────────┤            ├─────────────────────────────────┤
│                     │            │  薄实现（基本是转发）             │
│  深实现              │            └─────────────────────────────────┘
│                     │
└─────────────────────┘
```

Ousterhout 原书有一处用「实现行数 / 接口行数」来直观表示深度。Matt 明确拒绝这个框架，理由是它奖励往实现里灌代码。Matt 的替代定义：**深度 = 接口处的杠杆**，即调用者（或测试）每学一单位接口能驱动多少行为。

### 4.2 Matt 的词汇表

`codebase-design` skill 要求严格使用这几个词，不换成 component / service / API / boundary：

| 词 | 定义 | 避免的说法 |
| --- | --- | --- |
| **Module** | 任何有接口和实现的东西，不分尺度：函数、类、包、跨层切片 | unit、component、service |
| **Interface** | 调用者正确使用模块必须知道的一切：类型签名，还有不变量、调用顺序、错误模式、必需配置、性能特征 | API、signature（只覆盖类型层面） |
| **Implementation** | 模块内部的代码 | |
| **Seam**（Feathers） | 不改这个位置的代码就能改变行为的地方；模块接口所在的位置。接缝放哪是独立的设计决策 | boundary（与 DDD 的 bounded context 混淆） |
| **Adapter** | 在某个接缝上满足接口的具体实现，描述角色不描述内容 | |
| **Leverage** | 调用者从深度得到的：学一点接口，用很多行为 | |
| **Locality** | 维护者从深度得到的：改动、bug、知识、验证集中在一处 | |

### 4.3 四条原则

1. **深度是接口的属性，不是实现的属性**。深模块内部可以由很多小的、可替换的部件组成，它们只是不暴露在接口上。模块可以有内部接缝（私有，自己的测试用）和外部接缝（接口所在）。
2. **删除测试**（deletion test）。想象把这个模块删掉。如果复杂度随之消失，它是 pass-through；如果复杂度在 N 个调用点重新出现，它在挣自己的位置。CLAUDE.md「只有一个调用点的单行 helper 直接内联」是这条的特例。
3. **接口就是测试面**。调用者和测试穿过同一条接缝。如果想绕过接口去测内部，模块形状大概不对。
4. **一个 adapter 是假想接缝，两个 adapter 才是真接缝**。没有东西真的在接缝两侧变化，就不要引入接缝。单 adapter 的接缝只是多了一层间接。

### 4.4 本仓库案例：知识库接缝

`orchestrator/app/knowledge/adapter.py`：

```
KnowledgeAdapter(Protocol)           ← 接口：只有 hybrid_search 一个方法
   ├─ WeKnoraKnowledgeAdapter         ← 生产 adapter：refresh_index / refresh_chunks /
   │                                     expand_parents / allowed_ids / hybrid_search，
   │                                     父块展开、去重叠、YAML 元数据解析全藏在里面
   └─ tests/conversation_runtime.py 的 Knowledge  ← 测试 adapter：记录调用，按 kb 名返回固定命中
```

按 Matt 的原则检查：

- 两个 adapter，接缝是真的（原则 4）。
- 调用方只需要知道 `hybrid_search(kb, query, top_k, allow)`；WeKnora 分块重叠 80 字符怎么去、父块窗口怎么取，都在实现里（原则 1）。
- `conversation_runtime.py` 的模块文档字符串写着「只替换模型/供应商与知识库 I/O」，其他全部走真实 HTTP 链路（`app.main.app`）。测试面是 HTTP 接口，不是内部函数（原则 3）。这也是 CLAUDE.md「单测不碰真实模型与知识库」的实现方式：不是 mock 到处飞，而是只在两条真接缝上放替身。

模型侧同理：`app/models/fake.py` 的 `FakeChatModel` 继承 LangChain `BaseChatModel`，接缝是 LangChain 已经定好的模型接口，生产 adapter 是各供应商的真实模型，`set_model_router` 是接缝的注入点。

### 4.5 Ousterhout 的其他相关概念

- **Pass-through method**（第 7 章「Different Layer, Different Abstraction」）：一个方法只是调用另一个签名几乎相同的方法。它增加接口不增加功能，是浅模块的典型症状。删除测试直接针对它。
- **Define errors out of existence**（第 10 章）：与其抛错让调用者处理，不如改接口语义让错误情形不存在。观察题死锁案例的修复里有一条正是这个思路：`pause_text` 改成「给出真的认得的解除说法」，即暂停文案只承诺系统确实能解析的回答，把「用户按提示回答但系统听不懂」这个错误从接口层面消掉。
- **Design it twice**（第 11 章）：第一个想到的接口大概率不是最好的，至少设计两个再比。Matt 的版本（`DESIGN-IT-TWICE.md`）是并行起 3 个以上子代理，各给一个截然不同的约束（最小接口 / 最大灵活 / 最常见调用者最省事 / 围绕 ports & adapters），然后按深度、局部性、接缝位置比较，给出有倾向的推荐而不是菜单。
- **Information hiding / leakage**（第 5 章）：一个设计决策出现在多个模块里就是泄漏。本仓库 `contracts/` 把事件、动作、快照的形状集中在 Pydantic 模型里再生成到前后端，是在用代码生成消除泄漏；如果前端手改 `types/events.ts`，泄漏就回来了。

### 4.6 依赖分类与测试策略

`DEEPENING.md` 把一个待加深模块的依赖分四类，决定怎么跨接缝测：

| 类别 | 例子 | 怎么测 |
| --- | --- | --- |
| 进程内 | 纯计算、内存状态 | 合并模块，直接通过新接口测，不需要 adapter |
| 本地可替代 | Postgres → PGLite，文件系统 → 内存文件系统 | 测试里跑替身；接缝是内部的，不暴露到外部接口 |
| 远端但自有 | 自己的微服务、内部 API | 在接缝定义 port，生产用 HTTP adapter，测试用内存 adapter |
| 真外部 | Stripe、Twilio、以及本仓库的 DeepSeek / WeKnora | 作为注入的 port，测试给 mock adapter |

测试策略「替换，不叠加」：加深后在新接口写测试，浅模块上的旧单测删掉。测试断言接口可观察的结果，不断言内部状态；实现改了测试就得改，说明测过了接口。

## 5. Ubiquitous Language（统一语言）

### 5.1 原著定义

Evans《领域驱动设计》第 2 章「Communication and the Use of Language」：**领域专家、开发者、代码、文档使用同一套词汇**。一个概念一个名字，模型里的名字就是代码里的名字，也是对话里的名字。语言的分裂（业务说 A、代码叫 B、文档写 C）是模型腐烂的首要信号。

配套概念（第 14 章「Maintaining Model Integrity」）：

- **Bounded context**：一套语言有效的边界。同一个词在不同上下文里可以指不同东西，前提是边界明确。
- **Context map**：多个 bounded context 之间的关系图，写明谁给谁发什么、共享哪些类型。

### 5.2 Matt 的落地：CONTEXT.md

`domain-modeling` skill 把统一语言落成仓库根目录一个 `CONTEXT.md`，只放术语表，不放实现细节：

```md
# {上下文名}

{一两句：这个上下文是什么、为什么存在}

## Language

**Order**:
{一两句定义，说它是什么，不说它做什么}
_Avoid_: Purchase, transaction
```

规则：

- **要有态度**：同一概念有多个词时选最好的一个，其余列进 `_Avoid_`。
- **只放领域词**：超时、错误类型、工具函数这类通用编程概念不放，即便项目大量使用。
- **随时更新**：术语一确定就写，不攒批。
- 多上下文时根目录放 `CONTEXT-MAP.md`，列每个上下文的位置与关系。

会话中的主动纪律：用户用词与术语表冲突时立即指出；模糊词（「account」到底是 Customer 还是 User）提议精确词；用具体场景压边界；用户描述的行为与代码不一致时摆出来。

配套的 **ADR**（架构决策记录）只在三条同时满足时才写：难以逆转、没有上下文会让人疑惑、有真实的取舍。格式可以只有一段话。

### 5.3 本仓库案例

本仓库没有 `CONTEXT.md`，但统一语言散在几处：

- `docs/planning/2026-09-12_smart-service-tech-design/08_session-execution-contract.md` §1 术语表：session / run / version / card / pending_input / interrupt / action / snapshot，每个一句定义。这就是一个 bounded context（会话执行）的语言。
- `config/symptom_taxonomy.yaml`：`fault_family`（用户口语层的故障族）、`symptom_code`（受控代码，与 `plans.yaml` 的 `symptom_codes` 对应）、`discriminator`（判别题）、`selection_label`（多选题给用户看的说法）。同一现象在三层有三个名字，但每层的名字唯一，且映射关系写在注释里。
- 提交信息里的词：「症状码约束计划候选」「无通用计划覆盖时先问型号再 R5」。症状码、计划候选、型号、R5 都是项目词，读得懂提交信息的前提是共享这套语言。
- CLAUDE.md「术语先定义再用」是对人的统一语言纪律。

缺口：这些词没有一个权威的、`_Avoid_` 式的索引。比如「观察」（observation）、「操作条件」（operation_conditions）、「资源」（resources）在死锁案例中三个词交织出现，读 spec 需要来回对照代码才能确定它们的关系。一个 `CONTEXT.md` 能把这类关系写死。这是可选工作，不是本文的结论要求。

### 5.4 对 Agent 的意义

统一语言是 leading word 的项目级版本。提示词、代码、文档共用一套词时：

- Agent 在代码里 grep 提示词里的词就能命中，检索路径变短。
- Agent 产出的命名、提交信息、测试名自动落在同一套词里，人审起来省力。
- `wait-what` skill 的做法：Agent 的解释听不懂时，让它用 `CONTEXT.md` 的词重讲一遍。前提是 `CONTEXT.md` 存在。

## 6. 四个概念在 Matt 工作流里的位置

`ask-matt` 描述的主流程：

```
grill-with-docs ──▶ (prototype 回答跑不通的问题) ──▶ to-spec ──▶ to-tickets ──▶ implement ──▶ code-review
    │                                                              │              │
    │ 统一语言：会话中写 CONTEXT.md / ADR                            │              └─ tdd：每个测试一颗 tracer bullet，
    │                                                              │                 在事先约定的 seam 上测
    │                                                              └─ tracer-bullet 票，声明 blocking edges，
    │                                                                 每张放得进一个新上下文窗口
    └─ 词汇层：domain-modeling（领域词）、codebase-design（模块词），其他 skill 都引用它们
```

上下文纪律：grill → spec → tickets 保持在一个不间断的上下文里，之后每张票在新窗口里 implement。约束是 **smart zone**（模型还能清晰推理的窗口，约 150k token）；接近时在阶段边界 compact，而不是带着退化的推理继续。

对应本仓库现有做法：planning-with-files 的 `plan.md` 相当于 spec，`task_plan.md` 相当于票列表，`addendum.md` 相当于 ADR 加回顾。差别在两处：票是否按 tracer bullet 纵切、是否声明 blocking edges；术语是否有 `_Avoid_` 式的权威表。

## 7. 学习路径

按「先用起来、再读原著」的顺序：

1. **用一次 tracer bullet**。下一个跨层功能，写 plan 时按 §2.5 的句式拆，每个子任务的完成标准写成「从 X 输入到 Y 输出可验证」。
2. **读 `codebase-design/SKILL.md`**（约 150 行），对照 §4.4 把本仓库另外一个接缝（例如 `RulesService` 或 `sessions/graph.py` 的图节点）按四条原则过一遍。
3. **读原著对应章节**，每章一小时以内：
   - 《程序员修炼之道》Topic 12 Tracer Bullets、Topic 13 Prototypes and Post-it Notes、Topic 10 Orthogonality（正交性是 seam 的前身概念）
   - 《软件设计哲学》第 4 章 Modules Should Be Deep、第 5 章 Information Hiding、第 7 章 Different Layer Different Abstraction、第 10 章 Define Errors Out of Existence、第 11 章 Design it Twice
   - 《领域驱动设计》第 2 章 Communication and the Use of Language、第 14 章 Maintaining Model Integrity（只读 Bounded Context 与 Context Map 两节）
4. **读 `writing-for-agents/SKILL.md`**，然后拿 CLAUDE.md 做一遍 §3.3 的引导词重构练习和 §3.4 的否定检查。改不改是另一回事，练习本身就是学习。
5. **可选**：给本仓库写 `CONTEXT.md`，从 `08_session-execution-contract.md` §1 的 8 个词和 `symptom_taxonomy.yaml` 的 4 个词起步，每个加 `_Avoid_`。
