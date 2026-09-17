# 发布与自动化测试报告（2026-09-17）

发布版本 `20260917-a460530`。本轮跑了六套自动化测试，含一次基线对照。
结论先说：**我引入的回归 2 个，已修复并回到基线；发现的 7 个框架级问题都不是本次引入的，是长期没人认领的欠账。**

## 1. 发布与部署

| 项 | 值 |
| --- | --- |
| release_id | `20260917-a460530` |
| commit | `a460530` → 登记于 `c5d4f9d` |
| policy_version | 2026-09-14.1 → **2026-09-17.1**（source: public_site） |
| 镜像 | `haike/orchestrator:dev` 重建两次（`6becef7` / `a460530`） |
| /health | overall ok（db / redis / weknora / models.domestic / models.zhipu，overseas unconfigured 属预期） |

容器内实测（不是只看 /health —— runbook §3 明确 config 懒加载，健康检查 200 不代表配置可用）：

```
扫地机在保        policy=us_robot_vacuum_base          auto=[parts,repair,replace]
扫地机已换过货     policy=us_robot_vacuum_base          auto=[parts,repair]
吸奶器配件过保     policy=us_breast_pump_accessory      auto=[-]
线材终身保        policy=us_cable_powerline_lifetime   auto=[parts,repair,replace]
便携储能无来源     policy=-                             nh=True ['no_policy_matched']
```

「已换过货仍能自动寄配件」这一条是本次改造最直接的业务收益：以前换过一次货的在保机器只剩转人工。

## 2. 测试结果总览

| 套件 | 结果 | 说明 |
| --- | --- | --- |
| `scripts/ci-local.sh` | **全绿** | ruff / db-check(0007) / pytest / contracts / 前端 218 项 |
| 后端 pytest | **1003 passed, 1 skipped** | 含新增边界套件 |
| `tests/test_policy_boundaries.py`（新增） | **51 passed** | 见 §3 |
| `haike-eval all` | **165/165** | symptom 40、routing 20、emotion 40、policy 50、authorization 12、commitments 3；vision 仍 pending_data |
| `make inspect` | **27/36** | 与基线持平，见 §4 |
| `haike-replay verify-all` | **0/9** | 基线同样 0/9，见 §5 |
| 发布态隔离验证 | **950 passed** | 在 `6becef7` 的独立 worktree 上单独跑，确认提交态自洽 |

## 3. 边界与约束测试（新增 51 项常驻回归）

金标 `data/eval/policy/cases.yaml` 钉的是「典型输入 → 期望结论」，钉不住边界。新增
`orchestrator/tests/test_policy_boundaries.py` 覆盖十二类：

| 类别 | 探测点 | 结果 |
| --- | --- | --- |
| 月份算术 | 闰日 2/29 +12 月压到 2/28；1/31 +24 月保持 1/31；8/31 +12 月保持 8/31 | 全过 |
| 保修期闭区间 | 当天买当天报修在保；最后一天在保；后一天出保 | 全过 |
| 终身保 | 20 年后仍在保、`warranty_end` 为 None、**不触发过保排除项**、仍可自动寄配件 | 全过 |
| 三级匹配优先级 | 部件级 30 > 系列级 20 > 品类兜底 10；系列例外压过终身保；系列+部件同时命中 | 全过 |
| 系列子串误命中 | X10 不被投影仪 `Nebula X1` 吃掉；Nano 不落进 Prime 24 月；727 不落进 Prime；系列名大小写无关 | 全过 |
| 缺参数 | 四个必填字段各自缺失 → `missing_inputs` 指名道姓 | 全过 |
| 无来源不猜 | 目录外 SKU、未知渠道、CN 购买、便携储能 → 只转人工，`warranty_end` 为空、`remedies` 为空 | 全过 |
| 契约约束 | 非法 `part_class` 在 Pydantic 层就被拒 | 全过 |
| 渠道别名 | `Anker Store` / `Amazon` / `官方` 归一 | 全过 |
| 排除项交互 | 人为损坏免费档全灭但**不转人工**（政策明确不保 ≠ 判不了）；过保只剩 `paid_repair`；非吸尘器品类无付费维修档；换过货不影响配件档 | 全过 |
| 自动办理围栏 | 五种情形下 `auto_allowed` 必须同时满足 eligible + 公司承担 + 不需人工，且永不落在 refund / paid_repair | 全过 |
| 反幻觉 | 每条处置的条款都带 `source_url`；`policy_version` 一致；同输入同 `trace_id` | 全过 |
| 配置校验器 | 十二类非法配置必须被拒：未知来源、缺原文引用、零/负/非法月数、未知匹配键、非法处置、悬空条款、未知条件、条款无出处、同优先级交叠、退款自动办理 | 全过 |

## 4. 场景巡检：基线对照

用 `git worktree` 在改动前的 `3503c76` 上跑了一次基线，避免把既有失败算到本次头上。

| | 基线 `3503c76` | 本次改动后 | 修复后 |
| --- | --- | --- | --- |
| 通过 | 27/36 | 25/36 | **27/36** |

**我引入的 2 个回归**（已修，`a460530`）：`l3_idempotent_execution`、`l3_backend_faults`，
均为 `AuthorizationDenied: 写操作授权门未通过`。根因是
`orchestrator/app/inspection/l3_scenarios.py::valid_gate()` 里的 `region_purchase='CN'`
没跟着政策改 US。上一轮扫 CN 夹具只扫了 `tests/`，漏了 `app/inspection/`。

**基线就在失败的 9 个**（与本次无关，长期挂着）：

