# 30: 读图观察 diagnose.vision

**What to build:** diagnose 节点对故障图调用视觉任务输出 observations 与 visible_parts（internal），观察项再过一次 CP-in（如 smoke、deformed battery 触发 R4）；发 tool_call(vision)；备用模型不支持图片时降级为请用户文字描述并记 observations 为空。

**Blocked by:** 11（降级链与 task 预算）、29（图片上传与会话期存储）

**Status:** ready-for-agent

- [ ] 滚刷缠毛照片输出含「毛发缠绕」类观察（bake-off 样本之一）
- [ ] 含冒烟的图片观察触发 R4 升级
- [ ] 图片超过模型单请求上限时只保留最新几张
- [ ] 视觉链全部失败时流程不中断，image_observations 为空并记录

**设计依据：** 03 §1.4；09 §1；07 §6
