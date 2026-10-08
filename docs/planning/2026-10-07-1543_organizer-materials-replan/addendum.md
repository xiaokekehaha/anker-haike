# addendum

## 2026-10-08 决策落定

用户定 D1–D3，D4–D7 授权 Fable 5.1 裁决（原则：以官方资料为准，旧实现可清理）。

| # | 决定 |
| --- | --- |
| D1 | 可配置演示时钟，默认当天；评测集按固定日期标注 |
| D2 | 客户语言回复 + 前端附中文译文；转人工摘要与后台中文 |
| D3 | 显示送达但客户称未收到：告知送达信息 + 承运商调查单 → 转人工，不补发 |
| D4 | 删除过保付费维修，过保委婉拒绝（T29/T38/T51/T53） |
| D5 | 换货 / 补发 / 退款 / 承运商调查统一「提交服务单 → 转人工」，不承诺时效。闸门职责改为「能否提交」：质保（订单质保结束日期 ≥ 演示时钟，或查无订单且授权经销商 12 个月）、四项证据、安全、幂等；删 policy 检查与 human_approved 旁路 |
| D6 | 主线 T55；分支 T8（补发）、T2（送达冲突）、T29（过保）、T45（经销商 + 烫伤）；备选 T14（KB 判硬件故障直进换货）、T13（荷兰语、KB 未收录码） |
| D7 | 范围外品类删除（不是移出种子）；摄像头保留 |

## 对 plan.md 的修正

1. G7 改为：整删 `config/policy/` 与 `app/policy/`（US 规则引擎），质保判定收敛为 `{status: in|out|unknown, warranty_end, basis: order|dealer_12m}`。依据：资料只有订单质保结束日期与「Reseller（提供 12 个月质保）」一句。
2. 「前端载入工单」从 P2 提到 P0：63 单评测与演示都依赖它。
3. P0「原合成数据移出默认种子」改为删除。

## 执行顺序（取代 plan.md §3）

每一片做完：相关测试通过、ruff 清零，再进下一片。

1. **S1 官方数据导入**：`haike-official build` 把 xlsx 转成仓库内可提交的 `data/official/`（订单 + 包裹、经销商、Q&A、63 单、附件图缩略）；xlsx 本身不入库。
2. **S2 业务后端换数据**：订单模型加质保结束日期与多包裹、物流状态枚举；经销商名录 336 行 + 国家精确 / 商家模糊匹配；替换 `backends_mock.yaml` 与 `receipt_reference.yaml`。
3. **S3 清理**：删 US 政策引擎、付费维修、范围外品类、合成知识库 / 工单 / 评测集 / replay；闸门与回执按 D5 改。
4. **S4 知识库**：Q&A 导入 WeKnora + 错误码 / PN 精确索引；产品目录按 PN 重建。
5. **S5 63 单评测集 + 前端载入工单**。
6. 之后进 plan.md P1（首封解析、多语言、物流 / 质保分支、证据清单）。

## 2026-10-08 用户补充：不留历史包袱

「之前的是自己 mock 的，大胆点，不要有历史包袱，基于线上数据做真实环境数据。」已执行：

- `make db-backup`（haike_20261008T062038Z.dump）后清空会话、案件、执行、服务单表；WeKnora 快照 `data/knowledge/snapshots/20261008T062043Z`。
- 旧演示订单 / 经销商 / 运单、US 政策引擎、付费维修、confirm_context（购买地 / 使用地 / 渠道）一律删除，不做兼容迁移。

## S2–S3 设计（业务后端 + 质保 + 服务单）

```
订单系统（只读）  data/official/orders.yaml → OfficialBackend（内存）
经销商名录（只读）data/official/dealers.yaml → country 精确 + seller 归一化模糊
服务单（写）      Postgres service_orders（新表；order_no 可空，经销商路径无订单）
```

- 质保判定 `WarrantyDecision{status: in_warranty|out_of_warranty|unauthorized_dealer|unknown, basis: order|dealer|none, warranty_end, as_of}`：
  有订单 → 订单行 warranty_end ≥ 演示时钟；查无订单 → 凭证 seller+country 命中名录 → 购买日 + 12 个月；未命中 → unauthorized_dealer；缺信息 → unknown。
