# 多语言检索评估方案

目标：核对现有实现，给出英文症状表达与补查改写的标注、对照、上线门槛方案。此次只产出设计，不运行真实模型或修改运行配置。

## 阶段
- [x] 核对检索、改写、评分和评测入口。
- [x] 设计标注、消融对照和验收标准，保存 plan.md。
- [x] 核对文档与代码依据并交付。

## Next Step
A2 核实完成，结论见 addendum.md §8；后续可进行同查询三种检索通道对照，本次未执行。

## A2 复核
- [x] 确认当前镜像及租户检索配置。
- [x] 确认融合公式、match_type 的含义与现有请求记录。
- [x] 保存复核结论并解释证据边界。

## 错误记录
- 初次搜索包含不存在的 orchestrator/evals；后续通过 rg --files 定位实际评测目录。
- 后续路径猜测 evalsets、sessions/interpret.py、sessions/reduce.py 不存在；已定位 data/eval 与 app/conversation，未影响文件。
- A2 上游 knowledgebase_search_result.go 返回 404，已按已有文档定位为复数 results.go；日志无 RRF rank 匹配，不能恢复逐项融合贡献。
