# 勘误与实施记录

plan.md 自开发开始保持原样，本轮实施中对方案的修正、补充和取舍记在这里。

## 2026-09-17 P0 实施

### 1. D-SR-3 的执行范围比方案写的更大

方案写的是「主区域改 US；CN 保留枚举但不再给虚构值」。实施时发现只处理 CN 是不够的：
采集到的三站政策页原文都写着保修期表是美国的（"The standard warranty period for each product
in the **United States** is listed in the chart below. Warranty durations may vary by country,
region…"），EU / UK / DE 的月数一样没有来源。

所以 `config/policy/warranty_policy.yaml` 只有 US 规则，**其余全部区域落到 `no_policy_matched` 转人工**，
不只是 CN。旧的 EU 互认用例（DE 购买、FR 使用判为可自动办理）随之消失，这是按来源该有的结果：
那条互认规则本来就是虚构的。

代价：跨区域场景的演示能力下降。补法有两条，任选其一，都要等数据：主办方 SOP，或补采
EU/UK 各站的政策页。记在 plan.md §6 开放项第 1、4 条。

### 2. sleep_earbuds 归属：从「待定」改为 18 个月

findings.md §7 把 `sleep_earbuds` 列为归属待定。复核 soundcore 政策表后改判：该表耳机侧只有一行
「Headphones | **All Series** | 18 Months」，真无线耳机、头戴耳机、睡眠耳机都在这一行内，
"All Series" 是明确措辞，不是推断。

因此无来源品类从 5 个降到 4 个：`portable_power_station`（独立政策页未采集）、`home_storage`、
`baby_monitor`、`uv_printer`。这 4 个在 `warranty_policy.yaml` 里**故意没有规则**，
判定就是转人工，文件头注写明了原因。

### 3. 过保付费维修用新 remedy 表达，不再借用 repair

方案 D-SR-4 加了 `paid_repair`。实施时把原来「`repair` + `within_warranty: false` +
`cost_bearer: customer`」那条规则整个换成 `paid_repair`，而不是两者并存 —— 同一个 remedy 值
既表示保内免费维修又表示保外付费维修，提案卡和授权门都要靠 `cost_bearer` 二次判断才能区分。

配套：`loader.py` 的「自动办理只允许公司承担的非退款方案」断言把 `paid_repair` 也列进禁止自动办理，
虽然它的 `cost_bearer: customer` 已经挡住了，显式写出来免得以后有人改成 company。

### 4. 校验器第 7 条断言确认不用改

plan.md §3.4 判断 `loader.py:55-57`（自动办理只允许公司承担的非退款方案）不用改。实施验证成立：
寄配件正是公司承担的非退款方案，天然落在可自动办理区间，不需要为它放宽规则。

### 5. 演示订单数据必须跟着改，方案漏了

方案没提 `config/backends_mock.yaml`。实施时发现主演示订单 `DEMO-X10-001` / `DEMO-S1-002` 的
`region_purchase` 是 CN，政策改成 US 之后演示主路径**全部**走到转人工，proposal_card 根本不出现
（`test_a5_proposal_execute_snapshot_rating` 直接红）。

已把这两笔改为 US（金额币种一并从 CNY 改 USD）。`DEMO-CN-003` / `DEMO-DE-004` / `DEMO-UK-005` /
`DEMO-CN-006` 保持非 US，它们现在正好演示「购买地没有可引用政策 → 如实转人工」。
order_no 里的 CN/DE/UK 是历史命名，真正的区域以 `region_purchase` 为准，文件头注说明了。

`test_a6_approval_restores_graph` 原来用 UK 订单造「需人工特批」场景，UK 已经没有政策 →
连候选方案都出不来，人工没得批。改成「US 买、DE 用」的跨区域，场景意图不变。

### 6. 两处已知规则故意没编码

