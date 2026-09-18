# 诊断链路的回退：候选放宽与配置闭合性

日期：2026-09-18　范围：`orchestrator/app/diagnose/decision.py`、`orchestrator/app/plans/library.py`、
`config/plans.yaml`；改动 C 涉及 `orchestrator/app/conversation/{interpret,reduce}.py` 与 `sessions/graph.py`，单开一轮。

起因会话：`37cea3ff86574d05a162adf53bca34d3`（2026-09-18 17:47–17:48，7 轮，0 步骤，R2）。

## 1. 问题

### 1.1 这一次的实际链路

checkpoint（`next_action` / `observation_requests` / `symptom_codes` 通道）逐轮：

| 轮 | 用户 | 决策 | 结果 |
| --- | --- | --- | --- |
| 3 | 是的，很慢 | `ask / observation_changes_next_action` | 问 `pb_737_display`（题目由 `pb_737_output_check` 声明，5 个选项） |
| 4 | 设备不在身边 | `pause / operation_conditions_unavailable` | 被 `explicit_operation_reply` 截成 `device_missing`；该题的 `unknown` 选项没被采纳，请求记为 `status=unparsed` |
| 5 | 连接笔记本时显示 UVP／屏幕显示异常 | `ask / operation_conditions_recheck` | 观察事实写入成功（`option_id=laptop_uvp`），但 `device=false` 仍在，回问"设备现在在身边了吗" |
| 6 | 已在 | `handoff_offer / knowledge_coverage_missing` | `skipped=[output_check: excluded_by_observation, display_reset: excluded_by_observation]`，候选为空 → R2 |
| 7 | （重发同一句） | 同上 | 同一结论，只新增 escalation card rev2 |

关键事实：库里有专门承接这个答案的计划 `pb_737_laptop_uvp`（`requires_observations: pb_737_display=[laptop_uvp]`），
它从未进入候选集。原因是症状码门槛：

```
会话 symptom_codes = ['pb_no_input']            # 只来自事实；问诊收敛出的「指示灯异常」没有进来
pb_737_laptop_uvp.symptom_codes = [pb_no_output, pb_indicator_abnormal, pb_port_damage]

allowed_for(power_bank, ANKER-A1289, ['pb_no_input'])  -> [output_check, display_reset]   # laptop_uvp 被过滤
observation_gate({pb_737_display: laptop_uvp}):
    output_check  -> excluded      display_reset -> excluded      laptop_uvp -> ok（但不在集合里）
```

`decide_symptoms` 的 `_answer_codes`（decision.py:50）在候选 family 数 ≠ 1 且没有 selection 答案时返回空，
所以问诊收敛出的 `["充电宝自身充不进电","指示灯异常"]` 只剩事实那一个码进了 `symptom_codes`。

### 1.2 这不是孤例

`/admin/api/sessions`（2026-09-14 起，140 个会话，多为自测）：

```
escalated 37 | resolved 2
R2 14（零步骤 3）  R4 6（零步骤 5）  R5 4（零步骤 4）  R7 5（零步骤 5）
R8 6 / R6 2 属正常出口（范围外、保修）
```

R2+R4+R5+R7 = 29，占升级的 78%，其中 17 次一步排障都没发出去。历次复盘的根因各不相同
（ce6 缺判别问题→R7、r7 旧编码覆盖 narrowed→R7、safety 计划原文含「焦味」→R4、视觉否定清单→R4、
f30 两步 EXHAUSTED→R2、0f8809 资源信号吃掉观察答案、37cea3 本次），**形状一致**：某个闸门把集合清零 → escalate。

### 1.3 结构原因

```
facts ─► symptom_codes ─► allowed_for(∩codes) ─► constrain_plans(∩) ─► observation_gate(排除) ─► step_unavailable(排除) ─► ∅ ─► escalate
                                                                              ▲
                                        effective_exhausted（全链路唯一一处「加回来」）┘
```

1. 六道闸门只做交集与排除，唯一的恢复是 `effective_exhausted`（operation_conditions.py:215），只覆盖 `cannot_do`。
2. 失败只有终态语义：R1/R2/R4/R5/R7 全部汇入 `escalate → summarize`，没有"这一层假设错了，回上一层换条路"的中间态。
   `trace.skipped` 记了排除原因，但不参与决策。
