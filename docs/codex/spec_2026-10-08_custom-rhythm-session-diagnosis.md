# 自定义吸奶节奏会话检查

日期：2026-10-08。范围：检查会话 `3c686be289f6495e83a639df358df619` 的型号与知识命中情况，定位原因。本次只读检查业务系统，不修改业务代码或会话数据。

## 问题

用户先问“如何使用‘自定义吸奶节奏’功能？”，再补充“S1 Pro 穿戴式吸奶器，型号 T8D04”。助手仍称历史记录没有操作说明，观测台显示产品未识别。

## 已验证的证据

- `config/products.yaml:31` 收录 T8D04，名称为 eufy Wearable Breast Pump S1 Pro，品类 breast_pump，属于支持范围。通过实际 ProductCatalog 加载确认。
- `data/official/qa.yaml:11393` 的 `bp-0001` 标题正是 How do I use the custom rhythm feature on eufy Wearable Breast Pump S1 Pro(T8D04)?，适用型号为 T8D04。
- 使用项目现有 WeKnoraClient 只读访问当前配置的远端知识库，找到 `doc_id=bp-0001`，`parse_status=completed`、`scope=sku`、`sku_list=T8D04`，版本 `0cc02e6531d6`。排除“条目只在本地、尚未入库”。此次没有调用模型或向量检索。
- admin journey 接口返回三轮均为 `understand → dialogue → commit_issue`；前两轮 `primary_intent=explain`，第三轮 `complaint`。三轮 `retrieval_calls=[]`，未运行产品消歧或检索节点。
- 会话最终 `sku=null`、`category=null`、`product_state=unknown`、`knowledge_status=null`。

## 复现检查

只读接口检查命令：

```bash
curl -fsS http://127.0.0.1:5173/admin/api/sessions/3c686be289f6495e83a639df358df619/journey | jq -e '{product_identified: (.session.sku == "T8D04"), knowledge_searched: ([.runs[].retrieval_calls[]] | length > 0)} | . as $checks | ($checks, ([$checks[]] | all))'
```

结果为 `product_identified=false`、`knowledge_searched=false`，退出码 1。该检查证明这条历史会话未完成型号确认和知识检索；修复后的行为验收需要新会话，不能依赖旧历史记录自动改变。

## 原因

1. `orchestrator/app/conversation/interpret.py:148` 把“为什么这样做/怎么操作”统一指向 `explain`，没有区分“解释已有步骤”和“查询产品功能”。
2. `orchestrator/app/conversation/reduce.py:433` 将 `explain` 设置为 `reply_mode=dialogue`；`orchestrator/app/sessions/graph.py:1615` 随后直接进入 dialogue。实际三轮节点记录与这一分支一致。
3. `orchestrator/app/conversation/reply.py:160` 限定只能引用已提供记录，且该路径不提供知识证据。因此，即使第二轮文本明确给出 T8D04，也未进入产品确认及知识检索，回复继续围绕“记录中没有说明”。

核心问题是产品使用咨询进入了只解释已有记录的分支。型号目录与知识条目均存在；本次没有检索，所以不能据此判断检索召回质量。

## 修复方向与验收要求

- 区分产品功能咨询与已有步骤解释。产品功能咨询应在必要时追问并确认型号，再按型号检索官方 Q&A，依据命中内容回答。
- 追问后的型号补充必须恢复原始功能问题；保留原始问题和已确认型号，不能只用型号字符串作为检索问题。
- 普通使用咨询不应强行进入故障症状追问或排障步骤反馈流程；已有步骤解释仍应保留其原有语义。
- 验收包含首问缺型号、补充 T8D04 后命中 bp-0001、首轮同时提供型号和功能、已有步骤解释、不明确的 S1 Pro 同名产品等情况。自动化测试使用假模型和假知识库。

## 检查状态

诊断完成。临时只读脚本已运行通过并删除。未修改业务代码，未重放原会话，未提交。
