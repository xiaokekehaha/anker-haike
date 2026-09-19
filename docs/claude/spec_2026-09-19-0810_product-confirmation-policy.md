# 产品确认何时先问：策略与实现方案

起因：对比会话 934ad3145dad4e3bb21834540219d01b（吸奶器，未出产品卡，直接问症状）与
fbd1d02a5f7a43ffb8630ee2d01ef741（S1 Pro，出产品卡等用户选）。问题：是否应当一律先确认产品再继续。

## 结论

不是「一律先确认」，而是：**答案能改变下一步时才问；问就用一次点选；永远不做闸门。**

- fbd1d 出卡正确。「S1 Pro」同时命中吸奶器与扫地机，品类不定则没有任何适用计划，不问无法前进。
- 934ad 不出卡也正确。吸奶器两款 SKU（S1 Pro、E10）在计划库里只有 `category:breast_pump` 一张通用卡、四条通用计划，
  问型号不改变任何后续动作。它的真正弱点是首问用了 4/1 切分的是非题（见方案 C）。
- 现有规则漏掉一类场景：**品类已知、型号未知、且该品类的知识按型号分化**。今天这类会话直接落 `category_only`，
  把型号专属知识丢掉；头戴耳机没有通用卡，甚至直接 R5 结束而不问一句型号。这正是「先确认产品」直觉成立的地方。

## 两条会话的追踪

| | 934ad（吸奶器） | fbd1d（S1 Pro） |
| --- | --- | --- |
| 用户原话 | 「我的吸奶器出问题了：」 | 「我的 S1 Pro 不吸了，明天家里要来客人，急！」 |
| intake 抽取 | product_hints=[吸奶器]，symptoms=[] | product_hints=[S1 Pro]，symptoms=[不吸了] |
| 目录匹配 | 型号零命中；品类词 → breast_pump | 两个 SKU：EUFY-BP-S1-PRO、EUFY-S1-PRO，跨品类 |
| product_state | category_only | unknown + product_candidates=2 |
| 路由 | decide_symptoms 无事实 → 判别题「吸奶器能正常开机并运转吗？」（yes 侧 4 族 / no 侧 1 族） | prepare_card → product_card，pending select_product |
| 结束 | clarifying / symptom | awaiting_user / select_product |

同一句「S1 Pro 不吸了」在 09-18 16:46 的会话里选了吸奶器后走到 resolved / solved，卡片路径本身闭环正常。

## 第一性原理

1. **交付物只有一种**：一步适用、有来源、安全的操作。每个问题的正当性只有两种：答案改变下一步，或它是硬约束
   （安全 / 型号适用 / 资源 / 已执行，见 2026-09-19-0056 plan §约束 3）。
2. **型号是否硬约束由知识库决定**，不由「这是产品问题」决定。今天的分化情况：

   | 品类 | 型号专属知识（计划库 + 官方资料源） | 通用知识 | 型号对下一步的影响 |
   | --- | --- | --- | --- |
   | headphones | A3035 6 条、A3040 7 条计划，两张型号卡 | 无 | 硬约束：不知型号只能 R5 |
   | robot_vacuum | X10 Pro Omni 6 条（含 1 条与 X9 Pro 共用）计划 + 型号卡；官方资料 X10 9 篇、X9 1 篇、S1 Pro 1 篇 | 7 条计划 + 通用卡 | 有：X10 / X9 / S1 Pro 用户会拿到官方资料 |
   | power_bank | A1289 4 条专属；2 条通用计划对 A1289 `excluded_skus` | 有 | 有：A1289 与其他机型步骤不同 |
   | breast_pump | 计划无；官方资料只有 1 篇 `official_eufy_pump_suction`，且 sku_list 同时覆盖 S1 Pro 与 E10 | 有 | 无：两款型号拿到的知识完全相同 |
   | charger / earbuds / speaker / security_cam | 无 | 有 | 无 |

   注意 breast_pump 那篇官方资料：内容对两款型号一致，却标成 `scope=sku`，于是 `allowed_entries` 在 category_only 下把它过滤掉。
   这会让「先确认型号」看起来提升了精准度，真正原因是标签把品类通用的知识标成了型号专属（见方案 A 末条）。

