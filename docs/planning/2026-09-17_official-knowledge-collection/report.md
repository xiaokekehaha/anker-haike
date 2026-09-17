# 安克官方资料采集与入库验收

2026-09-17，已向本机项目 WeKnora 手册库补充 **11 篇官方支持文章的中文摘要、24 个完整技术问题单元**。实际解析为 **23 个子块**，全部完成解析；24 条逐单元查询均在前 5 条结果中返回完整目标单元，22 条排第 1、2 条排第 2。这是本批定向验收，不代表任意问法的整体检索准确率。

## 本批资料

| 范围 | 文章 / 单元 | 内容与来源 |
|---|---:|---|
| X10 Pro Omni | 4 / 9 | [吸力与清洁](https://service.eufy.com/article-description/The-X10-Pro-Omni-Troubleshooting-Weak-Suction-Power-and-Poor-Cleaning-Performance)、[充电与开机](https://service.eufy.com/article-description/What-should-I-do-if-my-X10-Pro-Omni-is-not-charging-or-powering-on)、[WiFi](https://service.eufy.com/article-description/What-Should-I-Do-if-My-X10-Pro-Omni-Fails-to-Connect-to-WiFi)、[错误提示与重启](https://service.eufy.com/article-description/Voice-Alerts-Quick-Solutions-for-the-X10-Pro-Omni) |
| S1 Pro 扫地机器人 | 1 / 2 | [吸力、护罩和尘盒密封](https://service.eufy.com/article-description/What-should-I-do-if-my-S1-Pro-s-suction-becomes-weak) |
| Anker 737 A1289 | 3 / 7 | [端口与功率](https://service.anker.com/article-description/Introduction-to-the-Anker-737-Power-Bank-24K-A1289)、[常见异常](https://service.anker.com/article-description/Anker-737-Powerbank-Common-Problem-Troubleshooting)、[UVP、空载功率和多设备分配](https://service.anker.com/article-description/Anker-737-Power-Bank-Special-Issues-Troubleshooting-FAQs) |
| eufy 吸奶器 S1 Pro / E10 | 1 / 2 | [官方通用吸力检查](https://service.eufy.com/article-description/Why-does-my-eufy-Breast-Pump-have-no-suction-or-weak-suction)，仅绑定当前目录这两个 SKU |
| Space One A3035 | 2 / 4 | [连接方式](https://service.soundcore.com/article-description/A-Guide-for-Bluetooth-Connection-about-Space-One)、[麦克风检查](https://service.soundcore.com/article-description/How-to-Fix-Microphone-Issues-with-Space-One) |

来源清单及逐条摘要：[anker_official.yaml](../../../data/knowledge/sources/anker_official.yaml)。原始 HTML、正文和抓取记录在忽略目录 `tmp/official-knowledge/`，未把整篇原文提交为知识内容。

## 切块与验证结果

- 采用现有父块 800、子块 200、重叠配置 80 字符；每段先按“产品 + 问题 + 完整操作/注意事项”组织，构建时拒绝超长单元。
- 23 个实际子块长 104–200 字符，全部关联父块。24 个语义单元全部在至少一个子块内完整出现，包括产品名、章节锚点和摘要末尾。
- 11 篇文档的来源 URL、哈希、版本、适用范围等全部回读一致。确认的 SKU 可见；其他 SKU、其他品类、仅确认品类及未知产品状态均不能获得这些型号专属文档。
- 24 / 24 条实测查询在前 5 条结果中命中完整目标单元，错误 0。详见 [机器验收记录](../../../reports/knowledge/anker-official-2026-09-17.json)。
- 手册库现有 20 篇：原有 9 篇和本批 11 篇；工单 380 条、FAQ 116 条。没有清库或重建知识库。
- 当前总库版本：`2026-09-17.2-fc326dc6345e+text-embedding-v4`。

## 本次改动和操作记录

- 新增定向采集、来源哈希校验、语义单元长度校验、SKU/品类校验、摘要生成和真实验收命令。
- 导入器补充来源字段，并从“仅 scope 存在”改为逐字段回读确认；按稳定文档 ID 匹配更新，避免标题变化生成重复旧资料。
- 调整随语料增长变化的测试数量与范围断言，旧的真实知识库测试改为显式开启，普通单测保持离线。
- 入库前完整源文件快照：`data/knowledge/snapshots/20260917T073900Z/`。正式入库入口另保存 `20260917T074209Z` 和重试前的 `20260917T074346Z` 快照；回退到本批之前应使用第一份。
- 首次写入发现远端元数据最多 20 字段的限制，删除冗余站点标记后重试成功。该次失败生成的本批临时文档已替换；最终统计为新增 10、替换本批临时文档 1、跳过原有 389、清理额外条目 0。
- `make lint`、`git diff --check` 通过；相关离线测试 35 项通过、1 项需显式开启的真实测试跳过。真实批次检索另由上述 24 条验收问题验证。

## 使用边界和后续接入

初次入库验收使用新适配器读取完整新库。随后用户授权重启，已于当天 15:55 重启本机业务服务，运行日志确认加载 20 篇手册，X10 业务会话返回新官方文档证据。737 UVP 场景在检索前重复澄清后升级，尚未通过业务验证，详见 [补充记录](addendum.md)。没有发布新应用镜像，也没有把新文档自动替换为排障计划的固定证据。

当前地区/发布状态过滤仍未实现，本批仅加入型号明确的技术内容。部分目录中的演示 SKU 与官网型号映射需另行校正；本批避开这些有歧义的映射。Space One 已有知识可检索，但完整业务排障能力仍取决于对应计划。

后续按“新增来源清单 → 抓取 → 核对摘要及哈希 → 构建 → 快照/导入 → 真实验收 → 刷新业务索引”接入，具体命令与检查点见 [操作说明](../../runbook/official-knowledge.md)。
