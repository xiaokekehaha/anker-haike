# 进度

## 2026-09-14

- 工作树核查：`diagnose.vision` 现状（含未提交的 `FaultLocalization` / `vision_vocab.yaml` / `localization.py`）、`models.yaml` 视觉链、bakeoff `score_vision`、graph 的 `route_after_vision`。确认 `data/eval/vision/cases.yaml` 尚不存在，bakeoff 跑的是 Pillow 合成图。
- 三路并行调研完成，原始材料落盘：[findings-prompting.md](findings-prompting.md)、[findings-models.md](findings-models.md)、[findings-industry.md](findings-industry.md)。
- 本机实测（三家国内视觉模型，合成图）：
  - 铭牌字号 / 对比度扫描 —— `deepseek-flash` 在铭牌占全图 0.38% 时开始出错、0.15% 时 0/3 且**编出完整假铭牌**（两次复跑编出的内容不同，确认是凭空生成）；`qwen3-vl-plus` 与 `glm-4.6v` 全条件 3/3。
  - 九宫格裁剪 + 2× 放大 —— 三家、全部条件拉回 3/3，是本次唯一在自家链路上被证实的提升手段，据此把 L3 定向复看由 P1 上调 P0。
  - 图文分路 —— 未复现文献中「编出被暗示的故障」，但 `glm-4.6v` 在误导文字下 2/2 **丢掉真实故障**。建议保留在 P0，理由由「防幻觉」改为「防漏检」。
- 产出 [research.md](research.md)：五层流水线方案、prompt 骨架、选型建议、质量门控阈值、评测 schema 与指标、票 62 的 P0/P1/P2 增补清单、四个待决策点。
- 实测脚本入库 [probes/](probes/)，已验证可从新位置复现。

## 未完成 / 交接

- 四个决策点待用户确认（research.md §11），其中「主位改 qwen-vl」是唯一建议立即执行的配置改动。
- 本次只做调研，**未改任何代码与配置**。
