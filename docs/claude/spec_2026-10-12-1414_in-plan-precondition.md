# 计划内检查不作入口前提（T29）

## 问题

T29 复测（`reports/eval/2026-10-12-1340_t29-multiturn/`）3 次中 2 次先发文字问句「门扣扣紧了吗」，1 次直接出 s1 卡。
问句内容就是 rv-0254 第 1 步。`diagnose.synthesize` 把它填成 needs_confirmation 的 missing_fact，服务端照发追问。
提示词已要求区分入口前提与待查原因（`synthesize.py` INSTRUCTION），不稳定。

推论：客户若答「没扣紧」，`precondition_status` 判 negated，rv-0254 整条丢弃；而没扣紧正是第 1 步要处理的原因。

## 方案

`filter_hypotheses` 的 needs_confirmation 分支先调 `in_plan_check(plan, missing_fact)`：

- 遍历计划的 action / question 步骤，跳过带 `condition` 的场景步骤；
- 取步骤原文首句，要求以 check / verify / inspect / ensure / confirm / make sure / test 开头；
- 用现有 `_covers` 判 missing_fact 的内容词是否都在首句里；
- 命中且 `supported_symptoms` 非空 → 记 `precondition_in_plan:{pid}:{step_id}`，按 supported 继续后续核对；
- 未命中或没有覆盖现象 → 原逻辑（已知 / 否定 / 已答 / 追问）。

已说过的检查由 guide 的 `check_plan_facts` 判 done 跳过，不改。

## 回放范围

本地 checkpoint 中 65 个不同的 (plan_id, missing_fact)，命中 11 个：rv-0254 s1、rv-0270 s1、rv-0271 s1、rv-0112 s1、rv-0363 s1、
bp-0090 s1、bp-0151 s1、bp-0164 s1。均为「检查 X」型步骤。场景前提（rv-0050 多楼层、rv-0218、rv-0087 If…）、
现象或错误码复述、动作指令（Power Cycle、Set … mode）不命中。

首句限定为「检查」类动词的原因：只做覆盖判断时，rv-0050「In multi-floor tasks」、rv-0218「When the robot does not start
from the station」会被当作计划内步骤，而它们是场景前提。

## 测试

`orchestrator/tests/test_in_plan_precondition.py`：`in_plan_check` 判定表；T29 首轮出 s1 卡不追问；门扣没扣紧保留方案；
无覆盖现象仍追问；场景前提仍追问；not_applicable 仍丢弃。

## 未处理

s2 卡没承接客户「已清洗」：事实为 `subject=it`，fact_check 未判 partial。与本问题无关，另行处理。
