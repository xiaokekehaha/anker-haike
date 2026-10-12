# 图片与官方资料复核

评审日期2026-10-11。10张本地原图均逐张查看；以下把肉眼可见、系统实际行为、不能推出的结论分开。原附件在每案过程记录中可直接打开。

## 图片逐张记录

| 案例 | 评审肉眼可见 | 本轮系统路径 | 判断边界 |
| --- | --- | --- | --- |
| T14 | 机器人和基站、前部红灯 | vision成功；依据4090码进售后核资格 | 图像不能证明墙传感器损坏，硬件结论依据是官方报码资料 |
| T20 | 木地板、基站、展开坡道、窗与暖气片，机器人不在画面 | vision成功，图像中文描述进入第二轮检索；问是否同一楼层 | 不能从基站照片得出机器人所在楼层；没有尺标，不能宣称精确间距 |
| T30 | 机器人外壳污迹、红色灯环 | vision成功，对客称外壳脏污并允许纠正，按E4查边刷 | 静态红灯不能判断闪烁、根因；外壳脏不等于电机故障 |
| T38 | 发票Anker012、2024-10-09、英国卖方、X10 Pro Omni | vision成功；先问清水箱水量 | 票据是购买事实，不是水路故障证据；不能见票据就结束排障 |
| T42 | 手持塑料件可见缺口，旁有机器人底部/基站 | vision成功；物损漏水进售后 | 原文漏水需保留；照片不能确认配件SKU、兼容型号及损坏成因 |
| T45 | Aeroflow订单确认、2025-12-09、S1 Pro泵；并非烫伤照片 | 无vision节点；安全规则先停用停充并转人工 | 烫伤来自原文，不是从购买截图识别；美国来自原文，不能说截图完整显示国家 |
| T46 | Anker013、2026-08-27、卖方Anker EufyHome、泵商品 | vision成功；问噪声连续或间歇 | 截图不能证明电机异响；“用了不到一个月”与购买日期不是同一事实 |
| T48 | 泵头、绿色指示点、黄色状态灯、外壳裂纹 | 产品咨询product_help路径；没有vision节点，补型号后检索文本答缺资料 | 不能评成模型“误识别绿色”。无型号标签不能只凭外观定精确型号；单帧无法分常亮/闪烁，裂纹不能自动推出液体/电池风险 |
| T53 | Anker015、2024-12-13、美国卖方Fantasia Trading LLC、S1 Pro | 订单核验后仍有vision，过保后继续诊断 | “24个月”“保内已故障”是客户自述；图像没有证明故障起始时间，不能自动批准或否认例外资格 |
| T55 | Anker016、2026-04-01、S1 Pro、卖方EufyHome | vision成功；订单在保，最终只索故障媒体及SN | 订单图不是故障图，要求故障照片不等于重复要收据；不到三周可能是使用时长而非购买时长 |

8次diagnose.vision最终成功，只证明调用完成，不证明识别全部正确。原始节点与状态在[图片节点证据](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-11-1712_official-63-evaluation/image-node-evidence.json)。本轮没有OCR字段级独立标注评分，不能给出OCR准确率。

T36原工单包含远程媒体URL，但官方本地附件集合没有T36；测试未下载并播放该媒体。报告不宣称已经听到噪声。

## 官方资料与个人判断的分界

| 案例 | 已确认来源事实 | 独立判断 | 尚需谁确认 |
| --- | --- | --- | --- |
| T13 | 本地官方Q&A全文找不到5116；运行状态code_miss且无远端检索调用 | 当前转人工合理，不能硬套相似通信码 | 知识维护方补该型号5116来源 |
| T32 | rv-0061含贴透明胶带临时固定传感器、成功率较高、更换前尝试措辞 | 本轮已展示真正操作，不再错误跳过；成功率及更换承诺不能由资料套话代替审核 | 厂商明确适用条件、风险提示、拒绝临时方案后的流程 |
| T40 | rv-0073确实含瓶安装检查、官方链接、照片/视频请求；卡片另有材料可分开提交说明 | 不能仅凭一张卡包含两种内容判错误；可选改进是拆得更清楚 | 如展开外链步骤，仍须保留液位测量前提 |
| T51 | bp-0111明写speaker cover、蓝牙检查、12秒重置及组合键恢复出厂 | 这些不是模型原创；充电状态和部件适用性仍不明，不能当已核准正确 | 厂商技术审核术语、蓝牙与停机的联系及适用型号 |
| T52 | 官方公共文章标题称充电盒不能充满，正文同时谈盒给泵充电和盒自身充电 | 两个能量传递对象应分开；本轮先问盒本身指示灯正确 | 知识维护方拆对象/重写标题，避免后续复用时混淆 |
| T53 | 系统按订单当前截止日判断过保，之后仍排障 | “保内发生、过保申报”是否例外是政策事实，不应由agent凭经验决定 | 官方售后政策/人工审查；本报告不作现实权利结论 |
| T54/T55 | bp-0125/bp-0102含hose示例；当前qa_overrides已在另一个噪声条目禁用外接软管步骤 | 一体式泵的软管例子需统一复核；本轮没有真正让用户拆软管 | 知识维护方与厂商技术 |

bp前缀不必然意味着乳泵：官方工作簿的“eufy Breast Pump Q&A”表内也包含摄像头条目，bp-0186/bp-0199的directory和PN明确是SoloCam S340。不能只看ID前缀就判跨品类检索错误。

## 本轮查询的外部官方页面

1. [eufy各型号乳泵LED状态页](https://service.eufy.com/article-description/What-does-the-status-of-each-LED-indicator-on-the-eufy-Breast-Pump-E10-S1-S1-Pro-representWhy-does-the-eufy-Breast-Pump-s-flange-stick-to-my-breast)：页面按E10、S1、S1 Pro提供图片表格。这里只据此确认官方存在灯态资料，不声称已从网页图片读出所有颜色含义，也不把静态照片解读成动态灯态。
2. [T8D04官方用户指南入口](https://service.eufy.com/article-description/Wearable-Breast-Pump-S1-Pro-User-Guide-T8D04)：可作为知识补齐入口；本轮没有导入生产知识库。
3. [充电盒无法充电/充满](https://service.eufy.com/article-description/The-charging-case-cannot-charge-be-fully-charged)：正文同时讲泵头与盒内触点对接，以及盒自身充电时长，支持必须区分两个对象的判断。
4. [S1 Pro清洁液使用与测量](https://service.eufy.com/article-description/How-do-I-use-eufy-cleaning-solution-with-my-S1-Pro)：官方先要求标记液位、用完一箱水后比较消耗，再进入下一步。因此液位短时间变化小不能仅凭肉眼就确诊不出液；本轮系统提供链接，不代表测试器完成测量。
5. [S1/S1 Pro清洁液说明](https://service.eufy.com/article-description/The-S1-Series-S1-and-S1-Pro-Cleaning-Solution-Information?urlName=The-S1-Series-S1-and-S1-Pro-Cleaning-Solution-Information)：说明基站自动稀释清洁液，支持“需按消耗量和条件观察”而不是预设故障的逻辑。

对外部资料仅保存简要归纳和链接，不用搜索摘要补造产品事实。官方完整本地Q&A源文、版本哈希和本轮所选条目保存在[知识依据](/Users/xiaoke.zhou/Documents/workspace/anker-haike/docs/planning/2026-10-11-1712_official-63-evaluation/knowledge-evidence.json)；实际检索与选择证据另存，二者不能混用。
