# 68: 症状体系多品类扩表

**What to build:** `haike-taxonomy cluster --tickets dev.csv --category <c>`：对脱敏工单开发集的症状原话做聚类（embedding + 规则），生成 `fault_family / symptom_code / 表述集合` 草稿供人工审核合并进 `config/symptom_taxonomy.yaml`；每条表述记来源工单批次；为每品类补 discriminators（区分问题）；`export-synonyms` 生成 `retrieval.yaml.synonyms`；interpret 候选列表按 category 注入并限 ≤ 60 条（超出按频次截断）。

**Blocked by:** 71（工单开发集）；P0 58（interpret 意图扩展）

**Status:** todo

**Owner:** —

- [ ] ≥ 2 品类各 ≥ 6 个族；每族 ≥ 5 条表述且含否定式 / 错别字样本
- [ ] `data/eval/symptom/cases.yaml` 用保留集样本，族准确率报告；unknown 率单列
- [ ] 同义词表由 taxonomy 生成，手写副本删除

**设计依据：** 06 §2；07 §1
