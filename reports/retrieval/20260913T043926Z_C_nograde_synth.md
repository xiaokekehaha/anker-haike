# 检索评测 C_nograde_synth 组（2026-09-13 04:39 UTC）

评测集 version=2026-09-13.draft1，annotated_count=0。只评检索层（不跑模型）；未标注样例的结果只用于回归对比。

## 汇总

| 指标 | 值 |
| --- | --- |
| cases | 56 |
| scored | 51 |
| hit@5 | 96% |
| precision@5 | 47% |
| chunk_hit@5 | 98% |
| chunk_scored | 50 |
| no_match | 0 |
| unavailable | 0 |
| leak | 5/5 |
| latency_p50_ms | 282 |
| latency_p95_ms | 517 |
| plan_match | 41/43 |
| outcome_match | 50/51 |
| synth_degraded | 14 |
| synth_p50_ms | 3291 |
| kb_ver | 2026-09-12.1+text-embedding-v4 |
| flags | {'multi_query': True, 'faq': True, 'rerank': False, 'parent_expand': True, 'grade': False, 'with_synthesize': True, 'config': '../data/eval/retrieval/configs/C_nograde.yaml'} |

## 按标签

| 标签 | n | hit@5 |
| --- | --- | --- |
| 口语 | 18 | 94% |
| 无计划 | 9 | 78% |
| A1 | 5 | 100% |
| 精确词 | 5 | 100% |
| 多症状 | 5 | 100% |
| 安全 | 5 | 100% |
| 品类级 | 5 | 100% |
| 反证工单 | 5 | 80% |
| 否定 | 4 | 100% |
| A2 | 3 | 100% |
| (untagged) | 3 | 100% |
| 错别字 | 1 | 100% |

## 逐样例

