# 已知事实与多问题承接（C 类）的真实回放

时间：2026-10-12 10:35–10:41（北京时间）。来源：`docs/planning/2026-10-11-2145_official-63-evaluation/report.md` 的 T29 / T34 / T63 与 T37 重复中的跨指南重问。

Codex 的 `2026-10-12-1023_official-63-review` 服务调用于 10:27:41 结束（主层、T20 / T28 / T51 重复与补采），之后才重建镜像。驱动同前（客户策略不变），启动前后逐文件核对运行源码与工作区一致。会话 JSON 与驱动按 .gitignore 只留本机。

## 根因与修复

| 案例 | 根因 | 修复 |
| --- | --- | --- |
| T63 | parts_purchase 由规则补进队列时没有原话；交接摘要取第一个带部件的症状事实当要买的部件，模型症状顺序是 detangle 在前 → 「要买 detangle elements」 | 规则补采购诉求时一并记下匹配的采购分句作 request_quote；摘要的部件只从采购原话里购买动词后的对象取（`purchase_object`），认不出就记缺失、对客文字不点名 |
| T29 | rv-0254 第 2 步「查格栅是否堵塞，并清洗清洁盘」，客户说清洁盘洗过了；fact_check 只有 done / unknown，整卡原样重发，不说明已做部分 | 新增 partial：照发这张卡，卡上说明客户已做的部分与这次要查的部分；remaining 必须逐字出自步骤原文，模型不能自拟检查项 |
| T37 重复 | fact_check 每条指南各判一次：rv-0111「检查水箱有没有水」判 done，切到 rv-0021 同一检查判 unknown，又发查水箱的卡 | 别的指南已判 done 的步骤与客户原话作为 `[done elsewhere]` 对照交给本计划的 fact_check，同一件事同样判 done |
| T34 | 「历史记录里看得到地图却用不了」第二个问句被吞掉；知识库没有这个答案 | 未改。63 单里非物流工单带附带问句的只有 6 单（T18 / T29 / T37 / T40 / T56 / T62），都是「怎么修 / 还能做什么」，排障本身就是回答；T34 这类「为什么」的附带问句只有 1 单。按「先看频率」不加子问题结构，T34 由人工交接承接 |

## 定向重放

| 案例 | 结果 | 判定 |
| --- | --- | --- |
| T63（3 次） | 3/3 对客「passed your request (the brush guard)」，摘要 part=brush guard、missing=[product] | 通过 |
| T29（主层驱动 3 次） | 1/3 发卡，第二卡带「You mentioned you've already done part of this ("I have already cleaned it"). This time, please focus on: Check whether the station cleaning tray grille is blocked…」；2/3 首轮先问污水箱卡扣 | 通过 |
| T29（追问答 yes、卡点未解决，3 次） | 2/3 第二卡带部分已做说明；1/3 首轮问卡扣时答 yes，fact_check 判 s2 unknown 没有 partial，s2 原样发出 | 部分通过：partial 是模型判定，有波动 |
| T37（3 次） | 3/3 不再执行 rv-0163，唯一一步被「水箱是满的」覆盖后说明理由进质保；本轮没有切换第二条指南，跨指南对照未被触发 | 跨指南对照只由单测覆盖 |

## 63 单主层（与 10:09 轮逐单比较首卡、停止原因、阶段、方案卡）

55 单一致，8 单不同：T16（首卡 s1 / s2 跳过与否）、T31 / T36 / T38 / T41（synthesize 判待确认先追问 / 判可执行发卡互换）、T40（本轮首轮追问后发 rv-0073 卡，与 10:09 重放 1/3 相同）、T53（接上「继续排障」路径）、T58（追问出口不同，都只问现象）。主层没有出现 partial 说明（T29 本轮首轮先追问卡扣）。差异均为 synthesize / intake 的既有波动，C 类改动只作用于 fact_check 判 partial、跨指南已判 done 的步骤与配件采购交接。

单测：T63 部件取自采购原话（换回旧摘要失败）、采购原话记录与认不出时缺失；T29 partial 校验（remaining 须出自原文、不跳过）与卡片说明（去掉修复失败）；跨指南已判 done 的对照。
