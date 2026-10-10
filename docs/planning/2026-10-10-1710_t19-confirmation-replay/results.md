# T19 确认问句真实回放

时间：2026-10-10 17:10–17:15（北京时间）。代码：HEAD 0a93d9c 加未提交的 rv-0023 覆盖改动；
`docker compose up -d --build orchestrator` 后串行回放，restart 计数 0，容器内 `qa_overrides.yaml` 与工作区 sha256 一致。
驱动：临时脚本（已删除），原文首发 → s1 固定「未解决」→ s2 按预设选项作答。每个选项一次，不代表稳定率。

| 会话 | s1 未解决后 | s2 作答后 | 结论 |
| --- | --- | --- | --- |
| T19-fine a246da9ba81e4768afd6b5f71d2b3281 | 出 s2 question 卡，两个选项，无可见文字 | 「To check the warranty I'll need your order details…」，stage=context，待上传凭证 | 通过 |
| T19-broken 651ffa844e8848bdaa392cc810c36bf9 | 同上 | 同上 | 通过 |

对比改动前（a38bbab1154c4b19b65b245e6c867053）：s1 未解决后直接发「If there are no abnormalities in the above steps … hardware problem」
并索单；现在不再出现这句条件结论，前提由客户选项确认后才进质保。

## 遗留

- 两个选项之后的可见文字相同：只有「To check the warranty…」，没有一句说明为什么进售后（`hardware_basis` 只覆盖 diagnose_outcome=warranty）。
  密封圈损坏一支也没有提示后续会要照片。属于 spec 里列的「不做」，待决定。
- run 3 的 apply_action rule 仍记为 R1（guide_exhausted 兼容码）。
- 两次会话的完整记录：`T19-fine.json`、`T19-broken.json`。
