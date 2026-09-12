# 实现阶段发现

## 环境
- 2026-09-12 起本机通过 colima + docker CLI + compose 插件具备 Docker，票 01 全部验收项已在本机实测通过。
- /health 整体 status 在默认通道 key 不全时为 degraded（deepseek 就绪但 dashscope / zhipu / anthropic 缺 key）。属预期；若演示前只想用 DeepSeek，需在票 09 评估「通道就绪」是否应改为「至少一个 provider 就绪」。

## WeKnora v0.8.0 与设计文档的差异
- 设计（票 01）只列 orchestrator / postgres / weknora-app / redis 四个容器；WeKnora app 的 compose 声明 `depends_on: docreader (service_healthy)`，文档入库依赖 docreader 的 gRPC 解析服务，因此 Compose 增加 `weknora-docreader`。
- WeKnora 官方 postgres 镜像是 `paradedb/paradedb:v0.22.2-pg17`（含 pgvector 与 pg_search），本项目沿用该镜像，用初始化脚本额外建 `haike` 库给编排服务，与 WeKnora 的 `WeKnora` 库分开。
- WeKnora Web UI（获取 tenant API key 用）放在 profile `ui`，默认不起。

## 票 05 会话骨架
- AsyncPostgresSaver 要求连接 `autocommit=True, prepare_threshold=0`；同一个池给业务表用时，多语句 SQL 会被 psycopg 拒绝（cannot insert multiple commands into a prepared statement）。规则：所有 DDL / 迁移逐条执行，票 47 做迁移工具时沿用。
- 内存存储的单测没有暴露上述问题，只有连真实 Postgres 才复现。约定：涉及数据库的票，集成测试用与运行时完全相同的连接参数，并至少跑一次本机真实链路。
- 本机 orchestrator/.venv 解析到 Python 3.14，而 Dockerfile 用 3.12-slim；镜像构建是 3.12 兼容性的实际把关点。
- httpx ASGITransport 不触发 lifespan，测试通过 app.state 注入内存存储与 InMemorySaver；B 的模型注册也在 lifespan 内，因此单测不依赖模型 key。

## 票 07 快照与投影
- LangGraph checkpoint metadata.step 在同一 thread 上跨 run 单调递增（含输入 checkpoint 的 step -1 起算），可直接作为契约 version 的来源，无需自维护计数器。异常 run 仍会写入输入 checkpoint，version 会 +1。
- session_events 一开始外键到 sessions 并级联删除，与「投影表可丢弃后重建」矛盾；已去掉外键。规则：事件日志与 checkpoint 不得依赖任何投影表。
- 事件协议里没有用户消息事件，timeline 的 user_message 只能来自 checkpoint 状态；节点在写 messages 时必须带 run_id，否则无法定位到 timeline 位置。后续改图状态的票需保持这一约定。

## 票 08 续接
- 票 05 把 run 写成请求内的生成器，客户端断开会触发 finally 取消图任务，违反 08 §7；票 08 改为 RunManager 后台执行。规则：任何长任务不得与 HTTP 响应生命周期绑定。
- httpx ASGITransport 会把 SSE 响应整体收完再返回，不能模拟「收到首帧即断开」；断连 / 中途续接语义要直接驱动 RunManager 或在真实 uvicorn 上用 curl --max-time 验证。
- 实时广播在进程内存，orchestrator 目前单副本；多副本部署前需改 Redis pub/sub 或粘性路由，已在票 08 记录，票 46 / 49 评估。

## 票 38 取消
- LangGraph 没有「节点边界取消」原语；取消 asyncio 任务会中断当前节点，状态停在上一个 checkpoint。这与 08 §7 的意图一致（部分工作丢弃、可继续），但意味着 apply_action 这类有副作用的节点必须以 action_id 幂等（08 §3 已要求），否则取消恰好落在副作用之后、checkpoint 之前会重放副作用。
- 票 13/14 接 ModelRouter 时：CancelledError 必须直接向上抛，不能进入重试链，否则「取消不再计费重试」不成立。
- 手测脚本里 `wait` 不带参数会等 nohup 的服务进程，导致误判卡死；后续脚本记录后台 curl 的 pid 单独 wait。

## 票 20 三段式等待
- LangGraph 中断语义（实测）：prepare 节点只执行一次；含 interrupt 的节点在恢复时从头重跑并重发自定义事件；`interrupt()` 所在节点的 checkpoint 不提交，中断后 metadata.step 停在上一节点；节点内 `get_config()["metadata"]["langgraph_step"]` 等于中断后推导出的 version。
- AsyncPostgresSaver 的 checkpoint 写入相对 astream 的 updates 流是异步的：在收到 `__interrupt__` 那一刻 `aget_state` 可能还是上一个 checkpoint。凡是「事件里的 version 必须等于 run 结束的 version」的场景，version 要在节点内确定并随载荷带出，不能在运行器中途查库。内存 saver 测不出这类竞态，数据库相关票必须带真实 saver 的测试。
- 图结构一变（加节点），依赖 progress 序列 / version 数值的测试全部要改，包括其他会话的测试（B 的 test_rules）。约定：改 graph.py 的人负责同步跑全量后端测试并修期望；后续测试尽量断言相对关系而非绝对 version。

