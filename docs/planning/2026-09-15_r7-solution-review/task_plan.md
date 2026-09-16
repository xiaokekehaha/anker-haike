# R7 spec 解决方案评估

## 目标
核对 spec 与当前实现，落实诊断决策、共同计划约束、进展预算和可追溯摘要。用户已授权开始开发；本次不部署。

## 阶段
1. 阅读 spec 与已有实施记录：complete
2. 执行现有针对性回归并核对剩余差距：complete
3. 记录推荐方案、边界与验收标准：complete

## Next Step
开发与验收完成，实施效果、边界和验证结果见 implementation.md；未部署。

## 开发阶段
4. 建立剩余问题的回归信号：complete
5. 实现共同计划约束、诊断快照与问答进展预算：complete
6. 实现摘要消费快照及失效边界：complete
7. 运行针对性和整体回归，交付实施记录：complete

## Errors
- 初次按猜测路径读取 app/policy/clarify.py 失败；已通过 rg 定位 app/sessions/clarify.py。
- 检查两个虚拟环境目录时根目录 .venv 不存在，实际使用 orchestrator/.venv；一次 config 通配符被 zsh 拒绝，已改用 rg 搜索目录。
- 开发时初次测试文件写入路径重复 orchestrator 前缀；改用正确工作目录相对路径。
- 两次路径/读取命令出错（contracts/src、diagnose/plans.py 和 sed 地址）；已定位真实 plans 模块并修正读取。
- 新测试初次引用 retrieval 配置函数路径不正确；改为实际 graph 导出。
- 新端到端 fixture 提供了不在用户原文中的产品 hint，被 reducer 正确拒绝；修正测试输入让型号真实出现在原文。
- Ruff 发现一个 import 排序问题，最终检查时修正。
- 新增 fixture 导入触发 Ruff F811；改用 usefixtures 装饰器，最终静态检查通过。

## 方法说明
评估阶段先执行已有精确回归，区分历史缺陷与当前行为。用户授权开发后先建立失败回归，再修复并验证完整 reducer→clarify→检索→步骤发布→摘要链路。未保留临时插桩；新增回归作为长期测试保留。