3. **问题成本不均**：点选 < 是非题 < 开放描述。但相当多用户不知道型号（吸奶器、礼物、家人购买），
   卡片必须带「不确定 / 其他型号」出口，出口通向 `category_only`，不通向 R7。
4. **多个未知并存时的顺序**：先问单位用户成本上信息增益最大的。必须问的（症状）不能省；可选的（型号）只在有增益时问。
   934ad 里两者都未知，症状是必需的，型号无增益，所以先问症状是对的；错的是症状问题的形式。
5. **模型猜测只能排序不能决策**（沿用 issue 19「不用模型猜型号」、09 §1.1「不凭置信度强行路由」）。
   fbd1d 的「明天家里要来客人」明显指向扫地机，可以把它排前面并在文案里点出，但不能替用户选。

## 方案

### A. 产品问题三档判定（核心）

在 `app/sessions/clarify.py` 的 `decide` 里，品类确定之后、`decide_symptoms` 之前，加一个确定性判定：

| 档 | 条件 | 动作 |
| --- | --- | --- |
| T0（已有） | 目录多命中 | 出卡，候选 = 命中的 SKU（fbd1d 现状） |
| T1（新增） | 品类已知、无确认 SKU、该品类存在「分化 SKU」 | 出卡，候选 = 分化 SKU + 「其他型号 / 不确定」 |
| T2（已有） | 品类已知、无分化 SKU | 不问，`category_only` 继续（934ad 现状） |

**分化 SKU 集合** `PlanLibrary.differentiated_skus(category, symptom_codes=())`：

- 该品类下 `applies_to.scope=sku` 计划的 `sku_list`，加上通用计划的 `excluded_skus`；
- 故障卡里以 SKU 为键、属于该品类的卡；
- 知识索引（`WeKnoraKnowledgeAdapter` 启动时建的 `IndexEntry`）里 `scope=sku` 且属于该品类的条目的 `sku_list`；
- 只保留目录里 `in_scope=true` 的 SKU；
- 已有症状码时，只算与这些症状码相交的计划（`allowed_for` 已按码过滤，直接复用）。
  没有症状码时取全部。这样问出去的每个选项都对应一条会改变下一步的知识。
- **标签修正**：`sku_list` 覆盖该品类全部在范围 SKU 的知识条目，按品类通用处理，不计入分化集合，
  `allowed_entries` 在 category_only 下也放行。今天 `official_eufy_pump_suction` 就是这种情况：
  不修正它会让吸奶器被误判为分化品类，出一张没有信息量的卡；修正后 category_only 的吸奶器用户也能拿到这篇官方资料。

规则细节：

- 集合为空 → T2。集合 ≤ 6 → 出卡；> 6 → 退回现有 product 文字追问（当前数据不会触发，留作上限）。
- 用户原话已声明不知道型号（「不知道型号 / 不清楚型号 / 不确定型号 / 忘了型号」）→ 视同选了「不确定」，不出卡。
  这保住 `test_category_word_without_model_goes_category_only` 的语义：说了不知道就不再问。
- 选「不确定」→ `product_state=category_only`，`category` 取卡片所属品类，`clarification=None`。
  品类无通用计划（headphones）→ 走现有 R5，但摘要写「已询问型号，用户不确定」，结束原因说真话。
- 用户不点卡而直接发症状 → 现有 `abandoned_card` 路径 → `category_only` + 事实入账，`decide_symptoms` continue 时清零澄清计数。
  这是合法的「跳过」，不是失败澄清；现有逻辑已满足，不改计数。
- T1 与 T0 一样只出一次卡：`prepare_card_calls` / `card_id` 派生沿用。

### B. 卡片契约

- `contracts/haike_contracts`：`ProductCardItem` 加 `allow_unknown: bool`（T1 为 true，T0 为 false）与可选 `note: str`；
  `SelectProduct.payload.sku: str | None`，`None` 表示「不确定 / 其他型号」。`make contracts` 重新生成，产物随改动提交。
