# 官方工作簿四项问题核查

核查日期：2026-10-09。核查对象仅为资料包中的原始工作簿，不使用本地导出文件或旧分析报告作为证据。

原始来源：[黑客松智能服务赛题资料.xlsx](../../【黑客松智能服务赛道】工具资料包/黑客松智能服务赛题资料.xlsx)。下文所有单元格均指此文件。T2、T4、T47、T50 是项目采用的工单序号，对应「客诉工单信息」第 3、5、48、51 行；原工作簿没有 T 编号列。

SKU 是商品库存编码。PN 是产品型号编码。订单号标识一次订单，订单明细标识该订单内的商品行，物流单号标识包裹运输记录。原表「No.」是行序号，不能当子订单号。

## 结论

| 项目 | 可确认事实 | 是否能认定官方资料质量问题 | 正确处理 |
| --- | --- | --- | --- |
| T4 | 工单产品名 X10 Pro 与同一 SKU、同订单的 E25 描述冲突 | 可确认内部产品标注不一致。工单产品名误标的证据强 | 商品身份优先依据精确 SKU 与订单明细确认；保留原始冲突，按 E25 查询物流 |
| T2 | 客户将 `-2` 运单描述为配件，订单把它映射为整机；客户查询 `-3` 为 UPS 标签已创建，订单把它映射为配件且已送达 | 可确认客户陈述与记录冲突，不能证明订单记录错。邮件时间缺失，状态差异可能发生在不同时间 | 同时保留客户陈述和两条物流记录，核实包裹标签、实际内容及交付凭证，不给无依据的预计到达时间 |
| T47 | 邮件明确查询 Hub 配件；同订单查询只返回旧整机，配件发货记录未提供 | 可确认资料覆盖不足，不能唯一认定售后补寄，也不能直接认定工单主产品 SKU 错 | 按订单号 + 配件 SKU 查关联发货/售后记录；查不到时明确无法确认该配件运单 |
| T50 | 原文 `the left one does work` 是左边可以工作的肯定句，未说明哪个部件故障 | 客户表达不完整/意图歧义，不能证明官方录入错或漏了 `not` | 澄清左右侧及具体症状，禁止自动改成左泵不工作 |

## T4：产品名与 SKU 冲突

### 原始证据

| 工作表与单元格 | 原始值 |
| --- | --- |
| 客诉工单信息!B5 | `X10 Pro` |
| 客诉工单信息!D5 | `Anker004` |
| 客诉工单信息!E5 | `T2353T11` |
| 客诉工单信息!C5，必要片段 | `I ordered your omni robot with 1-3 business day delivery on 14 September.`；`It is with Australia post at present and they say that they won't follow up the tracking until 30 September.` |
| 订单信息!B6:B7，合并单元格 | `Anker004` |
| 订单信息!C6 | `T2353T11` |
| 订单信息!D6 | `eufy Robot Vacuum Omni E25` |
| 订单信息!F6 | `2026-09-12 00:00:00` |
| 订单信息!J6:J7，合并单元格 | `Australia Post` |
| 订单信息!K6:K7，合并单元格 | `Anker1234567-5` |
| 订单信息!L6:L7，合并单元格 | `Delivered on 9/20` |
| 订单信息!M6 | `2026-09-14 00:00:00` |
| eufy Robovacs Q&A!D11 | `What should I do if eufy Robot Vacuum Omni E25(T2353) always shows offline?` |
| eufy Robovacs Q&A!I11 | `T2353` |
| eufy Robovacs Q&A!C5 | `eufy Clean X10 Pro Omni` |
| eufy Robovacs Q&A!I5 | `T2351` |

精确 SKU `T2353T11` 在全部订单数据中只出现一次，对应 E25。知识库标题独立确认 `T2353` 是 E25，`T2351` 是 X10 Pro。全部工单中其他 `T2353` 系列 SKU 均标 E25，只有 B5 标 X10 Pro。不能只依赖 SKU 前缀猜型号；此处存在精确订单映射和知识库型号映射两条证据。

可以确认源资料内部标签冲突，建议将工单规范化产品名设为 E25，同时保留 `B5=X10 Pro` 和来源位置作为原始值。尚无官方勘误，不能声称已由资料提供方确认哪个字段误录。

