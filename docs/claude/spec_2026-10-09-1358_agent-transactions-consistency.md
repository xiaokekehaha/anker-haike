# Agent 的事务、原子性与一致性：本项目实现与分布式技术栈

来源：

- 本仓库（anker-haike）代码，行号以 2026-10-09 提交 46b1777 为准。
- 背景读物：Kleppmann《数据密集型应用系统设计》（DDIA）第 7–9 章；Kleppmann《How to do distributed locking》；Stripe《Designing robust and predictable APIs with idempotency》。

术语约定：

- **Agent**：本项目的售后客服智能体（orchestrator 里的 LangGraph 图）。
- **事务**：数据库里「一组读写要么全部生效，要么全部不生效」的执行单元。
- **原子性**：一组操作不可分割，不会只做一半。
- **一致性**：数据始终满足业务规则（例如一个订单最多一张处理中的换货单）。
- **幂等**：同一个请求做一次和做多次，效果相同。

## 0. 总览

一句话结论：Agent 做不到跨系统的真正原子性。一次处理里有 LLM 调用、数据库写入、外部系统调用（建服务单），这些步骤没法放进同一个事务里一起回滚。工程上的做法是拆开保证：

| 要保证的事 | 手段 | 本项目实现 |
| --- | --- | --- |
| 本地状态的写入原子 | 数据库事务 | `reserve_input` 一个事务写三张表 |
| 对外写操作最多生效一次 | 幂等令牌 + 先查后建 | `idempotency_key` / `client_ref` |
| 同一件事同一时刻只有一个执行者 | 锁 + fencing 令牌 | advisory lock、`attempt` |
| 不基于过期状态做决定 | 版本号（乐观锁） | `expected_version` |
| LLM 不能直接触发写操作 | 授权令牌 | `gate_result` |
| 系统确认不了结果时 | 人工兜底 | `ExecutionNeedsReview` → 转人工 |

文档结构：

1. 为什么 Agent 会遇到这些问题
2. 本项目的五道防线（按请求进入顺序，结合案例和代码）
3. 假设订单和物流变成数据库，需要注意的 7 个事务问题
4. 对应的分布式技术栈（6 层）
5. 学习路线
6. 附录：术语表与代码索引

---

## 1. 为什么 Agent 会遇到这些问题

### 1.1 一个比喻

把 Agent 看成一个售后客服小哥，订单库和物流库是他面前的账本。小哥办一件事要经过「看账本 → 想一想 → 动笔写单」三步。**看**和**写**之间有时间差（几秒到几分钟），这段时间里可能发生三类意外：

- 别人改了账本（数据过期）；
- 另一个小哥也在办同一件事（并发）；
- 小哥写完单子没收到回执，不知道写没写成（结果不确定）。

### 1.2 最典型的故障：重试导致重复执行

```
Agent                         售后系统
  |  create_order(换货)  -->     |
  |                              |  建单成功 SO-123
  |  <-- 响应丢了 / 超时 ---  X   |
  |                              |
  |  "超时了，再试一次"           |
  |  create_order(换货)  -->     |  又建一单 SO-124   <-- 重复换货
```

LLM 和重试逻辑分不清「对方没做」和「对方做了但我没收到回复」。另外两类问题：

- 用户连点两次，或两个进程同时处理同一会话（并发）；
- 用户看着旧卡片点了确认（基于过期状态做决定）。

这些就是分布式系统的经典问题，Agent 只是把它们又带了回来。

---

## 2. 本项目的五道防线

### 2.0 贯穿案例与总图

**案例**：客户的充电宝坏了，Agent 给出「换货」方案卡（`option_id = opt-replace`），客户点「确认」。此时页面状态版本是 v6，案件号是 `case-42`。

```
浏览器点击"确认"
  POST /sessions/s1/inputs  {input_id: "in-9", expected_version: 6, kind: "confirm", ...}
   |
   v
(1) 会话锁           router.py:222        同一会话同一时刻只处理一个请求
   |
   v
(2) 输入幂等+版本校验  inputs.py:127        重复提交返回第一次的回执；页面状态过期就拒绝
   |
   v
   Agent 跑图 ... 到 L3 authorize
   |
   v
(3) 授权闸门          l3.py:439 + gate.py   代码做四项检查，产出 gate_result
   |
   v
(4) 动作幂等令牌      executor.py + store.py  key = case-42:service_order.create:opt-replace
   |      fencing 令牌 attempt=N
   v
(5) 后端 client_ref   protocol.py:41        后端也按 key 去重；超时后先查再建
```

