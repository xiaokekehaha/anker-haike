# 运行手册：告警、故障定位与日常运维（票 50）

配套：[发布 / 回滚 / CI](release.md)、[数据库备份 / 恢复 / 迁移 / 数据保留](database.md)、[线上部署与密钥](deploy-prod.md)、[可观测栈](../../deploy/observability/README.md)。本文面向值班人员：先看 §1 告警怎么来的、§2 收到告警怎么查，再按 §3 的风险表逐项处置。

## 1. 告警

告警在编排服务进程内计算（`orchestrator/app/observability/alerts.py`），不依赖外部告警系统；没配投递渠道时只写日志 `event=alert`，`/health` 的 `alerts` 块永远可看。

| 规则 | 触发条件（默认，环境变量可改） | 意味着 |
| --- | --- | --- |
| `model_chain_failed` | ModelRouter 整条链连续失败 ≥ 3 次（`ALERT_MODEL_FAIL_STREAK`） | 所有厂商都不可用 / key 失效 / 预算被限流耗尽；用户会看到「简化回复」或 error(recoverable) |
| `retrieval_empty_rate` | 最近 20 次知识检索中 no_match + unavailable > 50%（`ALERT_RETRIEVAL_EMPTY_RATE`，至少 10 次样本） | WeKnora 断开、tenant / kb_ver 不符，或知识库范围配错；排障会退到标准流程或 R5 |
| `queue_rejections` | 最近 60 s 全局有界队列拒绝率 > 20% 且拒绝 ≥ 5 次（`ALERT_QUEUE_REJECT_RATE`） | 并发超过 50 或上游变慢；用户看到「稍后重试」 |
| `health_check_failed` | `/health` 聚合状态连续 ≥ 3 次非 ok（后台每 60 s 探测，`ALERT_HEALTH_FAIL_STREAK` / `ALERT_HEALTH_INTERVAL_S`） | Postgres / WeKnora / 默认通道模型配置任一异常 |

- 冷却：同一规则 5 分钟内只投递一次（`ALERT_COOLDOWN_S`），期间的触发计入 `suppressed_total`；条件消失时投递一条 `resolved`。
- 投递：`ALERT_WEBHOOK_URL`（JSON，飞书 / 钉钉 / 企业微信 / Slack 都能显示 `text`）和 / 或邮件（`ALERT_EMAIL_TO` + `ALERT_SMTP_*`）。投递失败只记 `alert_delivery_failed`，不影响业务。
- 验证告警链路：把 `DEEPSEEK_API_KEY` 改成无效值起服务，发 3 条消息，几秒内 webhook 收到 `model_chain_failed`（2026-09-13 实测 4 s；测试见 `tests/test_alerts.py`）。
- 看状态：`curl -s localhost:8000/health | jq .alerts`；日志：`grep '"event": "alert"' logs/events.jsonl`。

## 2. 收到告警先做什么

