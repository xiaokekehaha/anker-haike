# 票 42：bake-off 评测与模型 ID 冻结

## 目标
一条命令对 models.yaml 每个 task 链上的候选模型跑金标样本（3 遍取中位数），输出 Schema 通过率 / 字段准确率 / 延迟 P50 / 成本四项并与门槛比对（model-selection §3.8），据结果冻结真实模型 ID 并写入 RELEASE.md。

## 阶段
1. 厂商现状核对（DeepSeek 实测 + 各家价目 / ID 文档） — complete
2. `app/bakeoff/` 评测包（样本加载、按别名单链调用生产函数、评分、报告）+ `haike-bakeoff` CLI — complete
3. 金标样本 `tests/fixtures/bakeoff/`（文本 task ≥ 20 条；视觉 task 15 张合成图 + 可选本机真实图目录） — complete（文本 88 条、视觉 30 张）
4. 假模型离线测试 + DeepSeek 单家真实实测 — complete（13 项单测；3 遍实测见 findings）
5. models.yaml 冻结（去 TBD、加 `params`）、release.sh bake-off 行、findings「bake-off 结果」 — complete

## 约束
- 只新增 `orchestrator/app/bakeoff/`、`orchestrator/tests/fixtures/bakeoff/`、`orchestrator/tests/test_bakeoff.py`、`config/bakeoff.yaml`；`app/models/config.py` / `registry.py` 只追加 `params` 字段透传；不改 `app/sessions/`、`app/guide/`、`app/observability/`。
- 评测调用复用生产函数（extract_intake / make_question / synthesize / observe_images / extract_receipt / polish_summary / rewrite_query / ModelRouter.stream），保证「评测的就是线上会跑的 Prompt 与后过滤」。
- 图片不落仓库（tests/test_images 扫描禁止）：视觉样本运行时用 Pillow 合成；真实照片走 `BAKEOFF_IMAGES_DIR`。

## Next Step
其他厂商 key 到位后 `make bakeoff` 补跑两家对比并按 judge 结果调主备；真实故障 / 凭证照片放 data/bakeoff-images/ 替换合成图；票 32 扩同义表后重跑 query.rewrite。
