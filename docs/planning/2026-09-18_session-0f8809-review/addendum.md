# Claude 修复评审：fbc3427

评审范围：`git diff cdc7c01...fbc3427 -- orchestrator/app orchestrator/tests`。当前发布登记 `4a72780`，版本 `20260918-fbc3427`。用户要求分析与评审，本轮不改应用实现、不改真实会话、不提交或发布。

需求依据：[Claude spec](../../claude/spec_observation_deadlock_20260918.md)；规范依据根目录 AGENTS.md / CLAUDE.md。此任务没有关联 issue，直接使用本地 spec。code-review 的两个审查轴独立完成。

## 判断

方向合理，能解除原会话的主要阻塞，但不能认定整条诊断链已经修好。需要修复下面两处边界误判。第一性要求是：接受新的用户证据，并准确更新它所属的状态；接受范围变宽时，不能把“提到了某选项”当成“确认该现象”。

## Standards

0 项新增规范问题。新增操作条件与复核逻辑集中在 operation_conditions，图节点负责发布与记录，职责基本清楚。已有 Any / 函数内导入不是此次新增，不计入评审。

## Spec

### P1：旧观察请求重新受理后，把解释问题当成观察回答

位置：[reduce.py:538](../../../orchestrator/app/conversation/reduce.py#L538)，以及 555—583 行。需求第 50 行要求旧请求继续“被回答接住”，没有授权把任何包含选项的消息都变成故障事实。

确定性离线序列：

1. A1289 已发出 pb_737_display 问题。
2. 用户“设备不在身边”，请求变为 unparsed，device=false。
3. 用户问“之前你问的‘连接笔记本时显示 UVP’是什么意思？”，语义明确为 explain。
4. 新代码仍 substring 匹配 laptop_uvp，写入 source_kind=user_report 的观察事实，将请求标记 answered，强制 reply_mode=diagnose，路由 reassess；回复变为设备可用性追问，没有解释选项。
5. 随后用户说“设备现在在身边”，decide_next 直接选择 pb_737_laptop_uvp 步骤；用户从未确认自己遇到 UVP。

原版本在第 3 步不会受理 unparsed 请求。此次扩大受理范围暴露了这条跨轮错误路径。

建议：保留补答能力，但要求当前消息确实在回答指定观察。解释、历史查询、引用助手选项不能写成用户发现；将回答绑定到 observation/request 和当前原文，而不是扫描所有开放请求后仅凭命中文本确认。

### P2：“拿到了”无上下文固定绑定 device_ready

位置：[operation_conditions.py:113](../../../orchestrator/app/conversation/operation_conditions.py#L113)。需求第 51 行要求资源到位给“对应 *_ready 信号”，第 52 行要求恢复资源。

确定性离线反例：当前复核问题是“清洁工具准备好了吗？”，设备和清洁工具均记录为缺失。用户回答“拿到了”，interpret 的确定性分支直接输出 device_ready，不再调用语义理解；reduce 将 device 改为 true，cleaning_tool 仍为 false。设备限制被错误解除，实际拿到的工具仍不可用。

建议：无指代短答优先绑定当前复核的 resource；只有明确提到设备，或上下文唯一指向设备时才写 device_ready。无法唯一定位时澄清，不能默认放行设备。

## 有效改动与尚未覆盖的原问题

- asked / unparsed / unknown 可接收之后明确提供的观察，这一方向合理。
- resource_asks 限制同次缺失只复核一次、资源恢复后清除记录，实现合理。
- 第 8 轮实际 semantic 的 reducer 回放，在原版本失败，修复版通过：即使 operation_update=null，精确短句“已经拿到了”也能令 device=true。
- 原问题“回充慢却转向输出排查”仍存在；config/plans.yaml 未改，A1289 输出/复位计划仍覆盖 pb_no_input，并共用偏输出场景的观察题。Claude spec 第 76—77 行明确列为未做，不算此次修复的新增回归，但不能据此声称原会话已完整修复。
- “设备不在身边”与 unknown 选项的匹配语义仍未统一，spec 亦已列出。
- 新增端到端用例从“没有输出”进入，没有重放原会话“有输出 → 给充电宝本身充电很慢”的分支；证明的是暂停/恢复通路，不是回充问题诊断正确。

## 验证

```text
cd orchestrator
uv run --env-file ../.env pytest -q tests/test_conversation_observation_deadlock.py tests/test_conversation_operation_conditions.py tests/test_diagnostic_loop.py
41 passed in 5.04s
```

另用临时脚本直接调用 interpret_turn / reduce_turn / decide_next，关闭真实模型与知识库，两条边界期望断言均失败。脚本只用于评审取证，不作为修复提交；完成后删除。本轮未重新验证真实模型是否会正确解释所有“拿到了，……”复合句，不把提示词修改视为已证明的语义稳定性。

## 用户授权后的修复

用户后续指令“修复”，将上述两条评审问题纳入实现。本节记录最终修改，前述评审保留为历史。

1. 观察接收只接受回答、补充、报告现象及受限的 unknown 意图。解释、历史查询和业务查询不再消费观察请求。理解不可用或意图不明时，明确选项标签/配置短语仍可直接补答；包含选项的长句不再单靠子串匹配写入设备事实。
2. 新增 `resolve_operation_reply`，由 interpret 与 reduce 共用。“拿到了／已经拿到了”优先绑定本问题当前复核的资源，否则只允许绑定唯一缺失资源。明确说“设备拿到了”仍按名称绑定；多项缺失且无明确指代时返回澄清，任何资源都不解除，模型错误提议也不能绕过此校验。
3. 既有暂停、资源复核去重和迟到的真实观察补答继续生效。资源澄清不会消耗同时等待的观察问题。

测试先红后绿：初次新增参数化测试 22 failed / 7 passed；修复后进一步加入模型不可用的 HTTP 边界，新增 4 条反例先失败，随后修复。最终：

```text
uv run --env-file ../.env pytest -q tests/test_conversation_observation_deadlock.py tests/test_conversation_operation_conditions.py tests/test_diagnostic_loop.py tests/test_conversation_reduce.py
81 passed in 5.17s
make lint
All checks passed!
git diff --check
通过
```

完整 HTTP 测试同时覆盖 FakeChatModel 与模型不可用：先询问 UVP 选项含义不会产生观察，随后拿到设备仍须回答观察问题，真正报告 UVP 后才发布对应步骤。未调用真实模型或知识库，未修改历史会话数据，未提交或发布。回充慢的提问方向不属于本次两项评审回归修复，仍保留为独立后续问题。
