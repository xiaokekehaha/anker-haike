# 人工测试指引（2026-09-13）

对象：本机 Docker Compose 环境 `http://localhost:8000`。目的：不看代码也能把 A1 / A2 / A3 三条主链路和关键边界走一遍。

---

## 0. 测试前必须先做的两件事

### 0.1 重建镜像（当前环境不重建就测不了）

现在跑着的 `haike-orchestrator-1` 是旧镜像配新 `config/`，真实对话在 intake 阶段就 `node_failed`（容器日志：`RulesConfig` 不认识规则配置里的 `pre_step`，Pydantic `extra_forbidden`）。容器内还缺 `app/guide/steps.py`、`app/retention.py`、`app/observability/alerts.py`、`app/inspection/cli.py`，前端 JS 也不是当前源码构建的。**只重启不重建无效。**

```bash
make up
```

重建后核对版本一致（两条 SHA 必须相同）：

```bash
docker exec haike-orchestrator-1 sha256sum /srv/app/sessions/graph.py; shasum -a 256 orchestrator/app/sessions/graph.py
```

### 0.2 认识 `/health` 的 degraded

顶部状态灯显示「部分服务暂不可用」＝ `/health.status=degraded`。当前原因只有一个：**模型 key 不全**（`config/models.yaml` 里 anthropic / google / dashscope 三家没 key）。db / redis / weknora 都是 ok。

- `.env` 里现有 `DEEPSEEK_API_KEY`、`ZHIPU_API_KEY`（zhipu 是容器启动之后才加的，重建后会变 ready）。
- 缺 `DASHSCOPE_API_KEY`，所以 domestic 链首位 `qwen-*` 全部跳过，实际每次调用都降到 **deepseek**；overseas 通道没有任何可用厂商。
- **这是预期状态，黄灯不影响 A1/A2/A3 测试**，只是没法验证「跨厂商降级」。

---

## 1. 服务、端口与模块清单

### 必须启动（`make up` 一条命令全起）

| 服务 | 容器 | 地址 | 作用 | 挂了会怎样 |
| --- | --- | --- | --- | --- |
| orchestrator | `haike-orchestrator-1` | http://localhost:8000 | FastAPI + LangGraph 编排，同源托管前端 | 全部功能不可用 |
| postgres | `haike-postgres-1` | localhost:5432 | 业务库 `haike` + WeKnora 库 | 会话 / 快照 / 产品 / 计划全挂 |
| redis | `haike-redis-1` | 容器内 6379 | 会话锁、幂等、SSE 流管理 | 动作幂等与并发保护失效 |
| weknora-app | `haike-weknora-app-1` | http://localhost:8080 | 知识检索 API | 检索报 unavailable，自动走预写计划（可继续测） |
| weknora-docreader | `haike-weknora-docreader-1` | 容器内 50051 | 文档解析（仅入库时用） | 不影响查询 |
| pg-backup | `haike-pg-backup-1` | — | 每日逻辑备份 | 只影响备份 |

### 按需启动

| 模块 | 启动方式 | 地址 | 什么时候要 |
| --- | --- | --- | --- |
| WeKnora 网页 | `docker compose --profile ui up -d` | http://localhost:8081 | 建 tenant / 取 API key（已配好，一般不用） |
| Langfuse 可观测 | `docker compose -f docker-compose.yml -f deploy/observability/compose.yaml --profile observability up -d` | http://localhost:3000 | 要看 trace / 延迟；需 `.env` 里 `LANGFUSE_ENABLED=true` + 公私钥。当前已在跑 |
| embedding 桩 | `cd orchestrator && uv run uvicorn --app-dir ../deploy/dev embedding_stub:app --port 8099` | http://localhost:8099 | 没有 `DASHSCOPE_API_KEY` 又要真检索时；同时要把 `EMBEDDING_BASE_URL` 指到 `http://host.docker.internal:8099/v1` 并重启 weknora-app |

### 前端页面

只有 `http://localhost:8000/` 一个单页，无子路由。模块：顶部健康灯 + 进度条、时间线（用户气泡 / 助手气泡 / 工具行）、四种卡片（ProductCard 产品确认、StepCard 排障步骤、ReceiptCard 凭证字段、SummaryCard 升级摘要）、证据抽屉、输入区（文本 / 图片上传 / 请求人工 / 取消）。

### 后端接口