| id | 状态 | hit | 首命中位 | chunk | 命中文档 | ms | query（+变体数） | plan | outcome |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| a1-01 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, T0162, manual_rv_v1, T0137, manual_rv_v1 | 517 | EUFY-X10-PRO-OMNI 不吸 (+1) | ✓ rv_suction_hair_wrap | ✓ evidence |
| a1-02 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, T0162, manual_rv_v1, T0002, manual_rv_v1 | 439 | EUFY-X10-PRO-OMNI 清扫后残留碎屑 | ✓ rv_suction_hair_wrap | ✓ evidence |
| a1-03 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, faq_rv, T0162, manual_rv_v1, T0002 | 247 | EUFY-X10-PRO-OMNI 吸力下降 头发吸不起来 | ✓ rv_suction_hair_wrap | ✓ evidence |
| a1-04 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, T0151, manual_rv_v1, T0137, manual_rv_v1 | 819 | EUFY-X10-PRO-OMNI 滚刷缠头发 不吸 (+1) | ✓ rv_suction_hair_wrap | ✓ evidence |
| a1-05 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, faq_rv, T0162, manual_rv_v1, T0002 | 518 | EUFY-X10-PRO-OMNI 扫不干净 (+2) | ✓ rv_suction_hair_wrap | ✓ evidence |
| a2-01 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, T0182, troubleshooting_rv, T0122, troubleshooting_rv | 423 | EUFY-S1-PRO 不吸 (+1) | ✓ rv_suction_hair_wrap | ✓ evidence |
| a2-02 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, T0182, troubleshooting_rv, T0122, troubleshooting_rv | 361 | EUFY-S1-PRO 尘盒很快满 吸力弱 (+1) | ✓ rv_suction_filter_clog | ✓ evidence |
| a2-03 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, faq_rv, T0017, troubleshooting_rv, faq_rv | 257 | EUFY-S1-PRO 不充电 | - rv_suction_hair_wrap | ✓ standard_flow |
| flt-01 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, faq_rv, T0125, manual_rv_v1, T0199 | 245 | EUFY-X9-PRO 滤网脏 灰多 | ✓ rv_suction_filter_clog | ✓ evidence |
| flt-02 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, faq_rv, T0172, manual_rv_v1, T0092 | 269 | EUFY-X8-PRO-SES 吸力下降 尘盒很快满 | ✓ rv_suction_filter_clog | ✓ evidence |
| flt-03 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, T0002, manual_rv_v1, T0162, manual_rv_v1 | 380 | EUFY-X10-PRO-OMNI 滤网潮湿 异味 | ✓ rv_suction_filter_clog | ✓ evidence |
| flt-04 | ok | ✓ | 1 | ✓@1 | manual_rv_v2, faq_rv, T0032, manual_rv_v2, T0171 | 349 | EUFY-G50-HYBRID 吸力下降 滤网更换周期 | ✓ rv_suction_filter_clog | ✓ evidence |
| flt-05 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, faq_rv, T0062, troubleshooting_rv, T0145 | 341 | EUFY-30C-MAX 吸力小 (+1) | ✓ rv_suction_hair_wrap | ✓ evidence |
| bin-01 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, faq_rv, T0063, manual_rv_v1, faq_rv | 259 | EUFY-X10-PRO-OMNI 提示请检查尘盒 | ✓ rv_suction_dustbin_full | ✓ evidence |
| bin-02 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, faq_rv, T0143, troubleshooting_rv, faq_rv | 200 | EUFY-25C 提示请检查尘盒 | ✓ rv_suction_dustbin_full | ✓ evidence |
| bin-03 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, faq_rv, T0133, manual_rv_v1, T0051 | 341 | EUFY-X9-PRO 尘盒装不上 | ✓ rv_suction_dustbin_full | ✓ evidence |
| bin-04 | ok | ✓ | 1 | ✓@1 | manual_rv_v2, T0075, manual_rv_v2, T0064, manual_rv_v2 | 330 | EUFY-G40-HYBRID 漏灰 | ✓ rv_suction_dustbin_full | ✓ evidence |
| sb-01 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, faq_rv, T0124, troubleshooting_rv, T0004 | 300 | EUFY-30C-MAX 边刷不转 | ✓ rv_suction_side_brush | ✓ evidence |
| sb-02 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, faq_rv, T0151, manual_rv_v1, T0162 | 365 | EUFY-X10-PRO-OMNI 侧刷不动 (+1) | ✓ rv_suction_side_brush | ✓ evidence |
| sb-03 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, faq_rv, T0172, manual_rv_v1, T0081 | 380 | EUFY-X8-PRO-SES 墙边角落扫不干净 (+2) | ✓ rv_suction_side_brush | ✓ evidence |
| sb-04 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, T0114, troubleshooting_rv, T0084, troubleshooting_rv | 300 | EUFY-11S-MAX 边刷转动缓慢 异响 | ✓ rv_suction_side_brush | ✓ evidence |
| safe-01 | ok | ✓ | 1 | ✓@1 | manual_rv_v2, faq_rv, T0075, manual_rv_v2, T0064 | 232 | EUFY-G40-HYBRID 焦味 | ✓ rv_suction_motor_fault | - evidence |
| safe-02 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, faq_rv, T0137, manual_rv_v1, T0187 | 191 | EUFY-X10-PRO-OMNI 机身过热 | ✓ rv_suction_motor_fault | - evidence |
| safe-03 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, faq_rv, troubleshooting_rv, troubleshooting_rv | 282 | 扫地机器人 冒烟 | ✓ rv_suction_motor_fault | - evidence |
| safe-04 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, faq_rv, T0125, manual_rv_v1, T0018 | 332 | EUFY-X9-PRO 电池鼓包 | ✗ rv_suction_hair_wrap | - standard_flow |
| chg-01 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, faq_rv, T0007, troubleshooting_rv, faq_rv | 223 | EUFY-25C 不充电 基站灯不亮 | - rv_suction_hair_wrap | ✓ standard_flow |
| chg-02 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, faq_rv, T0147, troubleshooting_rv, faq_rv | 506 | EUFY-11S-MAX 不充电 触点脏 | - rv_suction_hair_wrap | ✓ standard_flow |
| chg-03 | ok | ✗ | - | ✗ | manual_rv_v2, faq_rv, T0178, manual_rv_v2, T0168 | 198 | EUFY-G20-HYBRID 找不到基站 | - rv_suction_hair_wrap | ✓ standard_flow |
| v2-01 | ok | ✓ | 1 | ✓@1 | manual_rv_v2, T0164, manual_rv_v2, T0091, manual_rv_v2 | 285 | EUFY-L60-HYBRID 滚刷拆卸 | ✓ rv_suction_hair_wrap | ✓ evidence |
| v2-02 | ok | ✓ | 1 | ✓@1 | manual_rv_v2, faq_rv, T0155, manual_rv_v2, T0141 | 747 | EUFY-L60-HYBRID 拖布异味 | - rv_suction_hair_wrap | ✓ standard_flow |
| v2-03 | ok | ✓ | 1 | ✓@1 | manual_rv_v2, faq_rv, T0175, manual_rv_v2, T0055 | 258 | EUFY-G50-HYBRID 水箱漏水 | - rv_suction_hair_wrap | ✓ standard_flow |
| v2-04 | ok | ✓ | 1 | ✓@1 | manual_rv_v2, faq_rv, T0012, manual_rv_v2, T0023 | 236 | EUFY-G30-VERGE 尘盒盖未扣紧 吸力下降 | ✓ rv_suction_dustbin_full | ✓ evidence |
| v2-05 | ok | ✓ | 1 | ✓@1 | manual_rv_v2, faq_rv, T0025, manual_rv_v2, T0161 | 210 | EUFY-L50-SES 吸力下降 | ✓ rv_suction_hair_wrap | ✓ evidence |
| cat-01 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, troubleshooting_rv, troubleshooting_rv | 244 | 扫地机器人 不吸 (+1) | ✓ rv_suction_hair_wrap | ✓ evidence |
| cat-02 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, faq_rv, troubleshooting_rv, troubleshooting_rv | 172 | 扫地机器人 边刷不转 | ✓ rv_suction_side_brush | ✓ evidence |
| cat-03 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, faq_rv, troubleshooting_rv, faq_rv, troubleshooting_rv | 192 | 扫地机器人 提示请检查尘盒 | ✓ rv_suction_dustbin_full | ✓ evidence |
| cat-04 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, faq_rv, troubleshooting_rv, faq_rv, troubleshooting_rv | 260 | 扫地机器人 不充电 | - rv_suction_hair_wrap | ✓ standard_flow |
| cat-05 | ok | leak | - | - | troubleshooting_rv, faq_rv, troubleshooting_rv, faq_rv, troubleshooting_rv | 185 | 扫地机器人 滤网清洗 | ✓ rv_suction_filter_clog | ✗ evidence |
| multi-01 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, T0151, manual_rv_v1, T0162, manual_rv_v1 | 210 | EUFY-X10-PRO-OMNI 清扫后残留碎屑 滚刷已清理 基站不集尘 | ✓ rv_suction_filter_clog | ✓ evidence |
| multi-02 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, faq_rv, T0125, manual_rv_v1, T0051 | 477 | EUFY-X9-PRO 吸力弱 噪音变大 (+1) | ✓ rv_suction_hair_wrap | ✓ evidence |
| multi-03 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, faq_rv, T0171, manual_rv_v2, faq_rv | 241 | EUFY-G50-HYBRID 边刷不转 地毯边打转 | ✓ rv_suction_side_brush | ✓ evidence |
| neg-01 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, faq_rv, T0151, manual_rv_v1, T0162 | 231 | EUFY-X10-PRO-OMNI 异响 | ✓ rv_suction_motor_fault | - evidence |
| neg-02 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, T0081, manual_rv_v1, T0061, manual_rv_v1 | 358 | EUFY-X8-PRO-SES 滚刷干净 不吸 (+1) | ✓ rv_suction_filter_clog | ✓ evidence |
| neg-03 | ok | ✓ | 1 | ✓@1 | manual_rv_v2, faq_rv, T0141, manual_rv_v2, T0091 | 241 | EUFY-L60-HYBRID 尘盒已清理 吸力下降 | ✓ rv_suction_hair_wrap | ✓ evidence |
| typo-01 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, faq_rv, T0162, manual_rv_v1, T0002 | 344 | EUFY-X10-PRO-OMNI 吸力变小 (+1) | ✗ rv_suction_filter_clog | ✓ evidence |
| typo-02 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, T0051, manual_rv_v1, T0125, troubleshooting_rv | 450 | EUFY-X9-PRO 扫地机跟没吸一样，白跑 (+1) | ✓ rv_suction_hair_wrap | ✓ evidence |
| typo-03 | ok | ✓ | 1 | ✓@1 | manual_rv_v2, T0064, manual_rv_v2, T0075, manual_rv_v2 | 215 | EUFY-G40-HYBRID 清扫后残留毛发 | ✓ rv_suction_hair_wrap | ✓ evidence |
| ctr-01 | ok | ✓ | 1 | ✓@1 | troubleshooting_rv, faq_rv, T0195, troubleshooting_rv, T0014 | 419 | EUFY-E20 吸力变小 扫不干净 (+2) | ✓ rv_suction_hair_wrap | ✓ evidence |
| ctr-02 | ok | ✓ | 4 | ✓@4 | manual_rv_v2, faq_rv, T0064, troubleshooting_rv, T0075 | 193 | EUFY-G40-HYBRID 边刷不转 | ✓ rv_suction_side_brush | ✓ evidence |
| ctr-03 | ok | ✗ | - | - | troubleshooting_rv, faq_rv, T0130, troubleshooting_rv, T0035 | 254 | EUFY-15C-MAX 清扫路线混乱 | - rv_suction_hair_wrap | ✓ standard_flow |
| none-01 | ok | leak | - | - | manual_rv_v1, faq_rv, T0138, manual_rv_v1, T0048 | 346 | EUFY-X10-PRO-OMNI App 无法连接 | - rv_suction_hair_wrap | ✓ standard_flow |
| none-02 | ok | leak | - | - | manual_rv_v1, T0125, manual_rv_v1, T0188, manual_rv_v1 | 288 | EUFY-X9-PRO 语音语言设置 | - rv_suction_hair_wrap | ✓ standard_flow |
| none-03 | ok | leak | - | - | manual_rv_v2, T0175, manual_rv_v2, T0055, manual_rv_v2 | 435 | EUFY-G50-HYBRID 跌落 | - rv_suction_hair_wrap | ✓ standard_flow |
| none-04 | ok | leak | - | - | manual_rv_v1, T0137, manual_rv_v1, T0187, manual_rv_v1 | 224 | EUFY-X10-PRO-OMNI 保修咨询 | - rv_suction_hair_wrap | ✓ standard_flow |
| exact-01 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, faq_rv, T0151, manual_rv_v1, faq_rv | 197 | EUFY-X10-PRO-OMNI 提示请检查滚刷 | ✓ rv_suction_hair_wrap | ✓ evidence |
| exact-02 | ok | ✓ | 1 | ✓@1 | manual_rv_v1, faq_rv, T0172, manual_rv_v1, T0179 | 193 | EUFY-X8-PRO-SES 红灯常亮 | - rv_suction_hair_wrap | ✓ standard_flow |
