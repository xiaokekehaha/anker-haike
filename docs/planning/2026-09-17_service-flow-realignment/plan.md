# 客服流程按真实业务对齐（2026-09-17）

用户要求：仓库里的固定流程与模板要按实际公司业务流程来做；先体验线上流程，再定我们哪里改、怎么升级迭代。
本轮范围：**只出方案，不动代码**。线上实测证据见 [findings.md](findings.md)。

## 1. 问题

流程骨架（理解 → 澄清 → 排障 → 政策判定 → 提案 → 授权门 → 执行 → 跟踪 → 结案）与线上一致，2026-09-14 的 L3 系列已经把形状做出来了。**真正的缺口在内容与数据模型**：

1. `config/policy/warranty_policy.yaml` 首行写着「虚构演示，待真实 SOP 替换」，只覆盖 `robot_vacuum`。而 `config/products.yaml` 已有 20 个品类（2026-09-17 commit `349db04` 多品类落地）。政策引擎的 `defaults.no_policy_matched: needs_human` 意味着**其余 19 个品类的每一次政策判定都必然输出转人工**。独立托管率被政策层焊死在扫地机一个品类上。
2. 真实保修期是**品类 × 系列 × 部件**三级，跨度从 3 个月到终身（eufy 智能锁 18 个月但机械部件 36 个月；吸奶器 12 个月但配件 3 个月；Nebula X1 主机 2 年但随附麦克风 1 年）。现有 `applies_to: {category, region_purchase, channel}` + 单一 `warranty_months` 表达不了，补数据也补不进去。
3. 官方处置阶梯的第一档是「**提供更换配件**」，而 `RemedyDecision.remedy` 只有 repair / replace / refund / none。滚刷、滤网、耳塞套、鸭嘴阀这类最高频、成本最低、最该自动化的处置，我们现在只能升级成整机换货或转人工。
4. 官方明确写了质保受理的三个必要条件：充分购买凭证、**故障品序列号或清晰缺陷影像**、**公司必须记录买家已执行的排障步骤及结果**。第三条正是我们的核心产出；第一条我们允许跳过；第二条我们完全没有。

## 2. 前置决策

