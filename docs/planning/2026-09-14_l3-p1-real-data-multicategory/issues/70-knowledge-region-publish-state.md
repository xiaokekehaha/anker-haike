# 70: 知识按品类 / 区域入库与发布状态过滤

**What to build:** `ingest.py` front-matter 增加可选 `region_list`（标量逗号串）、`publish_state`（draft / approved / published / withdrawn，默认 published 以兼容旧文档）、`source_url`；`KnowledgeScope` 增 `region: str | None`；`adapter.py` 过滤：`publish_state == published` 必选；区域专属文档（region_list 非空）只在 scope.region 匹配时召回，通用文档不受影响；`service_context.region_use` 注入 scope；manifest 记录各状态条数；`haike-kb publish|withdraw <doc_id>` 只改元数据不重建向量。真实知识库按品类分批导入。

**Blocked by:** P0 55（service_context 提供 region）；真实知识库到手

**Status:** todo

**Owner:** —

- [ ] 旧文档无新字段照常可检索；draft 文档零召回（断言）
- [ ] 区域专属 vs 通用文档召回单测；region 未知时只召回通用
- [ ] 快照导出 / 导入保留新元数据；kb eval 基线不退化

**设计依据：** 06 §3「路由多维」；07 §1「知识库」