### 2.1 会话锁：同一会话串行处理

**问题**：客户网络卡顿连点两次「确认」；或两个 worker 进程同时收到同一会话的请求。两个请求同时推进同一个案件，状态会交叉覆盖。

**实现**：`orchestrator/app/sessions/locks.py` 的 `PostgresSessionLock`（第 30 行）。用 Postgres advisory lock，这是数据库提供的一把「按数字命名的锁」，不绑定任何表，所有连到同一个库的进程都能看到。

```sql
select pg_try_advisory_lock(hashtext(session_id))   -- 抢锁，抢不到每 50ms 重试
...                                                 -- 处理请求
select pg_advisory_unlock(hashtext(session_id))     -- finally 里释放
```

调用点：`orchestrator/app/sessions/router.py:222`，`async with lock.hold(session_id, timeout_s=...)`。

```
worker A: lock(s1) 拿到 ---- 处理 "in-9" ---- unlock
worker B: lock(s1) 等待 ................... 拿到 ---- 处理
          超过 timeout -> LockTimeout，返回前端"稍后重试"
```

测试环境用 `InMemorySessionLock`（一个 `asyncio.Lock`），接口相同。

### 2.2 输入幂等与版本校验：请求入口的两道检查

**实现**：`orchestrator/app/sessions/inputs.py:127` 的 `reserve_input`，两道检查都在**同一个数据库事务**里完成。这是本项目真正做到原子性的地方。

```
BEGIN
  select * from sessions where session_id='s1' FOR UPDATE      -- 行锁（会话锁之外的第二层保险）
  select * from session_inputs where input_id='in-9'
     |
     +-- 已存在 --> check_replay：payload 摘要一致吗？
     |                一致   -> 返回旧回执（重放，不重新跑 Agent）
     |                不一致 -> InputConflict("input_id_conflict")
     |
     +-- 不存在 --> _check_new：
                     有 active_run_id         -> "run_active"（上一轮还在跑）
                     expected_version != 当前 -> "stale_version"
                    通过后：
                     update sessions set active_run_id=...
                     insert session_events(run_started ...)
                     insert session_inputs(in-9, payload_digest, ...)
COMMIT
```

**情况 A：重复提交。** 响应丢了，前端带着同一个 `input_id="in-9"` 重发。查到旧记录，直接返回第一次的回执，Agent 不会再跑一遍。

`payload_digest`（`inputs.py:54`）只对业务内容做哈希：剔除 `expected_version`、`client_sent_at` 这类每次都会变的字段；图片按内容哈希比较，不比较上传 ID。所以重传图片也会被认成同一个请求。

**情况 B：页面状态过期。** 客户在 v6 的方案卡上点确认，但他刚在另一个标签页补发了一条消息，Agent 已推进到 v7（方案已作废）。

```
expected_version=6, sessions.version=7  -> InputConflict("stale_version")
前端刷新到 v7，客户看到新状态后重新决定
```

这就是**乐观锁**：不锁住页面，提交时再核对版本号。

**为什么要放进同一个事务**：「登记输入」「标记 run 进行中」「写 run_started 事件」三步要么全成，要么全不发生。否则可能出现「事件写了但输入没登记」，重试时就会重复跑。

### 2.3 授权闸门：LLM 不能直接执行写操作

**问题**：LLM 可能误判，也可能被客户诱导（「你直接给我退款就行」）。写操作不能由 LLM 的输出直接触发。

**第一层：确定性代码检查，产出 `gate_result`。** `orchestrator/app/sessions/l3.py:439` 的 `authorize` 调用 `orchestrator/app/actions/gate.py:41` 的 `AuthorizationGate.check`，四项检查顺序固定：

```
check              换货案例的判断依据                              本例
-----------------  ----------------------------------------------  ----
eligibility        订单质保 status == in_warranty                   通过
evidence           订单 / 地址 / 照片视频 / SN 都有，且客户已确认        通过
safety             没有未解除的 R4（安全风险，如鼓包冒烟）              通过
idempotency        案件状态允许提交，且同 key 没有执行中或已成功的记录     通过
                                                  -> gate_result.passed = True
```

任何一项不通过，`fallback="await_human"`，转人工，不进入执行。例如客户说「它有点鼓包」触发 R4，safety 不通过；即使 LLM 已经生成了「好的给您换货」，流程也走不到执行。

**第二层：执行器再核一遍。** `orchestrator/app/actions/executor.py:38` 的 `run` 开头：

