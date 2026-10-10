# 官方 63 单复测 P2：措辞不预设事实、充电盒对象、材料与操作分开

来源：`docs/planning/2026-10-10-1321_official-63-continuation/ambiguities.md` 的 A03、A05、A27、A29、A19，以及 P1 回放发现的 B17 多余排序句。都是低成本的文案或单点约束。

| 编号 | 问题 → 例子 | 方案 | 位置 |
| --- | --- | --- | --- |
| A03 T9 | 暂缓发货已交人工，物流结论又说「It will be sent on the expected ship date」 | 任务队列里有等人工的 order_change 时，预售结论改为「原计划日期见上，是否暂缓由同事确认」 | `backends/logistics.py` `sop_text(change_pending=)`，`sessions/l3.py` consult |
| A05 T14/T42 | 「it's covered by warranty service rather than further troubleshooting」读起来像已确认在保 | 改为「next step is an after-sales review …; whether it's covered by warranty depends on the check below」 | `sessions/l3.py` `HARDWARE_BASIS` |
| A27 T58 | 首封只有抱怨，回「I'm sorry we haven't solved this yet」预设了服务历史 | 没有任何步骤反馈和案件时改为请客户描述现象或选人工 | `conversation/reply.py` complaint 分支 |
| A29 B11 | 充电盒自身接电不亮，候选 bp-0025「泵开不了机」通过，发「长按泵电源键 12 秒」 | 标题没有充电关系时，若客户说的是充电盒自身不进电而标题不提 case，判对象不同，走已有的充电对象澄清 | `diagnose/charging.py` |
| A19 T40 | rv-0073 操作卡顺带要照片 / 视频，客户点「未解决」被当成材料也处理完了 | 操作步骤正文含材料请求（官方库 25 段）时，卡片预期结果写明「是否解决」和「上传材料」是两件事。只改显示，不拆步骤 | `plans/qa.py` |
| B17 | 「I don't have my receipt right now」被读成 order_query，回复前多出「replacement request → order details」 | 并列查询的引文是「没有 / 找不到 + 单号或凭证」且不是问句时，不算独立查询 | `conversation/request_constraints.py` |

可选未做：T40 把材料请求拆成独立的 material_request 节点（需要改 Q&A 段落拆分，25 段都受影响）；本次只做显示层区分。

测试：`orchestrator/tests/test_p2_wording_and_objects.py`。真实回放：`docs/planning/2026-10-10-1540_p2-wording-replay/results.md`。