| 场景 | 失败原因 |
| --- | --- |
| cannot_do_x3 | 连续三次 cannot_do 后没有 awaiting_input，直接收尾 |
| safety_mid_text | 中段安全词应走 rediagnose，实际 intake → escalate |
| wrong_device_receipt | 凭证设备不符时不出待输入卡 |
| low_confidence_order_hit | 低置信订单命中时不出待输入卡 |
| disconnect_refresh_after_feedback | 反馈后断线重连未重放 |
| all_models_down | 模型全挂时应按原文出卡，实际不出 |
| vague_input | 模糊输入直接回「无法完成这次理解」 |
| product_ambiguity | 同名多品类不出产品卡 |
| two_clarifications_then_r7 | 两次澄清后应判 R7，实际为 None |

这 9 个里 `wrong_device_receipt` / `low_confidence_order_hit` / `cannot_do_x3` 是同一类
（该出待输入卡而没出），值得一起查。

## 5. 回放包：9 个全部失效，基线亦然

`haike-replay verify-all` → `{"failed": [全部 9 个], "total": 9}`。基线同样 0/9。

漂移原因（recorded → current）：

- `prompt_ver`：interpret `2026-09-14.8` → `2026-09-17.1`、clarify `2026-09-13.1` → `2026-09-15.1`、vision `2026-09-14.1` → `2026-09-15.3`
- `models_ver`：`2026-09-13.5` → `2026-09-15.2`
- `kb_ver`：`2026-09-12.1` → `2026-09-17.3-fc326dc6345e`
- `policy_version`：`2026-09-14.1` → `2026-09-17.1`（本次新增的一行）
- `a9_vision`：manifest 根本不存在，包没录过

也就是说这套「断网重放核对」的防线已经全线失效一段时间了，本次只是在已经断掉的链条上又加了一环。

## 6. 给明天的框架 / 架构迭代输入

按影响排序。前三条是结构性的，不补的话越往后越贵。

### 6.1 发布链路比对的是工作树，不是 commit

`scripts/release.sh` 用 `cp -R config releases/$REL/config` 快照**工作树**，`release_id`
却取 `git rev-parse HEAD`。`scripts/release-check.sh` 也是拿清单比工作树。

后果在本次实测到了：`20260917-a460530` 的快照里 `plans.yaml` 是 `2026-09-17.2`
（另一条未提交任务线的中间状态），而 commit `a460530` 里是 `2026-09-17.1`。
release-check 报绿，因为它根本不看 commit。

而 `releases/<id>/config/` 正是 `make rollback` 的素材，runbook §3 又特别强调
「镜像与 config 必须是同一 release 的成对物」，错配的失败形态还很隐蔽
（/health 200、容器 healthy，只有走到对应节点的请求才 `error/node_failed`）。

**建议**：release.sh 从 `git archive HEAD config/` 取快照而不是 `cp -R`；工作树脏时
显式警告或拒绝；release-check 增加「快照 vs commit」一致性断言。

### 6.2 release-check 漏校验 policy_version 与 actions_version

RELEASE.md 的冻结版本表里有这两项，`release-check.sh` 的检查列表里没有。本次把
policy 从 `2026-09-14.1` 改到 `2026-09-17.1`，漂移检查完全抓不到。

**建议**：清单里列了什么，检查脚本就该校验什么，最好由同一份字段表驱动，避免两边手工同步。

### 6.3 巡检与回放不在 CI 里，失效无人认领

`make inspect` 27/36 和 `replay verify-all` 0/9 都是长期状态，CI 只跑 ruff / pytest /
contracts / 前端。结果是：巡检的 9 个失败变成了「常态」，回放包全线失效也没人发现。

**建议**：至少把 `make inspect` 接进 CI 并锁一个基线通过数（低于基线即失败），
比「全绿才能合」现实、比「完全不跑」有效。回放包要么定期重录，要么明确降级为手工工具。

### 6.4 政策夹具散落三处，改一次要同步三处

本次改区域，`tests/`、`app/inspection/`、`data/eval/` 三处都有硬编码的
`region_purchase='CN'`，我漏了 `app/inspection/` 那处，直接变成回归。

**建议**：抽一个共享夹具（如 `tests/fixtures/policy.py` 或 `app/inspection` 复用测试夹具），
让「一个典型可办理的政策输入」只有一处定义。

### 6.5 bake-off 与 models.yaml 脱钩

models 从 `2026-09-13.5` 升到 `2026-09-15.2` 已有两天，bake-off 报告没重跑，
`release-check` 每次都报这一条，然后每次都被忽略。这是典型的「长期红灯脱敏」。

**建议**：要么把它降级为 warning 并记入 RELEASE.md，要么补跑。长期红着最糟。

### 6.6 多 agent 并行下缺少文件归属机制

本次全程与另一条任务线共用工作树。表现出来的具体成本：

- 提交时需要手工拆 hunk（`test_conversation_l3.py` 里两条任务线的改动混在一起）
- 发布快照无法区分归属（6.1）
- 跑全量测试时无法判断失败归属，只能开 worktree 跑基线对照

**建议**：并行任务各自开 `git worktree`，而不是共用一棵工作树；或至少在 CLAUDE.md 里
把「按目录划分任务线」写成硬约定。

### 6.7 政策层本身的下一步

不算框架问题，但影响演示能力：

- 非 US 区域（CN / EU / UK）现在一律转人工。要恢复跨区域演示能力，需要主办方 SOP 或补采各站政策页。
- 4 个品类（便携储能 / 家用储能 / 婴儿监视器 / UV 打印机）公开页查不到，同样转人工。
- P1 整块未做：两条受理路径（30 天无理由 vs 质保）、SN 采集、凭证必填化、换货收货地址、
  不保清单 9 条、受理五分类。其中「受理五分类」直接对应评分五难点里的「分流」。
