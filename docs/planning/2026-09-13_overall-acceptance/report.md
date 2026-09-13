# 整体功能验证与完成情况盘点

验证时间：2026-09-13 09:06–09:25（CST）
源码基准：HEAD `4abcd4e` + 41 项未提交工作区改动
运行环境：本机 Docker Compose，`haike/orchestrator:dev`（09:19:03 由在途任务重建），服务 `http://127.0.0.1:8000`

## 一句话结论

**核心业务闭环（A1 / A2 / A3、中途纠正、取消、断线续接）在真实模型与真实知识库下全部跑通，全套自动化回归通过；但仍有 1 个新发现的启动期缺陷、若干文档与实际不符，以及票 32 / 40 / 42 的原有缺口未关闭，尚不具备「全部任务完成」的结项条件。**

---

## 一、已完成并本轮实测通过

### 1.1 自动化回归（全绿）

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| 后端 `uv run pytest -q` | **452 / 452** | 42.40 s，无跳过；较上轮 434 增加模型探测相关用例 |
| 前端 `npm test` | **131 / 131** | 16 个测试文件，含新增 ModelDialog |
| 契约 `make contracts-test` | **62 / 62** | 0.14 s |
| 生成器 `npm run test:codegen` | **6 / 6** | — |
| `make contracts-check` | 通过 | Schema 与前端生成物一致 |
| `make lint`（ruff） | 通过 | — |
| `npm run build` | 通过 | 含 tsc；有单 chunk 581.56 kB 的非阻断提示 |
| `haike-db check` | 通过 | database=0003 head=0003 |
| `make inspect`（stub 巡检，票 45） | **29 / 29** | first_visible p95=18 ms，card_ready p95=24 ms |
| 录制包重放 a1 / a2 / a3（票 43） | **3 / 3**，exit 0 | model_misses / knowledge_misses 均为空 |

> 注意：三条录制包在 09:12 被重新录制为 `models_ver=2026-09-13.2`。在此之前，配置升到 .2 而录制包仍是 .1，`make replay-verify` 会直接以 `replay_incompatible` 失败——**模型配置每次改版都必须重录回放包**，否则演示兜底手段失效。

### 1.2 真实服务六组场景（票 05–08、20–25、34–41）

用 `live_acceptance.py` 打真实 HTTP 服务，真实模型 + 真实 WeKnora，未注入 fake router、未开回放：

| 场景 | 结果 | 关键证据 |
| --- | --- | --- |
| A1 排障成功 | 通过 | evidence=ok、同 action_id 重发幂等、final_stage=done，6.9 s |
| A2 产品消歧 | 通过 | 产品卡 → 选择 → 步骤卡 → done，5.2 s |
| A3 凭证与升级 | 通过（范围受限） | 四字段 unreadable → 手工确认 → `channel_in_directory` 摘要，13.8 s |
| 中途补充与纠正（票 37/23） | 通过 | 旧动作返回 `stale_version`；「烧焦」命中 R4 立即升级，摘要保留已执行步骤 |
| 取消 run（票 38） | 通过 | done(cancelled) → active_run 清空 → 请求人工成功 |
| 断开后续接（票 08） | 通过 | after_seq 续接 118 个事件，seq 无重复，反馈后正常完成 |

A3 用的仍是 1×1 白图，**只证明低置信容错与人工确认通路，不证明真实截图 OCR 准确率**。

### 1.3 浏览器实机（票 02/06/21/28/34/36）

- A1 全流程：10 条知识来源 → 滚刷清理步骤卡 → 点「解决了」→ 已解决 + 结束语 → 输入区恢复。
- 步骤卡下方「补充新情况或纠正」入口（票 37）正常展示。
- 整个流程 **console error 为空**。

### 1.4 本轮新增能力（不在 50 票内）

模型连通性弹窗（`docs/planning/2026-09-13_model-connectivity`）已上线并实测：

- `GET /models/status` 列出当前通道 8 个模型；`POST /models/{alias}/probe` 直连探测。
- 实测：deepseek-flash **1171 ms**、glm-4.7 **1390 ms**、glm-4.6v **327 ms** 均已连通；qwen-* 报「未配置 / 缺少密钥」并跳过。
- 弹窗与 curl 共享 5 分钟缓存，显示检测时刻，行为正确。

### 1.5 票 42 本轮实质推进

智谱已完成真实 bake-off（`reports/bakeoff/bakeoff.md`），`config/models.yaml` 升到 `2026-09-13.2`，domestic 各链链尾换成实测达标的智谱位。**「只有一家厂商 key」这一说法已经不成立。**

---

## 二、未完成 / 未达标

### 2.1 ~~票 40 凭证识别~~ —— 报告写完后已提交为 done

