# 回放结果

时间：2026-10-10 14:33–14:36（北京时间）。代码：HEAD 09e41dd 加上本次未提交的 P0 改动；`docker compose up -d --build orchestrator` 重建，驱动记录的运行指纹与工作区一致（`runtime_unchanged=true`）。

## 结论

| 会话 | 改动前（1321 轮） | 本次 | 判定 |
| --- | --- | --- | --- |
| T53 | 「换货 → 退款 → 排障」；第五卡写「Please provide your shipping address so that we can replace the device」 | 「replacement request → device troubleshooting」；task_queue 只有 replacement_request / report_problem；第五卡结尾为「Whether a replacement or part can be sent depends on a warranty check.」 | 通过 |
| B15 | 首轮多出退款任务 | 与 T53 相同，无退款；过保后继续排障卡 | 通过 |
| R05 | 无退款（随机正确） | 无退款 | 通过（见采证说明） |
| T36 | 噪声卡写「we will send you a suitable replacement unit」，之后才核保 | 卡内无承诺，结尾为核保说明；未解决后收订单 / 凭证 | 通过 |
| T50 | 「Does the right pump hub produce any suction or motor movement at all?」 | 「You mentioned "the left one does work". Which side or part has the problem, and what exactly is it doing?」 | 通过 |
| B10 | 「Does the right pump hub produce suction while the left one does not?」（反转左侧） | 首问同 T50；模拟回答「右侧充电后不开机」后发 bp-0025 重置卡 | 通过 |

六个会话的客户可见文字与卡片均不含 replacement unit / shipping address / we will send|replace / so that we can replace / by sending you。

## 采证说明

- 第一次长路径回放（并发 3，目录 `long-attempt1-crashed/`）期间 orchestrator 进程以退出码 139（SIGSEGV）退出，容器按 unless-stopped 自动重启，驱动收到连接断开。日志在崩溃前只有正常的模型调用与检索记录，没有 Python 异常。之后改为串行（长路径 `--concurrency 1`，分层驱动副本的 Semaphore 由 3 改为 1），两次回放均无崩溃，restart 计数保持 1。崩溃原因未查明；1321 轮并发 3 跑 86 会话没有出现过，暂不能归因于本次改动，也不能排除。
- R05 的 journey 即时读取返回 404（1321 轮 R05 也出现过同样的即时 404），驱动记为 collection_error；会话本身完成，随后只读重取成功，存为 `branches/R05-journey-reread.json`，没有重发消息。
- 只有 6 个会话，每单一次；只证明这三处约束在这次运行中生效，不证明 63 单整体比例或稳定性。

## 证据

`long/`（T36、T50、T53）、`branches/`（B10、B15、R05）。JSON 受 `.gitignore` 规则 `docs/planning/2026-10-10-*/**/*.json` 影响只留本机。

## 崩溃调查（14:40–14:50）

现场：容器事件 `die exitCode=139`（SIGSEGV），`OOMKilled=false`，未设内存上限；`unless-stopped` 自动重启。uvicorn 单 worker，`PYTHONFAULTHANDLER` 未开启，所以没有原生栈。

崩溃前 1 秒内的最后动作（日志时间线）：

```
06:33:27.443  knowledge index refreshed {'kb_qa': 872}   <- 新容器第一次检索，加载索引
06:33:30.172  e7adc829 (T53) diagnose.vision started     <- Pillow 处理 T53.jpg，在事件循环里同步执行
06:33:30.212  两路 WeKnora hybrid-search 返回 (T36、T50)
06:33:30.251  两个会话 knowledge.search finished
06:33:3x      进程退出 139，无 Python 异常
```

复现尝试，均未崩溃：

| 尝试 | 结果 |
| --- | --- |
| 容器内对 T53.jpg 串行跑 `prepare` + `assess_all` 200 次 | 正常 |
| 容器内 6 线程并发处理全部 10 张官方附件各 30 轮 | 正常 |
| T36/T50/T53 并发 3 回放，热容器 3 次 | 正常，restart 计数不变 |
| `docker restart` 后冷启动立刻并发 3 回放 2 次 | 正常，restart 计数不变 |

判断：原生扩展里的偶发段错误，触发条件未知。本次 P0 改动只涉及纯 Python 的正则与字符串处理，不调用原生扩展，与崩溃无直接关系的可能性高，但没有原生栈不能证实。1321 轮 86 会话、本次 5 次复跑合计约 100 个会话只崩 1 次。

下一步建议（未执行）：在 docker-compose.yml 的 orchestrator 环境变量加 `PYTHONFAULTHANDLER=1`，下次段错误会把各线程的 Python 栈打到 stderr，可定位是哪个扩展；比赛演示前用 `docker inspect --format '{{.RestartCount}}'` 看一次是否再发生。

`crash-repro-*` 目录为复现尝试的原始记录。