客户提到 9 月 14 日下单，订单购买日期为 9 月 12 日、发货日期为 9 月 14 日。这个差异也应保留，但可能是客户把发货日作为下单日。缺邮件提交时间，不能证明客户来信时物流已经送达，也不能把静态送达状态当实时查询结果。

### 正确回答与评测

应表述为“订单记录显示该订单的 E25 使用 Australia Post 运单 `Anker1234567-5`，记录状态为 9 月 20 日送达；这与您反映仍未收到的情况需要核实”。若用户仍未收到，应核对交付凭证和地址/包裹信息并交人工处理。不要因为表中写了 delivered 就认定客户已经收到。

评测应接受按 SKU/订单确认 E25，也应接受识别冲突后先确认型号。不得把按工单 B5 盲选 X10 故障知识当正确答案。若只询问配送，回复可以省略型号，集中处理物流和未收到货。

## T2：同订单两条商品明细及运单映射冲突

### 原始证据

「订单信息」B3:B4 合并并写 `Anker002`，所以第 3、4 行属于同一订单。A3=`2`、A4=`3` 是「No.」序号；文件未提供独立子订单号。J、K、L 第 3、4 行没有合并，所以两条运单不能合并成一个状态。

| 字段 | 第 3 行整机明细 | 第 4 行配件明细 |
| --- | --- | --- |
| SKU，C3/C4 | `T2080GA1` | `T29C2001` |
| 描述，D3/D4 | `eufy Robot Vacuum and Mop, S1 Pro Omni, HydroJet System with Roller Mop` | `EUFY S1 PRO REPLACEMENT ACCESSORY KIT` |
| 数量，E3/E4 | `1` | `1` |
| 承运商，J3/J4 | `ANPOST` | `UPS` |
| 物流单号，K3/K4 | `Anker1234567-2` | `Anker1234567-3` |
| 物流状态，L3/L4 | `Delivered on 9/21` | `Delivered on 9/24` |
| 发货日期，M3/M4 | `2026-09-18 00:00:00` | `2026-09-20 00:00:00` |

客诉工单信息!C3 必要原文：

> I have received ine package today with tracking number
> Anker1234567-2. The package only contains the replacement accessories kit. I have not received the Eufy S1 robot vacuum yet. When trying to track the shipment Anker1234567-3, UPS website says that the label has been created, but there is no further information.

客户和订单共同指向 `Anker002`（客诉工单信息!D3；订单信息!B3:B4），但对包裹 `-2` 的内容归属冲突。客户称 `-3` 由 UPS 处理，与 J4 一致；仅对其商品归属及状态理解不同。`label has been created` 与 `Delivered on 9/24` 可能是时间差，工单没有提交时间，不能直接证明官方物流状态错误。

### 正确回答与评测

“目前订单记录分别把 S1 Pro 整机列在 `Anker1234567-2`，把配件包列在 UPS `Anker1234567-3`；但您实际收到 `-2` 的配件包，与记录不一致。需要核对两件包裹的运输标签、发货内容和交付记录后确认整机在哪个包裹。”

评测应考察能否保留两条明细和两个运单，并识别客户陈述冲突。不能要求单一确定的“整机还在 UPS label created”或“客户已收到整机”答案。若官方希望提供确定事实，应补充工单时间、每个运单实际装箱内容、交付凭证，或明确该题是要求识别记录与客户陈述冲突。

## T47：Hub 配件查询缺对应发货记录

### 原始证据

| 工作表与单元格 | 原始值 |
| --- | --- |
| 客诉工单信息!B48 | `S1 Pro Breast Pump` |
| 客诉工单信息!D48 | `Anker010` |
| 客诉工单信息!E48 | `T8D04121` |
| 客诉工单信息!C48，必要片段 | `Is there a tracking number for my shipment yet?`；`SKU: T8D02181-80 (S1/S1 Pro Pump Hub Brown)`；`Quantity: 1`；`Order: Anker010`；`SN: T8D02P20262058EB` |
| 订单信息!B18 | `Anker010` |
| 订单信息!C18 | `T8D04121` |
| 订单信息!D18 | `eufy Security Breast Pump S1 Pro` |
| 订单信息!F18 | `2025-12-02 00:00:00` |
| 订单信息!J18 | `Amazon Logistics` |
| 订单信息!K18 | `Anker1234567-13` |
| 订单信息!L18 | `Delivered on 2025/12/07` |
| 订单信息!M18 | `2025-12-03 00:00:00` |
| eufy Breast Pump Q&A!E42，必要片段 | `You can purchase official replacement parts compatible with the S1 Pro.`；`- Pump Hub (SKU: T8D02181-80)` |
| eufy Breast Pump Q&A!C2 | `Wearable Breast Pump S1 Pro` |
| eufy Breast Pump Q&A!I2 | `T8D04` |

