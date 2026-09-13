# 开发完成情况独立验收

> **后续状态：已按用户授权完成同步并继续验收，旧部署阻断已解除。最新结论见 [同步后验收报告](post-sync-report.md)。下文保留为同步前的原始证据。**

验收日期：2026-09-13；源码基准：`4abcd4e`（开始时工作树干净）；运行环境：本机 Docker Compose，服务 `http://127.0.0.1:8000`。

## 结论

**核心源码与自动化回归已基本就绪，但不能认定“全部开发和交付验收完成”；当前运行环境不具备演示条件。**

50 张票的文档状态为 **47 done、2 done-with-gap（32/42）、1 in-progress（40）**。这只是票面统计，不是 47 张票全部经过本轮逐条实机验收的证明。完成状态索引的“只有外部输入缺口、代码侧无阻塞”和巡检的“可冻结”，均不足以代表项目整体完成。

## 本轮实际执行结果

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| 后端 `uv run pytest -q` | 432 / 432 通过 | 44.39 s，无跳过；包含可连接本机 Postgres 的集成测试 |
| 前端 `npm test` | 123 / 123 通过 | 15 个测试文件 |
| 契约 `make contracts-test` | 62 / 62 通过 | Pydantic / Schema 等 |
| 生成器 `npm run test:codegen` | 6 / 6 通过 | 漂移、生成稳定性等 |
| `make contracts-check` | 通过 | Schema 与前端生成物一致 |
| `make lint` | 通过 | 后端 Ruff |
| `npm run build` | 通过 | 包含 TypeScript 检查；有 JS chunk >500 kB 非阻断提示 |
| `uv run haike-db check` | 通过 | database=0003，head=0003 |
| stub 巡检 | 29 / 29 通过 | 5 并发通过率 100%；[独立报告](inspection/latest.md) |
| A1 / A2 / A3 录制包重放 | 3 / 3 通过 | 模型/知识无 miss、无缺失事件、无 errors；日志见 replay-a1.log / replay-a2.log / replay-a3.log |
| 当前 8000 服务 A1 live 巡检 | **0 / 1，失败** | `run_started → progress → error → done`，没有步骤卡；[独立报告](live/latest.md) |
| 当前 `/health` | HTTP 200，业务 degraded | db/redis/weknora 正常；domestic 只有 DeepSeek ready，overseas 无 ready provider |

模拟模型与录制包成功不证明真实图片识别准确率、真实多厂商故障切换或真实负载时延达标。A3 回放日志的 OCR 四字段均 unreadable，之后流程可以继续，故不能以该回放证明真实订单自动识别成功。

## 阻断与缺口（按处理优先级）

### 1. P1：运行环境是旧镜像配新配置，真实对话立即失败

对当前服务创建新会话并执行内置真实 A1 巡检，快照 `last_error.code=node_failed`、stage=intake。容器日志已定位到 `RulesConfig` 无法识别当前规则配置的 `pre_step`，Pydantic 报 `extra_forbidden`。

版本比对证据：

- 容器 `app/sessions/graph.py` SHA256：`9b81d592014f0d738f57b6854bc4262d05d16c16843f0a5eced1430ff4d87176`。
- 当前源码对应 SHA256：`9561c37687dcbd29fcfccf955be59f047f494c47da9d01bd5b25dcc8a1353369`。
- 容器缺少 `app/guide/steps.py`、`app/retention.py`、`app/observability/alerts.py`、`app/inspection/cli.py`。
- 当前网页 JS 为 `index-B82VHpwr.js`；本轮源码构建为 `index-B68Q7dAN.js`，前端同样未同步。

**处理要求：**将当前源码构建成匹配配置的镜像并部署，重新执行真实 A1–A3 及恢复/取消/中途纠正验收。仅重启旧镜像不能解决代码缺失。此次验证没有部署或修改业务代码。

### 2. P2：票 32 仍有内部实现差异，不能统称只缺外部标注

