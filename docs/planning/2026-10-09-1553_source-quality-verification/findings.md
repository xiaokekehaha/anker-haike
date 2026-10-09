# 核查发现

- 定位原报告 docs/codex/2026-10-09_官方63案例全量测评与改进判断.md §7.1，共六项。
- 原报告已经区分字段不一致、来源冲突、信息不足、原话歧义、知识结构和时效风险；“已确认”标题易被理解为全部属于官方数据错误。
- 官方工作簿位于 docs/【黑客松智能服务赛道】工具资料包/黑客松智能服务赛题资料.xlsx。
- 原始 XML 核对 T46 对应 E124：除混合标题/问句/操作，还提到 bottle、speaker cover、tubing、hoses；需按 S1 Pro 官方部件确认适用性。
- T57 对应 E165 确实有 App 5.0 or higher 和 may be known issues，无有效期或修复版本。工单 C58 仅说多数摄像头不工作、不再录像，未确认升级、App 版本和固件版本；元数据 B58/E58 明确 SoloCam S340/T81701W1。
- 官方 S1 Pro 产品页和手册入口已检索；摄像头版本故障搜索返回多条社区用户陈述，不能将社区域名等同官方缺陷公告。
- 原工作簿 SHA-256：0cc02e6531d627433f9b5dba1978bfbf9f196b4581e033657c37ad2939007eb7。关键原始单元格存于 qa-source-cells.json。
- 官网 https://www.eufy.com/blogs/baby/best-wearable-breast-pump 明确 S1 Pro 为 0 external tubes；https://www.eufy.com/collections/breast-pump 也区分传统管路泵与 S1 Pro 一体可穿戴泵。据此 E124 中要求检查/更换软管的指导不适用于该型号。其余零件词仍需按正式部件名核对，不能把整段内容一概判错。
- 独立工作簿核查：T4 的型号标签与 SKU/订单/Q&A 型号编码冲突；T2 的客户叙述与订单映射及状态冲突，无法确定哪方错误；T47 只有整机记录、无 Hub 出库或售后关联；T50 原话是肯定 does work，不能替换为 doesn't work。
