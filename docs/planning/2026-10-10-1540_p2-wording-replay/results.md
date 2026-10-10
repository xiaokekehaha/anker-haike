# P2 真实回放结果

时间：2026-10-10 15:30–15:40（北京时间）。代码：HEAD 99cc1da 加上未提交的 P2 改动；`docker compose up -d --build orchestrator` 后串行回放，restart 计数 0。驱动同 `docs/planning/2026-10-10-1440_p0-guard-replay/plan.md`。

| 会话 | 改动前（1321 轮） | 本次 | 判定 |
| --- | --- | --- | --- |
| T9 | 暂缓已交人工，又说「It will be sent on the expected ship date」 | 「its original expected ship date is shown above. Whether it is held or cancelled is up to the colleague handling your request.」 | 通过 |
| T14 | 「it's covered by warranty service rather than further troubleshooting」 | 「the next step is an after-sales review …; whether it's covered by warranty depends on the check below」 | 通过 |
| T58 | 首封抱怨回「I'm sorry we haven't solved this yet」 | 「I'm sorry about the trouble with your device. Tell me what it is doing …」 | 通过 |
| B11 | 盒自身灯不亮后发 bp-0025「长按泵电源键 12 秒」 | 第二轮问「Have you tried a different charging cable or power adapter to charge the case?」，不再发泵重置卡 | 通过 |
| B17 | 第二轮带「replacement request → order details」 | 不再有 order details；但出现「replacement request → device troubleshooting」 | 部分，见下 |
| T40 | rv-0073 操作卡混材料请求，未解决后直接收凭证 | 三次回放模型都选 rv-0371（statement + 资料缺口）→ R5 交人工，未发 rv-0073 卡 | 未覆盖 |

## 未覆盖与新发现

- T40：新卡文案（`ACTION_WITH_MATERIAL_EXPECTED`）只有单测验证。本次三次 synthesize 都给 rv-0371 supported 0.72、rv-0073 needs_confirmation 0.6；1321 轮同一原文选的是 rv-0073。rv-0371 原文只有一句说明加「Suggested troubleshooting steps can be found at:」（链接缺失），走资料缺口直接交人工，比 rv-0073 的路径少了排障。这是候选排序的随机性，不是本次改动引起，未处理。
- B17：第二轮模型把第一轮原话重新解读成 report_problem + replacement_request（request_quotes 引的是第一轮文字，不在本轮原话里），于是出现新的排序提示。order_query 已按本次规则去掉。引文不在本轮原话里的诉求没有校验，属于另一个问题，未处理。
- 每单一次（T40 三次），不代表稳定率。
