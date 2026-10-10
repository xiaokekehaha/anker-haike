# 评测本地产物忽略规则

问题：现有 `docs/planning/2026-10-09-*/**/*.json` 只匹配 10 月 9 日的目录，截图中的 `2026-10-10-0932_method-audit-full-evaluation/enrichment/T20.json` 未命中。该文件未被 Git 跟踪，问题来自日期范围。

方案：补充 `docs/planning/2026-10-10-*/` 下 JSON、Python、日志、diff、txt、jpg、jpeg、png 的递归忽略规则，沿用 10 月 9 日的产物范围。Markdown 文档继续可被 Git 收录。保留 `.gitignore` 已有修改。

验收：`git check-ignore -v` 命中截图中的 T20.json、评测根目录的 JSON 与 Python 文件、复现目录的 JSON；Markdown 文件不命中。通过 `git ls-files --others --exclude-standard` 确认上述目录只剩 Markdown 文档；通过 `git diff --check` 检查改动。

追加范围：用户要求继续忽略官方 63 单复测产生的原始会话 Markdown。新增 `docs/planning/*_official-63-retest/conversations/`，按任务名称匹配，避免下一次复测因日期变化漏掉记录。规划、进度、报告与复核 Markdown 继续可被 Git 收录。

追加验收：`git check-ignore -v` 命中 `2026-10-10-1117_official-63-retest/conversations/B01.md`、`B18.md`、`T1.md`、`T63.md`；`plan.md`、`progress.md`、`report.md` 和 `review.md` 不命中。该目录的未忽略文件列表不再出现 `conversations/`。

后续范围统一：用户明确要求后续同类记录都可以忽略。将上述特定任务规则替换为 `docs/planning/**/conversations/`，覆盖任意日期、任务名和分轮嵌套目录中的原始会话。文件保留在本机，目录外的规划与报告文档继续可被 Git 收录。

后续验收：检查 `2026-10-10-1550_official-63-latest-review/conversations/` 中的 B、R、T 类记录均命中；用未来日期与新任务名路径验证通用规则；确认规划目录内不存在未忽略的 `conversations/` 文件，报告与规划文件不命中。只调整忽略规则，不删除文件或修改 Git 索引。
