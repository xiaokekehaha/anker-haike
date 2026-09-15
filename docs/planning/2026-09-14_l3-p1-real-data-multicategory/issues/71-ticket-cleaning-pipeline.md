# 71: 脱敏工单清洗与结构化管线

**What to build:** `haike-tickets probe raw.*` 输出字段统计与 mapping 草稿 → 人工确认 `mapping.yaml`；`ingest --mapping --batch`：去噪（空 / 重复 / 模板句）→ 结构化抽取（LLM 辅助：symptom_code、fault_class、remedy、region、channel、result，带原文引用；抽检 ≥ 10% 人工复核记录）→ 二次脱敏校验（手机 / 订单 / 地址正则 + NER 抽检，命中即拒绝入库）→ 按 family 分层随机分割开发集 / 保留集（保留集独立目录、只读）→ kb_tickets 入库（metadata: sku_list, region, channel, result, doc_version, batch）→ manifest。`sample --eval <set> --n` 从开发集抽评测样本。

**Blocked by:** 真实脱敏工单到手（到手前用合成样本验证管线）

**Status:** todo

**Owner:** —

- [ ] 合成脏数据（含伪手机号 / 地址）跑管线：脱敏校验拦截并报告
- [ ] 分割可复现（seed）；保留集文件哈希记录进 manifest
- [ ] 真实批次 ≥ 100 条入库；抽检记录归档

**设计依据：** 07 §2