- `graph.py`：`prepare_card` 写 `payload.allow_unknown / note`；`await_input` 透传；`apply_action` 的 `select_product` 分支处理 `sku is None`。
- `frontend/src/components/ProductCard.tsx`：`allow_unknown` 时多一个「其他型号 / 不确定」按钮；
  标题下加一行 `note`，T1 固定为「不同型号的排查方法不同」，向用户说明为什么要问。
- 观测台 `frontend/src/admin`：`selected_sku=null` 显示为「不确定型号」。该目录正由另一会话重构，只改显示文案，不动结构。

### C. 无症状时的首问改多选（与 A 独立，可单独做）

934ad 的真正缺口。`app/conversation/taxonomy.py` 的 `next_interview`：当 interview 尚无任何回答、候选 = 该品类全部故障族、
且故障族 ≤ 6 时，直接出 `symptom_selection` 多选题，不用判别题。理由：用户什么都没说时，一道 4/1 切分的是非题期望信息量接近零，
还必然再追一问；多选一步到位，且现有确定性解析（`symptom_question_answer`）已支持。有任何事实之后仍按最小切分选判别题。

### D. 可选复杂度（本轮不做）

- **卡与症状同轮并行**：让用户既点型号又描述现象。需要双待办槽或「软卡片」，改 `pending_input` 模型、reducer 与前端；
  收益是省一轮，代价是待办语义变复杂。先用 A 的串行：一次点选成本足够低。
- **T0 按上下文预排序**：用 `TurnInterpretation.device_category` 把更可能的候选排前并在文案里点出。只排序不决策。
- **事后补型号**：T2 品类在结案或进入 L3（换货 / 退款需要 confirmed_sku）时再问。现有 `_after_product` 已按 confirmed_sku 门控 service_context，等真正需要时再补。
- **分化阈值**：T1 目前按「存在分化知识」二值判定；robot_vacuum 15 款里只有 2 款分化，若实际点「其他型号」比例很高，可加先验阈值。先观察数据。

## 涉及文件

- `orchestrator/app/plans/library.py`：`differentiated_skus`
- `orchestrator/app/faultcards/`：按品类列出 SKU 键的查询
- `orchestrator/app/sessions/clarify.py`：`decide` T1 分支、「不知道型号」短语
- `orchestrator/app/sessions/graph.py`：`prepare_card` / `await_input` / `apply_action`
- `contracts/haike_contracts/`：`ProductCardItem`、`SelectProduct`；`make contracts`
- `frontend/src/components/ProductCard.tsx`、`frontend/src/admin/format.ts`
- `orchestrator/app/conversation/taxonomy.py`：`next_interview`（方案 C）
- 测试：`orchestrator/tests/test_sessions_clarify.py`、`test_plans.py`、`test_diagnose.py`、`frontend/src/components/Cards.test.tsx`

## 验收

- 「我的头戴耳机一边没声音」→ 产品卡 [Space One, Space Q45, 其他型号 / 不确定]；选 Q45 → `hd_q45_one_side` 步骤卡；
  选不确定 → R5 摘要含「已询问型号，用户不确定」。今天：直接 R5，不问。
- 「我的扫地机器人出问题了：」→ 卡 [X10 Pro Omni, X9 Pro, 其他型号 / 不确定]；选其他 → `category_only` → 五族多选题（方案 C）。
- 「我的吸奶器出问题了：」→ 不出卡；直接五族多选题。今天：4/1 是非题。
- 「我的 S1 Pro 不吸了」→ 现有跨品类卡不变，`allow_unknown=false`。
- 「扫地机不吸了，不知道型号」→ 不出卡，`category_only`，步骤卡（现有用例保持）。
- 「扫地机不吸了」→ 卡 [X10 Pro Omni, X9 Pro, 其他型号]，因 `suction_low` 存在 X10 专属计划；若某品类的分化计划与已知症状码不相交则不出卡。
- 「我的 Anker 737 充电宝充不进电」→ 单命中 A1289，不出卡（现状）。
- 既有回归：`test_sessions_clarify.py`、`test_plans.py`、`test_faultcards.py`、`test_diagnose.py`、`test_diagnostic_loop.py`；`make lint` 清零；
  `npm --prefix frontend run typecheck`。

