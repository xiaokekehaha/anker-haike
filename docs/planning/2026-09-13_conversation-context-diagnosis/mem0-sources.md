# Mem0 与当前会话记忆改造的适配判断

核查日期：2026-09-13。范围为官方文档；未安装 Mem0，未发送项目数据。以下能力针对核查时文档，实际接入需锁定 SDK/API 版本。

## 判断

当前修复不以引入 Mem0 为前提。应先让完整有序的近期问答参与理解，并修复问题切换、纠正以及旧 `escalate_reason` 持续控制路由的问题。Mem0 可作为后续的记忆抽取与检索层，尤其适合跨会话设备信息、既往排障和用户偏好的召回；它本身也支持跨轮上下文，不能简单归类为“只能做长期记忆”。这是基于本案已有诊断与下述官方能力的架构判断。

## 核实的能力及边界

1. **消息、记忆与最终提示词是三个环节。** Mem0 默认从消息抽取事实，通过 `search` 返回相关记忆；应用仍决定将哪些结果交给模型。`infer=False` 可以原样保存内容，但默认记忆不是逐字聊天记录。当前自动抽取为增量 ADD-only；需明确更正或移除记忆时，由应用调用 `update` / `delete`。因此不能把“调用 add”视为业务模型已经获得完整历史。[How Mem0 Works](https://docs.mem0.ai/core-concepts/how-it-works)

2. **托管 Platform 有抽取时的历史上下文支持。** 官方 Add 文档说明，相同 `user_id`（以及使用时的 `run_id`）下，只发新消息即可自动利用先前消息进行记忆抽取；该小节明确限定 Platform，不能据此承诺 OSS 一致。当前文档的对照表称 Platform 与 OSS 均 ADD-only；Platform 写入先返回待处理事件，需要确认完成。[Add Memory](https://docs.mem0.ai/core-concepts/memory-operations/add)

3. **Mem0 有时间能力，但不是会话顺序保障。** Platform v3 的 Temporal Reasoning 会根据查询时间表达与记忆事件日期提高匹配结果的排序；该功能文档明确不适用于 OSS SDK。`timestamp` 用于保留导入对话的原始时间，`reference_date` 用于指定搜索参考时间。它解决时间相关召回，不等同于完整问答按序回放；新记忆的日期信息通常还需几秒进入检索。[Temporal Reasoning](https://docs.mem0.ai/platform/features/temporal-reasoning)

## 对本案的具体含义（设计建议，非 Mem0 产品保证）

- 原始事件仍以项目数据库为事实来源，记录 `conversation_id`、`issue_id`、`event_id`、递增 `seq`、`created_at`、角色、内容与按钮/工具动作。时间戳解释时间，`seq` 确定同会话顺序。
- 近期问答直接按序提供；较早内容可用带来源的摘要。Mem0 若后续接入，负责补充检索相关历史事实，不取代必要的紧邻上下文。例如“刚说错了”需要知道紧邻发言和当前问题，不能只依赖相关性召回。
- 语义理解输出仍需表达历史回顾、切题、纠正及纠正目标；业务事实仍需维护已确认、撤回、待确认和来源关系。记忆检索结果不能直接变成新的升级指令。
- 旧 `escalate_reason` 若继续压过本轮意图，即使成功召回全部历史仍会重复转人工。此处应修复路由条件与状态更新，Mem0 不会替应用修改该逻辑。
- 只有跨会话记忆、历史规模、召回质量开始成为主要问题时，再用本案回放样本验证引入收益；重点看指代/纠正准确率、问题隔离、时间顺序、新增延迟及成本。

## 文档版本注意

搜索引擎缓存中 Add 文档仍出现旧的自动冲突合并描述，实时打开页面已是 ADD-only。Platform 官方迁移说明也明确由原来的自动 ADD/UPDATE/DELETE 转为 ADD-only，在检索时处理时效与相关性。不要据旧教程假定会自动把“说错了”对应的旧记忆删除。[Platform migration](https://docs.mem0.ai/migration/platform-v2-to-v3)