提交 `95d0ece`（09:35，晚于本报告正文）补上了真实视觉验收：15 张合成订单图 × 3 遍，deepseek-flash 与 glm-4.6v 均 Schema 100% / 字段 100%；真实服务端到端 A3 上传订单截图 → OCR 1.3 s → 四字段全对、逐字段置信度 0.97–0.98 → L1–L6 判 `order_verified`；把 DeepSeek key 置为无效后由 glm-4.6v 接手，四字段同样全对。

本报告第一章的 A3 仍是白图路径，**本轮我没有独立复验这段真实截图证据**，采信的是该提交的记录。

### 2.2 票 42 bake-off —— 已提交为 done，但票面结论与自动裁决互相矛盾

提交 `95d0ece` 完成了智谱实测并修正四处真实缺陷（`glm-4.7-flash` 不存在改 `glm-4.5-flash`；智谱静默忽略 `json_schema`，`structured` 改 `json_object`；补 `thinking: disabled`；guide.step 的 glm-4.7 实测 89% < 90% 换 glm-4.5-flash），models.yaml 冻结为 `2026-09-13.2`，并实测了把 DeepSeek key 置为无效后整链切智谱可完成 A3。这部分是扎实的。

**但同一提交生成的 `reports/bakeoff/bakeoff.md` 裁决段，对 9 个 task 里的 7 个写着「无来自另一家厂商的达标备用位（§3.8 要求主备至少两家）」**，与票 42 勾选项里「7 个两家均达主模型门槛、满足 §3.8」的结论直接冲突。

原因已定位：`bakeoff/runner.py:130-142` 的备用位判定除 schema / accuracy 外，还要求 `latency_p50 ≤ 主模型 × latency_ratio_max`，而 `config/bakeoff.yaml:10` 的 `latency_ratio_max: 1.5`。以 intake 为例，glm 1951 ms / deepseek 968 ms = 2.02 > 1.5，于是 schema 100% / 准确率 99% 的智谱位仍被判不够格当备用。

需要决策：要么放宽（或按 task 分档）延迟比并记录理由，要么承认这 7 个 task 的备用位未达标、把票面说明改回来。两份文档不能一个说满足、一个说不满足。

另外 `query.rewrite` 仍是两家都 0%（票 32 的词表问题，开关默认关闭）。

### 2.3 票 32 plans_ranked —— 三处差异原样未动

- `graph.py:380` `_after_product` 仍是 `vision → retrieve` **串行**，未实现原要求的读图/检索并行。
- `graph.py:1031` 第二轮补检索直接 `await _search_round(...)`，**没有整轮 ≤3 s 硬上限**，只有 `min_remaining_for_second_round_ms` 的前置闸门。
- `config/retrieval.yaml` 仍是 `2026-09-12.1`，`query_rewrite.enabled: false`；人工标注对照报告未做。这是 README 盘点里唯一承认的剩余缺口。

### 2.4 本轮未重做的验收项

票 46（HTTPS / 生产入口 / 访问控制）、票 47（破坏性备份恢复演练）、票 49（远端 CI 与分支保护）均未在本轮实际验证，不能据本地文件存在宣称生效。

---

## 三、遗留问题（按优先级）

### ~~P1~~ 已修复 — 会话运行时启动期异常，票 08 的重启孤儿收尾实际从未执行

容器每次启动都打出：

```
ERROR sessions.runtime session runtime unavailable: KeyError: 'seq'
```

链路已定位清楚：

1. `manager.py:153` 用 `max(e["seq"] for e in prior)` 直接取值。
2. 业务库 `session_events` 里有 **4 条 `run_started` 事件的 `event_json` 缺 `seq` 字段**（`session_id` 属于 09-11/09-12 的集成测试，`run_id` 为 `r1`），命中即抛 `KeyError`。
3. 异常被 `runtime.py:63` 的兜底 `except` 吞成一行 error 日志，于是 `reconcile_orphans()` 中断、`session runtime ready` 日志从不打印——**服务重启后遗留的 active run 不会被收尾成 `error → done(error)`，票 08 的这一条在本机环境是失效的**。

顺带暴露：集成测试直接往业务库 `haike` 写数据且不清理，`sessions` 表里已积累一批 `run-0` / `run-b` / `run-active` 的测试残留行，`active_run_id` 长期非空。

建议：`e.get("seq", 0)` 容错 + 单条孤儿失败不阻断整体循环；集成测试改用独立库或加清理。

### ~~P2~~ 已修复 — 快照 `last_error` 残留导致成功后仍弹错误提示

`2026-09-13_step-feedback-error` 已完成诊断但未修复，本轮复核代码原样：

- `snapshot.py:203` 从全部历史事件提取 `last_error`，后续成功运行不清理。
- `reducer.ts:156` 把快照里的 `last_error` 直接当成当前错误，且 `message: ''`、`recoverable: true`，前端因此回落到默认文案「出现了一个错误，可以稍后重试」。

