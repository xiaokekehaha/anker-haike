# 段落拆分（parts）真实回放

时间：2026-10-10 18:00–18:08（北京时间）。代码：HEAD 0a93d9c 加未提交的 parts 改动；`docker compose up -d --build orchestrator`
后串行回放，容器内 5 个改动文件与工作区 sha256 一致。之后只改了 rv-0341 一个禁用部分的 reason 文字，不影响行为。
驱动：临时脚本（已删除），原文首发；操作卡按预设反馈 not_solved，问句卡按预设选项；卡片类型与预设不符或无卡即停。
每个场景一次，不代表稳定率；not_solved 与选项都是模拟输入，没有操作真实设备。

| 场景 | 会话 | 卡片路径 | 终点 | 判定 |
| --- | --- | --- | --- | --- |
| T19 无异常 | fcb61c739e5e43e9ad88a5f5f4cdd611 | s1 操作 → s2 问句 | 索单（context） | 通过 |
| T19 密封圈坏 | 5cc60298d6294cb8aca65454d8f631bc | 同上 | 索单 | 通过 |
| T26 Yes | 00e645a2a12e4247a6b136cde2afdf85 | s1 → s2 → s3 问句 → s3b 泡沫操作卡 | 索单 | 通过 |
| T26 Not sure | 94d1084809004c6bb2f6e132b61c81e8 | 同上 | 索单 | 通过 |
| T36 噪音消失 | 40a55666fcc5462a96afaa14a0279a35 | s1 问句 | 说明「likely caused by the roller brush」后索单 | 通过 |
| T36 吱吱声 | 9efc8f58090c445d974fe5657c156f74 | s1 问句 → s1d 试拖地模式 | 索单，未出现换机承诺 | 通过 |
| T36 其他声音 | dfb2a8cd0e4741509a26ce41f316855f | s1 问句 → rv-0316 s1（万向轮） | rv-0316 一步未解决后索单 | 见遗留 |
| T53 | 28125f1412ab45abadce3cd47a53fd5c | s2 → s3 → s4 → s5 → s6 → s6c 问句 → s6e | 过保，关单未提交新申请 | 通过 |

对比 63 单评审时的问题：T19 不再先下条件结论；T26 问句单独收答案；T36 不再一张卡塞 4 个分支；T53 不再在 s6 重复 12 秒重置，
也没有「provide your shipping address」。

## 第二轮（18:30 前后，修 T36 计数与转售后过渡句后）

改动：诊断树里选中审核写成 EXHAUSTED 的分支（原文没覆盖）时，该指南不计入 MAX_GUIDES；进质保时 guide_exhausted
来路补一句「The official troubleshooting for this issue is complete and the problem isn't resolved, so the next step is an
after-sales review; whether it's covered by warranty depends on the check below.」。重建容器后回放，6 个改动文件 sha256 一致。

| 场景 | 会话 | 卡片路径 | 终点 | 判定 |
| --- | --- | --- | --- | --- |
| T36 其他声音 | f4e9a63f1e9e477f92c355ae2118b83d | rv-0341 s1 问句 → rv-0316 s1–s4 四项 | 过渡句 + 索单 | 通过（第一轮只发 rv-0316 s1） |
| T36 噪音消失 | 9dbaf9468de146048fdfff372ac81d9c | rv-0341 s1 问句 | 滚刷说明、过渡句、索单三条消息 | 通过 |
| T19 无异常 | 33720a3e0653439aad305bd3b77532f8 | s1 → s2 问句 | 过渡句 + 索单 | 通过 |

第一轮记的「说明句与索单句之间没有空格」是驱动把多条消息的 delta 直接拼接造成的；会话时间线里是两条独立的 assistant_message。

## 遗留

- 过渡句「problem isn't resolved」用在 T36 噪音消失一支时措辞偏宽：客户没有点过「未解决」，是诊断树直接得出了官方结论。
  句子本身不假（问题确实没修好），未另拆一句。
- T36 原始工单说过「所有滤网和刷子都换过、全部清洁过」：第二轮 rv-0316 的四项仍全部发出，滤网堵塞检查没有被 fact_check 跳过。
  这是事实承接问题（issue-register「已做事实 T36」），不在本次卡片拆分范围内，未处理。
- 记录：本目录 `*.json`（第二轮文件名前缀 r2-）。
