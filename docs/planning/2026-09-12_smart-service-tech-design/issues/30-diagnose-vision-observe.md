# 30: 读图观察 diagnose.vision

**What to build:** diagnose 节点对故障图调用视觉任务输出 observations 与 visible_parts（internal），观察项再过一次 CP-in（如 smoke、deformed battery 触发 R4）；发 tool_call(vision)；备用模型不支持图片时降级为请用户文字描述并记 observations 为空。

**Blocked by:** 11（降级链与 task 预算）、29（图片上传与会话期存储）

**Status:** done（2026-09-12，A 线接手会话；真实视觉模型 bake-off 样本待票 42 有 dashscope / anthropic key 后补跑）

- [x] 滚刷缠毛照片输出含「毛发缠绕」类观察（bake-off 样本之一）（假 router 回放：observations 含「滚刷缠绕大量毛发」，进 image_observations / visible_parts / observations，tool_call(diagnose.vision) finished 摘要带观察；图片以 data URL 进 internal 调用、用户文字包 <data>。本机无视觉模型 key，真实样本留票 42 bake-off）
- [x] 含冒烟的图片观察触发 R4 升级（观察项过 CP-in observation_terms，safety_flags source=observation term=smoke，vision 后直接 escalate(R4)，不再检索 / 调模型；摘要 reason 带命中词）
- [x] 图片超过模型单请求上限时只保留最新几张（上限取链上视觉模型 max_images 的最小值，未配置默认 4；5 张 → 只送最新 2 张，dropped 记录并在 tool_call 摘要注明）
- [x] 视觉链全部失败时流程不中断，image_observations 为空并记录（tool_call failed + vision_status=failed + model_trace model_used=skipped，run 继续检索并 done(completed)；视觉 provider 全部不可用 → vision_status=no_vision 并给用户固定提示「请用文字描述图片内容」（07 §6））

**设计依据：** 03 §1.4；09 §1；07 §6

**实现记录（2026-09-12，A 线接手会话）：** `app/diagnose/vision.py`（observe_images / select_images / image_limit / build_messages，VisionObservation schema）；graph.py 新增 vision 节点：产品已定且本 run 有 purpose=fault 新图 → vision → retrieve（R4 → escalate）；无图时路径不变。测试 tests/test_vision.py 7 项（模块级）+ tests/test_vision_graph.py 5 项（图级）。检索侧「图片新增观察补一次检索」的名额逻辑仍在票 32 的 retrieve 节点内（已留 hook 注释），本票让读图先于检索，observations 已在状态里可供其使用。
