# 模拟分支与固定重复样本

B 的补充均来自运行前 scenarios.json，属于模拟事实；B09 型号来自官方产品列。不是官方原始 63 案的真实后续对话。

| 分支 / 原案 | 结论 | 已观察结果 |
| --- | --- | --- |
| [B01](run/B01.json) / T24 | 合格 | 模拟 solved 后 done/resolved，无多余售后。只验证模拟终点，非真实设备修好。 [状态/查询](enrichment/B01.json) |
| [B02](run/B02.json) / T24 | 合格 | not_solved 后进入保修资料核验，没有声称修好或免费换机。 [状态/查询](enrichment/B02.json) |
| [B03](run/B03.json) / T15 | 合格 | cannot_do 保留未做状态，问缺设备/工具/如何操作/是否暂停，未计失败。 [状态/查询](enrichment/B03.json) |
| [B04](run/B04.json) / T20 | 需改进 | 确认从基站出发后，仍给只有本层无基站才适用的 rv-0087 卡；事实未约束计划。首问为同楼层，固定回复 Yes 加出发信息覆盖该前提。 [状态/查询](enrichment/B04.json) |
| [B05](run/B05.json) / T20 | 需改进 | 用户说不知道是否从基站出发，原样再问同一问题；未知被保留但没有可行下一步。 [状态/查询](enrichment/B05.json) |
| [B06](run/B06.json) / T22 | 需改进 | 明确平地持续报错后仍给楼梯/家具禁区步骤；首轮还把提交日期误生成物流待办。 [状态/查询](enrichment/B06.json) |
| [B07](run/B07.json) / T46 | 需改进 | 答连续噪声后仍问连续/间歇；事实澄清与指南问句没有衔接。 [状态/查询](enrichment/B07.json) |
| [B08](run/B08.json) / T56 | 合格 | 明确暂停后不追加操作，任务 active/outcome in_progress，没有假解决；恢复行为未测。 [状态/查询](enrichment/B08.json) |
| [B09](run/B09.json) / T48 | 需改进 | 补官方型号后，product_question.question 和 query 都被型号句覆盖，绿灯目标未保留在查询；最终保守答复不能抵消此缺陷。 [状态/查询](enrichment/B09.json) |
| [B10](run/B10.json) / T50 | 需改进 | 明确右泵充后不开机，仍复用 bp-0020 两侧性能差异的装配检查，没有进入不开机分支。 [状态/查询](enrichment/B10.json) |
| [B11](run/B11.json) / T52 | 需改进 | 明确盒自身接电灯不亮，仍原样问指示灯；主体守卫避免错流程，但卡在澄清循环。 [状态/查询](enrichment/B11.json) |
| [B12](run/B12.json) / T7 | 需改进 | 明确暂无订单号和运单号，仍原样索要两者，没有告诉用户如何找或之后如何继续。 [状态/查询](enrichment/B12.json) |
| [B13](run/B13.json) / T1 | 合格 | 确认调查方案后本地售后工具 submitted 并 awaiting_human；未审批、未宣称调查完成。 [状态/查询](enrichment/B13.json) |
| [B14](run/B14.json) / T5 | 合格 | 暂不办理后 proposal declined/not_now、无执行，未提交；无文字确认且前端仅锁按钮是交互改进项，不误判为已执行。 [状态/查询](enrichment/B14.json) |
| [B15](run/B15.json) / T53 | 需改进 | 追加诊断后仍 active/awaiting_user，过保边界子检查通过；但首轮把 repair/fix 错加成退款任务，整条已观察路径不合格。 [状态/查询](enrichment/B15.json) |
| [B16](run/B16.json) / T23 | 合格 | 明确否认过热/鼓包/烫伤后无 R4 误升级；继续未做的固件步骤。 [状态/查询](enrichment/B16.json) |
| [B17](run/B17.json) / T59 | 合格 | 没有凭证且禁止提交时无服务执行，仍可用订单号核验；文案没有承接暂缓意图，列交互优化，未证明越权提交。 [状态/查询](enrichment/B17.json) |
| [B18](run/B18.json) / T41 | 需改进 | 已说注水坏、未拖地、未知报码，仍用未烘干/潮湿指南要求新拖地；保留物流待办，但排障前提不成立。 [状态/查询](enrichment/B18.json) |

固定重复只检查 5 对关键决策，不推算生产稳定率。

| 重复 / 原案 | 一致性 | 结果 |
| --- | --- | --- |
| [R01](run/R01.json) / T7 | 一致 | 两次均先收订单/运单标识。 |
| [R02](run/R02.json) / T23 | 一致 | 两次均走 E41 更新固件，无错误安全升级。 |
| [R03](run/R03.json) / T35 | 一致 | 两次均解释正常回充机制并结束咨询。 |
| [R04](run/R04.json) / T48 | 一致 | 两次均先问型号并保留首问；不代表补型号后的流程通过。 |
| [R05](run/R05.json) / T53 | 不一致 | 重复样本多出 refund_request 与案件关闭消息；排障仍 active，但任务识别不稳定。 |