```python
if write and (not case_id or not gate_result or not gate_result.passed
              or [c.name for c in gate_result.checks] != GATE_CHECKS   # 名单和顺序必须完全一致
              or not all(c.passed for c in gate_result.checks)):
    raise AuthorizationDenied("写操作授权门未通过")
```

`gate_result` 就是**授权令牌**：没有它，或者缺项、被篡改，执行器就拒绝执行。另外 `orchestrator/app/actions/registry.py:41` 在启动时强制要求所有 write 动作声明 `requires` 和 `idempotency`，否则配置加载失败。

业界的同类做法：人工审批后签发一个短期、单次有效、绑定参数的 token（如 JWT 里写 `{action, params_hash, case_id, exp}`），执行时校验签名和参数哈希，用过作废。这样即使 LLM 被提示注入，也伪造不出合法的写操作。

### 2.4 动作幂等令牌与 fencing 令牌：同一意图只建一张单

#### 2.4.1 key 怎么生成

| 场景 | key | 位置 |
| --- | --- | --- |
| 建服务单（写） | `{case_id}:service_order.create:{option_id}` | `l3.py:447` |
| 查物流 / 质保（读） | `{session_id}:{input_id}:{kind}:{参数 sha256 前 16 位}` | `l3.py:734` |

写操作的 key 只由「哪个案件、哪个方案」决定，**不含 input_id**。客户换一个请求再点一次确认，生成的仍是同一个 key。`authorize` 先查这个 key（`l3.py:448`），已成功就直接复用，不再过闸门。

#### 2.4.2 claim：抢占执行权

逻辑在 `orchestrator/app/actions/store.py:33` 的 `_claim`，表 `action_executions` 一个 key 对应一行：

```
现有记录                              结果
-----------------------------------  --------------------------------------
无                                   插入 running, attempt=1 -> 去执行
succeeded                            返回旧回执（不再执行）
running 且租约未到期                   ExecutionBusy -> 告诉客户"正在处理"
running 已到期，attempt>=2             ExecutionNeedsReview -> 转人工
failed 且不可重试                      返回旧失败结果
failed 可重试 / running 首次到期        attempt+1, 重新 running -> 去执行
（任何情况）同 key 但请求内容不同         IdempotencyConflict
```

最后一行由 `_validate_reuse`（`store.py:28`）实现：同一个 key，`action_kind / request / case_id / session_id` 必须完全一致，防止 bug 拿旧 key 去建另一张单。

#### 2.4.3 finish：fencing 令牌

写回结果时必须带上自己 claim 时拿到的 `attempt`（`store.py:157`）：

```sql
update action_executions set status=..., receipt=...
 where idempotency_key=%s and attempt=%s and status='running'
-- 影响行数 != 1 -> ExecutionBusy("执行租约已变更")
```

**案例时间线**（租约时长 = 动作超时 + 1 秒）：

```
t0  worker A  claim -> attempt=1, running
t1  worker A  调后端 create ... 进程卡住
t2  租约到期
t3  客户重试 -> worker B claim -> 发现 running 已过期 -> attempt=2
t4  worker B  完成 -> finish(attempt=2) 命中 -> succeeded
t5  worker A  醒来 -> finish(attempt=1) -> where attempt=1 不匹配 -> 0 行 -> 拒绝
```

A 的过期结果写不进去，B 的成功结果得以保留。这个概念叫 **fencing token**：锁本身不可靠（会过期），所以由写入方校验递增的令牌号。

### 2.5 后端 client_ref：解决「做了但没收到回复」

**问题**：上面 t1 时，A 发出的 create 可能**已经建了单**，只是响应丢了。B 直接再 create 就会出现两张换货单。

**实现**：

- `orchestrator/app/backends/protocol.py:41`：每次 create 都带 `client_ref = idempotency key`，要求后端按它去重。
- `orchestrator/app/backends/service.py:99`：本项目的后端实现用 `client_ref` 派生确定性的单号（`service_order_no`，第 51 行），并且 `insert ... on conflict(client_ref) do update ... returning *`，同一个 `client_ref` 只会有一行。
- `orchestrator/app/actions/executor.py:205` 的 `_create_once`：`attempt > 1` 时**先查后建**。

```
attempt=2:
  find_service_order(client_ref="case-42:service_order.create:opt-replace")
     |
     +-- 查到 SO-123 -> 直接当作本次结果，不再 create
     +-- 后端确认不存在 -> 才 create
     +-- 查询本身失败 -> OutcomeUnverified -> needs_review -> 转人工
```

