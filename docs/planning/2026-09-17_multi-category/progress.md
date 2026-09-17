# 进度

## 2026-09-17

- 读官网 anker.com.cn/brands，确定五大产品线与品类口径；盘点代码里全部单品类假设（findings.md）。
- 用户确认分层：7 个深度品类 + 13 个目录品类；入库并实机验证；「历史不合理的规则、文案可以清理重建」。
- 代码改造：taxonomy 按品类分组、去掉 robot_vacuum 兜底与写死文案、FAQ 多文件、policy 品类反查、前端品类入口。
- 资料：products 20 品类 57 SKU；6 个新品类的 taxonomy / plans / fault cards / 手册 / FAQ / 工单。
- 回归：后端 897 passed（含活 WeKnora）；前端 214 passed；`make kb-anchors` 全绿。
- `make kb-ingest`：+186 条，errors 0；`make up` 重建；9 个品类一句话 smoke 全部走到预期路径（implementation.md §4）。
- 修正：吸奶器词表补「吸力变小 / 吸力下降」；目录级品类的结束原因独立为 `category_coverage_missing`；
  更正症状时按 issue 品类归一（改动前并集会把「吸力下降」同时归到扫地机与吸奶器）。
- 待：ci-local 最终结果、提交与发布（等用户）。

## Errors

- `make up` 在 orchestrator 目录下跑成「No rule to make target」，容器没重建，第一次 smoke 仍是旧挂载；改用 `make -C <repo>`。
- 实机 smoke 紧跟 run 结束就查 journey 拿不到 session（facts 投影异步落库），脚本改为轮询。
