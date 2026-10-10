# 模型 API 失败与余额核查

## Goal
只读核查当前系统近期模型 API 失败，判断是否存在供应商欠费，并给出明确充值对象或无需充值的证据。

### Phase 1: 运行环境与供应商定位
**Status:** complete
- 本机 Docker 服务健康，默认 domestic；已配置 dashscope、deepseek、zhipu。
- 检查已有未提交改动，不触碰其他会话文件。

### Phase 2: 实际错误与预算语义核对
**Status:** complete
- 脱敏读取运行日志、模型调用记录及近期复测结果。
- 区分厂商余额不足、限流、输出长度和本地调用时限。

### Phase 3: 当前状态验证与结果
**Status:** complete
- 按证据决定是否需要最小直连探测；记录结论和覆盖范围。

## Next Step
核查完成，向用户报告无需因当前错误充值。

## Errors Encountered
- docs/adr、docs/adrs 不存在；使用仓库现有文档定位，不再搜索这些路径。
- app/context/capacity.py 不存在；根据实际导入定位到 context/budget.py 与 router 的 budget_ms 逻辑。