| 编号 | 决策 | 默认 | 理由 |
| --- | --- | --- | --- |
| D-SR-1 | 政策数据源：主办方 SOP 优先。SOP 未到手期间，用公开站政策作过渡数据，每条带 `source_url` + `fetched_at` + 原文片段 | 采纳 | 用户已选「主办方 SOP 优先」，但 repo 内无任何 SOP / 经销商名录 / 脱敏工单（`kb_tickets/tickets.csv` 由 `gen_tickets.py` 生成）。schema 与规则形状与数据源无关，SOP 到位只换 data 层 |
| D-SR-2 | 政策匹配键从 `category` 扩为 `(category, series_pattern, part_class)` 三级，最具体优先；`warranty_months` 支持 `lifetime` 与 `none` | 采纳 | 不改这个，findings.md §7 的真实保修期表落不进来 |
| D-SR-3 | 主区域改为 US（有完整公开来源）；CN 保留枚举但不再给虚构值，无来源时命中 `needs_human` | 采纳 | `anker.com.cn` 无消费者售后政策页，国内走电商平台。虚构 12 个月既不可引用也不可审计，与「幻觉」评分项直接冲突 |
| D-SR-4 | `remedy` 枚举增加 `parts`（寄配件）与 `paid_repair`（过保付费维修）；提案排序按官方阶梯 `parts → repair → replace_refurb → replace_new → refund_partial` | 采纳 | 官方阶梯的第一档缺失，是当前托管率最大的单点损失 |
| D-SR-5 | 新增 `claim_type`：`quality_warranty` 与 `no_reason_return` 两条互斥路径，进政策引擎前判定 | 采纳 | 线上是两套独立规则（30 天/非质量/买家承担运费 vs 保修期内/质量/公司承担）。现有唯一 refund 规则是 `quality` + 7 天，两边都对不上 |
| D-SR-6 | 受理入口做五类分流，对齐线上：产品故障 / 售前咨询 / 退换货 / 订单物流 / 反馈 | 采纳 | 「分流」是评分五难点之一；线上第一步就分流，我们默认进排障 |
| D-SR-7 | 办理动作的证据门槛升级：`proof_of_purchase: valid` + (`serial_number` 或 `defect_evidence`) 为 `replacement.create` 的硬前置；`skip_receipt` 保留但结果降级为「只能转人工」 | 采纳 | 官方三个必要条件。跳过凭证仍能推进办理是我们与真实流程最实质的偏差 |
| D-SR-8 | 采集序列号：读图抽 `serial_hint`（复用铭牌链路）+ 用户手输兜底；**不做校验位算法** | 采纳 | 官方要 SN 或清晰缺陷影像。SN 编码规则无公开来源，自造校验就是新的幻觉 |
| D-SR-9 | 换货收货地址作为 `replacement.create` 必填参数，用卡片收集 | 采纳 | 线上表单明写「若申请换货寄到此地址」，缺了执行不了 |
| D-SR-10 | 不保清单 9 条落成 `exclusions` 规则，效果分三种：`no_free_remedy` / `needs_human` / `offer_paid_repair` | 采纳 | 现有只有 3 条；「正常损耗」「电池容量衰减」「过保」是真实工单里最高频的拒付理由 |
| D-SR-11 | `EscalationSummary` 增加 `troubleshooting_record`，字段按官方口径（步骤、指令原文、客户反馈结果、时间戳、证据 ID），可直接作为工单附件 | 采纳 | 这是我们已有能力，只欠一个对齐的输出口径；也是本产品对真实业务最硬的价值点 |
| D-SR-12 | `config/plans.yaml` 六个新品类的演示证据 ID（`manual_pb#c12` 等）必须替换为真实官方文章锚点 | 采纳 | 否则多品类是「有流程无依据」，与「可审计引用」的既有投入自相矛盾。接 `2026-09-17_knowledge-gap-fill` 那条线 |
| D-SR-13 | 会话身份（邮箱）**不引入** | 采纳 | 线上 Live Chat 用邮箱+姓名做会话准入，但那是为了转邮件工单。演示环境引入实名会带来脱敏与合规负担，收益只有「案件可跨会话查」，而我们已有 `case_id` |

## 3. 目标数据模型

### 3.1 政策规则（`config/policy/warranty_policy.yaml`）

```yaml
# 三级匹配，最具体优先：part_class > series_pattern > category
- policy_id: us_anker_power_bank_prime
  priority: 20
  source:
    url: https://www.anker.com/policies/refund-policy
    fetched_at: 2026-09-17
    quote: "Anker GaNPrime / Prime / MagGo Power Bank — 24 Months"
  applies_to:
    category: power_bank
    series_pattern: ["GaNPrime", "Prime", "MagGo"]   # 缺省匹配全部
    part_class: main_unit                             # main_unit / battery / mechanical / accessory / cable
    region_purchase: [US]
    channel: [official_store, platform_store, authorized_dealer]
  warranty_months: 24        # 或 lifetime / none
```

`part_class` 是新维度，用来表达「主机 18 个月、机械部件 36 个月、配件 3 个月」。品类级兜底规则 `priority: 10`，系列级 20，部件级 30。

### 3.2 两条受理路径

```yaml
claim_types:
  no_reason_return:                 # 30 天无理由
    window_days_from_purchase: 30
    requires: [undamaged, all_accessories, original_packaging]
    excludes: [bulk_order_ge_10, gift_item, crowdfunding, mystery_box]
    cost_bearer_shipping: customer
    refund_scope: product_price_only
    remedy: refund_full
  quality_warranty:                 # 质保
    within_warranty: true
    claim_window_days: 90           # 开单后 90 天内提交
    requires: [proof_of_purchase, serial_or_defect_evidence, troubleshooting_record]
    remedy_ladder: [parts, repair, replace_refurb, replace_new, refund_partial]
    replacement_warranty: max(remaining_original, 3_months)
```

### 3.3 不保清单