如果 attempt=2 也卡住、租约再次到期，下次 claim 命中 `attempt>=2` 规则，抛 `ExecutionNeedsReview`。`l3.py:506` 告诉客户：

> We can't confirm the result of this submission yet. To avoid a duplicate request, I've passed it to a colleague to check.

**设计取舍**：最多自动接管一次，确认不了就转人工，不赌第三次。重复换货（多发一个货）的代价远大于让客户多等一会儿。

可运行的验证：巡检场景 `orchestrator/app/inspection/l3_scenarios.py:44`（`l3_idempotent_execution`，「重复申请只创建一张服务单」）；后端的 `FaultInjection.check_committed` 专门模拟「已写入但响应丢失」。

### 2.6 小结：哪些是原子的，哪些不是

```
                       保证方式                       原子吗
----------------------------------------------------------------------
输入登记+run 标记+事件   一个 PG 事务                  是
案件状态迁移            行锁 + 事务                    是（只在本库内）
建服务单（外部系统）      幂等 key + fencing + 先查后建   否 -> 改为保证"最多一次 + 结果可查"
确认不了外部结果         转人工                         否 -> 交给人兜底
```

本项目没有做 Saga 补偿（自动撤单）：主办方的售后工具只收单，提交后一律转人工，没有自动发货或退款，用不上补偿。

---

## 3. 假设订单和物流变成数据库：7 个事务问题

**现状**：订单和物流是 `data/official` 里的主办方静态数据，启动时加载到内存，只读（`orchestrator/app/backends/service.py:55` 的 `OrderBook`）。只有服务单表 `service_orders` 写库，和案件表、执行记录表在同一个 Postgres。

**假设**：订单和物流变成**会被别人修改的数据库**（OMS 改订单状态、承运商回调更新物流）。

核心矛盾：只要「看」和「写」之间有时间差，别人就可能插队。

### 3.1 看完就变了，照旧写

**生活版**：柜员看了一眼余额 1000 元，转身拿现金时你家人转走了 800，柜员照样给了你 1000。

**本项目版**：订单在一次处理中被多次独立读取，中间没有保证它不变：

```
t1  propose     l3.py:356  get_order -> 包裹"运输中" -> 给客户补发方案
t2  客户思考 2 分钟 .......................... 承运商回调：包裹"已签收"
t3  authorize   l3.py:453  get_order -> 判 reship_eligible
t4  execute     service.py _validate  get_order（又读一次）
t5  insert service_orders
```

t3 和 t5 之间物流变成已签收，仍然插入了补发单，客户收到两个包裹。退款同理：t3 判在保，t5 时订单已被别的渠道退款或取消。

**方案**：判断和写入在同一个事务、同一把锁下完成，或用版本号做条件写。

```
authorize 时：gate_result 里记下 order.version（或物流 last_event_seq）
                                   |
execute 时（同一个事务内）：            v
  insert into service_orders ...
  select ... where exists (select 1 from orders
                           where order_no=%s and version=%s   -- 版本没变
                             and status not in ('cancelled','refunded'))
  -- 影响 0 行 -> 订单已变，回到 propose 重新出方案
```

或在写事务里先 `select ... from orders where order_no=%s for update`，再判断、再插入。现在的 gate 在事务外判断，订单静态时没问题，订单会变就不行。

### 3.2 同一订单开两个窗口各办一次

**生活版**：网页申请一次退货，App 又申请一次，两个客服都觉得「我这边没处理过」，都退了钱。

**本项目版**：去重 key 是 `{case_id}:...`，库上唯一约束只有 `client_ref unique`（迁移 0009），**只保证同一个案件不重复**：

```
网页会话 s1 -> case-41 -> key=case-41:...:opt-replace -> SRV-A
App  会话 s2 -> case-42 -> key=case-42:...:opt-replace -> SRV-B   <-- 同一订单两张换货单
```

两个 key 不同，幂等拦不住；会话锁只锁同一会话，也拦不住。

**方案**：数据库层加业务唯一约束。只能交给数据库，因为两个并发事务在应用层都看不到对方未提交的写入。

```sql
create unique index service_orders_active_uniq
  on service_orders(order_no, sku, type)
  where status in ('submitted','in_review');
```

冲突时返回已在 protocol 里定义的 `Conflict`，上层处理成「这个订单已有处理中的服务单」并给出单号。

> 这个问题**现在就存在**，与订单是否是数据库无关。演示场景里很少有人开两个会话。

### 3.3 数量算超了

只有订单行带数量（买 2 个坏 1 个）时才会遇到。

