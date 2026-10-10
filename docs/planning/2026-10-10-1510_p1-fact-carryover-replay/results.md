# P1 真实回放结果

时间：2026-10-10 15:12–15:25（北京时间）。代码：HEAD 2d7a1e5 加上未提交的 P1 改动；每轮前 `docker compose up -d --build orchestrator`，驱动记录运行指纹与工作区一致。串行（长路径 `--concurrency 1`，分层驱动副本 Semaphore=1），两轮 restart 计数均为 0。

驱动与判据同 `docs/planning/2026-10-10-1440_p0-guard-replay/plan.md`：T16/T27/T31/T37 用 1938 轮长路径驱动（动作卡固定未解决），B12/B17 用 1321 轮分层驱动与原模拟答复。

## 第一轮（long/、branches/）

| 会话 | 结果 | 问题 |
| --- | --- | --- |
| T16 | 首卡 rv-0056 s2 查磁铁，s1「装没装滤网」跳过 | 通过 |
| T27 | 异物检查卡跳过（done：「no blockage seen. roller mop area is clear.」），计划耗尽进质保 | 通过 |
| T31 | 擦触点 s3 跳过，发 s1 / s2 / s4 | 质保处回了 PROOF_LATER：`can't get past critical low battery` 被缺资料正则误判 |
| T37 | 换到另一条加水条目 rv-0111，仍发「没水就加水」 | 模型对荷兰语原文判 unknown |
| B12 | 第二轮回 TRACKING_LATER | 通过 |
| B17 | 第二轮回 PROOF_LATER，无方案 / 执行卡 | 通过 |

修正：缺资料正则必须同时出现单号 / 凭证名词；fact_check 提示词加「用户已说明状态即 done」的例子与多语言说明。

## 第二轮（long-r2/、branches-r2/）

| 会话 | 改动前（1321 轮） | 本次 | 判定 |
| --- | --- | --- | --- |
| T16 | s1 查滤网装没装 | 直接 s2 查磁铁 | 通过 |
| T27 | 重复发异物检查卡 | 异物卡跳过，进质保收订单 | 通过 |
| T31 | s3 让再擦触点 | s1 → s2 → s4，跳过 s3；质保处正常要订单 | 通过 |
| T37 | rv-0021「空了就加水」 | 加水条目判 done 跳过，发 rv-0163「App 水量监测不准，取出水箱时加满到 Max 线」 | 通过；rv-0163 正对应「满水仍报缺水」 |
| B12 | 第二轮逐字重复索单号 | 说明查不了、单号在哪找 | 通过 |
| B17 | 第二轮逐字重复索凭证 | 说明查不了保修、不会提交、凭证在哪找 | 通过 |

guide.step 模型输出（第二轮，服务日志）：T16 s1 done「It is fully installed and clean」；T27 s1 done「no blockage seen. roller mop area is clear.」；T31 s3 done「despite wiping clean the electrical connections」；T37 rv-0021 s1 done「Terwijl de schoonwater tank nog vol is.」，rv-0163 s1 unknown。

## 限制

- 每单两次，模型判定有随机性，不代表稳定率。
- B17 第二轮仍带「I'll handle your requests in this order: replacement request → order details.」：模型把「Do not submit any replacement request yet」读出了换货与订单两个诉求。这句排序提示与本次改动无关，未处理。
