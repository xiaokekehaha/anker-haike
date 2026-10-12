# 忽略评测运行 JSON

- 需求：`reports/eval/` 下的评测运行 JSON 只留本机，后续同类产物默认按此处理。
- 实现：`.gitignore` 增加 `/reports/eval/**/*.json`，覆盖任意日期及目录深度；`AGENTS.md` 记录主动维护忽略规则的约定。
- 范围：保留结论文档；已有跟踪文件不在本次移除。
- 验收：截图中的三个评测目录下 JSON 全部命中忽略规则，Markdown 和目录外 JSON 不受新增规则影响。
