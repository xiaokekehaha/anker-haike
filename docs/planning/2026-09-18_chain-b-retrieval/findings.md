# 实现依据

- 前期只读分析：docs/planning/2026-09-18_weknora-rag-analysis/chain-b-recommendations.md。
- adapter 请求15后裁5；search融合再裁5；grade硬过滤且insufficient不驱动rewrite；二轮追加而synthesize只看前12。
- 统一context已提供产品和历史，不重复建设上下文层。需要修改的是候选正文保留及task_data的最终选择。
- 原知识库与模型评测过旧，本轮采用可控替身证明流程，不冒充真实准确率评估。
