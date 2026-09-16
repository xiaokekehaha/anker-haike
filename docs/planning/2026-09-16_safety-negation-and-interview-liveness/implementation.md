# 实施说明

## 1. 安全词否定语义（`app/rules/service.py`）

匹配前先遮蔽被否定的安全词，遮后的文本再做原来的子串匹配。只承认**一种**否定形态：
否定词后面紧跟着一串安全词，词与词之间只允许白名单里的连接（空白、明显 / 任何 / 迹象 /
或 / 、/ signs of / any …）。跨过标点或任何实义字符即视为新的陈述，继续按命中处理。

这条「紧邻」约束是刻意的，它让下面两件事同时成立：

- 「未见冒烟烧焦鼓包漏液火花」「no smoke or burning smell」整串被遮，不再升级；
- 「无线充电座冒烟」的「无」后面接的是「线充电座」，不是安全词，**照样升级**。

同一遮蔽用在用户文本、动作备注与 CP-pre-step 的步骤文本上。安全判定宁可误报不可漏报，
所以判否定的条件比判命中严得多：看不出是否有危险（「看不出是不是烧焦」）仍然按命中处理。

## 2. 问诊活性（`app/diagnose/decision.py`）

`accept_answer` 区分两种新症状事实：

- **能归进故障族**（`symptom_codes` 非空）：照旧清零连续无进展窗口，总预算不变；
- **归不进**：记一次 `outcome="unmapped"` 的响应（`progressed=False`），
  让「连续两次无进展」和「累计八次」两个预算都能推进。

这样用户不断补充无法归类的描述时，系统最多两轮就带着已记录的现象转人工，而不是无限复读。
已被更正、已被接受的答案、以及旧分类版本的问诊都不进这条分支。

## 3. 词表补齐（`config/symptom_taxonomy.yaml`，版本 2026-09-14.2 → 2026-09-16.1）

「吸力下降」补 `缠 / 缠绕 / 头发 / 残留` 四个说法，词形沿用 `vision_vocab.yaml`
的 `text_aliases.phenomena.缠绕`。这是把图片路径已有的映射补给文字路径，不是新增判断。

**这是领域数据，最容易需要你按真实工单调整**，所以单独一个 commit，回退不影响其他修复。
版本号上调会让在途会话的旧问诊作废（既有设计），这正是版本字段存在的意义。

## 4. 不再无故要求「确认具体选择」（`app/conversation/commands.py`）

那句兜底文案加上「确实有待办卡」的前提。没有卡片时交回排障路径，由它重问判别问题。

## 5. 重复提问先承接（`app/sessions/clarify.py`、`graph.py`）

新增 `render_question(reason, detail, previous=...)`：本次要问的话与上一次问出去的原话相同时，
前面加一句「您说的我记下了。还需要先确认一项：」。

两个刻意的选择：

- **只改呈现**。问题原文、`question_id`、`symptom_interview` 结构一个字都没动 ——
  `symptom_interview` 会整体进入 intake 的上下文，动它等于改模型输入。
- 判重依据是 `clarification.question`（上一次真正问出去的那句）。`decide()` 与 `_clarify()`
  原先重建这个字典时会把它丢掉，现在保留；`previous.endswith(text)` 因此不会叠加两层承接语。

产品澄清与症状判别共用这条路径，两边的复读都一起解决了。

## 6. retention 回归（`tests/test_retention.py`）

原断言 `deleted["sessions"] == stats.sessions` 与产品行为矛盾：`purge_expired` 扫出的过期会话里，
带 30 天内 case 的那些会被 `delete_session_data` 保留。开发库里攒够这类会话后该用例必红
（在干净 HEAD 上同样红）。改为按 id 精确断言，并补一条「过期但带未关闭 case 的会话必须保留」。

## 验证

- 新增回归：`test_rules.py` 20 项（否定与正向各一组）、`test_diagnostic_next_action.py` 6 项、
  `test_retention.py` 1 项。
- 后端全量 **857 passed in 52.49s**（`tests/test_retention.py` 连跑两次均绿）；
  修改文件 Ruff 通过。
- 部署镜像内直接校验规则服务：否定清单不升级、`未见冒烟，滚刷烧焦` 与 `无线充电座冒烟` 仍升级。
- 实机：`1_滚刷缠绕_正常曝光.png` 连发 6 次无一误升级；
  「清扫效果不好 → 地面有残留」当轮就出排障步骤卡（改动前是复读判别问题）；
  「启动不了 → 不能 → 不能」仍两轮出步骤卡、无 R7。
- 未验证：findings 第 5 条的 intake 解析稳定性，需要 bake-off。

## 发布与部署（2026-09-16）

- 提交：`777bef2` 否定语义 / `6919d2f` 问诊活性 / `27dc85e` retention 回归 /
  `4fac6fc` 词表 / `66d561b` 本文档；release 登记 `20260916-66d561b`。
- 镜像 `haike/orchestrator:dev` = `6e214086409c`；上一版 `bd888c00f00b` 打了
  tag `before-negation-20260916`，回滚换 tag 重启即可。
- `make health` 全 ok（overseas 未配置为预期）；`make db-backup` haike 4.85 MB、WeKnora 1.82 MB。
- `make release-check` 仍有一项红：bake-off 报告基于 models.yaml 2026-09-13.5、当前 2026-09-15.2。
  **上一版发布前就存在**，与本次改动无关，需要单独跑 `make bakeoff`。