3. 决策权分散在 `explicit_operation_reply` / `decide_symptoms` / `decide_next` / `prepare_step` / `reduce`，
   上游能吃掉下游需要的输入（轮 4）。
4. 配置与决策没有闭合性校验：`plans.yaml` 只校验"选项被某个计划声明过"，没校验"回答这个选项后还有路可走"。

## 2. 改动 A：候选被排空前必须先放宽（decision.py）

### A0. 已在工作区、未提交的部分

另一会话的工作区改动已经落了阶梯的第一级（`decide_next` 的 `unlocked` / `candidates`）：

```python
for p in library.allowed_for(category=category, sku=sku)          # 不再按 codes 过滤
if p.requires_observations and ...
and (not codes or set(codes).intersection(p.symptom_codes)
     or p.observation_gate(option_ids)[0] == "ok")                # 明确观察可解锁症状码之外的计划
```

这一段单独就能修掉 1.1 的死路（`laptop_uvp` 计划重新进入候选）。本 spec 不重复实现它，
只接着把"放宽"变成结构而不是一处特判。

### A1. 放宽阶梯

`decide_next` 里把候选构造抽成一个带级别的函数，`handoff_offer` 只能在阶梯走完后返回：

| 级别 | 放宽的门槛 | 保持不变 |
| --- | --- | --- |
| `strict` | —（现状：ranked ∩ constrain_plans + 观察解锁） | 全部 |
| `observation` | 症状码门槛：以已知观察作为唯一门槛取计划 | 风险、资源、已执行、已耗尽 |
| `confidence` | `SWITCH_CONFIDENCE`(0.3) 置信度下限 | 同上 |
| `category` | SKU 级 → 品类通用计划兜底 | 同上 |

只放宽"推测性门槛"（症状码、模型置信度、SKU 收窄）。**不放宽**：`allowed_operations` 安全限制、
`step_unavailable`（资源/阻塞）、`execution_history` 去重、`effective_exhausted`。

### A2. 可观测与文案

- `NextAction.trace` 增加 `relaxed_level` 与每级被排除的原因；`guide_trace` 记一条 `candidates_relaxed` 事件。
- `handoff_offer` 的 reason 要能区分两种情况，摘要与前端文案分开：
  - `knowledge_coverage_missing`：阶梯走完仍无候选 → "这条现象当前资料没有对应步骤"。
  - `no_supported_followup`：有候选但都已执行/耗尽 → 现状文案。
- 观测台 Journey 页把 `relaxed_level` 显示出来，否则放宽会变成又一处看不见的隐式行为。

### A3. 回归

`orchestrator/tests/test_diagnostic_loop.py`（`decide_next` 的现有回归在这里）：

1. 复现 37cea3：codes=`['pb_no_input']` + 观察 `laptop_uvp` → 必须返回 `step`（`pb_737_laptop_uvp.s1`），不是 `handoff_offer`。
2. 阶梯边界：所有候选都因资源不可用被挡 → 仍是 `pause`，不能靠放宽绕过资源限制。
3. 阶梯到底：构造一个没有任何同品类计划的观察答案 → `handoff_offer/knowledge_coverage_missing`，且 `relaxed_level == "category"`。

## 3. 改动 B：加载期闭合性校验（plans/library.py）

### B1. 规则

`load_plans_config` 现有校验只到"`requires_observations` 指向的观察与选项被声明过"。补一条：

> 一个**被用作路由门槛**的观察（它的 `observation_id` 出现在任一计划的 `requires_observations` /
> `excluded_by_observations` 里），它的每个 `kind=finding` 选项，都必须至少有一个计划满足：
> ① 与声明该观察的计划同 category 且 SKU 面有交集；② `observation_gate({obs: option})` 不是 `excluded`；
> ③ 症状码覆盖声明计划的入场码（`set(declaring.symptom_codes) <= set(consumer.symptom_codes)`，
> 声明计划无症状码时跳过 ③）。否则报 `PlansError`。

③ 是关键：没有它就抓不到 1.1——`laptop_uvp` 有承接计划，但那个计划接不住把用户带进这道题的症状码。