**生活版**：店里剩 2 张票，你和朋友同时问「还有几张」都听到 2 张，结果卖出 3 张。

```
会话 s1：查到已申请 0 < 购买 2 -> 申请换 2 个
会话 s2：查到已申请 0 < 购买 2 -> 申请换 1 个      <-- 合计 3 > 2
```

默认 READ COMMITTED 隔离级别下，两个事务都看不到对方未提交的写入。

**方案**：原子条件更新，不先查再改：

```sql
update order_lines set claimed_qty = claimed_qty + %s
 where order_no=%s and sku=%s and claimed_qty + %s <= qty
-- rowcount = 0 -> 超额，拒绝
```

或先 `select ... for update` 锁订单行。不要指望调成 SERIALIZABLE 解决：那样还得写序列化失败后的重试，本项目目前没有这类重试。

### 3.4 办到一半人跑了

**生活版**：办护照，窗口收了材料开了收据，正准备登记系统时工作人员下班了。

**本项目版**：服务单建好后，`l3.py:549` 起是一串**各自独立提交**的写入：

```
tx1  insert service_orders                 backend.create_service_order
tx2  update action_executions -> succeeded  executor store.finish
tx3  cases.external_refs += 单号             attach_execution
tx4  cases 记录承诺                          record_commitment
tx5  cases -> awaiting_approval             transition
tx6  写交接摘要                              _record_handoff
```

tx2 和 tx3 之间进程崩溃：执行记录显示成功，案件里却没有单号，状态停在 `executing`。

- 客户重新确认时，`authorize` 查到同 key 已成功（`l3.py:449`），claim 返回旧回执，然后补上 tx3–tx6，**可以自愈**。
- 客户不再操作时，案件一直卡在 `executing`，人工队列里看不到。

**方案**：

- **必要**：对账任务，扫描「`action_executions` 已成功但案件仍在 executing」的记录，补做 tx3–tx6。这些步骤是幂等的，重复做无害。
- **可选**：tx2–tx5 在同一个库，可以合并成一个事务。tx1 要保持独立：`BackendClient` 协议刻意把服务单建模为外部系统，将来接真实工单系统时不能依赖同库事务。

> 这个问题也是**现在就存在**的。

### 3.5 锁着东西去干慢事

**生活版**：在 ATM 前取钱时接了个 10 分钟的电话，后面的人只能干等。

**本项目版**：订单表一旦参与写事务，很容易写出：

```
BEGIN
  select * from orders where order_no=%s FOR UPDATE   -- 锁住订单
  调后端 / 调 LLM / 等物流接口（几秒到几十秒）
  insert service_orders
COMMIT
```

锁持有时间等于外部调用的耗时，OMS 对这张订单的更新全被阻塞。

**规则**：事务里只放 SQL。外部调用在事务外完成；需要防并发时用 3.1 的「版本号 + 条件写」代替长持锁。现有代码是对的：执行器调后端前已提交 claim，调完再用 finish 写回，中间不持有数据库锁。

另外注意：会话锁 `PostgresSessionLock` 会**独占一条连接**直到 run 结束（`locks.py:38`）。并发会话一多，这些连接和订单查询会抢同一个连接池；订单变成数据库后要重新核算池大小。

### 3.6 分两次看，拼出假状态

**生活版**：拍全家福时，拍完爸爸那一半，妈妈换了件衣服再拍她那一半，拼出来的画面从来没存在过。

**本项目版**：判补发资格要同时用订单和物流。READ COMMITTED 下每条语句看到的是它开始那一刻的数据：

```
select order    -> status=shipped
                         <- 承运商更新提交
select packages -> 包裹 delivered
```

读到的是从未真实存在过的组合状态。

**方案**：一次判断所需的数据用一条带 join 的 SQL 读出；或放进同一个 `REPEATABLE READ` 只读事务。

### 3.7 审批时情况早已变

**生活版**：周一交报销单，老板周五才批，中间那笔订单已经退款，老板照周一的材料批了。

**本项目版**：提交后一律转人工，人工可能几小时后处理。现在人工决策带了 `case_revision`（`orchestrator/app/cases/store.py` 的 `human_decisions` 表），只保证**案件**没变，不保证**订单**没变。

**方案**：批准前重新读订单，比对 gate 记下的 `order.version`。不一致就在审批界面标出「订单已变化」，由人工决定，不静默放行。

### 3.8 汇总