1. `make health`：看哪个组件 down；`db` down 时 `/health` 本身返回 503。
2. `make logs`（或 `docker compose logs orchestrator --since 10m`）：搜 `ALERT`、`model_call`（看 `attempts[].error`）、`knowledge_search`（看 `status`）、`model_queue_full`。
3. 判断是**上游**（模型厂商 / WeKnora）还是**我们**（配置、容器、数据库）：上游问题以 §3 对应行的降级为主，不回滚；配置 / 镜像问题按 [release.md §3](release.md#3-回滚) 回滚。
4. 处置后确认 `resolved` 到达，`/health.alerts.active` 为空。

## 3. 风险处置表（对应 04 §1 稳定性表每一行）

| 风险 | 现象 | 定位 | 处置 |
| --- | --- | --- | --- |
| 模型 API 超时 / 限流 / 拒答 | `model_chain_failed`；回复带「简化回复」标注；日志 `model_call.status=error`，`attempts[].outcome` 为 timeout / rate_limited / refused | `make model-probe TASK=intake ALIAS=deepseek` 逐家探测；看厂商状态页；key 是否过期 | 换主备顺序：改 `config/models.yaml` 该 task 的 chain 后 `make release` + 重启（配置与镜像成对）；key 轮换见 §4；限流持续则临时把 `queue` 容量调低避免雪崩 |
| LLM 输出不符合 Schema | 日志 `attempts[].outcome=invalid_output`，业务走降级（intake 为 calm / 空、synthesize 用默认计划） | Langfuse 或 JSONL 看 `model_call.output` | 属提示词 / 模型质量问题：走 bake-off（`make bakeoff`）后再改 prompt 版本；不在线热改 |
| WeKnora 不可用 / 无命中 | `retrieval_empty_rate`；tool_call 提示「知识库暂不可用」；`knowledge_search.status=unavailable` | `make health` 的 weknora；`make kb-verify`；容器 `weknora-app` 是否 healthy；`WEKNORA_API_KEY` / tenant 是否变 | 重启 `docker compose restart weknora-app`；知识库损坏用 `make kb-snapshot DIR=…` 回滚；期间排障自动走预写计划（standard_flow），无需人工干预 |
| 图片过大 / 格式异常 | 上传 413 / 415，不产生 run | `session_images` 无行；日志 `ImageRejected` | 属预期拒绝；用户端提示已给出，不处理 |
| 状态机死循环 | 同一会话 run 不停、步骤卡反复 | 快照 `counters`（executed / skipped / plans_exhausted）与 `steps_executed` | 出口规则 R1 / R1b / R1c / R2 已封顶；若仍异常 `POST /sessions/{id}/cancel`，必要时 `make session-delete SID=` |
| 路由不确定 / 澄清循环 | 用户连续被追问 | 快照 `clarification.attempts`；日志 `clarify` | 两次后自动 R7 升级；若频繁出现检查 `config/products.yaml` 别名与 `safety_terms.yaml` |
| 重复推进 / 重复卡片 | 前端连点；`/actions` 返回 409 | 日志 `X-Action-Replayed`；`session_actions` 表 | 属协议正常行为（幂等 + 409 附快照）；只有 `lock_timeout`（503）持续出现才看数据库连接数 |
| 内部输出串入聊天 | 用户看到 JSON / 提示词 | 事件流里 message 事件来自哪个 task（只有 reply.stream / 安抚 / 结束语 / 澄清是 user_visible） | 属代码缺陷：回滚到上一 release 并记录复现会话 |
| 429 / 限流 | `queue_rejections`；用户看到 error(recoverable) | 日志 `model_queue_full.in_flight/limit`；厂商配额 | 降并发（前端 / 反代限速 `deploy/proxy`）；厂商配额提升；短期可把队列 limit 调低让失败更早更明确 |
| 备用模型风格不一致 | 回复标「简化回复」 | `message.model_tier=fallback` | 预期降级；主模型恢复后自动消失 |
| 演示网络不稳 | 模型 / 检索大面积失败 | `/health.models`、`retrieval_empty_rate` | 切回放：`REPLAY_CASE_ID=a1_hair_wrap` 重启（`make replay-check` 先核对清单）；前端顶部出现「演示回放」徽标 |
| 会话丢失 / 断流 / 刷新 | 前端「正在恢复连接」 | `GET /sessions/{id}` 快照；`GET /sessions/{id}/runs/{run_id}/events?after_seq=` | 由前端自动恢复；服务重启后 `orphan run finalized` 日志说明孤儿 run 已收尾；投影异常用 `make sessions-rebuild ARGS="--all"` |
| 安全信号晚到 | 中途出现 R4 摘要 | 日志 `cp_in` / `safety_flags` | 预期行为（CP-in 每条文本、图片观察、备注都检查）；不处理 |
| 错误产品进入排障 | 步骤与产品不符 | 快照 `product_state` / `product_confirmed`；`knowledge_search.scope` | 用户可发「说错了，是 X」触发 rediagnose；频繁出现检查目录别名 |
| 凭证误判 | 摘要 receipt.status 与实际不符 | `receipt.confidence`、`verified_facts` / `conflicts` | 低置信自动 needs_manual_check；人工按摘要核对，不改线上判定逻辑 |
| PostgreSQL 单点 | `/health` 503；所有会话接口 503 | `docker compose ps postgres`；磁盘 | 见 [database.md §3 恢复](database.md#3-恢复)；恢复后 `make sessions-rebuild ARGS="--all"` |
| 数据保留 / 清理任务 | 磁盘涨、`retention purge failed` | 日志 `retention_purge` 每 10 分钟一条；`make retention-purge` 手动跑 | 见 [database.md §6](database.md#6-数据保留与按会话删除票-48)；人工删除请求用 `make session-delete SID=` 或 `DELETE /sessions/{id}` |

## 4. 密钥轮换

1. 线上密钥只在仓库外的 env 文件（[deploy-prod.md §1](deploy-prod.md#1-密钥管理)），模型 key 只被编排容器读取。
2. 新 key 先本机探测：`DEEPSEEK_API_KEY=<new> make model-probe TASK=intake ALIAS=deepseek`。
3. 改 env 文件 → `make prod-down && make prod-up`（或 `docker compose up -d orchestrator`）→ `make health` 全 ok → 发一条消息确认 `model_call.status=ok`。
4. WeKnora key 轮换：在 WeKnora UI 重新生成 → 改 `WEKNORA_API_KEY` → 重启编排 → `make kb-verify`。
5. `ADMIN_TOKEN`（删除接口）与反代 basic auth（`make proxy-passwd`）按同样流程；轮换后 `make scan-secrets` 确认旧值不在仓库 / 镜像。

## 5. 备份 / 恢复 / 回滚 / 清理 速查

| 事项 | 命令 | 手册 |
| --- | --- | --- |
| 备份状态 | `make db-backup-status` | database.md §2 |
| 立即备份 | `make db-backup` | database.md §2 |
| 恢复 | `make db-restore FILE=<dump>` | database.md §3（含演练记录） |
| 回滚配置 | `make rollback REL=<release_id>` | release.md §3（镜像与 config 成对） |
| 知识库回滚 | `make kb-snapshot DIR=<snapshot>` | release.md §3 |
| 清理任务 | `make retention-purge` / 日志 `retention_purge` | database.md §6 |
| 告警自检 | 无效 key 起服务发 3 条消息 → webhook 收到 `model_chain_failed` | 本文 §1 |

## 6. 回滚演练（值班人员自测清单）

按 [release.md §3](release.md#3-回滚) 独立完成一次，预期 ≤ 5 分钟：

1. `ls releases/` 找到上一版 release_id，确认它与当前运行镜像 tag 成对（`RELEASE.md` 里的 image 字段）。
2. `git status config/` 无未提交改动。
3. `make rollback REL=<id>`：脚本复制 config、重启 orchestrator、等 `/health` 200（2026-09-12 演练 2 s）。
4. 发一条 A1 消息确认出步骤卡；`curl /health | jq .alerts.active` 为空。
5. 回滚失败（重启循环）时看 `docker compose logs orchestrator`：若是配置校验报错，说明 config 与镜像不成对，先切镜像 tag 再回滚。
