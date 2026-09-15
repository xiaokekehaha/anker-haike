# 视觉真实数据验收

当前没有真实故障照片，cases.yaml 保持空集，haike-eval vision 明确报告 pending_data。
不要把合成像素/JSON 输出的结构单测当作模型识别率。
补充至少 20 张脱敏照片后，按票 62 的 FaultLocalization schema，通过 haike-bakeoff 的 diagnose.vision 任务对国内可用链评测；记录真实模型、样本及错误，不凭空调整模型链序。
结构与安全回归见 tests/test_l3_experience.py、test_vision.py、test_vision_graph.py。