- **充电器的 SKU 级例外**：官方 24 个月那一行点名了 `511 Charger (Nano 3, 30W)` 与 `Nano (30W)—A2337`。
  目录里的 A2337 名字是「Anker Nano 65W 充电器」，与官方的 Nano 30W 对不上。按 SKU 编码会把一个
  对不上的映射固化进规则，所以只编了系列名这一层（GaNPrime / AnkerPrime / Anker Prime）。
- **线材 24 个月一档**（Anker 310/322/541/542/543/544/765、Bio-Nylon、Bio-Based）：目录里没有对应 SKU，
  编了也匹配不到任何产品，只会增加无法验证的规则面。

两处都写进了 `warranty_policy.yaml` 的注释，不是遗漏。

### 7. PolicyInput 只加了三级匹配需要的字段

plan.md §3.4 列了 `series / part_class / claim_type / serial_number / has_defect_evidence /
undamaged / all_accessories / original_packaging / order_type` 九个字段，那是 P0+P1 的终态。

P0 只加了 `series` 和 `part_class`（三级匹配必需）。其余字段属于 P1 的两条受理路径与证据门槛，
现在加进来只会是没有消费者的死字段。

### 8. 评测金标整体重写，并加了两项新断言

`data/eval/policy/cases.yaml` 从 54 条 CN/DE/UK 组合用例改写为 50 条：目录 20 个品类各一条在保
+ 一条过保，加终身保线材、吸奶器配件按部件计、不保清单、跨国、缺参数、已换货、系列名直给等边界。

新增两个钉死项：
- `warranty_end` 逐条钉死 —— 有人改了保修期而没改来源引用，金标会红。
- `parts_auto` —— 寄配件这一档是本轮的核心收益，必须有独立断言。

评测运行器 `app/evaluation/cli.py` 相应扩了输出字段，并把 `reason` 加进「断言成员关系而非整列表相等」
的字段表（原来只有 `missing`）。

### 9. 提示词里的单品类写死：三处都改了，改法是去掉品类而不是注入品类

plan.md 说「三处都应改为按会话的 `category_name` 注入」。实施时改成**去掉**品类词：

- `prompts/system.py` 的 `ROLE_LAYER` 是固定文本，靠的就是 prompt 前缀可缓存（07 §12 L1）。
  注入品类会按品类把缓存前缀切成 20 份。当前设备本来就在状态层的「产品」字段里，角色层不必重复。
- `diagnose/grade.py` 的 `INSTRUCTION` 同理，产品已经在 `compose_system_prompt` 的状态层里传了。
- `prompts/guide.py` 的产品缺省值改为**省略整行**，而不是换一个中性词：随便填一个品类会让模型
  按那个品类的部件改写步骤，省略则让模型只看 `instruction_src` 原文。

`graph.py:1439` 的过时 docstring 一并更正。

## 验收结果

| 项 | 结果 |
| --- | --- |
| `make lint` | All checks passed |
| `make contracts-check` | Contract artifacts are up to date |
| 后端全量 pytest | 952 passed, 1 skipped |
| `npm --prefix frontend run typecheck` | 通过 |
| 前端 `reducer.l3.test.ts` / `events.test.ts` | 46 passed |
| 20 个品类政策判定 | 16 个给出带条款引用的处置，4 个无来源品类转人工并给出 `no_policy_matched` |

plan.md §5 的五条验收：前四条已由 `tests/test_l3_policy.py` 与 `data/eval/policy/cases.yaml` 覆盖。
第五条（30 天非质量退货走 `no_reason_return`）属于 P1 的 `claim_type`，本轮未做。

## 遗留

- P1 全部未开始：两条受理路径、SN 采集、凭证必填化、换货收货地址、不保清单 9 条、受理五分类。
- P2 中「六个新品类演示证据换真实官方锚点」与 `2026-09-17_knowledge-gap-fill` 是同一件事，由那条线负责。
- 前端 `ProposalCard` 不需要改：它渲染后端给的 `option.title`，没有硬编码 remedy 文案。
  新增的「寄送更换配件」「申请付费维修」直接可用。
