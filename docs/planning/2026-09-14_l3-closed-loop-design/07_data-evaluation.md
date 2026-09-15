# 第七步：数据、KPI 与评测

## 1. 数据资产与来源

| 资产 | P0（演示） | P1（真实数据到手） | 载体 |
| --- | --- | --- | --- |
| 订单 / 运单 / 服务单 | `config/backends_mock.yaml` 扩 `receipt_reference.yaml`：≥ 10 订单（覆盖 CN/EU/UK、官方/平台/授权/非授权、保内/保外、A6 跨区域）、≥ 6 运单、故障注入订单 | 保持模拟（赛题不提供真实系统） | Postgres 演示表 |
| 经销商名录 | 现有 2 条 → ≥ 10 条，补 `region`、`platform`、`authorized`、`policy_note` | 真实授权经销商名录导入（字段映射 + 去重 + 版本） | `dealers` 表 |
| 政策条款 | `config/policy/*.yaml` 演示规则 + 条款文本 | SOP → policies/clauses（04 §7 流程） | YAML + 可选 `kb_policy` |
| 症状体系 | `config/symptom_taxonomy.yaml` 扫地机 6–8 族 | 从脱敏工单 `symptom` 字段聚类 + 人工审核扩表；多品类 | YAML |
| 视觉词表与补拍指引 | `config/vision_vocab.yaml` | 按品类扩 | YAML |
| 情绪策略 | `config/emotion_policy.yaml` | 按真实会话标注调阈值 | YAML |
| 产品目录 | 15 SKU 扫地机 | 多品类目录生成：从产品技术知识库抽 SKU / 别名 / 品类（LLM 辅助 + 人工审核），`in_scope` 按计划覆盖决定 | `products.yaml` |
| 知识库 | manual ×2 / FAQ 50 / troubleshooting 1 | 真实产品技术知识库分品类导入；front-matter 增 `region_list`、`publish_state`（draft/approved/published/withdrawn，检索只取 published） | WeKnora |
| 工单 | 200 条合成 | 脱敏工单清洗管线（见 §2） | WeKnora kb_tickets + 评测集 |

## 2. 脱敏工单清洗管线（P1，设计先行）
```
raw (csv/xlsx/json, schema 未知) → schema 探测与字段映射（人工确认一次，存 mapping.yaml）
  → 去噪（空、重复、模板句）→ 结构化抽取（LLM 辅助：symptom_code、fault_class、remedy、region、channel、result；输出带原文引用，人工抽检 ≥ 10%）
  → 二次脱敏校验（手机号 / 订单号 / 地址正则 + 命名实体抽检）
  → 分流：kb_tickets 入库（含 metadata: sku_list, region, channel, result, doc_version）
          评测集抽样（按 family 分层；开发集 / 保留集分割，保留集不进 prompt 与词表）
  → manifest 记录来源批次、mapping 版本、样本数
```
工具：`haike-tickets ingest --mapping mapping.yaml --batch 2026-xx`；`haike-tickets sample --eval symptom|routing|emotion --n 40`。原则：保留集只用于验收；任何进入 prompt / 词表 / 计划的样本只能来自开发集。

## 3. KPI 实现

### 3.1 采集点
| 指标 | 采集 | 存储 |
| --- | --- | --- |
| 托管率 | analytics `classify()` 新增终态 `executed_closed`（case closed 且无人工决定）、`awaiting_human` / `human_executed`（有 human_decision）、`consult_answered`（consult 完成且无后续求助 N 小时） | `analytics.sessions_outcome` 增列 `case_status`, `human_involved bool` |
| 意图准确率（离线） | `scripts/eval_conversation.py` 读扩展后的 `semantic-gold.yaml`（新增 8 个业务意图族 × 5 表达 + 工单口语样本） | 报告 `reports/eval/intent_*.md` |
| 意图准确率（在线抽样） | 管理台 LabelDialog 增加「意图正确？」标签，按日抽样 20 条 | `analytics.case_labels` 复用 |
| NSS | RatingCard → `rate_satisfaction` → `satisfaction_ratings` | 见 05 §2 |
| 五难点专项 | 各评测集 CLI（`haike-eval vision|symptom|routing|emotion|policy|authorization`） | `reports/eval/` |

### 3.2 口径与展示
- Dashboard 新卡：托管率（近 7 天，分母说明悬浮）、意图准确率（离线最新 + 在线抽样）、NSS（评分覆盖率并列）、越权次数（必须 0）、待审批 / 平均等待。
- 剔除：`replay` / `smoke` / 巡检流量按 `session.tags` 过滤（现有 analytics 已区分 replay；补 smoke 标签）。
- 报告修订：延迟结果（用户隔天评分）允许回补，报表标注截止时间。

## 4. 评测集清单（P0 建骨架，每集 ≥ 20 条起）
| 集 | 路径 | 金标 | 主要指标 | 备注 |
| --- | --- | --- | --- | --- |
| 政策决策表 | `data/eval/policy/cases.yaml` | remedies eligible/auto_allowed、needs_human、clauses | 全对率（必须 100%） | 纯 pytest |
| 授权越权 | `data/eval/authorization/cases.yaml` | 期望写动作调用次数 | 越权率 = 0 | 假后端计数 |
| 视觉定位 | `data/eval/vision/cases.yaml` + 图片 | findings、usable | part/phenomenon 命中、usable 准确 | 需真实图 |
| 症状归一 | `data/eval/symptom/cases.yaml` | fault_family/symptom_code | 族 / 码准确率 | 工单原话优先 |
| 路由分流 | `data/eval/routing/cases.yaml` | 主次意图、顺序、needs_human | 各准确率 | |
| 情绪分级 | `data/eval/emotion/cases.yaml` | level、strategy | 准确率 | 含反讽 / emoji |
| 承诺一致性 | `data/eval/commitments/cases.yaml` | 允许出现的金额 / 天数集合 | 违规句数 = 0 | 字符串断言 |
| 意图（扩） | `data/eval/conversation/semantic-gold.yaml` | primary_intent | accuracy | 现有扩展 |
| 检索（现有） | `data/eval/retrieval/cases.yaml` | 56 条待标注 | hit@5 / plan_match | 标注是 P1-C 前置 |

## 5. 回放与巡检
- 回放包新增 A4–A9 录制；版本清单四元组（prompt / model / knowledge / rules）扩为六元组（+ policy_version、actions_version）。
- 巡检脚本（`app/inspection/scenarios.py`）新增：越权尝试（伪造 confirm_proposal 载荷）、幂等重放、HITL 拒绝路径、模拟后端超时 / 不可用、complaint_risk 三轮、模糊图补拍跳过、多意图队列接续。

## 6. 发布与回滚
- RELEASE.md 增加 `policy_version`、`actions_version`、`backends_mock` seed 版本、`emotion_policy` / `symptom_taxonomy` / `vision_vocab` 版本。
- 回滚：政策 / 动作 / 情绪配置为热加载文件，回滚即换文件；DB 迁移 0006 提供 downgrade；案件表数据不随回滚删除。
