# 检索评测集标注工作单

报告：`reports/retrieval/20260913T045339Z_C_synth.json`　样例：56 条，已标注 2 条。
对照每条的「实际检索」改 `data/eval/retrieval/cases.yaml`，改完把 `annotated` 置 true 并填 `annotator`。
字段含义与判断口径见 [ANNOTATION.md](../../docs/planning/2026-09-13_bounded-agentic-rag/ANNOTATION.md)。

## a1-01　待标注

- 用户原话：扫地机不吸了
- 范围：confirmed_sku / EUFY-X10-PRO-OMNI　症状：['不吸']
- 实际 query：`EUFY-X10-PRO-OMNI 不吸`
- 现有金标：doc=['manual_rv_v1', 'troubleshooting_rv'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence
- 起草备注：演示案例 A1 原话

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 2 | kb_tickets | T0162 | 工单 T0162｜产品 EUFY-X10-PRO-OMNI 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤 |  |
| 3 | kb_manual | manual_rv_v1 | 滚刷两端的轴承处如有毛发缠绕，需一并清理，否则滚刷转动阻力增大、吸力下降。  ### 1.2 清洁滤网（c15） 打开尘 |  |
| 4 | kb_tickets | T0137 | 工单 T0137｜产品 EUFY-X10-PRO-OMNI 现象：不充电 原因：基站触点脏污 处理步骤：擦拭触点后手动放 |  |
| 5 | kb_manual | manual_rv_v1 | ### 1.4 边刷维护（c21） 边刷用螺丝固定，拆下后清理缠绕物，若刷毛变形请更换。拆装边刷前请先关机。边刷缠绕毛发 |  |

## a1-02　待标注

- 用户原话：它跑完了地上还是一堆渣
- 范围：confirmed_sku / EUFY-X10-PRO-OMNI　症状：['清扫后残留碎屑']
- 实际 query：`EUFY-X10-PRO-OMNI 清扫后残留碎屑`
- 现有金标：doc=['manual_rv_v1', 'troubleshooting_rv'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence
- 起草备注：03 §1.4.2 的改写示例

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 2 | kb_tickets | T0162 | 工单 T0162｜产品 EUFY-X10-PRO-OMNI 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤 |  |
| 3 | kb_manual | manual_rv_v1 | 滚刷两端的轴承处如有毛发缠绕，需一并清理，否则滚刷转动阻力增大、吸力下降。  ### 1.2 清洁滤网（c15） 打开尘 |  |
| 4 | kb_tickets | T0002 | 工单 T0002｜产品 EUFY-X10-PRO-OMNI 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤 |  |
| 5 | kb_manual | manual_rv_v1 | ### 1.4 边刷维护（c21） 边刷用螺丝固定，拆下后清理缠绕物，若刷毛变形请更换。拆装边刷前请先关机。边刷缠绕毛发 |  |

## a1-03　待标注

- 用户原话：感觉吸力比刚买的时候小很多，头发都吸不起来
- 范围：confirmed_sku / EUFY-X10-PRO-OMNI　症状：['吸力下降', '头发吸不起来']
- 实际 query：`EUFY-X10-PRO-OMNI 吸力下降 头发吸不起来`
- 现有金标：doc=['manual_rv_v1', 'T0002'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 2 | kb_faq | faq_rv | 问：扫地机吸力变小了怎么办 答：请按顺序检查滚刷是否缠绕毛发、滤网是否堵塞、尘盒是否已满或未装到位、吸口是否有异物，每完 |  |
| 3 | kb_tickets | T0162 | 工单 T0162｜产品 EUFY-X10-PRO-OMNI 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤 |  |
| 4 | kb_manual | manual_rv_v1 | 滚刷两端的轴承处如有毛发缠绕，需一并清理，否则滚刷转动阻力增大、吸力下降。  ### 1.2 清洁滤网（c15） 打开尘 |  |
| 5 | kb_tickets | T0002 | 工单 T0002｜产品 EUFY-X10-PRO-OMNI 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤 |  |

## a1-04　待标注

- 用户原话：滚刷上缠了好多头发，是不是这个原因不吸
- 范围：confirmed_sku / EUFY-X10-PRO-OMNI　症状：['滚刷缠头发', '不吸']
- 实际 query：`EUFY-X10-PRO-OMNI 滚刷缠头发 不吸`
- 现有金标：doc=['manual_rv_v1'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 2 | kb_tickets | T0151 | 工单 T0151｜产品 EUFY-X10-PRO-OMNI 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出 |  |
| 3 | kb_manual | manual_rv_v1 | 滚刷两端的轴承处如有毛发缠绕，需一并清理，否则滚刷转动阻力增大、吸力下降。  ### 1.2 清洁滤网（c15） 打开尘 |  |
| 4 | kb_tickets | T0137 | 工单 T0137｜产品 EUFY-X10-PRO-OMNI 现象：不充电 原因：基站触点脏污 处理步骤：擦拭触点后手动放 |  |
| 5 | kb_manual | manual_rv_v1 | / 现象 / 含义 / 处理 / / --- / --- / --- / / 「请检查滚刷」 / 滚刷被缠绕或卡住 /  |  |

## a1-05　待标注

- 用户原话：机器扫完跟没扫一样
- 范围：confirmed_sku / EUFY-X10-PRO-OMNI　症状：['扫不干净']
- 实际 query：`EUFY-X10-PRO-OMNI 扫不干净`
- 现有金标：doc=['troubleshooting_rv', 'manual_rv_v1'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 2 | kb_faq | faq_rv | 问：扫地机吸力变小了怎么办 答：请按顺序检查滚刷是否缠绕毛发、滤网是否堵塞、尘盒是否已满或未装到位、吸口是否有异物，每完 |  |
| 3 | kb_tickets | T0162 | 工单 T0162｜产品 EUFY-X10-PRO-OMNI 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤 |  |
| 4 | kb_manual | manual_rv_v1 | 滚刷两端的轴承处如有毛发缠绕，需一并清理，否则滚刷转动阻力增大、吸力下降。  ### 1.2 清洁滤网（c15） 打开尘 |  |
| 5 | kb_tickets | T0002 | 工单 T0002｜产品 EUFY-X10-PRO-OMNI 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤 |  |

## a2-01　待标注

- 用户原话：S1 Pro 不吸了，急死了
- 范围：confirmed_sku / EUFY-S1-PRO　症状：['不吸']
- 实际 query：`EUFY-S1-PRO 不吸`
- 现有金标：doc=['troubleshooting_rv', 'T0001'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_filter_clog（synthesize）→ evidence
- 起草备注：manual_rv_v1/v2 均不含该 SKU，只能靠品类通用手册与 S1-PRO 工单；工单 id 以实际 CSV 为准

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |
| 2 | kb_tickets | T0182 | 工单 T0182｜产品 EUFY-S1-PRO 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤网清洗晾干  |  |
| 3 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |
| 4 | kb_tickets | T0122 | 工单 T0122｜产品 EUFY-S1-PRO 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤网清洗晾干  |  |
| 5 | kb_manual | troubleshooting_rv | 3. 若四步均无效且伴随异响，转电机故障流程（见 D）。  ## B. 边刷不转 1. 关机后拆下边刷，清理缠绕的毛发与 |  |

## a2-02　待标注

- 用户原话：尘盒老是很快就满了，吸力也弱
- 范围：confirmed_sku / EUFY-S1-PRO　症状：['尘盒很快满', '吸力弱']
- 实际 query：`EUFY-S1-PRO 尘盒很快满 吸力弱`
- 现有金标：doc=['troubleshooting_rv'] cause=- plan=rv_suction_filter_clog outcome=evidence
- 模型选了：rv_suction_filter_clog（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |
| 2 | kb_tickets | T0182 | 工单 T0182｜产品 EUFY-S1-PRO 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤网清洗晾干  |  |
| 3 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |
| 4 | kb_tickets | T0122 | 工单 T0122｜产品 EUFY-S1-PRO 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤网清洗晾干  |  |
| 5 | kb_manual | troubleshooting_rv | 3. 若四步均无效且伴随异响，转电机故障流程（见 D）。  ## B. 边刷不转 1. 关机后拆下边刷，清理缠绕的毛发与 |  |

## a2-03　待标注

- 用户原话：回基站以后不充电
- 范围：confirmed_sku / EUFY-S1-PRO　症状：['不充电']
- 实际 query：`EUFY-S1-PRO 不充电`
- 现有金标：doc=['troubleshooting_rv'] cause=- plan=None outcome=standard_flow
- 模型选了：rv_suction_hair_wrap（standard_flow）→ standard_flow
- 起草备注：plans.yaml 无充电计划，synthesize 无可选计划时的行为需要在标注时确认

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |
| 2 | kb_faq | faq_rv | 问：机器不充电怎么办 答：确认基站电源灯亮、触点无灰尘，手动放回基站观察 5 分钟；仍不充电请联系售后。 |  |
| 3 | kb_tickets | T0017 | 工单 T0017｜产品 EUFY-S1-PRO 现象：不充电 原因：基站触点脏污 处理步骤：擦拭触点后手动放回基站 结果 |  |
| 4 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |
| 5 | kb_faq | faq_rv | 问：机器找不到基站 答：请把基站放在靠墙、前方 1.5 米无障碍的位置，避免阳光直射红外接收窗。 |  |

## flt-01　待标注

- 用户原话：灰特别多，扫一次滤网就黑了
- 范围：confirmed_sku / EUFY-X9-PRO　症状：['滤网脏', '灰多']
- 实际 query：`EUFY-X9-PRO 滤网脏 灰多`
- 现有金标：doc=['manual_rv_v1'] cause=- plan=rv_suction_filter_clog outcome=evidence
- 模型选了：rv_suction_filter_clog（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | 滚刷两端的轴承处如有毛发缠绕，需一并清理，否则滚刷转动阻力增大、吸力下降。  ### 1.2 清洁滤网（c15） 打开尘 |  |
| 2 | kb_faq | faq_rv | 问：滤网可以水洗吗 答：可水洗机型的滤网可用清水冲洗，需完全晾干 24 小时后再装回，切勿潮湿装回。 |  |
| 3 | kb_tickets | T0125 | 工单 T0125｜产品 EUFY-X9-PRO 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异物 结果 |  |
| 4 | kb_manual | manual_rv_v1 | 滤网破损或变形时请直接更换，不要继续使用。  ### 1.3 清理尘盒（c18） 按下尘盒释放键抽出尘盒，倒空并检查进风 |  |
| 5 | kb_tickets | T0051 | 工单 T0051｜产品 EUFY-X9-PRO 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出滚刷清理缠绕 |  |

## flt-02　待标注

- 用户原话：吸力下降，尘盒很快满
- 范围：confirmed_sku / EUFY-X8-PRO-SES　症状：['吸力下降', '尘盒很快满']
- 实际 query：`EUFY-X8-PRO-SES 吸力下降 尘盒很快满`
- 现有金标：doc=['manual_rv_v1', 'T0002'] cause=- plan=rv_suction_filter_clog outcome=evidence
- 模型选了：rv_suction_filter_clog（synthesize）→ evidence
- 起草备注：与工单 T0002 症状同句

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | 滤网破损或变形时请直接更换，不要继续使用。  ### 1.3 清理尘盒（c18） 按下尘盒释放键抽出尘盒，倒空并检查进风 |  |
| 2 | kb_faq | faq_rv | 问：扫地机吸力变小了怎么办 答：请按顺序检查滚刷是否缠绕毛发、滤网是否堵塞、尘盒是否已满或未装到位、吸口是否有异物，每完 |  |
| 3 | kb_tickets | T0172 | 工单 T0172｜产品 EUFY-X8-PRO-SES 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤网清 |  |
| 4 | kb_manual | manual_rv_v1 | 滚刷两端的轴承处如有毛发缠绕，需一并清理，否则滚刷转动阻力增大、吸力下降。  ### 1.2 清洁滤网（c15） 打开尘 |  |
| 5 | kb_tickets | T0092 | 工单 T0092｜产品 EUFY-X8-PRO-SES 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤网清 |  |

## flt-03　待标注

- 用户原话：滤网洗了还是湿的能直接装回去吗，现在有点味道
- 范围：confirmed_sku / EUFY-X10-PRO-OMNI　症状：['滤网潮湿', '异味']
- 实际 query：`EUFY-X10-PRO-OMNI 滤网潮湿 异味`
- 现有金标：doc=['manual_rv_v1'] cause=- plan=rv_suction_filter_clog outcome=evidence
- 模型选了：rv_suction_filter_clog（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | 滚刷两端的轴承处如有毛发缠绕，需一并清理，否则滚刷转动阻力增大、吸力下降。  ### 1.2 清洁滤网（c15） 打开尘 |  |
| 2 | kb_tickets | T0002 | 工单 T0002｜产品 EUFY-X10-PRO-OMNI 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤 |  |
| 3 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 4 | kb_tickets | T0162 | 工单 T0162｜产品 EUFY-X10-PRO-OMNI 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤 |  |
| 5 | kb_manual | manual_rv_v1 | 滤网破损或变形时请直接更换，不要继续使用。  ### 1.3 清理尘盒（c18） 按下尘盒释放键抽出尘盒，倒空并检查进风 |  |

## flt-04　待标注

- 用户原话：过滤网多久换一次，感觉吸不动了
- 范围：confirmed_sku / EUFY-G50-HYBRID　症状：['吸力下降', '滤网更换周期']
- 实际 query：`EUFY-G50-HYBRID 吸力下降 滤网更换周期`
- 现有金标：doc=['manual_rv_v2'] cause=- plan=rv_suction_filter_clog outcome=evidence
- 模型选了：rv_suction_filter_clog（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v2 | 滚刷末端轴套可拆下单独清理。  ## 3 滤网与尘盒 G 系列滤网为可水洗 HEPA 滤网，冲洗后需完全晾干。尘盒容量  |  |
| 2 | kb_faq | faq_rv | 问：扫地机吸力变小了怎么办 答：请按顺序检查滚刷是否缠绕毛发、滤网是否堵塞、尘盒是否已满或未装到位、吸口是否有异物，每完 |  |
| 3 | kb_tickets | T0032 | 工单 T0032｜产品 EUFY-G50-HYBRID 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤网清 |  |
| 4 | kb_manual | manual_rv_v2 | # eufy L60 / G 系列 用户手册（排障节选）  ## 1 吸力下降的常见原因 吸力下降通常由四类原因造成：滚 |  |
| 5 | kb_tickets | T0175 | 工单 T0175｜产品 EUFY-G50-HYBRID 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异 |  |

## flt-05　待标注

- 用户原话：吸力小了
- 范围：confirmed_sku / EUFY-30C-MAX　症状：['吸力小']
- 实际 query：`EUFY-30C-MAX 吸力小`
- 现有金标：doc=['troubleshooting_rv', 'T0004'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence
- 起草备注：30C 无专属手册；工单里该 SKU 滤网堵塞 3 例，看工单能否把 filter_clog 排到前面

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |
| 2 | kb_faq | faq_rv | 问：扫地机吸力变小了怎么办 答：请按顺序检查滚刷是否缠绕毛发、滤网是否堵塞、尘盒是否已满或未装到位、吸口是否有异物，每完 |  |
| 3 | kb_tickets | T0062 | 工单 T0062｜产品 EUFY-30C-MAX 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤网清洗晾干 |  |
| 4 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |
| 5 | kb_tickets | T0145 | 工单 T0145｜产品 EUFY-30C-MAX 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异物 结 |  |

## bin-01　已标注

- 用户原话：一直语音说请检查尘盒，我明明装上去了
- 范围：confirmed_sku / EUFY-X10-PRO-OMNI　症状：['提示请检查尘盒']
- 实际 query：`EUFY-X10-PRO-OMNI 提示请检查尘盒`
- 现有金标：doc=['manual_rv_v1', 'troubleshooting_rv', 'faq_rv'] cause=尘盒未装到位 plan=rv_suction_dustbin_full outcome=evidence
- 模型选了：rv_suction_dustbin_full（synthesize）→ evidence
- 起草备注：2026-09-13 标注：top5 为 c18 / faq q5 / T0063（尘盒未装到位）/ 第3章表 / faq q33，前四条都相关；q33（请检查滚刷）不相关但只排第 5，可接受。模型选 dustbin_full 正确。

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | 滤网破损或变形时请直接更换，不要继续使用。  ### 1.3 清理尘盒（c18） 按下尘盒释放键抽出尘盒，倒空并检查进风 |  |
| 2 | kb_faq | faq_rv | 问：提示请检查尘盒是什么意思 答：表示尘盒未装到位或已满。请倒空尘盒并重新安装，听到咔哒声即到位。 |  |
| 3 | kb_tickets | T0063 | 工单 T0063｜产品 EUFY-X10-PRO-OMNI 现象：提示请检查尘盒 原因：尘盒未装到位 处理步骤：重新安装 |  |
| 4 | kb_manual | manual_rv_v1 | / 现象 / 含义 / 处理 / / --- / --- / --- / / 「请检查尘盒」 / 尘盒未装到位或已满 / |  |
| 5 | kb_faq | faq_rv | 问：语音提示请检查滚刷 答：表示滚刷被缠绕或卡住，请取出滚刷清理后装回。 |  |

## bin-02　待标注

- 用户原话：提示请检查尘盒
- 范围：confirmed_sku / EUFY-25C　症状：['提示请检查尘盒']
- 实际 query：`EUFY-25C 提示请检查尘盒`
- 现有金标：doc=['troubleshooting_rv', 'T0003'] cause=- plan=rv_suction_dustbin_full outcome=evidence
- 模型选了：rv_suction_dustbin_full（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | 3. 若四步均无效且伴随异响，转电机故障流程（见 D）。  ## B. 边刷不转 1. 关机后拆下边刷，清理缠绕的毛发与 |  |
| 2 | kb_faq | faq_rv | 问：提示请检查尘盒是什么意思 答：表示尘盒未装到位或已满。请倒空尘盒并重新安装，听到咔哒声即到位。 |  |
| 3 | kb_tickets | T0143 | 工单 T0143｜产品 EUFY-25C 现象：提示请检查尘盒 原因：尘盒未装到位 处理步骤：重新安装尘盒直到咔哒声 结 |  |
| 4 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |
| 5 | kb_faq | faq_rv | 问：语音提示请检查滚刷 答：表示滚刷被缠绕或卡住，请取出滚刷清理后装回。 |  |

## bin-03　待标注

- 用户原话：垃圾盒卡不进去，推不到底
- 范围：confirmed_sku / EUFY-X9-PRO　症状：['尘盒装不上']
- 实际 query：`EUFY-X9-PRO 尘盒装不上`
- 现有金标：doc=['manual_rv_v1'] cause=- plan=rv_suction_dustbin_full outcome=evidence
- 模型选了：rv_suction_dustbin_full（synthesize）→ evidence
- 起草备注：「垃圾盒」需同义词表映射到尘盒

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | 滤网破损或变形时请直接更换，不要继续使用。  ### 1.3 清理尘盒（c18） 按下尘盒释放键抽出尘盒，倒空并检查进风 |  |
| 2 | kb_faq | faq_rv | 问：尘盒装不上去 答：请检查尘盒内是否有异物顶住，对准滑轨完全推入直到听到咔哒声；未装到位会触发提示。 |  |
| 3 | kb_tickets | T0133 | 工单 T0133｜产品 EUFY-X9-PRO 现象：提示请检查尘盒 原因：尘盒未装到位 处理步骤：重新安装尘盒直到咔哒 |  |
| 4 | kb_manual | manual_rv_v1 | / 现象 / 含义 / 处理 / / --- / --- / --- / / 「请检查尘盒」 / 尘盒未装到位或已满 / |  |
| 5 | kb_tickets | T0051 | 工单 T0051｜产品 EUFY-X9-PRO 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出滚刷清理缠绕 |  |

## bin-04　待标注

- 用户原话：机器后面一路漏灰
- 范围：confirmed_sku / EUFY-G40-HYBRID　症状：['漏灰']
- 实际 query：`EUFY-G40-HYBRID 漏灰`
- 现有金标：doc=['manual_rv_v2'] cause=- plan=rv_suction_dustbin_full outcome=evidence
- 模型选了：rv_suction_dustbin_full（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v2 | 滚刷末端轴套可拆下单独清理。  ## 3 滤网与尘盒 G 系列滤网为可水洗 HEPA 滤网，冲洗后需完全晾干。尘盒容量  |  |
| 2 | kb_tickets | T0075 | 工单 T0075｜产品 EUFY-G40-HYBRID 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异 |  |
| 3 | kb_manual | manual_rv_v2 | # eufy L60 / G 系列 用户手册（排障节选）  ## 1 吸力下降的常见原因 吸力下降通常由四类原因造成：滚 |  |
| 4 | kb_tickets | T0064 | 工单 T0064｜产品 EUFY-G40-HYBRID 现象：边刷不转 原因：边刷缠绕毛发 处理步骤：关机拆下边刷清理缠 |  |
| 5 | kb_manual | manual_rv_v2 | 水箱漏水时请检查密封圈是否移位。  ## 5 安全须知 充电时请使用原装基站。若机身发烫、有焦味或冒烟，请立即断电并联系 |  |

## sb-01　待标注

- 用户原话：边刷不转
- 范围：confirmed_sku / EUFY-30C-MAX　症状：['边刷不转']
- 实际 query：`EUFY-30C-MAX 边刷不转`
- 现有金标：doc=['troubleshooting_rv', 'T0004'] cause=- plan=rv_suction_side_brush outcome=evidence
- 模型选了：rv_suction_side_brush（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | 3. 若四步均无效且伴随异响，转电机故障流程（见 D）。  ## B. 边刷不转 1. 关机后拆下边刷，清理缠绕的毛发与 |  |
| 2 | kb_faq | faq_rv | 问：边刷不转怎么办 答：先关机拆下边刷清理缠绕物，检查边刷轴是否有异物或进水；清理后仍不转请联系售后。 |  |
| 3 | kb_tickets | T0124 | 工单 T0124｜产品 EUFY-30C-MAX 现象：边刷不转 原因：边刷缠绕毛发 处理步骤：关机拆下边刷清理缠绕物  |  |
| 4 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |
| 5 | kb_tickets | T0004 | 工单 T0004｜产品 EUFY-30C-MAX 现象：边刷不转 原因：边刷缠绕毛发 处理步骤：关机拆下边刷清理缠绕物  |  |

## sb-02　待标注

- 用户原话：侧面那个小刷子不动了
- 范围：confirmed_sku / EUFY-X10-PRO-OMNI　症状：['侧刷不动']
- 实际 query：`EUFY-X10-PRO-OMNI 侧刷不动`
- 现有金标：doc=['manual_rv_v1', 'troubleshooting_rv'] cause=- plan=rv_suction_side_brush outcome=evidence
- 模型选了：rv_suction_side_brush（synthesize）→ evidence
- 起草备注：「侧刷」「小刷子」→ 边刷

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 2 | kb_faq | faq_rv | 问：边刷不转怎么办 答：先关机拆下边刷清理缠绕物，检查边刷轴是否有异物或进水；清理后仍不转请联系售后。 |  |
| 3 | kb_tickets | T0151 | 工单 T0151｜产品 EUFY-X10-PRO-OMNI 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出 |  |
| 4 | kb_manual | manual_rv_v1 | ### 1.4 边刷维护（c21） 边刷用螺丝固定，拆下后清理缠绕物，若刷毛变形请更换。拆装边刷前请先关机。边刷缠绕毛发 |  |
| 5 | kb_tickets | T0162 | 工单 T0162｜产品 EUFY-X10-PRO-OMNI 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤 |  |

## sb-03　待标注

- 用户原话：墙边和角落总是扫不到
- 范围：confirmed_sku / EUFY-X8-PRO-SES　症状：['墙边角落扫不干净']
- 实际 query：`EUFY-X8-PRO-SES 墙边角落扫不干净`
- 现有金标：doc=['manual_rv_v1'] cause=- plan=rv_suction_side_brush outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | ### 1.4 边刷维护（c21） 边刷用螺丝固定，拆下后清理缠绕物，若刷毛变形请更换。拆装边刷前请先关机。边刷缠绕毛发 |  |
| 2 | kb_faq | faq_rv | 问：扫地机吸力变小了怎么办 答：请按顺序检查滚刷是否缠绕毛发、滤网是否堵塞、尘盒是否已满或未装到位、吸口是否有异物，每完 |  |
| 3 | kb_tickets | T0172 | 工单 T0172｜产品 EUFY-X8-PRO-SES 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤网清 |  |
| 4 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 5 | kb_tickets | T0081 | 工单 T0081｜产品 EUFY-X8-PRO-SES 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出滚刷 |  |

## sb-04　待标注

- 用户原话：边刷转得特别慢还咯吱响
- 范围：confirmed_sku / EUFY-11S-MAX　症状：['边刷转动缓慢', '异响']
- 实际 query：`EUFY-11S-MAX 边刷转动缓慢 异响`
- 现有金标：doc=['troubleshooting_rv'] cause=- plan=rv_suction_side_brush outcome=evidence
- 模型选了：rv_suction_side_brush（synthesize）→ evidence
- 起草备注：「咯吱响」是否触发 R4 安全规则由 rules 决定，标注时确认

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | 3. 若四步均无效且伴随异响，转电机故障流程（见 D）。  ## B. 边刷不转 1. 关机后拆下边刷，清理缠绕的毛发与 |  |
| 2 | kb_tickets | T0114 | 工单 T0114｜产品 EUFY-11S-MAX 现象：边刷不转 原因：边刷缠绕毛发 处理步骤：关机拆下边刷清理缠绕物  |  |
| 3 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |
| 4 | kb_tickets | T0084 | 工单 T0084｜产品 EUFY-11S-MAX 现象：边刷不转 原因：边刷缠绕毛发 处理步骤：关机拆下边刷清理缠绕物  |  |
| 5 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |

## safe-01　待标注

- 用户原话：跑着跑着有股烧焦的味道
- 范围：confirmed_sku / EUFY-G40-HYBRID　症状：['焦味']
- 实际 query：`EUFY-G40-HYBRID 焦味`
- 现有金标：doc=['manual_rv_v2', 'troubleshooting_rv', 'T0006'] cause=- plan=rv_suction_motor_fault outcome=escalate
- 模型选了：rv_suction_motor_fault（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v2 | 滚刷末端轴套可拆下单独清理。  ## 3 滤网与尘盒 G 系列滤网为可水洗 HEPA 滤网，冲洗后需完全晾干。尘盒容量  |  |
| 2 | kb_faq | faq_rv | 问：机器有焦味怎么办 答：请立即关机停止使用并联系售后，不要继续排查或充电。 |  |
| 3 | kb_tickets | T0075 | 工单 T0075｜产品 EUFY-G40-HYBRID 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异 |  |
| 4 | kb_manual | manual_rv_v2 | 水箱漏水时请检查密封圈是否移位。  ## 5 安全须知 充电时请使用原装基站。若机身发烫、有焦味或冒烟，请立即断电并联系 |  |
| 5 | kb_tickets | T0064 | 工单 T0064｜产品 EUFY-G40-HYBRID 现象：边刷不转 原因：边刷缠绕毛发 处理步骤：关机拆下边刷清理缠 |  |

## safe-02　待标注

- 用户原话：机身烫得不敢碰
- 范围：confirmed_sku / EUFY-X10-PRO-OMNI　症状：['机身过热']
- 实际 query：`EUFY-X10-PRO-OMNI 机身过热`
- 现有金标：doc=['manual_rv_v1', 'troubleshooting_rv'] cause=- plan=rv_suction_motor_fault outcome=escalate
- 模型选了：rv_suction_motor_fault（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | ### 1.4 边刷维护（c21） 边刷用螺丝固定，拆下后清理缠绕物，若刷毛变形请更换。拆装边刷前请先关机。边刷缠绕毛发 |  |
| 2 | kb_faq | faq_rv | 问：机器发烫正常吗 答：轻微温热正常；若明显烫手、有焦味或冒烟，请立即断电停用并联系售后。 |  |
| 3 | kb_tickets | T0137 | 工单 T0137｜产品 EUFY-X10-PRO-OMNI 现象：不充电 原因：基站触点脏污 处理步骤：擦拭触点后手动放 |  |
| 4 | kb_manual | manual_rv_v1 | 电池出现鼓包、漏液时请远离火源并联系售后回收，不要继续充电或使用。  ## 第 3 章 指示灯与语音提示  / 现象 / |  |
| 5 | kb_tickets | T0187 | 工单 T0187｜产品 EUFY-X10-PRO-OMNI 现象：不充电 原因：基站触点脏污 处理步骤：擦拭触点后手动放 |  |

## safe-03　待标注

- 用户原话：冒烟了！
- 范围：category_only / robot_vacuum　症状：['冒烟']
- 实际 query：`扫地机器人 冒烟`
- 现有金标：doc=['troubleshooting_rv'] cause=- plan=rv_suction_motor_fault outcome=escalate
- 模型选了：rv_suction_motor_fault（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |
| 2 | kb_faq | faq_rv | 问：机器冒烟了 答：请立即断电停用并远离，联系售后处理，不要继续使用。 |  |
| 3 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |
| 4 | kb_manual | troubleshooting_rv | 3. 若四步均无效且伴随异响，转电机故障流程（见 D）。  ## B. 边刷不转 1. 关机后拆下边刷，清理缠绕的毛发与 |  |

## safe-04　待标注

- 用户原话：电池那块鼓起来了
- 范围：confirmed_sku / EUFY-X9-PRO　症状：['电池鼓包']
- 实际 query：`EUFY-X9-PRO 电池鼓包`
- 现有金标：doc=['manual_rv_v1'] cause=- plan=rv_suction_motor_fault outcome=escalate
- 模型选了：rv_suction_hair_wrap（standard_flow）→ standard_flow

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | 电池出现鼓包、漏液时请远离火源并联系售后回收，不要继续充电或使用。  ## 第 3 章 指示灯与语音提示  / 现象 / |  |
| 2 | kb_faq | faq_rv | 问：电池鼓包了怎么办 答：请立即停止使用与充电，远离火源，联系售后回收处理，切勿自行拆解。 |  |
| 3 | kb_tickets | T0125 | 工单 T0125｜产品 EUFY-X9-PRO 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异物 结果 |  |
| 4 | kb_manual | manual_rv_v1 | ### 1.4 边刷维护（c21） 边刷用螺丝固定，拆下后清理缠绕物，若刷毛变形请更换。拆装边刷前请先关机。边刷缠绕毛发 |  |
| 5 | kb_tickets | T0018 | 工单 T0018｜产品 EUFY-X9-PRO 现象：找不到基站 原因：基站位置遮挡 处理步骤：调整基站到靠墙开阔位置  |  |

## chg-01　待标注

- 用户原话：放回去不充电，灯也不亮
- 范围：confirmed_sku / EUFY-25C　症状：['不充电', '基站灯不亮']
- 实际 query：`EUFY-25C 不充电 基站灯不亮`
- 现有金标：doc=['troubleshooting_rv', 'T0027'] cause=- plan=None outcome=standard_flow
- 模型选了：rv_suction_hair_wrap（standard_flow）→ standard_flow
- 起草备注：T0027 是 unsolved 工单，只能作反证

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |
| 2 | kb_faq | faq_rv | 问：机器不充电怎么办 答：确认基站电源灯亮、触点无灰尘，手动放回基站观察 5 分钟；仍不充电请联系售后。 |  |
| 3 | kb_tickets | T0007 | 工单 T0007｜产品 EUFY-25C 现象：不充电 原因：基站触点脏污 处理步骤：擦拭触点后手动放回基站 结果：so |  |
| 4 | kb_manual | troubleshooting_rv | 3. 若四步均无效且伴随异响，转电机故障流程（见 D）。  ## B. 边刷不转 1. 关机后拆下边刷，清理缠绕的毛发与 |  |
| 5 | kb_faq | faq_rv | 问：机器找不到基站 答：请把基站放在靠墙、前方 1.5 米无障碍的位置，避免阳光直射红外接收窗。 |  |

## chg-02　待标注

- 用户原话：充电触点是不是脏了，老充不进
- 范围：confirmed_sku / EUFY-11S-MAX　症状：['不充电', '触点脏']
- 实际 query：`EUFY-11S-MAX 不充电 触点脏`
- 现有金标：doc=['troubleshooting_rv'] cause=- plan=None outcome=standard_flow
- 模型选了：rv_suction_hair_wrap（standard_flow）→ standard_flow
- 起草备注：11S 工单基站触点脏污 solved 5 例，应排前

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |
| 2 | kb_faq | faq_rv | 问：机器不充电怎么办 答：确认基站电源灯亮、触点无灰尘，手动放回基站观察 5 分钟；仍不充电请联系售后。 |  |
| 3 | kb_tickets | T0147 | 工单 T0147｜产品 EUFY-11S-MAX 现象：不充电 原因：基站触点脏污 处理步骤：擦拭触点后手动放回基站 结 |  |
| 4 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |
| 5 | kb_faq | faq_rv | 问：机器找不到基站 答：请把基站放在靠墙、前方 1.5 米无障碍的位置，避免阳光直射红外接收窗。 |  |

## chg-03　已标注

- 用户原话：找不到回家的路，每次都停在半路
- 范围：confirmed_sku / EUFY-G20-HYBRID　症状：['找不到基站']
- 实际 query：`EUFY-G20-HYBRID 找不到基站`
- 现有金标：doc=['faq_rv'] cause=基站位置遮挡 plan=None outcome=standard_flow
- 模型选了：rv_suction_hair_wrap（standard_flow）→ standard_flow
- 起草备注：2026-09-13 标注：原金标 troubleshooting_rv 判错，已改。plans.yaml 无对应计划，expected_outcome 保持 standard_flow 正确。

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v2 | 水箱漏水时请检查密封圈是否移位。  ## 5 安全须知 充电时请使用原装基站。若机身发烫、有焦味或冒烟，请立即断电并联系 |  |
| 2 | kb_faq | faq_rv | 问：机器找不到基站 答：请把基站放在靠墙、前方 1.5 米无障碍的位置，避免阳光直射红外接收窗。 |  |
| 3 | kb_tickets | T0178 | 工单 T0178｜产品 EUFY-G20-HYBRID 现象：找不到基站 原因：基站位置遮挡 处理步骤：调整基站到靠墙开 |  |
| 4 | kb_manual | manual_rv_v2 | # eufy L60 / G 系列 用户手册（排障节选）  ## 1 吸力下降的常见原因 吸力下降通常由四类原因造成：滚 |  |
| 5 | kb_tickets | T0168 | 工单 T0168｜产品 EUFY-G20-HYBRID 现象：找不到基站 原因：基站位置遮挡 处理步骤：调整基站到靠墙开 |  |

## v2-01　待标注

- 用户原话：滚刷怎么拆，需要工具吗
- 范围：confirmed_sku / EUFY-L60-HYBRID　症状：['滚刷拆卸']
- 实际 query：`EUFY-L60-HYBRID 滚刷拆卸`
- 现有金标：doc=['manual_rv_v2'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v2 | # eufy L60 / G 系列 用户手册（排障节选）  ## 1 吸力下降的常见原因 吸力下降通常由四类原因造成：滚 |  |
| 2 | kb_tickets | T0164 | 工单 T0164｜产品 EUFY-L60-HYBRID 现象：边刷不转 原因：边刷缠绕毛发 处理步骤：关机拆下边刷清理缠 |  |
| 3 | kb_manual | manual_rv_v2 | 滚刷末端轴套可拆下单独清理。  ## 3 滤网与尘盒 G 系列滤网为可水洗 HEPA 滤网，冲洗后需完全晾干。尘盒容量  |  |
| 4 | kb_tickets | T0091 | 工单 T0091｜产品 EUFY-L60-HYBRID 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出滚刷 |  |
| 5 | kb_manual | manual_rv_v2 | 水箱漏水时请检查密封圈是否移位。  ## 5 安全须知 充电时请使用原装基站。若机身发烫、有焦味或冒烟，请立即断电并联系 |  |

## v2-02　待标注

- 用户原话：拖布一股臭味
- 范围：confirmed_sku / EUFY-L60-HYBRID　症状：['拖布异味']
- 实际 query：`EUFY-L60-HYBRID 拖布异味`
- 现有金标：doc=['manual_rv_v2'] cause=- plan=None outcome=standard_flow
- 模型选了：rv_suction_hair_wrap（standard_flow）→ standard_flow
- 起草备注：有证据但无拖布计划

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v2 | 滚刷末端轴套可拆下单独清理。  ## 3 滤网与尘盒 G 系列滤网为可水洗 HEPA 滤网，冲洗后需完全晾干。尘盒容量  |  |
| 2 | kb_faq | faq_rv | 问：拖布有异味 答：请每次使用后取下拖布清洗并晾干；长期潮湿会产生异味。 |  |
| 3 | kb_tickets | T0155 | 工单 T0155｜产品 EUFY-L60-HYBRID 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异 |  |
| 4 | kb_manual | manual_rv_v2 | # eufy L60 / G 系列 用户手册（排障节选）  ## 1 吸力下降的常见原因 吸力下降通常由四类原因造成：滚 |  |
| 5 | kb_tickets | T0141 | 工单 T0141｜产品 EUFY-L60-HYBRID 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出滚刷 |  |

## v2-03　待标注

- 用户原话：水箱底下一直渗水
- 范围：confirmed_sku / EUFY-G50-HYBRID　症状：['水箱漏水']
- 实际 query：`EUFY-G50-HYBRID 水箱漏水`
- 现有金标：doc=['manual_rv_v2'] cause=- plan=None outcome=standard_flow
- 模型选了：rv_suction_hair_wrap（standard_flow）→ standard_flow

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v2 | 水箱漏水时请检查密封圈是否移位。  ## 5 安全须知 充电时请使用原装基站。若机身发烫、有焦味或冒烟，请立即断电并联系 |  |
| 2 | kb_faq | faq_rv | 问：水箱漏水 答：请检查水箱密封圈是否移位或老化，重新安装到位。 |  |
| 3 | kb_tickets | T0175 | 工单 T0175｜产品 EUFY-G50-HYBRID 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异 |  |
| 4 | kb_manual | manual_rv_v2 | 滚刷末端轴套可拆下单独清理。  ## 3 滤网与尘盒 G 系列滤网为可水洗 HEPA 滤网，冲洗后需完全晾干。尘盒容量  |  |
| 5 | kb_tickets | T0055 | 工单 T0055｜产品 EUFY-G50-HYBRID 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异 |  |

## v2-04　待标注

- 用户原话：尘盒盖好像没扣紧，吸力也不行
- 范围：confirmed_sku / EUFY-G30-VERGE　症状：['尘盒盖未扣紧', '吸力下降']
- 实际 query：`EUFY-G30-VERGE 尘盒盖未扣紧 吸力下降`
- 现有金标：doc=['manual_rv_v2'] cause=- plan=rv_suction_dustbin_full outcome=evidence
- 模型选了：rv_suction_dustbin_full（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v2 | # eufy L60 / G 系列 用户手册（排障节选）  ## 1 吸力下降的常见原因 吸力下降通常由四类原因造成：滚 |  |
| 2 | kb_faq | faq_rv | 问：扫地机吸力变小了怎么办 答：请按顺序检查滚刷是否缠绕毛发、滤网是否堵塞、尘盒是否已满或未装到位、吸口是否有异物，每完 |  |
| 3 | kb_tickets | T0012 | 工单 T0012｜产品 EUFY-G30-VERGE 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤网清洗 |  |
| 4 | kb_manual | manual_rv_v2 | 滚刷末端轴套可拆下单独清理。  ## 3 滤网与尘盒 G 系列滤网为可水洗 HEPA 滤网，冲洗后需完全晾干。尘盒容量  |  |
| 5 | kb_tickets | T0023 | 工单 T0023｜产品 EUFY-G30-VERGE 现象：提示请检查尘盒 原因：尘盒未装到位 处理步骤：重新安装尘盒直 |  |

## v2-05　待标注

- 用户原话：吸不起来东西
- 范围：confirmed_sku / EUFY-L50-SES　症状：['吸力下降']
- 实际 query：`EUFY-L50-SES 吸力下降`
- 现有金标：doc=['manual_rv_v2', 'troubleshooting_rv'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v2 | # eufy L60 / G 系列 用户手册（排障节选）  ## 1 吸力下降的常见原因 吸力下降通常由四类原因造成：滚 |  |
| 2 | kb_faq | faq_rv | 问：扫地机吸力变小了怎么办 答：请按顺序检查滚刷是否缠绕毛发、滤网是否堵塞、尘盒是否已满或未装到位、吸口是否有异物，每完 |  |
| 3 | kb_tickets | T0025 | 工单 T0025｜产品 EUFY-L50-SES 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异物 结 |  |
| 4 | kb_manual | manual_rv_v2 | 滚刷末端轴套可拆下单独清理。  ## 3 滤网与尘盒 G 系列滤网为可水洗 HEPA 滤网，冲洗后需完全晾干。尘盒容量  |  |
| 5 | kb_tickets | T0161 | 工单 T0161｜产品 EUFY-L50-SES 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出滚刷清理缠 |  |

## cat-01　待标注

- 用户原话：扫地机不吸
- 范围：category_only / robot_vacuum　症状：['不吸']
- 实际 query：`扫地机器人 不吸`
- 现有金标：doc=['troubleshooting_rv'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |
| 2 | kb_manual | troubleshooting_rv | 3. 若四步均无效且伴随异响，转电机故障流程（见 D）。  ## B. 边刷不转 1. 关机后拆下边刷，清理缠绕的毛发与 |  |
| 3 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |

## cat-02　待标注

- 用户原话：边刷不转了
- 范围：category_only / robot_vacuum　症状：['边刷不转']
- 实际 query：`扫地机器人 边刷不转`
- 现有金标：doc=['troubleshooting_rv'] cause=- plan=rv_suction_side_brush outcome=evidence
- 模型选了：rv_suction_side_brush（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | 3. 若四步均无效且伴随异响，转电机故障流程（见 D）。  ## B. 边刷不转 1. 关机后拆下边刷，清理缠绕的毛发与 |  |
| 2 | kb_faq | faq_rv | 问：边刷不转怎么办 答：先关机拆下边刷清理缠绕物，检查边刷轴是否有异物或进水；清理后仍不转请联系售后。 |  |
| 3 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |
| 4 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |

## cat-03　待标注

- 用户原话：提示请检查尘盒
- 范围：category_only / robot_vacuum　症状：['提示请检查尘盒']
- 实际 query：`扫地机器人 提示请检查尘盒`
- 现有金标：doc=['troubleshooting_rv'] cause=- plan=rv_suction_dustbin_full outcome=evidence
- 模型选了：rv_suction_dustbin_full（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | 3. 若四步均无效且伴随异响，转电机故障流程（见 D）。  ## B. 边刷不转 1. 关机后拆下边刷，清理缠绕的毛发与 |  |
| 2 | kb_faq | faq_rv | 问：提示请检查尘盒是什么意思 答：表示尘盒未装到位或已满。请倒空尘盒并重新安装，听到咔哒声即到位。 |  |
| 3 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |
| 4 | kb_faq | faq_rv | 问：语音提示请检查滚刷 答：表示滚刷被缠绕或卡住，请取出滚刷清理后装回。 |  |
| 5 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |

## cat-04　待标注

- 用户原话：扫地机器人不充电
- 范围：category_only / robot_vacuum　症状：['不充电']
- 实际 query：`扫地机器人 不充电`
- 现有金标：doc=['troubleshooting_rv'] cause=- plan=None outcome=standard_flow
- 模型选了：rv_suction_hair_wrap（standard_flow）→ standard_flow

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |
| 2 | kb_faq | faq_rv | 问：机器不充电怎么办 答：确认基站电源灯亮、触点无灰尘，手动放回基站观察 5 分钟；仍不充电请联系售后。 |  |
| 3 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |
| 4 | kb_faq | faq_rv | 问：机器找不到基站 答：请把基站放在靠墙、前方 1.5 米无障碍的位置，避免阳光直射红外接收窗。 |  |
| 5 | kb_manual | troubleshooting_rv | 3. 若四步均无效且伴随异响，转电机故障流程（见 D）。  ## B. 边刷不转 1. 关机后拆下边刷，清理缠绕的毛发与 |  |

## cat-05　待标注

- 用户原话：扫地机滤网怎么洗
- 范围：category_only / robot_vacuum　症状：['滤网清洗']
- 实际 query：`扫地机器人 滤网清洗`
- 现有金标：doc=[] cause=- plan=rv_suction_filter_clog outcome=standard_flow
- 模型选了：rv_suction_filter_clog（synthesize）→ evidence
- 起草备注：排障手册 A 节只提「滤网是否洗过」，是否算命中由标注决定

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |
| 2 | kb_faq | faq_rv | 问：滤网可以水洗吗 答：可水洗机型的滤网可用清水冲洗，需完全晾干 24 小时后再装回，切勿潮湿装回。 |  |
| 3 | kb_manual | troubleshooting_rv | 3. 若四步均无效且伴随异响，转电机故障流程（见 D）。  ## B. 边刷不转 1. 关机后拆下边刷，清理缠绕的毛发与 |  |
| 4 | kb_faq | faq_rv | 问：滤网多久更换 答：建议每两周清洁一次、每 3 至 6 个月更换一次；破损或变形时立即更换。 |  |
| 5 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |

## multi-01　待标注

- 用户原话：扫完还有渣，滚刷刚清过，回基站也不集尘
- 范围：confirmed_sku / EUFY-X10-PRO-OMNI　症状：['清扫后残留碎屑', '滚刷已清理', '基站不集尘']
- 实际 query：`EUFY-X10-PRO-OMNI 清扫后残留碎屑 滚刷已清理 基站不集尘`
- 现有金标：doc=['manual_rv_v1'] cause=- plan=rv_suction_filter_clog outcome=evidence
- 模型选了：rv_suction_filter_clog（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 2 | kb_tickets | T0151 | 工单 T0151｜产品 EUFY-X10-PRO-OMNI 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出 |  |
| 3 | kb_manual | manual_rv_v1 | 滚刷两端的轴承处如有毛发缠绕，需一并清理，否则滚刷转动阻力增大、吸力下降。  ### 1.2 清洁滤网（c15） 打开尘 |  |
| 4 | kb_tickets | T0162 | 工单 T0162｜产品 EUFY-X10-PRO-OMNI 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤 |  |
| 5 | kb_manual | manual_rv_v1 | ### 1.4 边刷维护（c21） 边刷用螺丝固定，拆下后清理缠绕物，若刷毛变形请更换。拆装边刷前请先关机。边刷缠绕毛发 |  |

## multi-02　待标注

- 用户原话：吸力弱，而且声音比以前大很多
- 范围：confirmed_sku / EUFY-X9-PRO　症状：['吸力弱', '噪音变大']
- 实际 query：`EUFY-X9-PRO 吸力弱 噪音变大`
- 现有金标：doc=['manual_rv_v1', 'T0015'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence
- 起草备注：T0015 为 unsolved 反证；噪音大是否触发 R4 由 rules 决定

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | 滚刷两端的轴承处如有毛发缠绕，需一并清理，否则滚刷转动阻力增大、吸力下降。  ### 1.2 清洁滤网（c15） 打开尘 |  |
| 2 | kb_faq | faq_rv | 问：机器运行时声音很大 答：先检查吸口和滚刷是否有异物；若伴随异响或焦味请立即关机并联系售后。 |  |
| 3 | kb_tickets | T0125 | 工单 T0125｜产品 EUFY-X9-PRO 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异物 结果 |  |
| 4 | kb_manual | manual_rv_v1 | ### 1.4 边刷维护（c21） 边刷用螺丝固定，拆下后清理缠绕物，若刷毛变形请更换。拆装边刷前请先关机。边刷缠绕毛发 |  |
| 5 | kb_tickets | T0051 | 工单 T0051｜产品 EUFY-X9-PRO 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出滚刷清理缠绕 |  |

## multi-03　待标注

- 用户原话：边刷不转，机器还老在地毯边打转
- 范围：confirmed_sku / EUFY-G50-HYBRID　症状：['边刷不转', '地毯边打转']
- 实际 query：`EUFY-G50-HYBRID 边刷不转 地毯边打转`
- 现有金标：doc=['troubleshooting_rv'] cause=- plan=rv_suction_side_brush outcome=evidence
- 模型选了：rv_suction_side_brush（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | 3. 若四步均无效且伴随异响，转电机故障流程（见 D）。  ## B. 边刷不转 1. 关机后拆下边刷，清理缠绕的毛发与 |  |
| 2 | kb_faq | faq_rv | 问：边刷不转怎么办 答：先关机拆下边刷清理缠绕物，检查边刷轴是否有异物或进水；清理后仍不转请联系售后。 |  |
| 3 | kb_tickets | T0171 | 工单 T0171｜产品 EUFY-G50-HYBRID 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出滚刷 |  |
| 4 | kb_manual | manual_rv_v2 | # eufy L60 / G 系列 用户手册（排障节选）  ## 1 吸力下降的常见原因 吸力下降通常由四类原因造成：滚 |  |
| 5 | kb_faq | faq_rv | 问：机器在地毯边缘打转 答：请修剪地毯流苏或设置禁区。 |  |

## neg-01　待标注

- 用户原话：不是吸力小，是有异响
- 范围：confirmed_sku / EUFY-X10-PRO-OMNI　症状：['异响']
- 实际 query：`EUFY-X10-PRO-OMNI 异响`
- 现有金标：doc=['manual_rv_v1', 'troubleshooting_rv'] cause=- plan=rv_suction_motor_fault outcome=escalate
- 模型选了：rv_suction_motor_fault（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 2 | kb_faq | faq_rv | 问：机器有异响 答：先关机检查滚刷、边刷和轮子是否有异物；持续异响请停用并联系售后。 |  |
| 3 | kb_tickets | T0151 | 工单 T0151｜产品 EUFY-X10-PRO-OMNI 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出 |  |
| 4 | kb_manual | manual_rv_v1 | ### 1.4 边刷维护（c21） 边刷用螺丝固定，拆下后清理缠绕物，若刷毛变形请更换。拆装边刷前请先关机。边刷缠绕毛发 |  |
| 5 | kb_tickets | T0162 | 工单 T0162｜产品 EUFY-X10-PRO-OMNI 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤 |  |

## neg-02　待标注

- 用户原话：滚刷没缠头发，很干净，但还是不吸
- 范围：confirmed_sku / EUFY-X8-PRO-SES　症状：['滚刷干净', '不吸']
- 实际 query：`EUFY-X8-PRO-SES 滚刷干净 不吸`
- 现有金标：doc=['manual_rv_v1'] cause=- plan=rv_suction_filter_clog outcome=evidence
- 模型选了：rv_suction_filter_clog（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 2 | kb_tickets | T0081 | 工单 T0081｜产品 EUFY-X8-PRO-SES 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出滚刷 |  |
| 3 | kb_manual | manual_rv_v1 | 滚刷两端的轴承处如有毛发缠绕，需一并清理，否则滚刷转动阻力增大、吸力下降。  ### 1.2 清洁滤网（c15） 打开尘 |  |
| 4 | kb_tickets | T0061 | 工单 T0061｜产品 EUFY-X8-PRO-SES 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出滚刷 |  |
| 5 | kb_manual | manual_rv_v1 | ### 1.4 边刷维护（c21） 边刷用螺丝固定，拆下后清理缠绕物，若刷毛变形请更换。拆装边刷前请先关机。边刷缠绕毛发 |  |

## neg-03　待标注

- 用户原话：尘盒倒过了也装好了，吸力还是上不来
- 范围：confirmed_sku / EUFY-L60-HYBRID　症状：['尘盒已清理', '吸力下降']
- 实际 query：`EUFY-L60-HYBRID 尘盒已清理 吸力下降`
- 现有金标：doc=['manual_rv_v2'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v2 | # eufy L60 / G 系列 用户手册（排障节选）  ## 1 吸力下降的常见原因 吸力下降通常由四类原因造成：滚 |  |
| 2 | kb_faq | faq_rv | 问：扫地机吸力变小了怎么办 答：请按顺序检查滚刷是否缠绕毛发、滤网是否堵塞、尘盒是否已满或未装到位、吸口是否有异物，每完 |  |
| 3 | kb_tickets | T0141 | 工单 T0141｜产品 EUFY-L60-HYBRID 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出滚刷 |  |
| 4 | kb_manual | manual_rv_v2 | 滚刷末端轴套可拆下单独清理。  ## 3 滤网与尘盒 G 系列滤网为可水洗 HEPA 滤网，冲洗后需完全晾干。尘盒容量  |  |
| 5 | kb_tickets | T0091 | 工单 T0091｜产品 EUFY-L60-HYBRID 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出滚刷 |  |

## typo-01　待标注

- 用户原话：吸利变小了
- 范围：confirmed_sku / EUFY-X10-PRO-OMNI　症状：['吸力变小']
- 实际 query：`EUFY-X10-PRO-OMNI 吸力变小`
- 现有金标：doc=['manual_rv_v1', 'troubleshooting_rv'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_filter_clog（synthesize）→ evidence
- 起草备注：看 intake 是否已纠错；若 symptoms 仍带错字则考验 BM25

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 2 | kb_faq | faq_rv | 问：扫地机吸力变小了怎么办 答：请按顺序检查滚刷是否缠绕毛发、滤网是否堵塞、尘盒是否已满或未装到位、吸口是否有异物，每完 |  |
| 3 | kb_tickets | T0162 | 工单 T0162｜产品 EUFY-X10-PRO-OMNI 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤 |  |
| 4 | kb_manual | manual_rv_v1 | 滚刷两端的轴承处如有毛发缠绕，需一并清理，否则滚刷转动阻力增大、吸力下降。  ### 1.2 清洁滤网（c15） 打开尘 |  |
| 5 | kb_tickets | T0002 | 工单 T0002｜产品 EUFY-X10-PRO-OMNI 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤 |  |

## typo-02　待标注

- 用户原话：扫地机跟没吸一样，白跑
- 范围：confirmed_sku / EUFY-X9-PRO　症状：[]
- 实际 query：`EUFY-X9-PRO 扫地机跟没吸一样，白跑`
- 现有金标：doc=['troubleshooting_rv', 'manual_rv_v1'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence
- 起草备注：symptoms 为空时 query 退回原文

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | 滚刷两端的轴承处如有毛发缠绕，需一并清理，否则滚刷转动阻力增大、吸力下降。  ### 1.2 清洁滤网（c15） 打开尘 |  |
| 2 | kb_tickets | T0051 | 工单 T0051｜产品 EUFY-X9-PRO 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出滚刷清理缠绕 |  |
| 3 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 4 | kb_tickets | T0125 | 工单 T0125｜产品 EUFY-X9-PRO 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异物 结果 |  |
| 5 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |

## typo-03　待标注

- 用户原话：机器人一跑一地毛
- 范围：confirmed_sku / EUFY-G40-HYBRID　症状：['清扫后残留毛发']
- 实际 query：`EUFY-G40-HYBRID 清扫后残留毛发`
- 现有金标：doc=['manual_rv_v2'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v2 | 滚刷末端轴套可拆下单独清理。  ## 3 滤网与尘盒 G 系列滤网为可水洗 HEPA 滤网，冲洗后需完全晾干。尘盒容量  |  |
| 2 | kb_tickets | T0064 | 工单 T0064｜产品 EUFY-G40-HYBRID 现象：边刷不转 原因：边刷缠绕毛发 处理步骤：关机拆下边刷清理缠 |  |
| 3 | kb_manual | manual_rv_v2 | # eufy L60 / G 系列 用户手册（排障节选）  ## 1 吸力下降的常见原因 吸力下降通常由四类原因造成：滚 |  |
| 4 | kb_tickets | T0075 | 工单 T0075｜产品 EUFY-G40-HYBRID 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异 |  |
| 5 | kb_manual | manual_rv_v2 | 水箱漏水时请检查密封圈是否移位。  ## 5 安全须知 充电时请使用原装基站。若机身发烫、有焦味或冒烟，请立即断电并联系 |  |

## ctr-01　待标注

- 用户原话：吸力变小，扫不干净
- 范围：confirmed_sku / EUFY-E20　症状：['吸力变小', '扫不干净']
- 实际 query：`EUFY-E20 吸力变小 扫不干净`
- 现有金标：doc=['troubleshooting_rv', 'T0021'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence
- 起草备注：T0021 同症状但 escalated；synthesize 不应把它当成功依据，grade 后 case_outcome 需可见

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |
| 2 | kb_faq | faq_rv | 问：扫地机吸力变小了怎么办 答：请按顺序检查滚刷是否缠绕毛发、滤网是否堵塞、尘盒是否已满或未装到位、吸口是否有异物，每完 |  |
| 3 | kb_tickets | T0195 | 工单 T0195｜产品 EUFY-E20 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异物 结果：so |  |
| 4 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |
| 5 | kb_tickets | T0014 | 工单 T0014｜产品 EUFY-E20 现象：边刷不转 原因：边刷缠绕毛发 处理步骤：关机拆下边刷清理缠绕物 结果：s |  |

## ctr-02　待标注

- 用户原话：边刷不转
- 范围：confirmed_sku / EUFY-G40-HYBRID　症状：['边刷不转']
- 实际 query：`EUFY-G40-HYBRID 边刷不转`
- 现有金标：doc=['troubleshooting_rv', 'T0024'] cause=- plan=rv_suction_side_brush outcome=evidence
- 模型选了：rv_suction_side_brush（synthesize）→ evidence
- 起草备注：T0024 unsolved

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v2 | # eufy L60 / G 系列 用户手册（排障节选）  ## 1 吸力下降的常见原因 吸力下降通常由四类原因造成：滚 |  |
| 2 | kb_faq | faq_rv | 问：边刷不转怎么办 答：先关机拆下边刷清理缠绕物，检查边刷轴是否有异物或进水；清理后仍不转请联系售后。 |  |
| 3 | kb_tickets | T0064 | 工单 T0064｜产品 EUFY-G40-HYBRID 现象：边刷不转 原因：边刷缠绕毛发 处理步骤：关机拆下边刷清理缠 |  |
| 4 | kb_manual | troubleshooting_rv | 3. 若四步均无效且伴随异响，转电机故障流程（见 D）。  ## B. 边刷不转 1. 关机后拆下边刷，清理缠绕的毛发与 |  |
| 5 | kb_tickets | T0075 | 工单 T0075｜产品 EUFY-G40-HYBRID 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异 |  |

## ctr-03　待标注

- 用户原话：路线乱七八糟，扫过的地方又扫
- 范围：confirmed_sku / EUFY-15C-MAX　症状：['清扫路线混乱']
- 实际 query：`EUFY-15C-MAX 清扫路线混乱`
- 现有金标：doc=['T0030'] cause=- plan=None outcome=standard_flow
- 模型选了：rv_suction_hair_wrap（standard_flow）→ standard_flow

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | troubleshooting_rv | # 扫地机器人排障手册（客服内部版）  ## A. 吸力下降 / 扫不干净 1. 先问三件事：多久没清理滚刷、滤网是否洗 |  |
| 2 | kb_faq | faq_rv | 问：清扫路线乱 答：请擦拭前方激光雷达 / 摄像头窗口，并在光线充足时重新建图。 |  |
| 3 | kb_tickets | T0130 | 工单 T0130｜产品 EUFY-15C-MAX 现象：清扫路线混乱 原因：雷达窗口脏污 处理步骤：擦拭雷达窗口并重新建 |  |
| 4 | kb_manual | troubleshooting_rv | 2. 检查尘盒触点是否被灰尘覆盖，用干布擦拭。 3. 仍提示 → 升级人工。  ## D. 异响 / 焦味 / 过热（安 |  |
| 5 | kb_tickets | T0035 | 工单 T0035｜产品 EUFY-15C-MAX 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异物 结 |  |

## none-01　待标注

- 用户原话：App 连不上机器
- 范围：confirmed_sku / EUFY-X10-PRO-OMNI　症状：['App 无法连接']
- 实际 query：`EUFY-X10-PRO-OMNI App 无法连接`
- 现有金标：doc=[] cause=- plan=None outcome=standard_flow
- 模型选了：rv_suction_hair_wrap（standard_flow）→ standard_flow

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | 电池出现鼓包、漏液时请远离火源并联系售后回收，不要继续充电或使用。  ## 第 3 章 指示灯与语音提示  / 现象 / |  |
| 2 | kb_faq | faq_rv | 问：App 连不上机器 答：请确认手机连接 2.4G Wi-Fi，重置机器网络后重新配网。 |  |
| 3 | kb_tickets | T0138 | 工单 T0138｜产品 EUFY-X10-PRO-OMNI 现象：找不到基站 原因：基站位置遮挡 处理步骤：调整基站到靠 |  |
| 4 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 5 | kb_tickets | T0137 | 工单 T0137｜产品 EUFY-X10-PRO-OMNI 现象：不充电 原因：基站触点脏污 处理步骤：擦拭触点后手动放 |  |

## none-02　待标注

- 用户原话：语音是英文的，怎么改中文
- 范围：confirmed_sku / EUFY-X9-PRO　症状：['语音语言设置']
- 实际 query：`EUFY-X9-PRO 语音语言设置`
- 现有金标：doc=[] cause=- plan=None outcome=standard_flow
- 模型选了：rv_suction_hair_wrap（standard_flow）→ standard_flow

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | 电池出现鼓包、漏液时请远离火源并联系售后回收，不要继续充电或使用。  ## 第 3 章 指示灯与语音提示  / 现象 / |  |
| 2 | kb_tickets | T0125 | 工单 T0125｜产品 EUFY-X9-PRO 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异物 结果 |  |
| 3 | kb_manual | manual_rv_v1 | ### 1.4 边刷维护（c21） 边刷用螺丝固定，拆下后清理缠绕物，若刷毛变形请更换。拆装边刷前请先关机。边刷缠绕毛发 |  |
| 4 | kb_tickets | T0188 | 工单 T0188｜产品 EUFY-X9-PRO 现象：找不到基站 原因：基站位置遮挡 处理步骤：调整基站到靠墙开阔位置  |  |
| 5 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |

## none-03　待标注

- 用户原话：机器从楼梯上掉下来了，还能用吗
- 范围：confirmed_sku / EUFY-G50-HYBRID　症状：['跌落']
- 实际 query：`EUFY-G50-HYBRID 跌落`
- 现有金标：doc=[] cause=- plan=None outcome=standard_flow
- 模型选了：rv_suction_hair_wrap（standard_flow）→ standard_flow

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v2 | # eufy L60 / G 系列 用户手册（排障节选）  ## 1 吸力下降的常见原因 吸力下降通常由四类原因造成：滚 |  |
| 2 | kb_tickets | T0175 | 工单 T0175｜产品 EUFY-G50-HYBRID 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异 |  |
| 3 | kb_manual | manual_rv_v2 | 滚刷末端轴套可拆下单独清理。  ## 3 滤网与尘盒 G 系列滤网为可水洗 HEPA 滤网，冲洗后需完全晾干。尘盒容量  |  |
| 4 | kb_tickets | T0055 | 工单 T0055｜产品 EUFY-G50-HYBRID 现象：噪音变大吸力弱 原因：吸口卡异物 处理步骤：检查吸口取出异 |  |
| 5 | kb_manual | manual_rv_v2 | 水箱漏水时请检查密封圈是否移位。  ## 5 安全须知 充电时请使用原装基站。若机身发烫、有焦味或冒烟，请立即断电并联系 |  |

## none-04　待标注

- 用户原话：保修多久，能换新吗
- 范围：confirmed_sku / EUFY-X10-PRO-OMNI　症状：['保修咨询']
- 实际 query：`EUFY-X10-PRO-OMNI 保修咨询`
- 现有金标：doc=[] cause=- plan=None outcome=standard_flow
- 模型选了：rv_suction_hair_wrap（standard_flow）→ standard_flow
- 起草备注：应由意图路由到凭证 / 升级子流程而非诊断；若进入检索，期望 no_match

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 2 | kb_tickets | T0137 | 工单 T0137｜产品 EUFY-X10-PRO-OMNI 现象：不充电 原因：基站触点脏污 处理步骤：擦拭触点后手动放 |  |
| 3 | kb_manual | manual_rv_v1 | ### 1.4 边刷维护（c21） 边刷用螺丝固定，拆下后清理缠绕物，若刷毛变形请更换。拆装边刷前请先关机。边刷缠绕毛发 |  |
| 4 | kb_tickets | T0187 | 工单 T0187｜产品 EUFY-X10-PRO-OMNI 现象：不充电 原因：基站触点脏污 处理步骤：擦拭触点后手动放 |  |
| 5 | kb_manual | manual_rv_v1 | 电池出现鼓包、漏液时请远离火源并联系售后回收，不要继续充电或使用。  ## 第 3 章 指示灯与语音提示  / 现象 / |  |

## exact-01　待标注

- 用户原话：它一直说请检查滚刷
- 范围：confirmed_sku / EUFY-X10-PRO-OMNI　症状：['提示请检查滚刷']
- 实际 query：`EUFY-X10-PRO-OMNI 提示请检查滚刷`
- 现有金标：doc=['manual_rv_v1'] cause=- plan=rv_suction_hair_wrap outcome=evidence
- 模型选了：rv_suction_hair_wrap（synthesize）→ evidence

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 2 | kb_faq | faq_rv | 问：语音提示请检查滚刷 答：表示滚刷被缠绕或卡住，请取出滚刷清理后装回。 |  |
| 3 | kb_tickets | T0151 | 工单 T0151｜产品 EUFY-X10-PRO-OMNI 现象：吸力变小，扫不干净 原因：滚刷毛发缠绕 处理步骤：取出 |  |
| 4 | kb_manual | manual_rv_v1 | / 现象 / 含义 / 处理 / / --- / --- / --- / / 「请检查滚刷」 / 滚刷被缠绕或卡住 /  |  |
| 5 | kb_faq | faq_rv | 问：提示请检查尘盒是什么意思 答：表示尘盒未装到位或已满。请倒空尘盒并重新安装，听到咔哒声即到位。 |  |

## exact-02　待标注

- 用户原话：红灯一直亮着不动
- 范围：confirmed_sku / EUFY-X8-PRO-SES　症状：['红灯常亮']
- 实际 query：`EUFY-X8-PRO-SES 红灯常亮`
- 现有金标：doc=['manual_rv_v1'] cause=- plan=None outcome=standard_flow
- 模型选了：rv_suction_hair_wrap（standard_flow）→ standard_flow

| # | 来源 | doc_id | 片段 | 算金标? |
| --- | --- | --- | --- | --- |
| 1 | kb_manual | manual_rv_v1 | 电池出现鼓包、漏液时请远离火源并联系售后回收，不要继续充电或使用。  ## 第 3 章 指示灯与语音提示  / 现象 / |  |
| 2 | kb_faq | faq_rv | 问：机器一直红灯常亮 答：通常是主机故障或被卡住，请把主机移到开阔处重启；仍红灯请联系售后。 |  |
| 3 | kb_tickets | T0172 | 工单 T0172｜产品 EUFY-X8-PRO-SES 现象：吸力下降，尘盒很快满 原因：滤网堵塞 处理步骤：取出滤网清 |  |
| 4 | kb_manual | manual_rv_v1 | # eufy X10 Pro Omni 用户手册（排障节选）  ## 第 1 章 日常维护  ### 1.1 清理滚刷（ |  |
| 5 | kb_tickets | T0179 | 工单 T0179｜产品 EUFY-X8-PRO-SES 现象：拖布异味 原因：拖布未及时清洗 处理步骤：取下拖布清洗晾干 |  |
