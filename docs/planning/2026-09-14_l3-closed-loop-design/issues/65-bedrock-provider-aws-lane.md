# 65: Bedrock provider 与 aws 通道（可选，待 D-L3-2 确认）

**What to build:** `models.yaml` 增 `providers.bedrock {sdk: bedrock, region_env: AWS_REGION, lane: aws}`、模型 `bedrock-sonnet / bedrock-haiku`（Claude on Bedrock，vision + native structured）、`lanes.aws` 镜像 overseas 链；`app/models/registry.py` 增 `ChatBedrockConverse` 初始化（依赖 `langchain-aws`），凭证走标准 AWS 链（env / profile），缺凭证时模型 skipped 不报错；`haike-probe` 支持 aws 通道；bake-off 对 aws 通道跑 10 个 task 并出报告。文档：方案中「与 AWS 的关系」段落（02 §4）。

**Blocked by:** —

**Status:** todo（待用户确认）

**Owner:** —

- [ ] `MODEL_LANE=aws` 启动健康；无凭证时 health 标 skipped 而非 failed
- [ ] probe 10 个 task 通过；bake-off 报告入 `reports/bakeoff/`
- [ ] 不引入 Bedrock Knowledge Bases；检索路径不变（断言无新依赖）

**设计依据：** 02 §4；00 D-L3-2/3/4