结果：一个会话只要历史上失败过一次，之后每次成功反馈拉快照都会重新弹出错误提示。本轮浏览器用的是全新会话，未触发，但缺陷仍在。

> **2026-09-13 10:35 已修复并实测**：
> - `manager.py` 的 `reconcile_orphans` 改从事件表的列取 seq / run_id / type（不再读 `event_json`），并对单个会话加 try/except 隔离；重新部署后启动日志为 `session runtime ready (orphan runs finalized: 26)`，再次重启为 `finalized: 0`，26 条积压孤儿一次性收尾。
> - `snapshot.py` 把错误挂到所属 run，只暴露最近一次 run 的错误；`LastError` 增补 `message` / `recoverable`，`reducer.ts` 的 restore 分支改用真实文案。原问题会话 `d99223bb…` 的 `last_error` 已变为 `null`，`repro_snapshot.py` 由 AssertionError 转为 exit 0，浏览器恢复该会话不再弹错误。
> - 回归：后端 454/454、前端 132/132、契约 62/62、codegen 6/6、巡检 29/29、回放 3/3、真实六场景 6/6。

### P2 — 发布清单与实际部署再次不一致（票 49）

| 项 | RELEASE.md / 报告 | 实际 |
| --- | --- | --- |
| models.yaml | 2026-09-13.1 | **2026-09-13.2** |
| bake-off 报告抬头 | models.yaml 2026-09-13.1 | 内容已是 .2 的评测 |
| 镜像 tag | `haike/orchestrator:20260913-4abcd4e-sync-085548` | **`haike/orchestrator:dev`**（09:19 重建） |

当前清单无法用于识别或回滚本次运行的版本。

### P2 — 告警只到日志，且健康灯长期误报

- `/health` 的 `alerts.sinks=[]`，未配置 webhook / email，票 50 的外部通知不能算上线。
- `health_check_failed` 规则**一直处于 active**（`streak=13`，已 fired 3 次、抑制 8 次），根因是 `/health` 因缺 dashscope / anthropic / google key 恒为 `degraded`——而 deepseek + 智谱实际可用、业务全部通过。这是持续误报，会淹没真实告警。
- 页面健康口径同样过粗（模型项按「配置齐全度」判定）。新上线的模型弹窗提供了真实连通性视角，建议让 `/health` 的模型项也改用「当前通道是否至少一家可调用」。

### P3 — 其他

- `kb_ver` 仍是 `2026-09-12.1+stub-embedding-1024`，真实 embedding 召回质量未验收（票 26/27）。
- 前端产物单 chunk 581.56 kB（gzip 175 kB），超过 500 kB 提示阈值，未做代码分割。
- 工作区 41 项改动全部未提交、未推送；本次运行的镜像无法仅凭 HEAD 复现。

---

## 四、票面状态对照

50 张票的**文档状态**在本报告正文写完后发生变化：提交 `95d0ece` / `2381a4f` 把票 40、42 改为 done，现为 **49 done / 1 done-with-gap（32）**。按本轮实测，这个统计需要这样读：

- **实测支撑充分**：01–08、13–14、19–25、28–29、31、33–39、41、43、45（回归 + 真实场景 + 浏览器均覆盖）。
- **实测支撑部分**：09–12、17–18、26–27、30、44、48（本轮只经自动化与间接证据，未做真实故障照片、真实负载、保留策略到期等专项）。
- **明确未达标**：32。40 / 42 已于 09:35 提交为 done（证据见 2.1 / 2.2），其中 42 的票面结论与自动裁决仍需对齐。
- **本轮未验证**：46、47、49（生产入口 / 恢复演练 / 远端 CI）。
- **50 票外新增**：模型连通性弹窗，已实测通过。

---

## 五、建议的收口顺序

1. ~~修 `reconcile_orphans` 的 `KeyError`~~ —— 已完成（2026-09-13 10:35）。**仍待处理**：集成测试直写业务库 `haike` 且不清理，建议改用独立库或加清理，否则残留行会继续累积。
2. ~~修快照 `last_error` 口径~~ —— 已完成（2026-09-13 10:35）。
3. 重新生成匹配 `2026-09-13.2` / 实际镜像 tag 的 RELEASE.md，并同步 bakeoff.md 抬头（P2）。
4. 收敛 `health_check_failed` 误报，`/health` 模型项改按真实可调用判定；给 alerts 配一个实际 sink（P2）。
5. 票 42：对齐票面结论与 `bakeoff.md` 裁决——决定是调整 `latency_ratio_max`（并记录理由），还是承认 7 个 task 的备用位未达标。
6. 票 32：补整轮 3 s 硬上限；串行方案要么改回并行，要么正式做需求变更。
7. ~~票 40：真实订单截图端到端识别验收~~ —— 提交 `95d0ece` 已记录完成（本轮未独立复验）。
