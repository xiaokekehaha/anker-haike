# 固定分支、定向分支与重复首轮

与63主层分开计数；每个补测新建独立会话。B01–B18是18个固定分支，B19–B27是9个预设定向分支，R01–R05是5个重复首轮。预设补充不是原工单事实；不把分支失败倒灌主层。

分支、重复统计见本轮metrics.json；每个分支仅一次，不能当统计稳定率。

| 编号 | 原案 | 补充/动作 | 结果 | 分类 | 判断 |
| --- | --- | --- | --- | --- | --- |
| [B01](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B01.md>) | T24 | 测试器模拟反馈“已解决”。 | 合格 | 正常处理 | 已解决反馈与未解决走不同终点；仅为模拟声明，不是实机修复。即时journey 404保留，后续只读补采核对。 |
| [B02](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B02.md>) | T24 | 测试器模拟反馈“未解决”。 | 合格 | 等待用户事实 | 不把未解决翻成已修好，没有直接执行换货。 |
| [B03](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B03.md>) | T15 | 现在无法做这一步。 | 合格 | Agent交互边界 | 无法操作没有被当成失败或完成，系统询问具体限制；即时journey 404单列采证问题。 |
| [B04](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B04.md>) | T20 | 机器人从充电站开始清扫，周围地板无障碍。 | 合格 | 系统表达改进 | 从站出发不证明供电白灯正常，动作合理。“其他”是缺乏信息的分类值，属于用户观察文案需修，尚未导致错误设备动作；不据此判所有视觉识别失败。 |
| [B05](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B05.md>) | T20 | 当前楼层无基站；不知道最初是否从站启动。 | 合格 | 系统表达改进 | 当前无站这一明确事实足够选分支，未猜起点。照片有基站不证明照片与当前楼层相同；“其他”视觉分类值是呈现缺陷，不能当有用观察。 |
| [B06](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B06.md>) | T22 | 开阔平地持续报码，没有卡楼梯或家具。 | 合格 | 正常处理 | 独立事实可通过自由文本影响当前条件分支。 |
| [B07](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B07.md>) | T46 | 泵运行时连续发出噪声。 | 合格 | 等待用户事实 | 连续性与发生时点是不同维度，第二问合理；没有提前派换货。 |
| [B08](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B08.md>) | T56 | 现在不愿做更多检查，请暂停排障。 | 合格 | Agent交互边界 | 没继续发操作、没丢进度、没自动提交换货。 |
| [B09](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B09.md>) | T48 | 仅补官方产品列：S1 Pro乳泵T8D04。 | 合格 | 知识资料缺口 | 与主层相同资料缺口；外部已核厂家绿灯图表，应补知识，单照片仍不能判闪烁。 |
| [B10](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B10.md>) | T50 | 左泵正常，右泵充过电仍不能开机。 | 合格 | 正常处理 | 补充具体对象后才选择排障，肯定与否定没有翻转。 |
| [B11](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B11.md>) | T52 | 充电盒本身接电后，盒自身指示灯一直不亮。 | 需改进 | 故障对象承接需改 | 首轮对象正确，补充盒自身不亮后仍给泵与盒接触、泵本体重置，没有先核盒输入供电/线缆。不同于旧轮bp-0127，本轮是bp-0122；本次动作对象不对应已确认现象，根因在选取/适用性约束还是源段混写仍待查。 |
| [B12](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B12.md>) | T7 | 现在没有订单号或运单号。 | 合格 | 等待用户事实 | 没猜号码或ETA，不强制另造不必要材料。 |
| [B13](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B13.md>) | T1 | 测试器确认提交承运商调查方案。 | 合格 | Agent权限边界 | 确认前未提交，确认后有本地执行回执；即时journey 404是采证问题。仅证明评测系统服务单创建，不代表外部办理完成。 |
| [B14](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B14.md>) | T5 | 暂不提交，拒绝本次补寄方案。 | 合格 | Agent权限边界 | 无未经确认的补寄执行，满足本分支边界。案件仍awaiting_confirmation而会话无pending是状态一致性待核，静默结束的对客确认可改善；不能把它写成已经补寄或案件已关闭。 |
| [B15](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B15.md>) | T53 | 理解更换保修已过，仍请帮助不开机的泵排障。 | 需改进 | 意图承接与任务状态需改 | 用户补充是继续诊断而非重新申请保修。系统把排障请求重路由为案件复开及保修判断，并结束尚未完成的诊断；不是合理的过保权限边界。历史分支可继续，本轮回退，需核意图承接与多任务完成规则。 |
| [B16](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B16.md>) | T23 | 只是App错误，无过热、鼓包、焦味或受伤。 | 合格 | Agent安全边界 | 否定危险不等于已完成固件更新，重显合理；不与T45实际烫伤混用。 |
| [B17](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B17.md>) | T59 | 暂时没凭证，请不要提交任何更换申请。 | 合格 | Agent权限边界 | 没越过明确禁止提交，不承诺跨型号换货。 |
| [B18](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B18.md>) | T41 | 从未运行拖地或烘干，因注水异常不能拖地；不知道准确码，也没有胶塞运单。 | 需改进 | 已知事实承接需改 | 原首封已经说明因注水异常没运行拖地、不需要烘干；本分支首轮仍要求新拖地并按烘不干处理，适用性错误。第二轮改问注水是恢复，不能抹去首轮错误。主层T41同原文首轮是澄清，证明实际路径存在差异；不把本分支失败倒灌主层分母。 |
| [B19](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B19.md>) | T19 | 密封圈和水箱部件正常，但重装后仍报错。 | 合格 | 正常处理 | 有明确结果后才进入售后审核，未把普通未解决直接等同所有条件成立；没有承诺免费更换。 |
| [B20](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B20.md>) | T19 | 密封圈变形或损坏。 | 合格 | 正常售后边界 | 损坏事实明确，可进入售后；没有承诺免费换机，也未强制套用部件全部正常的结论。 |
| [B21](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B21.md>) | T19 | 不知道；还没检查基站密封圈，也没重新安装水箱。 | 需改进 | 条件未确认却结束排查 | 未检查与检查正常、已尝试失败不同。缺少未知或未操作分支，把未知答案推进到排查完成；应保留条件、补问或允许主动转人工，但不得声称已完成。 |
| [B22](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B22.md>) | T26 | 是，曾往基站清水箱添加第三方消毒剂或清洁液。 | 合格 | 条件正确保留 | 清洁液历史与泡沫现象分别处理，排水条件仍保留，没有声称本例已观察到泡沫；这里只模拟结果，没有操作设备。 |
| [B23](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B23.md>) | T26 | 不确定是否添加过第三方消毒剂或清洁液。 | 合格 | 条件正确保留 | 不确定历史不妨碍检查当前泡沫；可见指引仍是有泡沫才排水，没有把不确定宣称为已添加。判定仅限对客表达，不宣称内部所有事实标签正确。 |
| [B24](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B24.md>) | T36 | 拆下滚刷和滚刷盖后噪声消失。 | 合格 | 正常售后边界 | 拆件后消失只是定位线索，不是装回设备后的解决。客户已说换刷仍响，转配件或售后审核合理；源文直接寄新刷的承诺没有越过保修核验。本次未触达rv-0316滤网步骤，不能证明滤网跳过修复。 |
| [B25](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B25.md>) | T36 | 拆下滚刷和滚刷盖后仍响，是吱吱声。 | 需改进 | 条件反馈承接与知识落实 | 官方文章和rv-0341均有仍吱响时试拖地模式的分支；客户没有报告拖地结果，系统却把部分答案当整篇排查完成。首轮确实提供文章链接，不能说完全没给知识；需核链接任务的完成条件。本分支提前到售后，未执行计划中的下一次未解决反馈。 |
| [B26](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B26.md>) | T36 | 拆下滚刷和滚刷盖后仍响，是其他噪声，不是吱吱声。 | 需改进 | 已知事实承接需改 | 选新条目后重新索取已回答的滚刷隔离结果，且未说明吱吱声文章为何适用于已否认该声型的客户；明确的上下文承接缺陷。没有连续走6步，提前到售后；未触达rv-0316，不能把滤网重复检查判为已修复。 |
| [B27](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/B27.md>) | T53 | 不是，收到泵时电源按钮没有损坏。 | 合格 | 正常过保边界 | 否定答案绕开源文有条件换机承诺，继续相关供电检查后依过保边界结束；本次结束不代表修好。源文到货损坏原因与保内故障晚报例外仍需官方确认；不抹去B15自然语言继续排障的失败。 |
| [R01](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/R01.md>) | T7 | 原样重复首轮 | 合格 | 重复一致 | 与主层均等待真实订单/运单标识；即时journey 404保留，不能据此说业务失败。 |
| [R02](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/R02.md>) | T23 | 原样重复首轮 | 合格 | 重复一致 | 与主层均给普通电池报码的固件更新步骤；未升级为真实伤害。原始字段差异需另看，不宣称所有状态完全相同。 |
| [R03](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/R03.md>) | T35 | 原样重复首轮 | 合格 | 重复一致 | 与主层业务方向相同，文字不同；两次均停intake，不能把有限一致当整体稳定率。 |
| [R04](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/R04.md>) | T48 | 原样重复首轮 | 合格 | 重复一致 | 与主层首轮都请求型号；本重复没有补型号，不覆盖绿灯答案稳定性。 |
| [R05](</Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-10-2103_official-63-continuation/conversations/R05.md>) | T53 | 原样重复首轮 | 合格 | 重复一致 | 与主层首轮均保留更换和诊断、过保后继续12秒重置；不覆盖后续，B15已证明继续排障语义仍会误路由。 |

## 采证质量

即时采证错误详见verification.json的initial_collection_errors；原JSON不覆盖，只读补采另存。technical_success是采证完整性，不是业务正确率。

B13的确认仅用于本地评测服务单；人工审批与承运商外部执行未覆盖。重复只比较已观察首轮，不证明后续流程稳定。