[票 32](../2026-09-12_smart-service-tech-design/issues/32-diagnose-synthesize-plans-ranked.md)第 15、25 行已注明两处差异却勾选完成：

- 原要求文本检索与读图并行，当前 `vision → retrieve` 串行（graph.py:1711）。先做图片安全检查有其理由，但须正式调整验收要求，不能直接等同原要求完成。
- 原要求补检索整轮 ≤3 s；当前第二轮直接 `await _search_round(...)`（graph.py:1030–1033），没有整轮 3 s 硬超时。适配器 8 s 超时和 run 总 deadline 不能证明该项达标。

此外，人工标注的改写开关对照报告尚缺；已有 bake-off 记录显示 `query.rewrite` 字段准确率为 0%，主要因严格同义词校验拒绝结果。当前 `config/retrieval.yaml` 开关保持 false，这是已关闭的未达标能力，不能算已通过启用验收。

**处理要求：**实现时限约束；对串行方案明确做需求变更或补回并行；完成标注与真实改写对照后再决定启用。

### 3. P2：真实视觉验收与第二厂商评测未完成，部分“缺 key”说明已经过时

- 票 40 明确 in-progress：真实 A3 订单截图识别及低置信提示未验收；票 30 虽 done，也把真实故障照片验收留到后续。
- 票 42 缺至少两家厂商的真实主备评测，当前只有 DeepSeek 实测证据。
- 最新 `models.yaml` 已将 DeepSeek 配成视觉候选，并放入 `diagnose.vision` / `warranty.receipt_ocr` 链；bake-off findings 已报告 DeepSeek 合成图 OCR/vision 实测。因此“真实 OCR 必须等另一个视觉 key”不应继续作为唯一阻塞理由；需要真实样本和实际端到端复验。

依据：[模型评测发现](../2026-09-12_smart-service-bakeoff/findings.md)、票 30 / 40 / 42、config/models.yaml:25、38、43。本轮仅核对既有评测记录，没有重新进行完整付费模型评测。

### 4. P2：发布冻结清单仍是旧演练版本

根目录 `RELEASE.md` 仍记录 `drill-b`、Git `d13c7fa`、`models.yaml=2026-09-12.2-bad`、TBD=9、无回放包。当前源码模型版本已为 2026-09-13.1，三个回放包也已存在。当前发布清单不能用于识别或回滚本次交付版本。

票 49 的“CI 失败阻止合并”还注明需要管理员配置分支保护；本轮未查询远端设置，故该项未验证，不能据本地 workflow 存在宣称已生效。

**处理要求：**实际部署验证后重新生成匹配 Git / 镜像 / 配置 / 回放包的正式发布清单，核实远端 CI 与分支保护。

### 5. P2：巡检“可冻结”判定范围过宽

`orchestrator/app/inspection/report.py:147` 仅判断 `summary['failed']` 是否为空就输出“可冻结”。分组运行也会进入同一判定，未检查完整场景集、live 验收或票 32/40/42 的外部缺口。因此 29/29 stub 通过仅能证明已运行模拟场景通过。

**处理要求：**把该结论限制为本次已执行巡检集，或增加冻结所需完整场景与真实环境门槛；项目验收不能直接引用这一自动结论。

## 验收边界与建议

本轮盘点了 50 张票的状态，执行全部现有自动化回归、数据库版本检查、三条离线回放，并抽查关键实现和真实部署。没有重新执行所有历史手工项目（HTTPS/限速、破坏性备份恢复、故障停机、真实图片质量评测、远端 CI/分支保护、完整浏览器交互与生产负载测试），这些不能标成本轮已验收。

建议给 Claude 的完成判定改为：**核心代码回归通过，等待部署同步、票 32 差异处理、真实视觉样本和双厂商评测、正式发布清单更新后再验收交付。** 首先处理旧镜像与新规则配置不兼容，因为它已阻断当前正常对话。
