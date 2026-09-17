# 实现记录

日期：2026-09-17。品类口径见 task_plan.md，单品类假设盘点与决策见 findings.md。

## 1. 配置与资料

| 文件 | 内容 |
| --- | --- |
| `config/products.yaml` → 2026-09-17.2 | 20 个品类按官网五大产品线组织，新增 `line` 字段；57 个 SKU（扫地机 15 沿用，新增 42 个公开型号作种子）。`home_storage` 是唯一 `in_scope: false`（电工安装、专业售后）；`robot_vacuum` 关键词加「机器人」 |
| `config/symptom_taxonomy.yaml` → 2026-09-17.1 | 顶层改为 `categories.<cat>.{families, discriminators}`；扫地机 8 族沿用并加 `selection_label`；新增移动电源 6 族 / 充电器 6 族 / 无线耳机 6 族 / 音箱 6 族 / 安防摄像头 6 族 / 吸奶器 5 族，各 2 道判别题。新品类症状码带 `pb_ / chg_ / eb_ / spk_ / cam_ / bp_` 前缀 |
| `config/plans.yaml` → 2026-09-17.1 | 6 个扫地机计划不变；新增 26 个计划（每品类 3–5 个，含安全停用计划），证据 55 条锚到新手册 / FAQ |
| `config/fault_cards.yaml` → 2026-09-17.1 | 新增 6 张 `category:<cat>` 通用故障卡（faults + signatures + safety） |
| `config/vision_vocab.yaml` → 2026-09-17.2 | `parts` 扩到 29 个（接口 / 数据线 / 插脚 / 充电盒 / 耳塞套 / 镜头 / 鸭嘴阀 / 隔膜…），`phenomena` 加「弯折」「锈蚀」，`category_parts` 覆盖 5 个品类，签名 18 条 |
| `data/knowledge/kb_manual/` | 新增 `manual_{pb,chg,eb,spk,cam,bp}.md`（小节标题带 `(cNN)` 锚点）与 `faq_{pb,chg,eb,spk,cam,bp}.yaml`（10–12 条 / 品类） |
| `data/knowledge/scripts/gen_tickets.py` | 按品类生成：扫地机 200 条与原文件逐字节一致（T0001–T0200），六个品类各 30 条（T0201–T0380） |
| `data/eval/policy/cases.yaml`、`authorization/cases.yaml` | 每个用例显式写 `category: robot_vacuum`，不再依赖默认值 |

全部新资料标注「人工演示样本，待真实资料替换」。

## 2. 代码

| 位置 | 改动 |
| --- | --- |
| `conversation/taxonomy.py` | 重写：`taxonomy_for(category)`、`families(category=None)`（None → 全品类并集）、`normalize / canonical_codes / select_discriminator / discriminator / next_interview / interview_codes` 都带品类；interview 里记 `category`，品类变则重开；多选题选项文案取词表 `selection_label` |
| `diagnose/decision.py` | 无词表的品类 → `escalate(category_coverage_missing)`（R5），不借用其他品类判别题；品类一定后过滤掉别的品类的症状码（intake 阶段品类未知时用并集归一）；`next_interview(..., category=)`；候选码按品类 |
| `sessions/clarify.py` | 症状固定问句按品类选判别题；范围外 `confirmed` 的处理沿用上午改动；提示词去掉扫地机举例；`coverage_missing` 含新原因 |
| `escalation/summary.py` | 故障族标签按品类；新增原因文案「该品类暂无可用的排查资料，已整理问题记录转人工」 |
| `conversation/interpret.py`、`diagnose/query.py`、`sessions/graph.py` | 症状码候选 / 查询词按品类；`CATEGORY_LABELS` 删除，改 `category_label()` 读目录；`OUT_OF_SCOPE_TEXT` 改 `out_of_scope_text()` 按目录里 in_scope 品类所属产品线生成 |
| `catalog/service.py` | `CategorySpec.line`；`category_hint` 最长关键词优先（「无线充电器」不被「充电器」抢、「割草机器人」不被「机器人」抢） |
| `knowledge/faq.py`、`knowledge/ingest.py`、`docker-compose.yml` | FAQ 索引装多品类文件（每条带 doc_id / category），`get_faq_index` 默认读目录；ingest 合并全部 faq 文件一次 replace；compose 挂整个 `kb_manual/` 目录 |
| `policy/models.py`、`policy/engine.py`、`sessions/l3.py` | `PolicyInput.category` 可空；engine 缺品类时按 SKU 从目录反查，反查不到 → 匹配不到政策 → 转人工 |
| `bakeoff/tasks.py`、`knowledge/eval.py`、`knowledge/reachability.py`、`inspection/` | 去掉 `robot_vacuum` 默认值：样本必须给品类或可由 SKU 反查 |
| `frontend/src/components/ChatPane.tsx` | 品类快捷入口改为 8 个真实品类，点击文案可被 `category_hint` 认出 |