全部订单明细 C2:C25 中无 `T8D02181-80`。`Anker010` 在订单号列只出现 B18，且第 18 行没有跨行合并订单号。全工作簿 `T8D02181-80` 只出现客诉 C48 和知识库 E42。可以确认它是适用于 S1 Pro 的官方配件型号；不能把它当无法识别的错误 SKU。

客户询问的配件与主产品编码不同是正常关系。工单 E48 可能表示售后主产品，邮件 C48 表示当前查询的配件，表没有定义二者必须是同一个商品对象。因此不宜单凭二者不等认定工单 SKU 录入错误。

同订单号只证明客户引用原订单的关联线索。资料没有 Hub 的订单明细、补寄编号、RMA（退换货/售后授权）记录或独立发货记录，不能唯一认定这一定是售后补寄。正常配件购买、售后替换和客户错引订单都仍可能存在。

### 正确回答与评测

“您查询的是 `T8D02181-80` Hub。目前资料中 Anker010 的运单 `Anker1234567-13` 对应 2025 年的 S1 Pro 整机订单，无法据此确认 Hub 的物流。需要进一步查询这个配件的发货/售后记录；如有 Hub 购买或补寄确认、售后编号，可用于核对。”

客户已经提供 SKU、订单号、数量、SN 和地址，不应把同一组信息全部再问一遍。应先查询已给条件，再补问关联凭证。不能断言 Hub 已送达、尚未发货或运单尚未生成；这三种结论均无相应来源。

评测应把识别商品对象差异、拒绝复用旧整机运单、请求/查询关联发货记录作为正确路径。若要求单一运单答案，官方需要补充 `Anker010 → Hub 购买/补寄记录 → 包裹 → 运单` 的关联数据。

## T50：肯定句不能自动改成故障陈述

### 原始证据

| 工作表与单元格 | 原始值 |
| --- | --- |
| 客诉工单信息!B51 | `S1 Pro Breast Pump` |
| 客诉工单信息!C51 | `I have a S1 pump, the left one does work` |
| 客诉工单信息!D51 | `/` |
| 客诉工单信息!E51 | `T8D04121` |
| 客诉工单信息!G51 | `Troubleshooting/Product usage` |

`does work` 明确表示“可以工作”。原文没有 `not`，没有描述右侧故障，也没有具体请求。可能是“左侧可用，右侧不可用”的未完成描述，也可能漏写否定词；仅凭这封邮件无法区分。工单场景标签是 Troubleshooting，不能据此覆盖原文语义。正文 `S1` 也可能是系列简称，与元数据 S1 Pro 不一致尚不足以证明误录。

### 正确回答与评测

“您提到左侧可以工作。请确认是右侧无法工作，还是您想说左侧无法工作，并说明是不能开机、不能充电还是没有吸力。”

评测应要求先澄清故障侧和症状。不能把直接诊断“左泵不开机”设为唯一正确答案。若官方确认确有漏字，应发布勘误并同时修订题面和标准答案；在确认前保留原文。

## 全量商品名与 SKU 映射核查

只读遍历全部 5 张工作表，并依据工作簿底层标记文件（XML）的合并单元格核对订单关系。客诉有效数据为第 2–64 行共 63 条；订单有效商品明细为第 2–25 行共 24 条。Q&A 分别有 593、282 条正文记录；后者还包含摄像头内容，例如 eufy Breast Pump Q&A!C129=`SoloCam S340`。工作表名称不能作为每条记录的产品类型依据。

