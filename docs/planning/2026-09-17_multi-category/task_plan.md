# 多品类支持（按安克官网品类口径）

## 目标

把「本期只做扫地机」（D1）扩成多品类：品类划分与命名对齐安克官网（anker.com.cn/brands，2026-09-17 读取）
的五大产品线，用户报任一品类都能进入排障或得到诚实的结束原因，不再一律 R8。资料由本任务自行补齐（演示样本，标注待真实资料替换）。

## 官网口径（2026-09-17）

| 产品线 | 官网描述的品类 |
| --- | --- |
| Anker Charging（移动电源与配件） | 移动电源、充电器、数据线、无线充电器、充电站、集线器 / 拓展坞 |
| Anker SOLIX（家用与便携能源） | 便携储能（户外电源）、阳台光储 / 家用储能 |
| Anker eufy（智能家居） | 家庭安防（摄像头 / 门铃）、扫地机器人、割草机器人、婴幼儿看护（吸奶器、婴儿监视器）、个人健康（体重秤） |
| Anker soundcore（影音） | 无线耳机、头戴式耳机、睡眠耳机、音箱、便携投影仪 |
| Anker eufyMake（创意工具） | UV 打印机 |

## 阶段

1. 盘点单品类假设（taxonomy / vision_vocab / 默认值 / 文案 / 评测数据）：complete（findings.md §1–3）
2. 定分层：7 个深度品类 + 13 个目录品类，home_storage 留范围外：complete（用户 2026-09-17 确认）
3. 代码改造：taxonomy 按品类分组、vision_vocab 按品类分组、去掉 robot_vacuum 兜底、out_of_scope 文案从目录生成、FAQ 多文件、policy 品类反查：complete
4. 资料补齐：products.yaml 20 品类 57 SKU、6 个新品类的 taxonomy / plans / fault_cards / 手册 / FAQ / 工单：complete
5. 入库（make kb-ingest）、回归、实机验证：complete（implementation.md §3–4）；发布：pending

## 用户追加（2026-09-17）

「历史有不合理的地方，规则，文案，都可以清理，然后重建」——据此清理了：写死的品类中文名表、
写死「仅支持 eufy 扫地机器人」的范围外文案、`next_interview` 里写死的扫地机选项文案（改为词表 `selection_label`）、
clarify 提示词里的扫地机举例、FAQ 单文件假设与 compose 单文件挂载、bakeoff / eval / policy 里的 robot_vacuum 默认值。

## 边界

- 资料是演示样本，逐份标注 `source: 人工演示样本，待真实资料替换`；不冒充官方手册。
- 不改产品消歧「规则查表不用模型」的原则；品类关键词与 SKU 别名仍走目录。
- 不动历史会话。
