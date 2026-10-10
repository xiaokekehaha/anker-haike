# 官方 Q&A 段落拆分（parts）：T19 / T26 / T36 / T53

## 问题

一个官方编号段落被编成一张操作卡，卡上只能回「解决 / 未解决 / 做不到」。段落里实际有多件事时，「未解决」回不了是哪一件：

```
T19 rv-0023 s2  「以上检查无异常且重装后仍报错 → 基站硬件问题」   前提没问过就下结论
T26 rv-0063 s3  问句（是否加过第三方清洁液）+ 观察泡沫 + 有泡沫才排水  问句答案丢失
T36 rv-0341 s1  4 个 if 的噪音诊断树                              不知道走哪一支
T53 bp-0114 s6  4 个子病因，其中 12 秒重置与 s2 重复、带换机承诺       重复发已失败的步骤
```

全库正则统计（下限）：段内诊断树约 15 条、操作段夹问句 3 段、条件结论 1 条。「检查 X，如果 Y 就做 Z」写在一张操作卡（53 段）现有处理可用，不在范围内。

## 方案

`data/official/qa_overrides.yaml` 的段落覆写加 `parts`：按段内唯一的原文锚点 `at` 把一段切成多步，依次生成
`s{pos}`、`s{pos}b`、`s{pos}c`…；每部分可单独写 kind / title / options / branches / default / disabled。

- `branches` 目标：数字是段落位置（原有），字符串是本条 step_id 或 `EXHAUSTED`。`default` 是回答不在选项里时的目标。
- 校验：锚点必须唯一且依次后移，未知字段报错；测试核对切出的文字拼回去等于原段落。
- 段落图示只挂在第一部分。
- `decide_next` 加 `replay_end`：沿已回答的边重放已耗尽的计划。
  - 走到官方交售后段：即使没有「未解决」也走 guide_exhausted 进质保判断（T36「拆下滚刷噪音消失 → 滚刷问题」）。原先会换下一条候选指南或落到 R2。
  - 选中审核写成 EXHAUSTED 的选项（原文没覆盖的那一支）：该指南不计入 MAX_GUIDES，下一条候选指南完整走完（T36「其他声音」→ rv-0316 四项）。
- 转售后过渡句：`hardware_basis` 增加 guide_exhausted 来路，索单前先说「官方排查已走完仍未解决，下一步是售后审核，是否在保看下面的核查」。

不做：控制 / 背景答案分类、未知答案挂起、发卡门槛、REASSESS 终点、合约与前端改动
（`docs/planning/2026-10-10-1656_t26-conditional-troubleshooting/plan.md` 的完整方案）。全库同类结构约 20 条，按条目审核覆写即可。

## 各条目

| 条目 | 拆法 |
| --- | --- |
| rv-0023 | s2 改问句：密封圈与部件正常仍报错 / 密封圈变形破损，两个回答都记事实后进质保 |
| rv-0063 | s3 问句（Yes / No / Not sure，背景，都继续）→ s3b 操作卡（摇水箱看泡沫，有泡沫排水换水） |
| rv-0341 | s1 问句：拆下滚刷和盖板后噪音消失 → s1b 说明（滚刷导致）→ s1c 交售后；吱吱声 → s1d 试拖地模式，未解决 → s1e 交售后；其他声音 / 不在选项 → EXHAUSTED，交给候选里的 rv-0316 |
| bp-0114 | s6 磁吸线；12 秒重置部分禁用（与 s2 重复）；s6c 问「收到时按钮就坏了吗」，是 → s6d 交售后，否 / 其他 → s6e 换充电器和线 |

交售后段的承诺句（「We can resolve this by sending…」「we will send…」「provide your shipping address…」）由 `customer_text` 去掉，客户看不到。

## 评审

Fable 5.1 独立评审，采纳：branches 支持 `EXHAUSTED`、加 `default`、bp-0114 问「出厂 / 到货即损坏」而非「按钮是否损坏」、
rv-0341 承诺句须去掉（已核实 `customer_text` 去掉）。未采纳：
- 「s3 与 s3b 共用 instruction_src 会被去重」：实测两者分别是 `rv-0063#s3`、`rv-0063#s3b`。
- 「用 guide_trace 里的 handoff_step 判断」：trace 是单轮流水，跨轮丢失；改为从已回答历史重放计划，与 `_first_open_step` 同一做法。
- 「补 T26 规划 §7 的契约 / 前端测试」：本方案不改契约与前端。

## 影响面

- 全库 872 个计划逐个比对改动前后：只有 qa_bp_0114、qa_rv_0341 变化（rv-0023 / rv-0063 的覆写在比对前已存在），没写覆写的条目不变。
- 进行中的会话：bp-0114 旧 s6 卡回答后走新的 s6c；rv-0341 旧 s1 是操作卡，新 s1 是问句卡，按新卡类型校验会拒绝旧的「未解决」反馈（not_allowed_now）。不做旧卡兼容，受影响会话重新开始。
- `tests/fake_qa.py` 的 `QAHitAdapter` 支持多个 qa_id（T36 需要两条候选）。

## 验证

- `tests/test_conversation_official_tickets.py`：结构、校验、原文拼回、T19 两支、T26、T36 三支（其他声音走完 rv-0316 四项）、T53、转售后过渡句；去掉对应覆写后新测试失败。
- 相关 19 个测试文件 353 条通过，`make lint` 通过。
- 真实回放：`docs/planning/2026-10-10-1800_card-parts-replay/results.md`。