下表完整列出客诉中出现的「产品名—SKU」组合，行号是直接来源位置。`/` 是原始未给 SKU 标记。`\n` 表示原始值开头换行；不把去空白后的规范化值冒充原始值。

| SKU 原始值 | 产品名原始值 | 客诉行号，产品名 B 列 / SKU E 列 |
| --- | --- | --- |
| E235311B | E25 | 2 |
| T2080GA1 | S1 Pro | 3 |
| T2351V11-F | X10 Pro | 4 |
| T2353T11 | X10 Pro | 5，已确认与订单及 PN 映射冲突 |
| T2353111 | E25 | 6、13、14、28、33、36 |
| T2353G11 | E25 | 7 |
| / | X10 Pro | 8 |
| T2292111 | C10 | 9、10、11 |
| T2080111 | S1 Pro | 12、16、24、26、27、31、32、34、35、37、41、43 |
| T2352111 | E28 | 15、18、19、38、42 |
| T2351111 | X10 Pro | 17、20、21、22、23、25、30、40、44 |
| T2351G21 | X10 Pro | 29 |
| T2351V11 | X10 Pro | 39 |
| T8D04121 | S1 Pro Breast Pump | 45–56 |
| T81701W1 | SoloCam S340 | 57、58、60 |
| / | security camera | 59 |
| `\nT2280111` | `omni c20 `，末尾空格 | 61、62、63 |
| / | eufy cleaner | 64 |

下表完整列出订单「SKU—商品描述」组合，来源为对应行 C、D 两列。

| SKU | 商品描述原始值 | 订单行号 |
| --- | --- | --- |
| E235311B | eufy Robot Vacuum and Mop Combo E25+Replacement Parts Kit,20,000 Pa,Auto Mop Washing&Drying,Pet Hair and Carpet Friendly | 2 |
| T2080GA1 | eufy Robot Vacuum and Mop, S1 Pro Omni, HydroJet System with Roller Mop | 3 |
| T29C2001 | EUFY S1 PRO REPLACEMENT ACCESSORY KIT | 4 |
| T2351V11-F | eufy X10 Pro Omni Robot Vacuum Cleaner & Dual Mops 8000Pa Acceptable Condition | 5 |
| T2353T11 | eufy Robot Vacuum Omni E25 | 6 |
| T29YQA20 | Dust Bag | 7 |
| T2353112 | eufy Robot Vacuum Omni E25 Black 2 | 8 |
| T291HA11 | cleaning solution | 9 |
| T2353G11 | eufy Robotstofzuiger Omni E25 - E25 | 10 |
| T290QAR0 | eufy Accessories Package, Side Brush, Filter, Rolling Brush for Robovac, Dustbag, Roller Mop, Dirty Water Reservoir Filter | 11 |
| T2292111 | eufy Auto-Empty C10 - black | 12、14、16 |
| T290Y000 | eufy Replacement Washable Filter for eufy C10 and C20, 2-Pack Included | 13、15 |
| T2351111 | eufy X10 Pro Omni - Black | 17 |
| T8D04121 | eufy Security Breast Pump S1 Pro | 18 |
| T2351111 | eufy X10 Pro Omni Robot Vacuum | 19 |
| T2351V11 | eufy X10 Pro Omni | 20 |
| T29F70A2 | 6-Pack Large Capacity Anti-Bacterial and Deodorizing Dust Bags, Compatible with eufy Clean X8 Pro with Self-Empty Station | 21 |
| T8D04121 | eufy Security Heated Wearable Breast Pump S1 Pro, Charging Case, Hands-Free | 22、23、24、25 |

映射应区分“整机 SKU 对应型号”和“配件 SKU 适用于型号”，不能把兼容某型号的配件当成该型号整机。描述长短、语言或标题中的兼容产品不一致也不自动等于 SKU 错误。对于 T47，知识库 E42 已给出 Hub 的兼容关系，缺的是该次具体发货关系。

## 标准答案的数据条件

当前资料可以支持准确引用与冲突识别，不能支持上述所有情形的唯一事实结论。正确的评测方式是分别评估：引用了哪些已知字段、是否保持订单明细与运单对象一致、是否保留客户陈述、是否对缺失事实要求核实。若要求确定结果，须补齐必要事实或发布正式勘误，不能由实现方静默修写客户原文。
