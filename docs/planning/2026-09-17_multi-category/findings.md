# 发现：单品类假设盘点（2026-09-17）

## 1. 配置层

| 文件 | 假设 | 改法 |
| --- | --- | --- |
| `config/symptom_taxonomy.yaml` | 顶层一个 `category: robot_vacuum`，`families` / `discriminators` 都是扫地机的 | 改成 `categories: {<cat>: {families, discriminators}}`，共享 `version` |
| `config/vision_vocab.yaml` | `parts` 是扫地机部件；提示词把整张表塞给视觉模型 | `parts` 按品类分组，提示词取并集；`category_parts` 由分组直接得出 |
| `config/products.yaml` | 6 个品类、只有 robot_vacuum `in_scope: true`，其余名称与官网不一致（「耳机」「摄像头」） | 按官网五大产品线重排：加 `line` 字段，品类名与官网一致，补关键词与代表 SKU |
| `config/plans.yaml` / `fault_cards.yaml` | 已支持 `applies_to.category` / `category:<cat>` 键，只是内容全是扫地机 | 只补内容 |
| `config/policy/warranty_policy.yaml` | 三条政策全 `category: robot_vacuum` | 本任务不动（L3 质保另议），去掉代码默认值即可 |

## 2. 代码层

| 位置 | 假设 |
| --- | --- |
| `conversation/taxonomy.py` | `normalize` / `canonical_codes` 用 `cfg["category"]` 闸门；`next_interview` 候选 = 全部 families；`select_discriminator` 读顶层 discriminators；`normalize(text, category="robot_vacuum")` 默认值 |
| `diagnose/decision.py:271` | `category != taxonomy()["category"]` → 只会泛问症状 |
| `conversation/interpret.py:196` | 给模型的候选 symptom_code 列表 = 全部 families |
| `escalation/summary.py:101`、`diagnose/query.py:74`、`sessions/clarify.py:288` | 直接遍历顶层 families |
| `diagnose/query.py:15-16` `CATEGORY_LABELS` | 手写六个品类中文名；应从目录 `categories[].name` 取 |
| `or "robot_vacuum"` 兜底 | `query.py:59`、`l3.py:54`、`graph.py:1475`、`knowledge/faq.py:109`、`knowledge/eval.py:46-57`、`policy/models.py:10`、`taxonomy.py:16`、`bakeoff/tasks.py:92`、`knowledge/reachability.py:128` |
| `graph.py:1430` `OUT_OF_SCOPE_TEXT` | 写死「本期智能排障仅支持 eufy 扫地机器人」 → 从目录 in_scope 品类生成 |
| `frontend/src/components/ChatPane.tsx:5` | 品类快捷入口只有 robot_vacuum 一项 |

## 3. 数据层

- `data/knowledge/kb_manual/` 4 份全是 `*_rv`；`kb_tickets/tickets.csv` 由 `scripts/gen_tickets.py` 生成，SKU / 案例全是扫地机。
- 知识入库（`knowledge/ingest.py`）已按 doc 元数据 `category` / `scope` / `sku_list` 建索引，多品类不用改代码，只补 doc。
- `data/eval/retrieval/cases.yaml`、`conversation/cases.yaml` 只有扫地机（conversation 里有一条 earbuds 的意图样本）。

## 4. 官网品类 → 目录键（拟）

| 产品线 `line` | 品类键 | 官网名 |
| --- | --- | --- |
| charging | power_bank / charger / cable / wireless_charger / charging_station / hub | 移动电源 / 充电器 / 数据线 / 无线充电器 / 充电站 / 集线器与拓展坞 |
| solix | portable_power_station / home_storage | 便携储能（户外电源） / 家用储能 |
| eufy | security_cam / robot_vacuum / robot_mower / breast_pump / baby_monitor / smart_scale | 家庭安防 / 扫地机器人 / 割草机器人 / 吸奶器 / 婴儿监视器 / 体重秤 |
| soundcore | earbuds / headphones / sleep_earbuds / speaker / projector | 无线耳机 / 头戴式耳机 / 睡眠耳机 / 音箱 / 便携投影仪 |
| eufymake | uv_printer | UV 打印机 |

## 5. 分层建议

- **深度品类**（taxonomy + plans + fault card + 手册 / FAQ / 工单）：扫地机器人（已有）、移动电源、充电器、无线耳机、音箱、家庭安防摄像头、吸奶器。
  依据：赛题材料点名的品类 + 用户实测的「充电与移动电源」+ 消费量大、常见故障有公开常识可写。
- **目录品类**（`in_scope: true`，有关键词与代表 SKU，无计划）：其余 13 个。
  行为：品类识别成功 → `decide_symptoms` 在该品类下没有 families → 判别题为空 → `question_coverage_missing` → R5「现有资料没有可执行的排查」→ 摘要带上 intake 抽到的症状转人工。比 R8 诚实，且不多问一轮。
- 演示样本逐份标 `source: 人工演示样本，待真实资料替换`。SKU 名取自公开型号，作目录种子，不保证与官网 SKU 编码一致。
