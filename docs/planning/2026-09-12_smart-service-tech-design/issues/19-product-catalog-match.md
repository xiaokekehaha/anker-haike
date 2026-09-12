# 19: 产品目录表与匹配服务

**What to build:** products 表与约 20 个 SKU 的 seed（含 S1 Pro 同名异类），规则服务提供型号精确匹配 + 别名模糊匹配的 lookup_product 工具，返回候选带 in_scope 标记。不用模型猜型号。

**Blocked by:** 01（Compose 骨架与 /health 聚合）

**Status:** done（2026-09-12）

**Owner:** Claude Code B（模型层线，2026-09-12 认领；改动范围 `orchestrator/app/catalog/`、`config/products.yaml`，共享文件 Makefile / main.py / pyproject 只追加）

- [x] seed 脚本可重复执行，含 in_scope=false 的吸奶器（`config/products.yaml` 21 个 SKU：15 台扫地机 + 6 个范围外产品，含同名异类 eufy S1 Pro 吸奶器；`make seed WHAT=products` upsert + 清理已删 SKU，本机 Postgres 连跑两次结果一致）
- [x] 「S1 Pro」返回两个候选，「扫地机 X」单命中，「随便」零命中（候选按范围内优先排序并带 in_scope）
- [x] 别名表配置化并进入 L4 内存缓存（products.yaml 的 aliases / categories.keywords；`ProductCatalog` 启动加载到 `app.state.catalog`，`reload()` 仅在配置 version 变化时替换；也可 `load_from_db` 从表加载）
- [x] 匹配逻辑有单元测试（tests/test_catalog.py 20 项：整句精确、句中别名长优先占位（X 不误中 X10）、去品类词后模糊 ≥ 0.85、无空格写法、配置错误、重载、表 seed 幂等）

**设计依据：** 03 §1.3、§3.1；07 §12

**实现记录（2026-09-12，Claude Code B）：** `orchestrator/app/catalog/`（service.py：配置模型、归一化、`lookup_product` 三级匹配、`category_hint` 供消歧降级 category_only；store.py：products 表 DDL / upsert / 从表加载）；`app/seed_cli.py`（`haike-seed`）；settings 新增 `CATALOG_CONFIG_PATH`。返回类型直接用 contracts 的 `ProductCandidate`。已知限制：全无空格的「eufyx8pro」这类写法不做句中匹配，只能整句或模糊命中。