| 条目 | effect |
| --- | --- |
| 正常老化磨损、电池容量衰减、颜色变化 | `no_free_remedy` |
| 无有效购买凭证 | `needs_human`（先让客户补，补不出才拒） |
| 丢失或被盗 | `no_free_remedy` |
| 已过保修期 | `offer_paid_repair`（RoboVac / HomeVac / Vacuum）或 `no_free_remedy` |
| 非质量问题超过购买后 30 天 | `no_free_remedy` |
| 赠品与促销品 | `no_free_remedy` |
| 第三方维修或改装、使用非核准部件 | `no_free_remedy` |
| 外力损坏、误用（跌落 / 极端温度 / 进液 / 不当操作） | `needs_human`（可能有延保覆盖意外损坏） |
| 非授权经销商购买 | `needs_human` |
| 跨国携出或国际转运 | `needs_human` |

「误用」与「跨国」判为 `needs_human` 而不是直接拒付：前者可能落在付费延保的意外损坏范围内，后者线上口径是"void"但实务上有例外，两者都不该由 AI 单方面拒绝。

### 3.4 校验器的硬阻塞点

`orchestrator/app/policy/loader.py::validate` 现有 7 条断言，其中 6 条会直接挡住本方案。换真实政策数据之前必须先改这里，否则 `ConfigError` 起不来：

| 行 | 断言 | 冲突 |
| --- | --- | --- |
| [loader.py:27](../../../orchestrator/app/policy/loader.py:27) | `policy.get("source") != "demo"` 就报错 | **换成真实 SOP 或公开站来源会直接启动失败**。需改成来源白名单 + 每条必须有 `source_url`/`fetched_at` |
| [loader.py:35](../../../orchestrator/app/policy/loader.py:35) | `applies_to` 必须恰好是 `{category, region_purchase, channel}` | 三级匹配落不进来 |
| [loader.py:37](../../../orchestrator/app/policy/loader.py:37) | `warranty_months` 必须为正整数 | 终身保（Anker 多款线材）与「不保」表达不了 |
| [loader.py:39-46](../../../orchestrator/app/policy/loader.py:39) | 交叠检测只比 category / region / channel 三键 | 三级匹配后需要改成按 specificity 判定，品类兜底与系列特例本来就该交叠 |
| [loader.py:58-60](../../../orchestrator/app/policy/loader.py:58) | `remedy` 只允许 repair / replace / refund | 挡住 `parts` 与 `paid_repair` |
| [loader.py:61-66](../../../orchestrator/app/policy/loader.py:61) | `effect` 只允许 allow / needs_human / no_free_remedy | 挡住 `offer_paid_repair` |
| [loader.py:55-57](../../../orchestrator/app/policy/loader.py:55) | 自动办理只允许公司承担的非退款方案 | **不用改**。寄配件正好是公司承担的非退款方案，天然落在可自动办理区间内 |

`PolicyInput`（[models.py](../../../orchestrator/app/policy/models.py)）需要新增：`series` / `part_class` / `claim_type` / `serial_number` / `has_defect_evidence` / 商品状态三项（`undamaged`、`all_accessories`、`original_packaging`）/ `order_type`（bulk、crowdfunding、gift）。

`data/eval/policy/cases.yaml` 现有 54 条用例全部基于旧 schema，需整体重写。

## 4. 落地顺序

### P0 — 政策层可用（不做则多品类演示等于没做）

| 项 | 改动面 |
| --- | --- |
| 政策 schema 三级化 | `config/policy/warranty_policy.yaml`、`orchestrator/app/policy/{loader,engine,models}.py`、`data/eval/policy` 回归 |
| 20 个品类真实保修期入表 | findings.md §7 的三张表；公开来源覆盖 15 个品类，缺 `portable_power_station`（独立政策页未采）、`baby_monitor`、`home_storage`、`uv_printer`、`sleep_earbuds` 归属待定，这 5 个显式标 `source: unknown` 并走 `needs_human` |
| 区域主键改 US，CN 去虚构值 | `config/policy/regions.yaml`、`warranty_policy.yaml` |
| `remedy` 加 `parts` / `paid_repair` | `contracts/haike_contracts/common.py` → `make contracts` 重新生成前端类型；`app/sessions/l3.py:21` 的 `REMEDY_TITLES` 与提案排序 |
| 清掉提示词里残留的单品类写死 | 见下 |