只对"被用作路由门槛"的观察生效：`rv_power_supply` 的 `dock_power_light` / `dock_contacts` /
`charging_indication` 是纯记录型步骤观察，没有任何计划按它路由，不受此约束。

### B2. 伪代码

```python
routed = {cond.observation_id
          for p in cfg.plans
          for field in ("requires_observations", "excluded_by_observations")
          for cond in getattr(p, field)}
for declaring in cfg.plans:
    for obs in declaring.observations():
        if obs.observation_id not in routed:
            continue
        for option_id in obs.finding_ids():
            known = {obs.observation_id: option_id}
            if not any(
                c.applies_to.category == declaring.applies_to.category
                and _sku_overlap(c.applies_to, declaring.applies_to)
                and c.observation_gate(known)[0] != "excluded"
                and set(declaring.symptom_codes) <= set(c.symptom_codes)
                for c in cfg.plans
            ):
                problems.append(
                    f"{declaring.plan_id}.{obs.observation_id}={option_id} 没有可承接的计划："
                    f"回答该选项后同面计划全被排除或症状码接不住"
                )
```

`_sku_overlap`：两边都是 `category_generic` → True；一边 SKU 级 → 另一边必须覆盖它的 `sku_list`
（`category_generic` 且未 `excluded_skus` 掉，或 SKU 清单有交集）。

### B3. 现存配置的唯一命中

当前库里只有 `pb_737_display` 是路由门槛观察，四个 finding 选项中 `laptop_uvp` 不合格：

```
声明计划 pb_737_output_check.symptom_codes = [pb_no_output, pb_no_input, pb_indicator_abnormal, pb_port_damage]
承接计划 pb_737_laptop_uvp.symptom_codes   = [pb_no_output,              pb_indicator_abnormal, pb_port_damage]
                                                            ^ 缺 pb_no_input
```

改法：给 `pb_737_laptop_uvp.symptom_codes` 补 `pb_no_input`。语义成立——用户报"自身充不进电"、
且接笔记本时显示 UVP，属同一台 737 的功率协商问题，该计划的 s1（用仅输出的 USB-C2 验证）正是下一步。
`normal` / `low_current` → `output_check`，`abnormal` → `display_reset`，两者症状码已覆盖，无需改。

注意：`config/plans.yaml` 当前有另一会话未提交的改动（给 `abnormal` 选项补 `phrases`），落地时按行合并，不要整文件覆写。

### B4. 回归

`orchestrator/tests/test_plans.py`：

1. 真实 `config/plans.yaml` 加载通过（补完 `pb_no_input` 之后）。
2. 参数化坏配置：删掉 `pb_737_laptop_uvp` 的 `pb_no_input` → `PlansError`，消息里带 `pb_737_display=laptop_uvp`。
3. 纯记录型观察（`dock_power_light`）不触发该校验。

## 4. 改动 C（下一轮）：本轮输入的单一仲裁点

现状：`explicit_operation_reply` 在语义理解之前按整句匹配短语表，命中即视为操作信号。
于是判别题自己提供的选项"设备不在身边或无法判断"被当成资源信号，题目那一轮记 `unparsed`（37cea3 轮 4，
同一个洞在 0f8809 已出现过一次）。`has_operation_context` 已经打过一次补丁来收窄触发面，方向对但不够。

设计方向：本轮输入先进一个 resolver，按"当前有哪些未决问题"（判别题 / 观察题 / 资源题 / 业务题）决定这句话归属谁，
确定性短语只在其归属的 pending 上生效。影响面是 `interpret.py` / `reduce.py` / `graph.py::route_entry` 三处，
与 A、B 无依赖，单开一轮做，先写 planning 目录。

## 5. 不做

- 不改历史会话数据、不重写已发布的摘要。
- 不引入让模型自由生成操作步骤的"规划 agent"：步骤原文仍只能来自审核过的计划库。
  真要在管道空转时接入受限搜索，是 C 之后单独评估的事。
- 不放宽安全限制、资源限制与去重；本 spec 的"放宽"只针对症状码、置信度、SKU 收窄这三道推测性门槛。

## 6. 现状

本轮只出文档，未改代码。A0 描述的那一级已在工作区（另一会话，未提交），A1–A3、B、C 均未实现。
