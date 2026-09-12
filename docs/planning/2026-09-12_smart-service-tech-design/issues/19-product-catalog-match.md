# 19: 产品目录表与匹配服务

**What to build:** products 表与约 20 个 SKU 的 seed（含 S1 Pro 同名异类），规则服务提供型号精确匹配 + 别名模糊匹配的 lookup_product 工具，返回候选带 in_scope 标记。不用模型猜型号。

**Blocked by:** 01（Compose 骨架与 /health 聚合）

**Status:** ready-for-agent

- [ ] seed 脚本可重复执行，含 in_scope=false 的吸奶器
- [ ] 「S1 Pro」返回两个候选，「扫地机 X」单命中，「随便」零命中
- [ ] 别名表配置化并进入 L4 内存缓存
- [ ] 匹配逻辑有单元测试

**设计依据：** 03 §1.3、§3.1；07 §12