## 实施记录（2026-09-19，A 与 C）

已实施：

- `PlanLibrary.differentiated_skus(category, symptom_codes)`：型号专属计划的 sku_list 加通用计划的 excluded_skus，按码收窄。
- `KnowledgeScope.category_skus` 与 `covers_category`：sku_list 覆盖全品类的资料按通用处理，`allowed_entries` 在 category_only 下放行；
  `sku_scoped_skus` 给出索引里真正分化的 SKU。`knowledge_scope_of` 从目录填 category_skus。
- `knowledge.runtime.indexed_entries()`：读已加载的索引；`disambiguate` 节点在判定前 `ensure_index`，拉取失败按索引为空处理。
- `clarify.decide` T1 分支：`differentiated_candidates` 非空时带 `product_candidates` 与已知 `symptom_codes` 返回 continue → prepare_card。
- `diagnose.decision.known_symptom_codes`：从 `decide_symptoms` 抽出的症状码解析，T1 与 decide_symptoms 共用。
- `taxonomy.next_interview`：无回答、候选为全部故障族、故障族 ≤ `SELECTION_FIRST_MAX`(6) 时首问多选。
- 测试：`test_plans.py`、`test_knowledge_adapter.py`、`test_diagnostic_next_action.py`、`test_sessions_clarify.py` 各新增用例。

与 plan 的偏差：

1. **故障卡不计入分化集合。** 型号卡里的条目都指向计划；型号卡对同一计划只是 first_step 文案更具体，步骤正文来自计划证据，
   不改变下一步。按「答案改变下一步」的原则只算计划与知识索引。X10 的吸力条目因此不触发型号卡，「扫地机不吸了」保持不出卡。
2. ~~单候选不出卡，等 B。~~ B 已落地，下限改为 1；单候选卡靠「其他型号 / 不确定」出口成立。
3. ~~头戴耳机选「不确定」的 R5 文案随 B 一起做。~~ 已做，见下。

## 实施记录（2026-09-19，B）

- 契约：`SelectProductPayload.sku: str | None`；`ProductCard` 事件与 `ProductCardItem` 加 `allow_unknown`、`note`；
  `ProductCardItem` 加 `selected_unknown`。`make contracts` 已重新生成 schema 与前端类型。
- `prepare_card`：`product_state == category_only` 且有 `category` 时为型号卡（T1），payload 带 `allow_unknown=true`、
  `note=不同型号的排查方法不同`、`category`；目录多命中的 T0 卡 `allow_unknown=false`（品类未定，没有可退回的品类）。
- `apply_action`：`sku is None` → `category_only`、清空候选与澄清计数，`card_results` 记 `selected_unknown`，
  `observations` 追加「已询问型号，用户不确定；按品类通用方法继续」，随 R5 摘要一起呈现。
- 路由：`route_after_disambiguate` 只要有候选且未确认就出卡（T1 可能只有一个候选）。
- **选完产品先判症状**（顺手修的既有缺口）：之前「我的 S1 Pro 出问题了」选完型号直接走 retrieve，在没有任何现象时下发第一条计划的步骤。
  现在 `decide` 的症状判定尾段抽成 `clarify.symptom_decision`，`apply_action` 在 select_product 后复用：缺现象 → `_decision=clarify`
  → 新增边 apply_action → clarify 问一句；品类没计划 → R5。T0 / T1 / 「不确定」三种选择同一套判定。
- `POST /sessions/{id}/actions`：`sku=null` 只在 `allow_unknown` 的卡上通过，否则仍 409 `invalid_selection`。
- 前端 `ProductCard`：`allow_unknown` 时多一个「其他型号 / 不确定」按钮，`note` 显示在标题下；
  选中任一项后全部按钮禁用并标「已选择」。reducer 折叠事件时带新字段并保留 `selected_unknown`。
- 观测台复用聊天端只读 Timeline，未另改。
- 测试：`test_sessions_clarify.py` 新增三例（异响单候选卡 → 不确定 → 通用计划；头戴耳机 → 不确定 → R5 含「已询问型号」；
  跨品类卡 `sku=null` → 409），`Cards.test.tsx` 新增一例。
