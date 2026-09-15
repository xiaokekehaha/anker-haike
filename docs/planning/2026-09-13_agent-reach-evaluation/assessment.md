# Agent-Reach 能否应用于 anker-haike

调研日期：2026-09-13。结论：**能用于扩展互联网信息获取，但业务接入需要新增检索适配层。建议复用其上游搜索/阅读工具，保留本项目的 LangGraph 和 WeKnora。** 本轮完成源码调研与接入设计，未安装、修改服务或实测第三方搜索。

## 1. 上游是什么

按用户描述，本次对象为 [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach)，不是同名 SSH 远程开发工具。

Agent-Reach 主要提供工具安装配置、渠道健康检查和 Agent 使用说明。源码中的 `AgentReach` 类只提供 `doctor/doctor_report`，自带 MCP 只暴露 `get_status`。实际搜索通过 mcporter 调 Exa，网页阅读通过 Jina Reader；它不是可直接替代本项目 KnowledgeAdapter 的统一搜索 SDK。存在局部网页读取等 helper，不代表所有渠道有统一 API。

核查版本：v1.5.0 Beta，commit `da5044d26fc6adddb6554d5679c94ac22e76e428`。完整源码依据、平台依赖和官方链接见 [上游调研](official-research.md)。

因此要区分两种应用：给能执行工具的开发 Agent 安装使用说明，与给本项目线上 AI 增加搜索接口。前者不自动实现后者。本报告重点评估后者。

## 2. 与当前项目怎么衔接

| 当前实现 | 含义与接入建议 |
| --- | --- |
| `orchestrator/app/knowledge/search.py:search_round` 查询说明书/工单，支持可选 FAQ | WeKnora 继续负责内部可信知识；外网独立 provider，避免混淆资料来源 |
| `orchestrator/app/sessions/graph.py:retrieve` 集中检索、评分、补检索和假设生成 | 在最终 synthesize 前增加受控的外网补充阶段，沿用时间预算与 trace |
| `config/retrieval.yaml` 高级检索开关默认关闭 | 不能假定已有 coverage 信号；需启用并验证 grade，或先按确定性的 no_match/显式联网需求触发 |
| `knowledge/adapter.py:KnowledgeScope` 限定 SKU/品类 | 外部结果必须另验机型、区域、固件版本，query 中带型号不等于页面适用 |
| `diagnose/synthesize.py` 限定预写 plan_id 与有效 evidence_id | 联网可补充判断依据；新增排障步骤仍需要独立维护计划库 |
| `contracts/haike_contracts/common.py:EvidenceItem`、`frontend/src/components/EvidenceDrawer.tsx` | 需补 URL、标题、抓取时间和可信度展示，不能只把 URL 塞进 doc_id |
| `knowledge/ingest.py` 可导入带 front matter 的 Markdown | 可承接审核后的互联网资料，但当前导入器仅拣选固定 metadata，需保留外部出处字段 |

尚未核验部署中的配置覆盖，上述开关结论限于仓库配置。图中的故障卡和预写计划也是现有依据来源。

## 3. 推荐的第一期