多品类在 `349db04` 落地，但三处提示词仍写死扫地机，20 个品类共用：

- [system.py:17](../../../orchestrator/app/prompts/system.py:17) `ROLE_LAYER`：「负责扫地机器人的故障排查、产品确认与升级转人工」——每一轮回复都带这句。
- [grade.py:74](../../../orchestrator/app/diagnose/grade.py:74) `INSTRUCTION`：「下面是用户对扫地机器人故障的描述……」——检索片段相关性打分被品类词误导，直接影响非扫地机品类的召回质量。
- [guide.py:23](../../../orchestrator/app/prompts/guide.py:23) 步骤改写的产品缺省值 `'扫地机器人'`。

三处都应改为按会话的 `category_name` 注入，未知品类用中性表述。`graph.py:1439` 的 docstring 说「本期仅支持扫地机」也已过时（`out_of_scope_text` 实际按目录 `in_scope` 产品线生成），顺带更正。

### P1 — 受理合规（对齐官方三个必要条件）

| 项 | 改动面 |
| --- | --- |
| 两条路径分流 `claim_type` | 政策引擎 + `PolicyInput` + 提案层 |
| SN 采集（读图 + 手输） | `contracts` 新字段、`app/sessions/graph.py::vision`、`config/vision_vocab.yaml`、新增待输入卡 |
| 凭证必填化，`skip_receipt` 降级 | `app/sessions/receipt.py`、`config/actions.yaml` 的 `requires` |
| 换货收货地址 | `config/actions.yaml`、新增卡片、`replacement.create` 参数 |
| 不保清单 9 条 | `config/policy/warranty_policy.yaml` 的 `exclusions`、`config/policy/clauses.yaml` |
| 受理五分类 | `app/sessions/graph.py::understand`、`config/rules/intent_terms.yaml` |

### P2 — 真实资料与输出口径

| 项 | 改动面 |
| --- | --- |
| `troubleshooting_record` 对齐官方口径 | `app/escalation/summary.py`、`contracts` |
| 六个新品类演示证据 → 真实官方锚点 | `config/plans.yaml`、`data/knowledge/sources/anker_official.yaml`，走既有 `kb-official-fetch → build → ingest → verify` 管线 |
| 自助入口对标（订单追踪 / 发票 / 配件 / 保修注册） | 评估是否纳入演示动作集，还是只作为 L3 快路径的答复内容 |

## 5. 验收

- 政策引擎对 20 个品类各构造一条在保 + 一条过保用例，`needs_human` 只允许出现在 5 个 `source: unknown` 品类与不保清单命中的场景；其余必须给出带条款引用的处置。
- 每条政策判定输出的 `clauses` 能回链到 `source_url` + `quote`，无来源的条款不允许出现在用户可见文本里。
- 「滚刷坏了」这类配件问题，提案首选必须是 `parts` 而不是 `replace`。
- 无凭证 / 无 SN 且无缺陷影像时，`replacement.create` 的授权门必须不通过。
- 30 天内非质量退货用例走 `no_reason_return`，不进保修期判定。

## 6. 开放项

1. **主办方 SOP、经销商名录、脱敏工单何时到手**。到手后 §3 的 data 层整体替换，schema 不动。若赛前拿不到，演示需明示政策数据来自公开站并标注采集日期。
2. **portable_power_station 的独立政策页**（`anker.com/anker-portable-power-station-warranty-policy`）本次未采集；若该品类要进演示需补。
3. `baby_monitor` / `home_storage` / `uv_printer` / `sleep_earbuds` 四个品类在三站政策表里都找不到对应行，需要确认是归入某个现有行还是本就不在售后保修范围。
4. 中国区政策无公开来源。若演示面向国内评委且要展示 CN 场景，需要主办方提供国内三包口径。