```
GET    /health                                  聚合健康（db/redis/weknora/models）
GET    /health/live                             存活探针
POST   /sessions                                建会话
POST   /sessions/{sid}/messages                 发消息（multipart，可带图）→ SSE
POST   /sessions/{sid}/actions                  卡片动作（选产品 / 步骤反馈 / 确认凭证 / 请求人工）
POST   /sessions/{sid}/cancel                   取消当前 run
GET    /sessions/{sid}                          快照（刷新恢复用）
GET    /sessions/{sid}/runs/{rid}/events        断线续接
GET    /sessions/{sid}/images/{img}             取会话内图片
DELETE /sessions/{sid}                          人工删除（需 .env 配 ADMIN_TOKEN + 请求头 X-Admin-Token）
```

---

## 2. 启动与冒烟（约 5 分钟）

```bash
make up && make ps
```

```bash
make health
```
期望：`db/redis/weknora` 均 `ok`；`models.domestic.providers_ready` 含 `deepseek`（重建后应再多 `zhipu`）；整体 `degraded` 正常。

```bash
make db-check && make kb-verify
```
期望：`database=0003 / head=0003`；`kb_manual` 3 条、`kb_faq` 52 条、`kb_tickets` 200 条，状态都是 `completed`。

打开 http://localhost:8000/ ：状态灯显示「部分服务暂不可用」（黄），输入框可用。

---

## 3. 主链路人工测试

> 每条用例：**做什么 → 该看到什么**。任一条对不上就记录 session_id（浏览器地址栏或快照接口）和时间点。

### 用例 A1：排障成功（最核心，先测这条）

1. 输入 `eufy X9 Pro 扫地机不吸了，滚刷缠了很多头发`，发送。
2. 期望依次出现：
   - 助手先流式吐出一句**安抚语**（不是模板套话），进度条从 intake 往后走；
   - 一行**工具行**「检索知识库」，成功显示命中条数，失败显示「知识库暂不可用，按标准排障流程」——**两种都算通过**，失败时流程必须继续；
   - 一张**步骤卡**：标题、操作说明、预期结果，可能有 ⚠ 注意事项和「来源 N」角标。
3. 点步骤卡「来源」角标或悬停 → 证据抽屉展开，能看到知识片段出处。
4. 点 **「解决了」** → 期望：助手给结束语，进度条到完成态，不再出新步骤卡。

### 用例 A2：产品消歧

1. 新开页面（刷新即新会话），输入 `我的 S1 Pro 不吸了`。
2. 期望出现**产品确认卡**，两个候选：`eufy S1 Pro 扫地机器人`（在服务范围）和 `eufy S1 Pro 吸奶器`（应有范围外标记）。
3. 选 **扫地机器人** → 期望进入检索 → 步骤卡，和 A1 后半段一致。
4. 反向测一次：新会话同样输入，选 **吸奶器** → 期望走 R8 范围外，给出转人工 / 说明，不下发排障步骤。

### 用例 A3：多步未解决 → 凭证 → 升级

1. 新会话输入 `eufy X10 Pro 扫地机不吸了，滚刷缠了很多头发`。
2. 步骤卡连续点 **「还没解决」**，重复到系统要求上传凭证（最多 8 轮；中途进度条应切到升级/凭证阶段）。
3. 到凭证阶段：输入区提示变成「请上传订单截图…」，出现三个跳过选项（没有凭证 / 看不清 / 稍后再提供）。
4. 上传一张订单截图（真实截图最好）+ 点「上传凭证」。
   - 期望出现**凭证卡**，列出订单号 / 渠道 / 购买日期 / 金额四个字段，识别不出的显示为空或低置信提示，**字段可手工编辑**。
   - ⚠ 已知缺口：票 40 仍是 in-progress，真实订单截图的自动识别**没有验收过**；回放包里四个字段全是 unreadable。字段全空属于已知问题，**手工改完能继续就算这一步通过**。
5. 确认字段 → 期望出现**升级摘要卡**：故障描述、已做过的步骤、凭证结论（渠道是否在授权名录）、后续动作。摘要内容应与前面实际发生的一致，不能凭空编造。
6. 另测一次跳过分支：在第 3 步直接点「没有凭证，跳过」→ 期望照样给出升级摘要，只是凭证结论写明未提供。

---

## 4. 边界与异常（挑着测）

