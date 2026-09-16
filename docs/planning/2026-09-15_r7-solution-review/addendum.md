# 发布与部署记录（2026-09-16）

本文追加记录发布动作，不修改原有 plan / implementation。

## 提交

- `da6bbb3` fix(diagnose)：共同计划约束、问诊进展预算、摘要补齐（含 `test_diagnostic_next_action.py` 16 项）
- `5b23054` docs(spec)：可审计引用评估稿（与本任务无关，顺带入库）
- `72d3e58` chore(release)：登记 `20260916-5b23054`，快照 `releases/20260916-5b23054/config/`

## 发布前检查

| 项 | 结果 |
| --- | --- |
| ruff | 通过 |
| 后端 pytest | 830 passed / 1 failed（`test_retention.py` 的库存量数据问题，见下） |
| contracts-check + 契约单测 | 通过，94 项 |
| 前端单测 / 构建 | 207 项通过，构建成功 |
| `make release-check` | bake-off 一项红：报告基于 models.yaml 2026-09-13.5，当前 2026-09-15.2。**上一版发布时已存在**，需要 `make bakeoff` 重跑 |

## 部署

- `make up` 重建 `haike/orchestrator:dev` → `bd888c00f00b`；上一版 `bc0a6d901735` 已打 tag `before-r7-decision-20260916`，回滚可直接改 tag 重启。
- `make health`：db / redis / weknora / models.domestic / models.zhipu 全 ok；overseas 未配置（预期）。`/health/live` = ok。
- `make db-backup`：haike 3.94 MB、WeKnora 1.82 MB，均 ok。

## 实机验证（新会话，未触碰历史数据）

- `ec58f77b52d34b6f99372c97829d8096`：「eufy X10 Pro Omni 启动不了 → 不能 → 不能」。第一、二轮均下发 step_card，全程无 R7。
- `fb2c48650f524723914868591bdd9696`：「清扫效果不好 → 地面有残留 → 滚刷上缠了很多头发」。三轮无 R7、无错误；但三轮都原样重复「设备按电源后能正常启动吗？」，没有回应用户新给的现象——符合「有进展就继续」的设计，但读起来像没听见，值得单独评估提问复述策略。
- 上一版 smoke 脚本复跑：症状多选路径四轮正常（「可多选」提示、两者都有），纯图片路径命中下面的 R4 误升级而中断。

## 发现的问题（均与本次改动无关）

1. **视觉负向描述触发 R4 误升级**。`1_滚刷缠绕_正常曝光.png` 三次复现一次：视觉模型写出观察项「未见冒烟烧焦鼓包漏液火花」，`config/rules/safety_terms.yaml` 的 `observation_terms` 按子串匹配到「烧焦」，直接升级安全风险并终止排障。根因是观察项匹配没有否定语义处理，而 `diagnose/vision.py` 的提示词又要求「出现冒烟 / 烧焦…时中英文各写一次」，诱导模型写出这类否定清单。
2. **`test_retention.py::test_purge_expired_sessions_real_postgres_keeps_active_and_fresh` 在本机失败**。`purge_expired` 会保留带 30 天内 case 的过期会话，断言却要求 `deleted["sessions"] == stats.sessions`。库里现有 13 个过期会话、12 个带近期 case，因此必红。在 HEAD 干净代码上同样失败，属既有断言过严。
