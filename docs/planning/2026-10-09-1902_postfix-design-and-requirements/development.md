# 开发记录

方案和需求已先建立；从本记录创建起 plan.md 冻结。起始代码 HEAD：eefc1a4。

| 需求 | 状态 | 复现/修改/验证 |
| --- | --- | --- |
| R1 | 已实现，相关自动回归通过 | `diagnose/synthesize.py` 检查完整输入预算、裁剪尾部候选与证据并同步白名单；删除模型失败后的检索顺序执行兜底；必要内容仍超限时返回明确原因 |
| R2 | 已实现，相关自动回归通过 | `sessions/l3.py` 关闭案件完成当前任务；`sessions/graph.py` 覆盖排障耗尽入口及新人工/安全请求；`diagnose/decision.py` 修正结束后的解释 |
| R3 | 已实现，相关自动回归通过 | `conversation/reduce.py` 保留结构化原话为不确定事实；按类型去重，允许有来源的明确事实替代不确定旧版本 |
| R4 | 已实现，相关自动回归通过 | 新增 `diagnose/charging.py`，由候选标题与客户原话独立核验受电对象；在适用性过滤处接入，不依赖模型自报 matched_subject |
| R5 | 已实现，相关自动回归通过 | `sessions/clarify.py` 去掉通用症状问题中的扫地机错误码示例 |
| R6–R9 | 后续需求，未开发 | 知识节点、请求证据、动作结果、统计投影；不计为本轮完成 |

## 边界

单元与 HTTP 回归使用假模型、假知识库和隔离的运行夹具，不调用真实模型或外部知识库。不改变原始案例内容。不把自动测试通过等同于真实模型全部稳定。

## 19:15 确定性复现

新增 `tests/test_postfix_decision_boundaries.py`，运行 `cd orchestrator && uv run pytest -q tests/test_postfix_decision_boundaries.py`：20 failed / 7 passed。失败对应未经验证执行、完整上下文超预算、关闭案件虚假等待、表单主诉丢失、充电对象自证漏洞及跨品类代码。正向对照（真实人工等待、已有极性、内部设备充电）通过。此时尚未修改实现。

## 开发与验证迭代

1. 第一批实现后，上述 27 项通过。随后补测结束后解释、新人工/安全请求、同值不同类型事实和不确定事实确认，均先得到失败再修复；新增文件最终包含 38 项测试。
2. R2 的新测试暴露 `reopened` 不能直接跳 `awaiting_approval`，按既有状态机补上 `proposing`；没有放宽迁移规则。关闭后仅保存摘要不会触发虚假人工事件，真实新人工请求和安全事件仍会入队。
3. 第一组 10 个相关文件通过 224 项；随后根据降级行为变化，扩展到图片、回放、恢复、长对话和官方案例回归。
4. 图片用例中独立设置视觉与文字假模型，避免视觉模型重试消耗文字诊断脚本。所有 11 项图片会话测试通过。全提供方失败用例断言正常结束、R5、无错误事件且无操作卡；只读图失败用例断言仍能依据有效文字诊断出卡。
5. 17 文件联合回归第一次得到 293 passed / 2 failed；两处是 T55/T29 旧夹具仍无诊断结果却期望出卡。修正假模型前提，并纠正 T29 的知识条目；不删除质保和过保断言。

## 影响与限制

- 所有变化均为共享后端规则，生产代码没有按 T 编号、订单或 QA 编号分支。精确错误码、真实人工边界、多诉求排队、正常查询和会话恢复纳入相关回归。
- 无数据库迁移、无契约变更、无前端代码变更。本轮没有发布、提交或重启运行服务。
- 主诉保留不等于肯定故障；不确定事实仍需澄清。充电关系校验目前覆盖英文明确句式，不是全语言因果理解。
- 去掉未验证兜底可能提高故障期间的澄清/交接率；必须以真实复测评估，不能为了出卡率恢复兜底。
- 本轮没有运行修改后真实模型的 63 单全量评测，没有全量 pytest 或前端浏览器验收。自动回归能证明指定边界与流程，不证明所有真实生成结果稳定。
- R6–R9 尚未开发。方案与需求先行记录；不能将这些条目列为已修复。

## 最终验证

2026-10-09 19:35：17 个相关测试文件合计 **295 passed in 15.22s**；`make lint` 通过；`git diff --check` 通过。此前单独运行修改后的官方案例文件 **40 passed**。未发现本轮已覆盖流程的回归失败。

从 `orchestrator/` 执行的最终联合命令：

```sh
uv run pytest -q \
  tests/test_postfix_decision_boundaries.py \
  tests/test_applicability_facts.py \
  tests/test_diagnosis_recovery.py \
  tests/test_conversation_round5_boundaries.py \
  tests/test_conversation_reduce.py \
  tests/test_conversation_l3.py \
  tests/test_l3_experience.py \
  tests/test_sessions_clarify.py \
  tests/test_context_capacity.py \
  tests/test_guide_step_kinds.py \
  tests/test_vision_graph.py \
  tests/test_replay.py \
  tests/test_conversation_lifecycle.py \
  tests/test_conversation_recovery.py \
  tests/test_conversation_escalation_summary.py \
  tests/test_conversation_long_flow.py \
  tests/test_conversation_official_tickets.py --tb=short
```

从仓库根目录执行 `make lint` 和 `git diff --check`。没有运行全量 pytest；上述 295 是自动测试项数，不是官方工单数或模型调用次数。

后续真实验收：部署或启动包含本次工作区修改的固定版本，记录代码标识、模型/知识库配置及官方源文件版本，再跑全部 63 单；按实际人工入队终止，不继续模拟人工审批。优先观察 T20/T29/T51/T52/T53/T58 的行为与交接率变化，记录 R6–R9 未完成造成的残留，不能与本轮自动测试结果合并计算通过率。