## 票 22 幂等与锁
- 重放的事件流来自 session_events 的 jsonb，键序与首次实时发送不同；比较必须按语义（解析后相等），前端也不得依赖字段顺序。
- 会话锁持有到 run 结束是 08 §4 的要求，但意味着第二个动作可能等到接近 run deadline；若演示中体验不佳，可改为「锁只覆盖校验 + 启动，run 期间由 active_run 守卫返回 run_active」——这是产品决策，记入票 23 讨论。
- 用 `async with` 风格的锁在「响应返回后仍需持有」的场景要手动 `__aenter__/__aexit__`，并用 handoff 标记决定由谁释放；本票第一版漏了 409 分支释放，靶向测试（短超时 + 409 后再动作）才抓出来。
- 再次出现并行会话改同一文件（store.py）。约定升级：动手前在票面写 Owner 与目录边界；看到目录已有 Owner 的会话不得写入。

## 票 22 / 23 动作协议
- 会话锁持有到动作 run 结束，Postgres 实现独占一条池连接（默认池 10）：并发活跃动作数不能超过池余量，否则后续请求在 getconn 上等待直至 lock_timeout。演示规模足够；多副本或高并发前改 Redis lock（08 §4 允许），已记入票 46 / 49 评估项。
- 「复用 action_id 重试」的真实语义不是重发 Command(resume)：resume 时 await_input 已消费 interrupt 并提交 checkpoint（version 前进），失败发生在 apply_action。此时 checkpoint 无中断、`next=('apply_action',)`、状态里留有 last_action。服务端据此识别同 action_id 的重试，以 None 输入让图从 apply_action 继续，并跳过 version / pending 校验；快照 pending_input 为空（不再等待用户输入）。其他 action_id 在这个半状态下得到 not_allowed_now。
- 动作 run 以 error / cancelled 结束时撤销 session_actions 占位（否则重试只会重放失败流）；completed / awaiting_input 才回填结果。apply_action 以 card_id 幂等，重复继续不重放副作用。
- 快照 pending_input 的优先级：active_run 非空 → 空；checkpoint 里有挂起 interrupt → 以它为准（interrupt_id = card_id，version 取快照 version）；图停在 apply_action 前且带 last_action → 空；否则回退到事件日志折叠（保留票 38 「取消后 pending 不变」的语义与其构造式测试）。
- 校验顺序里把全局动作（request_human / rediagnose）放在 version 检查之前分流：08 §4 步骤 4 规定它们不校 version 与 pending，票 25 / 37 接入前统一返回 not_allowed_now。
- 契约错误码 version_mismatch 改名 stale_version（票 23 票面用词）：`make contracts` 重生成 Schema 与前端类型，同时更新了 Codex 线的 frontend/src/api/events.test.ts 里的类型断言（生成物比对否则 CI 失败）。
- 从 Postgres 重放的事件（jsonb）键序与实时事件不同，JSON 内容相同；比对事件流要按对象比较而不是按文本行比较。

## 票 24 澄清与 R7
- LangGraph 在中断态收到新输入：丢弃挂起的 interrupt、从 START 重跑，状态里的 pending_card 不会自动清掉。规则：intake 是唯一入口节点，负责把失效 pending_card 置 None 并交 disambiguate 记录；快照 pending_input 以 checkpoint 中断为准所以自然为空。
- 产品卡片本身算一次「请确认产品」的澄清（prepare_card 计数）：用户不选而改发文本 → 文字追问一次 → 再不明就 R7，与 09 §2.1「两次未选中」一致；点选卡片后计数清零。
- 抽取降级（HAIKE_LLM=off 或模型失败）时 symptoms 为空，症状判定回退到原文：去掉产品 / 品类词后只剩指代或空 → 视为没有故障描述（03 §1.4.1 规则 3）；产品已确认或品类已定时承接更早轮次的故障描述，避免「这个又不行了」被反复追问。
- 「品类明确但本期不支持」的零命中（充电器、吸奶器等）现在直接 out_of_scope + escalate_reason=R8，不再走 unknown → 追问；REASON_TEXT 有 R8，但摘要 product 文案对非扫地机品类仍写「扫地机器人（型号未确认）」，属票 25 范围。
- 旧的会话骨架测试用的占位文本（"a"、"第一句"、"充不上电"）在真实语义下都是「品类未定」，票 24 后走 clarify（intake / disambiguate / clarify 仍是三节点，version 不变，stage 停在 disambiguate）。
- 手测脚本用 curl `-d "text=中文"` 会把原始 UTF-8 字节直接放进 urlencoded 体，服务端按 latin-1 解出乱码；要用 `--data-urlencode`。浏览器 fetch 不受影响。
- uvicorn 里 HAIKE_LLM=off 不生效：main.py lifespan（票 17）无条件 set_model_router，本机手测会真实调用模型；单测靠 tests/__init__ 的环境变量 + 不跑 lifespan 才关掉。建议 B 在 lifespan 里同样尊重该开关。

## 票 47 迁移与备份
- `pg_dump --no-owner` + 超级用户 `pg_restore` 会把对象属主变成超级用户，应用账号立刻失去访问权；恢复脚本必须显式把属主改回目标库属主（用 `--role` 在旧对象属主已乱时会因 `must be owner` 失败，改成恢复后统一 ALTER OWNER 更稳）。
- 恢复 / 主库重启后，psycopg_pool 默认不会检查借出的连接，第一个请求会撞到 `terminating connection due to administrator command`；池要开 `check=AsyncConnectionPool.check_connection`。
- pg_restore 对「扩展属主」等无害告警返回非零，脚本不能用其退出码判成败，用恢复后的健康检查兜底。
- macOS 没有 `timeout` 命令，手测脚本用 `curl --max-time`。
- 基线迁移用 IF NOT EXISTS 是为了收编已存在的库；从第二条迁移起应写常规 DDL，并在 CI 用 `make db-check` 卡版本。