| 用例 | 操作 | 期望 |
| --- | --- | --- |
| 安全升级 | 首句就发 `机器冒烟了` | 立刻 R4 升级转人工，**不检索、不出步骤卡** |
| 排障中途安全词 | A1 到步骤卡后，输入框发 `刚才有焦糊味` | 中断排障转升级 |
| 模糊输入 | 首句 `这个又不行了` | 追问品类 / 型号，不检索 |
| 追问上限 | 连续两次仍答不清品类 | R7 升级，摘要里记录澄清经过 |
| 中途纠正型号 | A1 到步骤卡后输入 `说错了，我的是 X10 Pro` | 重新判断故障、重新出卡；**旧步骤卡的按钮点下去应报冲突并被忽略，计数不变** |
| 请求人工 | 任意时刻点「请求人工」 | 立即 R3 摘要，忽略当前卡片校验 |
| 刷新恢复 | 反馈提交后刷新页面 | 时间线完整重建，不丢事件、不重复 |
| 取消 | 助手正在出字时点「取消」 | 当前 run 停止，页面可继续对话 |
| 重复点击 | 步骤卡按钮连点两次 | 只推进一次 |
| 知识库断开 | `docker compose stop weknora-app`，再走 A1；测完 `start` 回去 | 工具行显示「知识库暂不可用，按标准排障流程」，**仍然出步骤卡** |
| 图片排障 | 发故障照片 + 文字 | 助手观察内容体现在回复里；含冒烟等危险特征应转 R4 |
| 新建会话 | 发一条消息后点工作区右上「新建会话」 | 页面回到空白欢迎态；下拉里旧会话仍在。运行中 / 有待输入卡片时先弹确认，确认后先取消 run 再清空 |
| 切换会话 | 新会话再发一条，然后在「切换会话」下拉选回第一条 | 时间线、阶段条、待输入卡片按快照恢复；再切回第二条同理。列表只存本浏览器（localStorage，最多 20 条，48 h 后本地丢弃） |
| 切到过期会话 | 用 `make retention-purge HOURS=0` 清掉服务端会话后再从下拉切换 | Toast「该会话已过期或已删除」，该项从下拉消失，页面回到空白 |
| 新标签页 | 复制地址开新标签 | 是空白新会话（当前会话按标签页隔离），但下拉里能看到所有最近会话 |

---

## 5. 不通过浏览器的验证

```bash
make inspect
```
29 个 stub 场景一条命令跑完（幂等、安全、恢复、并发等），结果回填 `docs/planning/2026-09-12_smart-service-implementation/findings.md`。**注意**：它的「可冻结」结论只看失败列表是否为空，不代表整体验收通过。

```bash
make inspect LIVE=http://127.0.0.1:8000
```
追加一条打真实模型的 A1。**这条现在是失败的（0/1）**，重建镜像后应转为通过——这也是判断 0.1 有没有修好的最快方式。

```bash
make replay-verify CASE=a1_hair_wrap
make replay-verify CASE=a2_disambiguate
make replay-verify CASE=a3_receipt_channel
```
断网重放录制包。三条都应通过，但它只证明事件流形状正确，**不证明真实模型效果**。

```bash
make test && npm --prefix frontend test
```
后端 432、前端 123，应全绿。

---

## 6. 出问题怎么定位

```bash
docker compose logs -f --tail=200 orchestrator
```

- 页面一直转圈 / 立刻报错 → 先看容器日志有没有 `node_failed`，再回到 0.1 确认镜像是否重建。
- 步骤卡不出 → 看工具行状态与 `/health` 的 weknora；检索挂了也应出卡，不出卡是 bug。
- 卡片按钮点了没反应 → 多半是 409 版本冲突（旧卡），页面应有提示；无提示是 bug。
- 想看某会话全貌：`curl -s localhost:8000/sessions/<sid> | python3 -m json.tool`。
- 事件明细：`logs/events.jsonl`。

---

## 7. 已知不可能在本轮测出来的

1. **跨厂商降级**：缺 dashscope / anthropic / google key，链条实际只有 deepseek（+zhipu）。
2. **真实凭证 OCR 准确率**（票 40 in-progress）与**真实故障照片识别**（票 30 未用真实样本验收）。
3. **票 32 两处实现差异**：文本检索与读图当前是串行而非并行；补检索没有整轮 ≤3 s 硬上限。检索改写开关 `config/retrieval.yaml` 保持关闭。
4. **发布清单**：根目录 `RELEASE.md` 还是 `drill-b` 旧演练版本，不能用于回滚本次交付。
5. 远端 CI 分支保护、HTTPS 反代 / 限速、破坏性备份恢复演练，都不在本指引范围内。

详细依据见 `docs/planning/2026-09-13_completion-verification/report.md`。
