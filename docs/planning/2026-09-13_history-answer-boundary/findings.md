# 历史回查边界诊断

## 结论
本次触发的是历史 reader 的时间顺序边界，根因为语义模型把当前追问自己的 ID 当成历史查询目标。不是原始问答丢失，也不是上下文截断。业务代码未修改。

## 证据
- 会话：0695759cefe7432c8f168a6145e7628d；run：98de469d09cd4102b3047d3ff942b18e。
- 当前输入：“你怎么回答呢”；entry_id=e29a9400-9304-4dff-9eab-408fbc18c036；seq=178。
- logs/events.jsonl:729 的 intake 输出 primary_intent=history_query，history_request.mode=reference，source_entry_ids=[当前输入 ID]。
- logs/events.jsonl:730 的上下文 omitted_entries=0，tokens=5964；seq=147 的问题、seq=153 的回答、seq=158/163 的上一轮问答均在模型输入中。
- reader.py:9 只保留 first_seq < before_seq。graph.py:783 传入当前 input_seq=178。因此当前输入被排除。
- reference 分支得到 selected=[] 和 missing_ids=[当前输入 ID]，reader.py:43 返回固定兜底。
- graph.py:787 将 decision 改为 reply_mode=clarify，reply.py:17 直接返回 clarification；没有让回复模型再依据完整上下文回答。
- 会话 API 中 seq=183 的助手消息正是该文案，model_tier=null。

## 原始回答仍然存在
“币圈怎么来支付”（seq=147）的回复（seq=153）是：“好的，请描述新问题，以及是否仍是同一台设备。之前的问题记录会保留。”

## 回放验证
命令：python3 docs/planning/2026-09-13_history-answer-boundary/replay.py --expect-success
结果：退出码 1，AssertionError 为用户遇到的完整文案。

命令：python3 docs/planning/2026-09-13_history-answer-boundary/replay.py
结果：退出码 0。重放原请求得到同样错误；仅改引用为 seq=147 的问题，立即找回对应问答；仅改成 recent，同样成功；仅将时间边界推进到 179，当前输入变为可选（只用于证明原因，绝非修复建议）。

回放依据模型日志元数据，run 分组以 reply_to_input_id 等价重建，部分历史 ID 在源日志已脱敏。它确定性验证 reader 条件，不宣称重跑大模型必然输出相同 ID。

## 修复建议
1. 保留 first_seq < input_seq，当前追问不能冒充过去的回答。
2. 语义解释和服务端校验应区分“当前输入 ID”与“可回查的历史目标 ID”。当前输入自引用属于目标解析失败，不能误报原文不可用。
3. 对“你怎么回答呢”这类承接追问，应沿上一轮回查的目标定位原问题及其助手回复；歧义时澄清具体哪条问题。
4. 无效目标应受控重解析或澄清；只有确认目标存在但原文确实无法读取时才使用原始记录不可用文案。
5. 下一轮回复还把此次兜底当成了记录缺失的事实，并重复“无法复述”。应避免把助手先前的失败文案当作存储状态的权威证据。

## 修复阶段补充
- 原会话上一轮实际 history_request.mode=recent，选中了多个问答；没有保存唯一被讨论的问题。原请求回放修复后会返回目标澄清，不能无依据指定其中一条。
- 服务端 read_history_for_turn 将连续回查指向上一轮成功读取的唯一问答；旧模型当前输入自引用也可在同样约束下修复。目标多义、无效引用、被其他轮打断时返回 history_target_unresolved。
- 新增 follow_up 语义模式，提示“我刚问了什么”优先 reference 定位具体问题；回复上下文携带 history_selection，避免将旧失败文案当成存储事实。
- 7 项 HTTP 回归旧实现全红，修复后通过；全部 57 项会话测试通过。原记录 replay.py --check-fixed 通过；ruff 与 git diff --check 通过。

## 部署验收
已部署本地 Compose 镜像 21d15d489435，服务健康。真实模型新会话 88feb940900a44a596a1c798b3812a2f 按用户三句原话执行，最终回复：

> 根据记录，我之前的回答是：“好的，请描述新问题，以及是否仍是同一台设备。之前的问题记录会保留。”

详细输出见 live-smoke.json。此为真实模型单次冒烟验证；模型语义解析存在随机性，服务端错误引用与歧义路径由确定性 HTTP 回归覆盖。旧会话的已保存气泡不会被追溯改写。