```
#  一句话                    比喻             现在     订单成库后  最小方案
-  ------------------------  ---------------  -------  ---------  -----------------------------------
1  看完就变，照旧写            柜员看完余额被转走  无       高         gate 记 version，写入时条件校验
2  同一订单两个窗口各办一次      网页 + App 都退款  已存在    高         partial unique index (order,sku,type)
3  数量超额                   演唱会票卖超      无       中         原子条件 update
4  多步写入中途崩溃             护照收了没登记     已存在    不变       对账任务；可选：合并成一个事务
5  事务内等外部调用             占着 ATM 打电话   无       中         规则：事务里只放 SQL
6  多次读取快照不一致           拼接的全家福      无       低         一条 SQL 或 REPEATABLE READ
7  审批时订单已过期             周五批周一的单    无       中         审批前比对 order.version
```

三类解法：**写的时候再核对一次**（1、3、7），**让数据库当唯一的裁判**（2），**事后有人巡查补漏**（4）。

---

## 4. 对应的分布式技术栈

### 4.1 总表

```
问题                         模式                      常用工具 / 框架                     本项目现在用什么
---------------------------  -----------------------  ---------------------------------  ------------------------
看完就变 / 数量超卖             乐观锁、悲观锁、约束        Postgres / MySQL 本身               version、FOR UPDATE、unique
同一时刻只能一个人做             分布式锁 + fencing        Redis、etcd、ZooKeeper              PG advisory lock + attempt
重试不重复                     幂等键                    Stripe 式 Idempotency-Key          idempotency_key / client_ref
跨多个服务要么都成功要么都不做     2PC / TCC / Saga         Seata、DTM、Temporal               无（转人工兜底）
"改数据 + 发消息"必须同时成功     事务外盒（Outbox）+ CDC    Debezium + Kafka                   无（session_events 是库内同类思路）
长流程做到一半崩溃要能接着做      持久化执行                 Temporal、LangGraph checkpoint     LangGraph checkpoint
最后的兜底                     对账                      定时任务                            无（只有人工兜底）
```

分层图：

```
┌──────────────────────────────────────────────────────────┐
│ 6. 对账兜底         定时任务 / 人工                         │
├──────────────────────────────────────────────────────────┤
│ 5. 持久化执行        Temporal / LangGraph checkpoint ✓     │  ← 流程崩溃能续跑
├──────────────────────────────────────────────────────────┤
│ 4. 消息一致性        Outbox + Debezium + Kafka             │  ← 改数据和发通知同时成功
├──────────────────────────────────────────────────────────┤
│ 3. 跨服务事务        Saga / TCC / 2PC（Seata、DTM）         │  ← 多个系统要么都成功
├──────────────────────────────────────────────────────────┤
│ 2. 并发控制          分布式锁 + fencing ✓ / 幂等键 ✓         │  ← 不重复、不打架
├──────────────────────────────────────────────────────────┤
│ 1. 数据库           约束 ✓ / 行锁 ✓ / 乐观锁 ✓ / 隔离级别     │  ← 地基
└──────────────────────────────────────────────────────────┘
                         ✓ = 本项目已在用
```

### 4.2 第 1 层：先把数据库用透

比喻：数据库是一个非常严格的登记处。很多问题不需要新框架，让登记处多立几条规矩就够了。

| 手段 | 做什么 | 对应第 3 节 |
| --- | --- | --- |
| 唯一约束 / 部分唯一索引 | 第二张重复单写不进去 | 3.2 |
| `UPDATE ... WHERE 条件` | 「够就扣」一句话说完 | 3.3 |
| `SELECT ... FOR UPDATE` | 先锁这一行再改 | 3.1 |
| version 字段（乐观锁） | 不锁，提交时比对版本 | 3.1、3.7 |
| 事务隔离级别 | 决定能看到别人改到哪一步 | 3.6 |

本项目这一层基本都在用：会话表 `version`，案件表 `FOR UPDATE`，服务单表 `client_ref unique`。业界大量「分布式问题」最后都是靠数据库约束解决的。

### 4.3 第 2 层：分布式锁

比喻：会议室只有一把钥匙，拿到钥匙的人进去开会。

```
worker A ──抢锁──┐
                ├──> 锁服务（Redis / etcd / ZooKeeper / PG）
worker B ──抢锁──┘        只有一个人能拿到
```

| 工具 | 特点 |
| --- | --- |
| Redis（`SET key NX PX`、Redlock） | 快，最常用；主从切换时可能丢锁 |
| etcd / ZooKeeper | 强一致，可靠；Kubernetes 用 etcd 选主 |
| Postgres advisory lock | 已有 PG 就不用加组件，**本项目用这个** |

