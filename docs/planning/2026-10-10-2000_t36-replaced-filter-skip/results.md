# T36 已换滤网仍发滤网检查：根因与修复

时间：2026-10-10 20:00–20:50（北京时间）。

## 根因

T36 原文「Alle filters en borstels zijn vervangen en alles is schoongemaakt」已抽成 action_taken 事实，但 rv-0316 四张卡全发。两道跳过防线：

```
matches_reported（关键词，guide/steps.py）  荷兰语 vervangen / schoongemaakt 不在英文词表 → 动作集合为空，永不命中
fact_check（模型判 done，guide/fact_check.py）同一输入 8 次：s2 done 7/8，s3 done 2/8；回放那次落在 unknown
```

模型摇摆在边界：「换了新滤网」算不算「检查滤网是否堵塞」，「全部清洁过」覆盖哪些部件。提示词只有「水箱是满的」一个例子。

## 修复

1. fact_check 提示词加规则与例子：换了新部件 → 对「检查该部件堵塞 / 脏污 / 缠绕 / 变形」判 done；步骤还要查没换的部位（盖条、安装位、轴）整步 unknown；
   「全部清洁过」只对点名部件算数。附 T36 荷兰语原文的三条判定例子。
2. 因客户已做过而跳过的步骤，在下一张卡的 context（计划走完时作为消息）说明一次并引客户原话：
   `I've skipped "<步骤首句>" because what you told us already covers it ("<原话>").`
   fact_check 的 done 常在选步时（decide_next）就被跳过、走不到发卡循环，所以在发布到它后面的步骤或计划走完时统一说明，按 instruction_src 去重只说一次。

不做：给关键词匹配补多语言词表；rv-0316 s3（缠绕变形 + 盖条安装位磨损）不拆，整步保留。

## 稳定性（真实模型，同一会话状态清掉该计划历史后重复 8 次）

| 会话 | 计划 | 改前 | 改后 |
| --- | --- | --- | --- |
| T36 f4e9a63f | rv-0316 | s1 unknown 8；s2 done 7 / unknown 1；s3 unknown 6 / done 2；s4 unknown 8 | s1 unknown 8；s2 done 8；s3 unknown 8；s4 unknown 8 |
| T16 214fcbc6 | rv-0056 | s1 done 8；s2 unknown 8 | 同左 |
| T27 d8b81d93 | rv-0147 | s1 done 8 | 同左 |
| T31 87912d87 | rv-0473 | s3 done 8，其余 unknown 8 | 同左 |
| T37 69260b8b | rv-0021 | s1 done 8 | 同左 |

改后结果是在运行中的容器里用工作区新 `fact_check.py` 替换模块测的（容器镜像未重建）；回归的 4 单是 P1 已修好、依赖 done 判定的案例，没有回退。
根因分析时另一组 8 次（同一 T36 输入）为 s2 / s3 同时 done 4 次、全 unknown 4 次，与上表改前一组合计说明改前确实不稳定。

## 真实整链路回放（21:40 前后，镜像重建后）

容器内 fact_check.py / steps.py 与工作区 sha256 一致。驱动：T36 原文首发，rv-0341 问句选「其他声音」，操作卡一律未解决。两次都没走到 rv-0316：

| 会话 | 实际路径 | 原因 |
| --- | --- | --- |
| e600e3177dd34b7fa2f9c14776e9cd29 | rv-0315 s1–s4 → 过渡句 + 索单 | synthesize 把 rv-0315（集尘时异响）判 supported 0.72，排第一；rv-0341 / rv-0316 都没进候选 |
| 37de2b5a32444be2b782d37a746b819f | 第一轮直接追问「拆下滚刷和盖后噪音会消失吗」，无卡 | synthesize 给 rv-0341 needs_confirmation 0.6，走追问；rv-0315 同轮判 needs_confirmation |

- rv-0315 s1「检查尘盒是否堵塞」fact_check 判 unknown（引了原文但没判 done）。按新规则这是对的：客户换的是滤网和刷子，「全部清洁过」没点名尘盒。
- 新发现（不在本次范围）：客户写的是「tijdens het stofzuigen」（吸尘时），rv-0315 标题是「dust collection process」（基站集尘时），
  synthesize 仍判 supported 0.72，时机不符。同一原文两次候选分别是 rv-0315 与 rv-0341，候选选择本身不稳定。
- 跳过说明在整链路上的表现，以单测（T16 / T36 / T37）和上面的 8 次判定统计为准；真实回放没能触达 rv-0316。
- 记录：本目录 `T36-other-*.json`（被 .gitignore 排除，只在本机）。