## 3. 回归

- 后端全量 **897 passed**（含活 WeKnora 的 `test_live_category_only_excludes_sku_docs`，计数更新为 9 份手册 / 380 条工单）。
  新增 / 改写：目录形状与产品线、`category_hint` 最长匹配、拓展坞 → R5、家用储能 → R8 文案、吸奶器卡片选择进排障、充电器无型号进本品类问诊、plans 32 个、fault cards 品类卡、FAQ 多文件、ingest 计数。
- 前端 typecheck 通过，24 文件 214 项通过。
- `make kb-anchors`：chunking_bad 0 / unreachable 0 / metadata_missing 0（55 个锚点全部可达）。

## 4. 入库与实机（2026-09-17）

- `make kb-ingest`：created 186（6 手册 + 180 工单）、skipped 203、faq_entries 116、errors 0；`kb_ver` → `2026-09-17.1+text-embedding-v4`；入库前自动导出了快照。
- `make up` 重建（10:10 → 12:10），容器已挂 `kb_manual/` 目录。
- 每品类一句话新会话：

| 品类 | 输入 | 结果 |
| --- | --- | --- |
| 移动电源 | 充电宝插上手机没反应 → 换线了还是不行 | 步骤卡 `pb_port_debris/s1` |
| 充电器 | 我的充电器出问题了：→ 充电很慢，不快充 | 步骤卡 `chg_slow_check/s1` |
| 无线耳机 | 耳机只有一边有声音，重置过还是不行 | 步骤卡 `eb_charging_contacts/s1` |
| 音箱 | 音箱连上手机但没有声音 | 步骤卡 `spk_bt_repair/s1` |
| 安防摄像头 | 摄像头 App 显示离线 | 步骤卡 `cam_offline_reconnect/s1` |
| 吸奶器 | 吸奶器吸力变小了 | 判别题「吸奶器能正常开机并运转吗？」（随后把「吸力变小」补进词表） |
| 扫地机 | 扫地机不吸了 | 步骤卡 `rv_suction_hair_wrap/s1` |
| 拓展坞（目录级） | 我的拓展坞识别不了硬盘 | R5，原因文案「该品类暂无可用的排查资料」，没有借扫地机的问题 |
| 家用储能（范围外） | 阳台光储充不进电 | R8，文案列出五条产品线，不再写「仅支持 eufy 扫地机器人」 |

## 5. 未做 / 观察

- 13 个目录级品类没有 taxonomy / plans / 知识：识别后 R5 转人工。要做深度就按本轮六个品类的模板补。
- SKU 编码与型号名是公开渠道的演示种子，不保证与官方 SKU 一一对应。
- `warranty_policy.yaml` 仍只有扫地机的三条政策：其他品类走到质保核对会 `no_policy_matched` 转人工（L3 另议）。
- 视觉提示词把 29 个部件整表给模型；部件多了以后是否影响识别质量，需按票 42 的 bake-off 重测。