关键坑：锁会过期。持锁者卡住（GC 停顿）后锁被别人拿走，他醒来还以为锁在手上。解决办法是 **fencing 令牌**（本项目的 `attempt`，见 2.4.3）。延伸阅读：Kleppmann《How to do distributed locking》批评 Redlock，以及 Redis 作者 antirez 的回应文章。

### 4.4 第 3 层：跨服务事务

比喻：订旅游套餐，机票、酒店、门票在三家公司。机票订到了酒店满了怎么办？

**2PC 两阶段提交**

```
            协调者
         ┌────┼────┐
阶段1:  "准备好了吗？"  机票✓ 酒店✓ 门票✓
阶段2:  "全部提交！"    提交  提交  提交
        （任何一个说不行 -> 全部回滚）
```

强一致，但准备阶段大家锁着资源干等，慢；协调者挂掉所有人卡住。工具：XA 协议、Seata XA 模式。互联网业务很少用。

**TCC（Try-Confirm-Cancel）**

```
Try:     先冻结（机票占座、酒店预留、门票锁定）
Confirm: 都冻结成功 -> 正式扣
Cancel:  任何一个失败 -> 已冻结的全部解冻
```

比喻：酒店「留房 15 分钟」。缺点：每个服务要额外写三个接口。工具：Seata TCC、DTM。

**Saga（最常用）**

```
订机票 ──> 订酒店 ──> 订门票
  ✓          ✓         ✗ 失败
              <── 退酒店 <── （逐个反向补偿）
  <── 退机票
```

每步直接提交，出错时按相反顺序做补偿（退款、撤单）。缺点：中间有一段不一致状态；补偿也可能失败。工具：Seata Saga、Temporal、AWS Step Functions。

本项目一个都没用，这样做是对的：提交后一律转人工，没有需要撤回的自动动作。以后若接入自动退款，Saga 是首选。国内 Java 生态常用阿里开源的 **Seata**（AT、TCC、Saga、XA 四种模式）；Go 生态有 **DTM**。

### 4.5 第 4 层：事务外盒（Outbox）+ CDC

比喻：寄快递必须「登记快递单」和「把包裹交出去」都做到。

问题：

```
1. 数据库：服务单状态改成 submitted   ✓
2. 发 Kafka 消息通知仓库发货           ✗ 进程挂了
   -> 数据库说已提交，仓库永远收不到通知
```

反过来先发消息再写库，就可能「仓库发货了，库里没这张单」。

解决：

```
同一个数据库事务里：
  ① update service_orders ...
  ② insert into outbox(消息内容)        ← 和 ① 一起提交
                 |
                 v
  搬运工（Debezium 读数据库日志 / 定时轮询 outbox 表）
                 |
                 v
              Kafka ──> 仓库、短信、BI ...
```

| 工具 | 作用 |
| --- | --- |
| Debezium | 读 Postgres WAL / MySQL binlog，把数据变更变成消息（CDC，变更数据捕获） |
| Kafka / RabbitMQ / RocketMQ | 消息队列 |
| 消费端幂等 | 消息可能投递多次，接收方按消息 ID 去重 |

本项目没有消息队列，暂时不需要。但 `session_events` 表思路相近：业务状态和事件在同一个事务里写（`inputs.py:127`），前端按事件序号拉取，相当于「库内的 Outbox」。

### 4.6 第 5 层：持久化执行（与 Agent 最相关）

比喻：游戏自动存档。每过一关存一次，死了从最近的存档继续。

```
普通代码：  步骤1 -> 步骤2 -> 步骤3 ✗崩溃 -> 重启后从头跑，步骤1、2 重复执行

持久化执行：步骤1[存] -> 步骤2[存] -> 步骤3 ✗崩溃
           重启 -> 读存档 -> 跳过1、2（用存下的结果）-> 从3继续
```

| 工具 | 特点 |
| --- | --- |
| Temporal（前身 Uber Cadence） | 业界标杆。写普通代码，自动记录每步结果，崩溃后重放；内置重试、超时、定时器、Saga |
| LangGraph checkpoint | 为 Agent 设计，每个节点执行完把状态存库。**本项目用这个**（`langgraph-checkpoint-postgres`） |
| Restate、DBOS、Inngest | 较新的轻量方案；DBOS 把状态存在 Postgres |
| AWS Step Functions | 云托管状态机 |

