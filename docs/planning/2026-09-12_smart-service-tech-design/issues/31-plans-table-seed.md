# 31: 预写排障计划表与 seed

**What to build:** plans 表（plan_id / version / fault / applies_to / steps 含 instruction_src、expected_result、caution、next_on）与 5 个计划的 seed：毛发缠绕、滤网堵塞、尘盒满、边刷、电机故障（一步即 EXHAUSTED）。启动加载校验 next_on 引用合法、instruction_src 指向的证据存在。

**Blocked by:** 01（Compose 骨架与 /health 聚合）

**Status:** done（2026-09-12）

**Owner:** Claude Code B（模型层线，2026-09-12 认领；改动范围 `orchestrator/app/plans/`、`config/plans.yaml`，共享文件 Makefile / main.py / pyproject 只追加）

- [x] 5 个计划加载成功，任一 next_on 指向不存在 step_id 时启动失败（`config/plans.yaml` 五个计划 + evidence 索引；Pydantic 校验 next_on 只能是本计划 step_id / DONE / EXHAUSTED 且不自指、instruction_src 格式与证据存在、step_id / plan 重复、scope=sku 必带 sku_list；坏配置时 uvicorn `Application startup failed`，错误逐项列出）
- [x] 计划进入 L4 内存缓存，配置版本变更可重载（`PlanLibrary` 挂 `app.state.plans`，`reload_if_changed()` 按 version 判断；同 plan_id 保留最高版本）
- [x] 有计划模型的 JSON Schema 供后续 synthesize 枚举使用（`plan_json_schema()` / `PlanLibrary.schema_for(category, sku)` 把 plan_id 收窄为允许集合枚举；`make plans-schema` 输出）

**设计依据：** 09 §3.1；03 §3.1

**实现记录（2026-09-12，Claude Code B）：** `orchestrator/app/plans/`（models.py：Plan / PlanStep / NextOn / AppliesTo，`next_step_id(step, feedback)` 规则推进、`applies(category, sku)`；library.py：加载 + 跨计划校验 + L4；store.py：plans 表 upsert）；`make seed WHAT=plans` 本机实测 5 条。与票面差异：`instruction_src` 指向的证据暂由 plans.yaml 内 `evidence` 段登记（doc_id#chunk_id + snippet），票 26/27 接 WeKnora 后改为从入库元数据校验。tests/test_plans.py 18 项。
