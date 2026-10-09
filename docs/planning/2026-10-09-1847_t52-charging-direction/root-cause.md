# T52 充电方向根因

结论：没有证据表明意图路由或检索改写把问题换了。直接错误发生在 diagnose.synthesize 的方案适用性判断；服务端只比部件名称，且候选名称仍由同一模型填写，不能独立验证供受电关系。事实抽取的症状压缩和因果关系缺失增加了误判风险，但单独恢复完整症状不能修复漏洞。

本轮只分析，未修改应用代码、评测标签或测试。未调用真实模型和知识库，数据库只读。

## 第一轮实际追踪

18:43:26，session 7e5bfac6635344629763f105b5602b55：

1. 用户原句：My charging case will not charge therefore I cannot charge my pump motors. I am an exclusive pumper
2. intake 输出 primary_intent=report_problem。事实 value=will not charge，subject=charging case，quote=My charging case will not charge，polarity=affirmed；未抽出第二句因果结果。
3. query.py 将 subject 拼回检索词，实际 query=charging case will not charge。rewrite_decision.triggered=false，reason=disabled。
4. 召回 bp-0067「泵在盒内不充电」和 bp-0039「充电盒不给泵充电」。模型可见的片段标题和首步已经包含方向，不是只看到了模糊的 charging 关键词。
5. synthesize 实际输出 qa_bp_0067：applicability=supported，supported_symptoms=[will not charge]，matched_subject=charging case，matched_timing=null，confidence=0.72。rationale 为「充电盒不充电，先查泵与盒内磁吸充电口对位及指示灯」。qa_bp_0039 也写 matched_subject=charging case，confidence=0.6。
6. filter_hypotheses 放行上述两条；本轮 dropped 仅包含另一个候选 qa_bp_0122 的 subject_mismatch。guide 发 qa_bp_0067 的第一步：对齐泵充电针与盒内磁吸端口。

记录：[model-evidence.json](model-evidence.json)、[checkpoint-evidence.json](checkpoint-evidence.json)。模型日志中的一个证据 ID 数字尾段被原有脱敏器遮蔽；相关文档关联以 checkpoint 为准。

## 为什么当前修复挡不住

供受电关系指「谁给谁充电」。充电盒可以同时是电源→盒子的受电方和盒子→泵的供电方，两种关系都包含 charging case，部件名称相同不能证明关系相同。

- `synthesize.py:233`：只有用户 subject 和模型 matched_subject 均非空，才执行对象核对；模型留空便跳过。
- `synthesize.py:164`：两个字符串相同或互相包含直接返回无冲突。charging case 对 charging case 不拦；对 pump in the charging case 也不拦。
- `synthesize.py:170`：后续中心词核对仍是部件名称核对，不表示施动方、受动方或供电方向。
- `synthesize.py:97`：timing 校验只实现提前发生与未能启动的词表冲突；字段描述虽然提到方向，但没有充电方向判断。
- `filter_hypotheses` 没有从真实 Plan / 官方文档读取独立的充电适用条件。它校验了合法 plan_id、证据 ID 和症状字符串，却没有验证该证据确实支持用户的这一动作关系。matched_subject 和 applicability 由同一个模型一起给出，错误解释可以共同通过。

Plan 当前包含 fault、applies_to、symptom_codes、steps，没有供受电关系或入口现象的结构化条件。事实只有 subject、value、polarity、timing，也未表达 therefore 的因果依赖。后一轮即使抽出两条症状，仍只是两条平级事实。

## 离线单变量验证

将第一轮真实模型假设和真实事实送入当前 filter_hypotheses，固定方案与证据。synthesize.py 与两轮运行版本指纹均为 7dd49807dca1a5c590165ed811afafffe8e68718b2883ffae2c4b1b90aaf7f83。

| 输入变化 | 结果 |
|---|---|
| 原始模型输出，matched_subject=charging case | 错误方案保留 |
| 仅将 matched_subject 改为 pump hub | 拦截，生成盒子自身问题的澄清 |
| 仅将 matched_subject 改为 pump in the case | 拦截 |
| 仅将 matched_subject 留空 | 错误方案保留 |
| 仅将 matched_subject 改为 pump in the charging case | 错误方案保留 |
| 仅将 matched_subject 改为 charging case is not charging the pumps | 错误方案保留 |
| 对照：在双方 timing 显式写入相反充电方向 | 错误方案保留 |
| 将真实 value 及 supported_symptoms 一起恢复为 charging case will not charge | 错误方案保留 |

健康断言运行 exit 1：T52 actual recorded hypothesis still releases the case-to-pump plan。机制对照再次运行 exit 0，所有上述结果断言通过。未改实现，健康断言失败是本次分析的预期结果。

数据：[reproduction-results.json](reproduction-results.json)。临时读取和回放脚本已删除。

## 第二轮为什么澄清也偏了

18:47:26，session 533c18bcc0184415b8ada2479197932f；synthesize.py 指纹与第一轮相同，但其他应用文件存在变更，两轮不能当作全应用完全相同的随机重复实验。

intake 抽出 charging case will not charge 和 cannot charge pump motors 两条事实，主语分别是 charging case 和 pump motors。模型仍把 qa_bp_0039 判 supported，matched_subject=charging case，声称覆盖两条症状。

核对第一条事实主语相同，不冲突；核对第二条事实时，pump motors 对 charging case 被判部件不一致。代码把这个第二条事实的主语塞进通用澄清模板，最终问「Is the problem with the pump motors itself ...」。这条问句可由保存的第二轮模型输出和真实事实精确复现。

因此，第二轮只是通过另一条部件冲突停住了，并未证明系统理解了盒子输入供电失败这一首要问题。不能只验收 clarify 终点。

## 为什么回归没有挡住

运行 `cd orchestrator && uv run pytest -q tests/test_applicability_facts.py -k 'subject_level_mismatch or subject_contained or part_level'`：3 passed，21 deselected，0.42s。

- 第84行 T52 回归人工填写 matched_subject=pump in the case，提前提供了模型实际没给对的候选解释；只证明正确候选解释下名称不同会被拦。
- 第97行 test_subject_contained_in_candidate_is_fine 使用同一个 qa_bp_0067、同一个盒子自身不充电事实，matched_subject=charging case，明确断言方案应保留。它把这次真实失败路径写成了通过条件。
- 当前 first_card_forbid 能发现这次错误首卡，但同一案例到达 clarify 时，还需要检查问句是否保留盒子自身受电失败，不能只看流程终点。

## 必要修复边界

1. 事实保存完整现象，表达受影响对象和主要故障；避免把「因此泵无法充电」平铺成独立故障后抢走诊断焦点。
2. 从官方候选标题/正文建立可追溯的供受电适用条件，例如区分「盒子接收充电失败」和「盒子给泵充电失败」。候选条件不能再由选方案模型用一个自由主语字符串自行证明。
3. 服务端检查这一关系是否被用户事实支持；缺必要关系按未知处理，同名、包含或字段为空不能自动放行。如果原句仍有歧义，澄清围绕盒子插电后的输入供电/指示灯；原话已明确的事实不重复询问。
4. 回归使用本次真实误判输出，覆盖同名、包含、空主语、两条因果症状及澄清主语；修正把错误路径当成正例的测试。

额外模型调用、更大检索数量、专门针对 bp-0067 的禁止列表都不是修复该验证漏洞的必要条件。是否存在更合适的盒子自身供电官方条目、召回排序能改善多少，本轮未做全库验收；不能把最终错卡直接归因于缺知识或检索改写。
