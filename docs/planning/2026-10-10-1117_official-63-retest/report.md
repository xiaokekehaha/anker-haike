# 官方 63 案复测报告

2026-10-10 本轮已完成 T1–T63，全量保留原始正文及 10 个原附件；另完成 18 个固定模拟多轮分支。首轮 55/63 合格（87.30%）；已观察完整路径 49/63 合格（77.78%），13 个需改进、1 个待核。

| 口径 | 分母 | 合格 | 需改进 | 待核 | 合格占比 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 原始首轮 | 63 | 55 | 8 | 0 | 87.30% |
| 本次已观察完整路径 | 63 | 49 | 13 | 1 | 77.78% |
| 固定模拟分支，单独计分 | 18 | 12 | 6 | 0 | 66.67% |

合格是处理质量判断，不是问题已解决。动作卡后的 not_solved 为固定模拟输入，遇到未知事实、材料、方案确认或真实人工队列时停止。没有真实设备操作、人工审批及发货结果，本轮不计算真实解决率。首轮与完整路径按同一案例分别观察，不是两组独立样本。

## 仍需改进

13 个完整路径问题及 1 个待核项如下；同一案例可能同时涉及多项原因，表内不重复计数。

| 案例 | 实际问题 |
| --- | --- |
| [T16](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T16.md>)、[T27](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T27.md>)、[T31](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T31.md>)、[T37](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T37.md>)、[T41](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T41.md>) | 未充分承接原文已知事实，重复安装、异物、触点或水箱/烘干条件检查。 |
| [T19](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T19.md>)、[T26](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T26.md>)、[T40](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T40.md>) | 条件结果、独立问句或上传材料与动作混合，未解决反馈不能证明各前提已确认。 |
| [T36](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T36.md>)、[T53](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T53.md>) | 源步骤中的寄配件/换机承诺缺资格校验；T53 与过保拒绝换货边界冲突。 |
| [T50](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T50.md>) | 左侧正常事实未充分利用，未先澄清实际故障就进入双侧弱吸力流程。 |
| [T60](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T60.md>) | 缺型号与具体症状时直接以泛化检索未命中交接，信息不足被当作产品缺资料。 |
| [T63](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T63.md>) | brush guard 被改为 detangle elements，回复和交接摘要主对象错误。 |
| [T51](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T51.md>)（待核） | speaker cover、Bluetooth 等来自官方 bp-0111，但对乳泵电池诉求的源资料适用性需要核查。 |

固定分支的 6 个缺陷为 [B04](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/B04.md>)、[B05](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/B05.md>)、[B10](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/B10.md>)、[B12](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/B12.md>)、[B17](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/B17.md>)、[B18](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/B18.md>)：分别涉及定位事实承接、未知出发位置的重复追问、右侧不开机仍套弱吸力、缺物流标识后原句重复、缺凭证后任务误分类，以及没烘干仍推烘干流程。

## 本轮有效行为与知识边界

[T22](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T22.md>)/[B06](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/B06.md>) 保留并选取平地报错分支；[T46](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T46.md>)/[B07](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/B07.md>) 的独立问句能承接连续噪声回答；[T48](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T48.md>)/[B09](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/B09.md>) 补型号后实际查询仍是绿灯问题；[T52](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T52.md>)/[B11](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/B11.md>) 保持充电盒自身为充电主体。这些是本轮路径证据，不代表所有变体已经稳定通过。

[T35](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T35.md>) 的咨询 answered 与 SQL consult_answered 一致，已撤销仅凭 intake/draft 阶段作出的初步疑点。[B15](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/B15.md>) 过保后诊断仍保持 active，未被换货案件终点覆盖；但 T53 后续承诺缺陷仍存在。

[T13](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/conversations/T13.md>) 的 5116 对应资料未命中时真实交接；T48 未找到绿灯依据时明确说明未知。处理边界合格，但对应错误码和绿灯含义仍未得到知识解答。T9/T45 的 awaiting_human 表示已进入人工队列，不表示人工已办理。

## 执行与证据

官方案例共 135 次交互，分支 36 次，共 81 个唯一会话、171 次交互、2456 个事件。全部交互有完成事件，事件通过契约校验，0 对话错误。原文与 Excel、附件哈希一致，81 个会话最终审计均完整。B02 首次异步审计读取 404，原记录保留；只读补采同会话恢复，没有重跑模型覆盖结果。

官方运行时间为 11:18:09–11:20:58，分支为 11:21:11–11:22:34（Asia/Shanghai），并发为 3。调用实际 HTTP 服务、模型和知识库；后续客户反馈由测试器模拟，没有执行设备动作。

官方运行期间 HEAD 从 0a2adde 变为 6af9e989；已加载的业务修改被其他会话提交，容器身份与业务、契约、配置、官方 YAML 的字节指纹始终不变。分支期间 HEAD 与字节指纹都不变，判断对应这一轮运行代码。

事前判据沿用原意对象、资料适用性、业务安全边界、下一步可反馈和状态承诺一致五项；同一评审者看过历史，不能称盲测。本轮没有重做历史 R 层的 5 个重复首轮，因此不报告重复稳定性，也不直接比较不同口径的历史通过率。

证据入口：

- [官方 63 案逐案复核](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/review.md>)；[18 个固定分支复核](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/branches-review.md>)。
- [汇总指标与判断哈希](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/metrics.json>)；[协议、来源与版本校验](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/verification.json>)。
- [事前评分方法](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-0932_method-audit-full-evaluation/method.md>)；[原文及附件来源审计](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-0932_method-audit-full-evaluation/source-audit.json>)。
- [本轮冻结计划](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/plan.md>)；[方法补充及勘误](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-1117_official-63-retest/addendum.md>)。
