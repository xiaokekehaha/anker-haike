# 证据

- 管理页面 HTTP 200，标题“电池掉电很快”。
- 页面显示进行中、产品未识别、两轮、0 个步骤。
- 第一轮 4.6 秒：理解诉求、产品消歧、澄清追问、保存问题；第二轮 8.2 秒，3 个节点。
- 工作区已有 30 个已跟踪文件修改及其他任务未跟踪文件，主要涉及检索、模型配置和 sessions/graph.py；不得覆盖。
- 第二轮用户补充“Anker 737 充电宝型号 A1289”，助手返回理解失败兜底；快照 last_error=null，管理台轮次为 completed。
- 第二轮 intake 追踪：qwen-flash outcome=error，deepseek outcome=timeout，总耗时8004ms；最终 primary_intent=unknown、patch_count=0。
- context_built=4013，最终输入估算6409 < 16000，未截断、历史未遗漏，排除本次上下文超限。
- 运行服务为14小时前构建的Docker容器；本地未提交修改不等于运行时代码。
- 已运行捕获记录检查 `jq -e '.runs[1].nodes[0].summary.primary_intent != "unknown"' /tmp/haike-1ad8-journey.json`，输出false、退出1；原始失败记录仅用于取证，后续以离线回放验证实际代码。

## 待验证假设
1. 主模型内容无法解析，检查每次attempt原始错误类型与响应。
2. 整链8000ms让备用模型没有独立完成时限，检查每次attempt耗时与router deadline。
3. 降级规则没有处理明确型号补充，检查原始输入经过现有解释器的确定性回放。

## 已证实根因
- 原始JSONL第二轮主模型报 `LengthFinishReasonError`，completion_tokens=512、prompt_tokens=4986，耗时5687ms；不是型号不存在或输入超限。
- 备用deepseek实际耗时2268ms后被整链8000ms预算截断；三级链第三家没有执行。
- product_question_answer仅确定性处理单独品类词、无空格型号串或是/否；本次完整自然语言补充走模型，失败后普通降级规则没有匹配业务意图，返回unknown。
- 同时观察到管理台completed、last_error=null：表示本轮正常送达降级回复，不表示语义理解成功。模型调用表仍正确记录status=error。
- 未发现此次进入检索或知识库调用。

## 修复与验证
- models.yaml默认通道intake输出上限512→1536，配置版本2026-09-18.2；其他任务既有配置保留。
- interpret_turn整链预算8000→15000ms。
- 新增HTTP回归3场景全部通过：历史512额度保留失败对照；当前额度下确认ANKER-A1289并保持同一issue；主位模拟5.687秒失败，第二位3秒成功，可用时限9.313秒。
- 初版回归在修改前为1通过2失败，修改后3通过；make lint通过。
- 未请求真实模型或知识库，未修改原会话数据。当前运行容器需要后续重建才能加载Python预算改动，单独重启无法加载宿主机Python源码。