先实现「官方网页搜索 + 网页正文读取 + 可追溯引用」。Exa 做搜索，可先验证 Exa 自带正文获取是否足够，按正文质量需要增加 Jina Reader；通过本项目拥有的 HTTP/MCP 适配器调用，其服务条件需实测。只需要这些能力时，不必把 Agent-Reach 整套工具装进业务容器。工具范围依据见 [Exa 官方 MCP 文档](https://exa.ai/docs/reference/exa-mcp)。

```text
用户问题 → 产品确认 → 内部知识检索
                         ↓
               判断是否需要互联网补充
                         ↓
               官方来源搜索 → 正文读取
                         ↓
               校验来源、机型、版本与相关性
                         ↓
               生成有引用的回复 / 排序既有计划
```

建议先从 no_match 和用户明确请求外部资料触发，设置独立开关。内部资料 sufficient 时直接回答；grade 未运行时不臆造 coverage。WeKnora unavailable 是服务故障，应单独记录，外网可用不能把它改报为内部知识恢复。当前 adapter 缺失分支会提前返回，实施时要明确该分支的联网策略。

适合的场景：检索已确认机型的官方支持文章、操作说明或更新公告；用户提供公开网页链接时提取正文辅助理解。搜索结果先经过官方域名白名单和正文核查。官方支持域名需要实际确认，不能仅凭搜索摘要认定。

建议新增模块与改动范围（以下均为待实现设计）：

- `orchestrator/app/external_search/`：provider、搜索策略、结果规范化、来源与 URL 校验、缓存和超时。
- `config/retrieval.yaml` 与对应 Pydantic 配置：`external_search.enabled`、域名范围、条数、总耗时预算。
- `sessions/graph.py`：触发条件、工具进度事件、外网状态与现有 synthesize/reply 的衔接。
- `contracts` 和前端类型/来源抽屉：新增可选外部元数据，兼容历史事件与快照；内部模型输入也要保留可信度。
- 回放、评测和隐私日志：保存可重现的外部结果快照，日志不记录客户敏感原文。

适配器建议提供 `search(query, scope, deadline)` 和 `read(url, deadline)`，返回结构化结果。最少包含 `evidence_id/title/url/snippet/provider/fetched_at/trust_level/product_scope`，发布时间可空；抓取时间与发布时间分开。空结果、超时、限流、鉴权失败分开记录。外部结果不要直接继承内部文档的信任等级，也不要拿不同 provider 的原始分数直接排序。

业务进程使用固定接口；若确需 CLI，在独立 worker 中通过固定程序和参数数组执行，限制为只读搜索/阅读。上线镜像固定版本，安装和升级发生在构建/运维阶段。

## 4. 第二期：资料采集与知识库补充

Agent-Reach 更容易发挥价值的方向，是帮助采集官方教程、视频字幕及社区故障线索，生成待审核资料。审核后补上 SKU、区域、版本、原始 URL、内容指纹，再导入 WeKnora 或用于维护排障计划。

| 来源 | 对本项目的价值 | 建议顺序 |
| --- | --- | --- |
| 官方支持网页 | 说明书补充、操作方法、更新公告 | 第一期 |
| 官方 YouTube/B 站内容 | 视频教程的文字检索；字幕可用性另验 | 第二期，优先离线 |
| Reddit 等社区 | 发现真实用户的症状表达与共性反馈 | 第二期，线索性质 |
| 小红书等登录平台 | 中文使用体验；依赖登录状态与平台可用性 | 后续按业务价值选择 |
| Twitter/GitHub | 公告与技术社区信息 | 对当前售后场景优先级较低 |

字幕读取不等于视频画面理解。社区经验不直接升级为可执行维修步骤，也不自动覆盖官方保修口径。

## 5. 落地条件与验证

这些约束来自当前售后场景及新增联网接口：

- 外发查询只使用必要的机型和故障摘要；当前 `build_query` 在无症状时可回退用户原文，不能直接复用为外发查询。订单号、SN、联系方式不应发给第三方搜索服务。
- 外部网页作为资料处理，沿用 `wrap_data` 并在程序侧限制工具/计划能力；包装文本本身不能代替权限边界。
- URL 读取需限制协议、私网地址及每次重定向目标，避免新增任意 URL 获取能力访问项目内网。
- 免费访问具有配额和限流条件，不能据此承诺零成本或稳定 SLA；生产密钥、并发、目标部署网络的可达性需要实测。
- 搜索和读取共用上限，为回复预留预算。建议首轮试验最多检索 3 条、读取 2 页，总预算 5–8 秒；这些是设计起点，不是已测性能。

建议使用 20–30 个标注样例与现有链路对照，覆盖：内部证据充分、内部无命中、外部官方命中、错误机型、冲突版本、仅社区来源、恶意网页文本、私网 URL、限流和超时、敏感用户文本、旧快照回放。

验收重点：能否补回原先缺失的官方依据；引用可打开且与结论一致；跨机型误用受控；外网故障正常降级；不会产生越界 plan_id/步骤；关闭开关保持既有流程；记录延迟和第三方请求量。离线回放测试与目标部署网络中的真实搜索 smoke test 分开执行。

本轮是可行性评估，以上验收尚未执行，未宣称线上已具备搜索能力。

## 建议决策

值得接入互联网搜索能力。优先以官方网页搜索/阅读做小范围验证，Agent-Reach 作为工具选型和部署参考；后续用其平台工具扩充离线资料采集。这样能沿用现有售后证据、计划和回放机制，也便于替换上游搜索服务。
