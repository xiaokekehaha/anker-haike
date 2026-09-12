# 31: 预写排障计划表与 seed

**What to build:** plans 表（plan_id / version / fault / applies_to / steps 含 instruction_src、expected_result、caution、next_on）与 5 个计划的 seed：毛发缠绕、滤网堵塞、尘盒满、边刷、电机故障（一步即 EXHAUSTED）。启动加载校验 next_on 引用合法、instruction_src 指向的证据存在。

**Blocked by:** 01（Compose 骨架与 /health 聚合）

**Status:** ready-for-agent

- [ ] 5 个计划加载成功，任一 next_on 指向不存在 step_id 时启动失败
- [ ] 计划进入 L4 内存缓存，配置版本变更可重载
- [ ] 有计划模型的 JSON Schema 供后续 synthesize 枚举使用

**设计依据：** 09 §3.1；03 §3.1