- 演示时钟：`DEMO_TODAY`（YYYY-MM-DD），未设取当轮时间。
- 凭证字段 `order_no / seller / country / purchase_date`（channel → seller，新增 country），替代 confirm_context 卡。
- 方案：`ServiceOrderType = replace | refund | reship | carrier_investigation`；ProposalOption 去掉 cost_bearer / clauses / auto_allowed / dispatch_estimate。
- 写动作 `service_order.create`：闸门四项 warranty / evidence_and_consent / safety / idempotency；成功回执「服务单已提交，人工处理中」，不给时效。
- 过保 → 告知质保结束日期并委婉拒绝，案件 closed_unresolved；未授权经销商 → 引导联系商家售后。

## 2026-10-08 S1–S3 完成记录

已完成并验证（ruff 0；后端 1019 passed / 1 skipped；契约 94 passed、无漂移；前端 typecheck 0、232 passed）：

- S1：`app/official/{build,models}.py` 导出 `data/official/`（16 订单 / 330 经销商 / 875 Q&A / 63 工单 / 10 附件），`pn_of` 做 SKU→PN 归一。
- S2：订单与物流只读主办方数据（`app/backends/service.py` + `logistics.py`）；服务单写新表 `service_orders`（迁移 0009，删除全部 `*_mock` 与 `dealers` 表，`cases.policy_decision` 改名 `warranty`）。
- S3：删除 US 政策引擎（`app/policy/`、`config/policy/`）、付费维修、`confirm_context` 卡、旧演示订单 / 名录 / 运单配置；质保判定 `app/warranty/service.py`（订单质保结束日 / 授权经销商 12 个月 / 名录 country 精确 + seller 模糊）；服务单 `service_order.create`（replace / refund / reship / carrier_investigation）提交后转人工，闸门 eligibility / evidence / safety / idempotency；SOP 四项证据缺什么问什么；演示时钟 `DEMO_TODAY`。
- 物流：送达不补发、给承运商调查单（D3）；未送达 / 退回 → 补发单；预售告知发货日；「没收到 + 要退款」先查物流。
- 多语种：降级意图词与 R4 / R3 / R6 规则词补英、荷、德、法、西语；订单号识别改为 Anker 编号格式。
- 线上实测（真实模型）：T1 / T6（荷兰语）→ 承运商调查单；T8 → 补发单；T9 → 预售发货日。
- 评测：`data/eval/policy` 换成 `data/eval/warranty`（16 例，as_of 2026-10-08），authorization 改为新闸门 13 例。

已知未处理：
- boundary 巡检 6 个场景在本次改动前（HEAD）就失败，非本次回归。
- 产品目录、排障方案、知识库仍是旧数据，S4 替换（设计见 `s4_knowledge_design.md`）；replay a1–a8 与旧场景脚本待 S5 重录。

## 2026-10-08 勘误：SOP 流程图未被截断

findings.md §2 说「截图左侧被裁、最左侧节点不可见」是读图错误：当时用 `sips -c --cropOffset` 切左右两半，实际取到的是中段。按真实坐标重读后，流程起点完整：

```
query输入 → 意图识别 → <服务边界判断> --N--> 转人工
                              |Y
                              v
                    AI检索知识并生成回复 → <问题是否解决> → …（其余与 findings §2 一致）
```

- 「服务边界判断」对应现有范围外 R8 → 转人工；「意图识别」对应 intake。
- 黄框规则 1 原文为「显示送达的包裹**一般情况下**不再补发」，findings 转写漏了「一般情况下」；D3（送达但称未收到 → 承运商调查单转人工）与此一致。
- D8 ①（向主办方确认缺失节点）撤销。

## 2026-10-08 S4 进度（未提交）

