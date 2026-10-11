# T60 / T43 / T47 修复

时间：2026-10-11 02:30–03:15（北京时间）。来源：`docs/planning/2026-10-10-2103_official-63-continuation/report.md` P1。

## 根因与修复

| 案例 | 根因 | 修复 |
| --- | --- | --- |
| T60 | ① 愿望句「I just want my hoover to clean」被模型抽成症状；`concrete()` 只在检索落空的「缺什么」检查里用，synthesize 的 supported_symptoms 不经过它，rv-0527 被判适用。② rv-0527「We recommend cleaning … so that we can provide…」第二句的 can 让整段被判成说明，说明型指南走「已解释」出口直接 done，客户没有反馈入口 | ① `filter_hypotheses`：覆盖的现象全是愿望句、又没有错误码的候选丢弃（wish_only），交给症状追问。② 以「We recommend / suggest doing…」开头的段落不判说明。全库分类只变 rv-0093 / rv-0527 两段（都是操作建议） |
| T43 | 西语「desconectado」直接作检索词，召回 12 条全是离地 / 被困，没有 Wi-Fi / 离线条目；synthesize 空列表又没给追问 → R5 | 现象全都只有一两个词（汉字不算）、无错误码、召回有结果却没有一条适用时，先请客户具体说一次，带新描述重新检索；只问一次，答完仍查不到再交人工 |
| T47 | intake 把客户贴的表单字段（SKU / SN / 地址 / 商家）都列进 answer_request，超出物流字段 → 走逐字段答复，「Product model: T8D04121」把整机当成客户问的泵头；`record_mismatch_note` 只在物流答复里用 | 客户问的商品与订单记录对不上时，不论 answer_request 列了哪些字段，都先说差异，不逐字段列整机 |

T43 更根本的办法（intake 输出英文症状摘要参与检索）未做，需先用 63 单非英文工单评估。

## 真实回放（镜像重建后）

| 案例 | 会话 | 实际 | 判定 |
| --- | --- | --- | --- |
| T60 | 115a5eec | 首轮出型号卡；选 C20 后不再发 rv-0527 说明并结束，改问「Could you describe what the device is doing…」，stage 仍为 diagnose | 通过 |
| T43 | 8fa613b7 | 首批 synthesize 空列表（补查后第二批对 rv-0271 判待确认），追问「Is the robot currently failing to connect to Wi-Fi, or is it connected to Wi-Fi but showing as offline in the app?」 | 通过：不再直接转人工；这次是第二批候选给出的追问先于新的笼统现象追问生效 |
| T47 | 9f37fe84 | 「The order record shows T8D04121; I don't see a separate shipment for T8D02181-80. If this part came from a separate order…」，不再列「Product model: T8D04121」 | 通过 |

三单采证时 journey 接口均 404（与 21:03 轮记录的同一现象），会话本身正常；T60 第二步用临时脚本在同一会话上选型号完成。

全库 872 个计划比对只有 qa_rv_0093 / qa_rv_0527 变化。单测 5 条（T60 两条、T43、T47 两条中新增一条），T47 去掉修复失败。ci-local 全绿（后端 1271、契约 91、前端 230）。