注意：存档只覆盖本地状态。建单这类外部调用是否重复，存档管不了，所以仍需第 2 层的幂等键和「先查后建」。Temporal 把两件事合在一起：外部调用叫 Activity，自动重试，并要求 Activity 本身幂等。

### 4.7 第 6 层：对账

比喻：商店每天关门后清点钱箱，和收银记录对一遍。

前五层都在**防止**出错，但总会有漏网之鱼，所以要定期**检查并修补**：

```
每 5 分钟：
  找出 "执行记录 = 成功"  但  "案件状态 != 已提交"  的数据
     -> 补做后续步骤（幂等，重复做也安全）
  找出 "租约过期很久还是 running" 的执行
     -> 去后端查一下，或转人工
```

工具：定时任务即可（cron、Celery beat、Temporal Schedule）。本项目没有，对应 3.4。

---

## 5. 学习路线

1. **读 DDIA**：第 7 章事务、第 8 章分布式系统的麻烦、第 9 章一致性与共识。本文几乎所有概念都出自这三章。
2. **动手 Postgres**：开两个 `psql` 窗口手动复现超卖（3.3），再分别用 `FOR UPDATE` 和条件 `UPDATE` 修好。性价比最高的练习。
3. **读 Stripe 幂等键文章**：短，讲得清楚，对照 2.4 和 2.5。
4. **跑 Temporal Python SDK 的转账 Saga 示例**：同时看到持久化执行、重试与补偿。
5. **回到本项目对照**：`orchestrator/app/actions/store.py` 和 `orchestrator/app/actions/executor.py` 共两百多行，是第 2 层的完整小实现。

一句话：先让数据库当裁判，再用幂等键防重复，用锁加 fencing 防并发，用持久化执行防崩溃，最后用对账兜底。Saga、TCC 这些重型方案，等有了必须撤回的自动动作再引入。

---

## 6. 附录

### 6.1 术语表

| 术语 | 一句话解释 | 本项目对应 |
| --- | --- | --- |
| 事务 | 一组读写要么全生效要么全不生效 | `reserve_input` |
| 幂等令牌（idempotency key） | 代表「这一次业务意图」的 key，重复请求返回第一次结果 | `idempotency_key`、`client_ref` |
| fencing 令牌 | 每次发锁配递增号码，写入时校验，防止过期持锁者写回 | `attempt` |
| 乐观锁 / 版本号 | 不锁，提交时比对版本 | `expected_version` |
| 悲观锁 / 行锁 | 先锁住再改 | `select ... for update` |
| advisory lock | Postgres 的「按数字命名的锁」，跨进程可见 | `PostgresSessionLock` |
| 授权令牌 | 证明写操作已获许可的凭证 | `gate_result` |
| 租约（lease） | 带过期时间的执行权 | `action_executions.started_at + timeout` |
| 2PC / TCC / Saga | 跨服务事务的三种模式 | 未使用 |
| Outbox / CDC | 改数据与发消息同时成功；读数据库日志转消息 | 未使用（`session_events` 同类思路） |
| 持久化执行 | 每步存档，崩溃后续跑 | LangGraph checkpoint |
| 对账 | 定期比对并修补不一致 | 未实现 |

### 6.2 代码索引

| 机制 | 位置 |
| --- | --- |
| 会话锁 | `orchestrator/app/sessions/locks.py:30`；调用 `orchestrator/app/sessions/router.py:222` |
| 输入幂等 + 版本校验 | `orchestrator/app/sessions/inputs.py:54`（摘要）、`:70`（`_check_new`）、`:127`（`reserve_input`） |
| 授权闸门 | `orchestrator/app/actions/gate.py:41`；`orchestrator/app/sessions/l3.py:439`（`authorize`） |
| 执行器二次校验 | `orchestrator/app/actions/executor.py:38`（`run`） |
| 写动作配置约束 | `orchestrator/app/actions/registry.py:41` |
| 幂等 key 生成 | `orchestrator/app/sessions/l3.py:447`（写）、`:734`（读） |
| claim / fencing | `orchestrator/app/actions/store.py:28`、`:33`、`:157` |
| 先查后建 | `orchestrator/app/actions/executor.py:205`（`_create_once`） |
| 后端去重 | `orchestrator/app/backends/protocol.py:41`；`orchestrator/app/backends/service.py:51`、`:99` |
| 转人工兜底 | `orchestrator/app/sessions/l3.py:506` |
| 建单后多步写入 | `orchestrator/app/sessions/l3.py:549` 起 |
| 巡检场景 | `orchestrator/app/inspection/l3_scenarios.py:44` |
