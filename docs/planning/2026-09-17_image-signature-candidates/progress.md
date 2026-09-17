# 进度

## 2026-09-17

- 复现：用 `2026-09-15_evidence-next-action/smoke.py` + `data/demo-photos/1_滚刷缠绕_正常曝光.png` 重放 9db 序列，
  会话 10c5eeaf46004f2dbdf951fd0d4d65e4：无 R7，但三问品类、末轮只剩 `rv_suction_motor_fault`。
- 定位：`fault_localization` 全程在状态里；被 `symptom_codes` 过滤挡在候选集外（三处过滤都只读 kind=symptom 事实）；
  `category_hint` 关键词无部件词。详见 findings.md。
- 实现：
  - `config/vision_vocab.yaml` → 2026-09-17.1，新增 `category_parts`。
  - `app/diagnose/localization.py`：`signature_matches`（按 finding 归因）、`part_categories`；`signature_plans` 改为其上的去重。
  - `app/sessions/graph.py` vision 节点：部件推品类并入 `visual_product` 候选；签名命中的 plan 症状码写成
    `kind=symptom / source_kind=image_signature` 事实，按 value 去重；retrieve 处的内联 import 收到顶部。
- 回归：`test_l3_experience.py` +1（配置一致性 + part_categories + signature_matches），
  `test_conversation_evidence_next_action.py` +2（9db 序列全路径：品类确认问句、症状事实唯一、codes 双码、候选含双计划、末轮步骤卡；
  通用部件不产生线索）。两文件 35 passed。
- 相邻十个套件 164 passed；`make lint` 通过。
- `make up` 重建镜像（10:55），实机重放会话 97f56692c3574b91b916918837e1a1c9：首轮即「是扫地机器人吗」确认句，
  末轮候选五计划含 hair_wrap 与 motor_fault，步骤卡为 `rv_suction_hair_wrap s1 检查并清理滚刷`，无 R7。详见 implementation.md §4。
- `scripts/ci-local.sh` 全绿：ruff / db-check / pytest 895 passed / contracts 94 / 前端 214。
- 未提交 git commit。