已完成：
- 知识库：WeKnora `haike_kb_qa` 872 条（一条 Q&A 一知识，1500 字不父子）；旧三库删除（快照 20261008T062043Z）；`make kb-ingest` 末尾 REINDEX（ParadeDB bm25 批量删除后失效）。
- `app/official/qa_index.py`：错误码 + PN 精确索引（420 键）；Q&A → 指南 steps 410 / answer 427 / warranty 38（「先重启，仍未解决 → 质保」25 条拆成两步）。
- `app/official/message.py`：首封解析（App 报错 / RMA / 邮件，英荷德法西，PN / SN / 码 / 订单 / 国家 / 商家）。
- `app/plans/qa.py`：Q&A 生成 872 个计划取代 plans.yaml；plans.yaml、fault_cards.yaml、app/faultcards、app/plans/store.py 已删；settings / Dockerfile 去掉对应路径；seed_cli 只剩 products。
- retrieve：错误码精确命中（qa_exact 证据）→ 未收录码 R5 code_miss → 硬件故障 Q&A 直接进质保（R6）→ 其余语义检索，候选 = 命中 Q&A 的计划。
- 排障未解决（R1/R2）→ service_context 质保判断（SOP「确认是否进入换货」）；R1 上限 10、R1c 12。
- 消歧：首封 PN 直接锁产品；吸奶器 / SoloCam 单品类自动确认；有现象描述或错误码即继续（不强制中文症状码）。
- 产品目录 8 个 PN；前端首屏 3 品类 + 真实工单示例；步骤卡显示 Q&A 图片 / 视频（契约 TroubleshootStep.media）；证据来源标签改为官方 Q&A。
- 63 单评测集 `data/eval/tickets/cases.yaml` + `app/evaluation/tickets.py`：35 单 SOP 终点可确定性判定，全部通过。
- 冒烟（无模型）：T18/T27 3212 → qa_rv_0147 步骤卡；T11 EB1L → qa_rv_0481；T14 4090 → 质保（收凭证）；T13 5116 → R5。

进行中：三个子代理分组修旧测试（引擎测试用 tests/fixtures/engine_plans.yaml 夹具；目录 / 会话 / 知识库测试换新 PN 与 kb_qa；巡检 / bakeoff / 杂项）。tests/test_zz_smoke.py 是临时冒烟，提交前删除或转正。

仍待（见 remaining_work.md）：旧知识模块与语料目录删除（faq / official / anchors / reachability / snapshot / ingest 拆分）、symptom_taxonomy 与问诊简化、多语回复与双语显示（C1–C4、E4）、载入工单入口（E3）、回放与 bake-off 重做、文档与 CI 收尾。

### 2026-10-08 测试清理（第 1 步收尾）

- 依据：自建计划库 plans.yaml、故障卡、症状问诊族、范围外 / 目录级品类（储能、拓展坞、耳机、充电器）已删，测这些机制的用例没有修的对象。
- 删除 17 个测试文件：test_plans、test_faultcards、test_diagnose、test_diagnose_grade、test_diagnostic_loop、test_guide、test_retrieve_p0、test_knowledge_parent、test_conversation_retrieval、test_diagnostic_next_action、test_conversation_diagnostic、test_conversation_evidence_next_action、test_conversation_scope_conflict、test_conversation_operation_conditions、test_conversation_observation_deadlock、test_conversation_intake_output，以及 sessions_clarify / sessions_human / vision_graph 中依赖已删品类与问诊族的用例。
- 协议层测试（冲突 409、幂等、凭证、人工、读图、生命周期）保留，只把自建 SKU 换成官方 PN、把「不吸了」换成带官方错误码的消息（离线无模型时只有错误码路径能确定性出步骤卡）。
- 新增 test_conversation_official_tickets：T18 / T11 / T16 出官方步骤卡，T14 直进质保（R6），T13 未收录码转人工（R5）。tests/fake_qa.py 提供返回真实 Q&A 的假检索。
- 顺带修了两处真实缺陷：中文「报错 6025」「错误码 E23」认不出错误码（INLINE_CODE 只认英文关键词）；已记录错误码的会话下一轮被当成「无现象」重新问诊（described 未看 error_codes）。
- 多轮排障推进已补一条：T28 重启 → 未解决 → 质保步 → 未解决 → R6 进入订单 / 凭证收集。
- 删测试后的覆盖缺口：语义检索候选排序、读图与文字冲突以外的读图联动。按 remaining_work.md D4/D5 用 63 单回放补，不恢复旧用例。
- 结果：后端 780 passed / 1 skipped，ruff 0；前端 typecheck 0、232 passed；contracts 94 passed。
