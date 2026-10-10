# 方法、证据与复现

## 固定输入

本轮计划在首次发送前冻结，见plan.md；开发后未改，复评与方法纠正写addendum.md。已看历史，因此称独立判断，不称盲测。

主层T1–T63逐案新建会话，原工作簿“客诉工单信息”C2:C64、data/official/tickets.yaml的body、驱动input、首轮message.text逐字符一致；63案原本地附件列表一致，10文件hash与服务器input_received匹配。工作簿SHA256为`0cc02e6531d627433f9b5dba1978bfbf9f196b4581e033657c37ad2939007eb7`。

只在系统明确问型号或给产品卡时按官方产品列补充，没有预先塞型号列或历史评测标签。操作卡只模拟not_solved；遇独立问题、材料请求、方案确认或人工边界停止，不猜答案。最多18轮保护；本轮没有因触发保护而截断。

18分支和5重复来自13:21轮固定scenarios.json，各自独立会话；补充均标来源。B01 solved是假设反馈，不是实机修好；B13确认服务单是在本地评测系统内执行，没有人工审批或外部承运商处理。所有现实维修、配件下单、发货和安全处理都未实测。

## 评分

首轮和继续观察的路径分别打分，全部63案留分母；分支、重复不混入。合格表示当前实际观察范围内方向、事实承接、来源和权限合理，允许停在必要澄清/材料/人工。需改进须有已发生输出或流程证据，不能因为没走到最终解决就失败。待核用于证据/口径/适用性不足。

每案主分类唯一；并存标签可重复，标签频次不能相加当缺陷数量。正常Agent边界、资料缺口、措辞改善可能属于合格案。已召回未落实不等同零召回；知识库只提供资料，“执行”指系统是否正确承接并给适用可反馈步骤，不代表自动操作机器。

通用知识仅用来核逻辑和证据边界。专有型号、政策及保修日期以来源与评测当前日期2026-10-10核；网页核验只供评审，没有回写知识或测试会话。中文是逐轮业务译述，不增加客户事实；完整多语原文、系统文字和卡片原文同时保留。

## 采证与版本

- run/：63原始JSON、运行metadata、前后fingerprint。
- branches/：23原始JSON、运行metadata、前后fingerprint；7个初始journey 404原样保留。
- enrichment/：同86会话snapshot、journey和case只读补采；不重发输入。
- verification.json：63正文来源对齐、附件hash、2472事件契约解析、170轮done、86独立session、原JSONhash、判断hash和六份指纹对齐。
- knowledge-evidence.json：875条QA范围、5116/绿灯搜索结果、13条相关QA完整原文及源文件hash。本地全文搜索不代替实际WeKnora事件。
- review-data.yaml、branch-data.yaml：人工中文译述、裁定、分类与理由。build_report.py只离线展开记录和统计。
- document-verification.json：86份对话的170轮译述覆盖、实际文字/步骤原文一致、283个本地链接、原证据未改、评分与模型异常一致，以及本轮所有文档/JSON/脚本密钥模式零命中。

源码HEAD`0a93d9c683d60b5d33ca9c3fe3d0972d694caec4`，两批和补采间identity/runtime/local一致；217个运行文件与本地对应hash均匹配。本次串行用于采证，未验证并发性能。T21一次模型超时后重试保留在journey；用户侧零error。7个即时journey 404补采成功，根因未证明，不称服务从未出错。

## 复现命令

Makefile没有63案或本轮离线生成专用目标，因此使用已保存驱动；后端运行仍通过uv和根.env。下面长路径/分支命令会调用真实模型并创建新评测会话，离线生成和补采不会调用模型。不要将输出指向本轮证据目录覆盖原始运行。

```bash
make health
cd orchestrator
uv run --env-file ../.env python ../docs/planning/2026-10-10-1550_official-63-latest-review/evaluate_long.py --output /tmp/haike-63-new-run --concurrency 1
uv run --env-file ../.env python ../docs/planning/2026-10-10-1550_official-63-latest-review/evaluate.py --layers BR --output /tmp/haike-63-new-branches
```

只读补采和离线重算针对本轮目录：

```bash
cd orchestrator
uv run --env-file ../.env python ../docs/planning/2026-10-10-1550_official-63-latest-review/collect.py
uv run --env-file ../.env python ../docs/planning/2026-10-10-1550_official-63-latest-review/build_report.py
uv run --env-file ../.env python ../docs/planning/2026-10-10-1550_official-63-latest-review/validate_report.py
```

本轮没有业务代码改动，未运行构建、全量pytest或CI，也没有必要用单测调用真实模型。新建采证/生成脚本均实际运行并验证产物。文档和JSON保存在本地，不等于已提交；未修改已有.gitignore或他人工作。
