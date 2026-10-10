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

## 未完成

- 真实整链路回放未做：重建镜像时 PyPI 下载超时，构建未完成。单测覆盖了 T16（跳过说明在下一张卡）、T37（计划走完时说明作为消息）、T36（s2 跳过说明出现在 s3 卡上）。
