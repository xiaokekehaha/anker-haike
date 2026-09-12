# 发现

- HEAD 为 9413c3f，工作区有大量未提交实现，不能仅按 git log 判断完成度。
- frontend/README.md 仍描述首页空壳，已落后于当前 App、会话与卡片实现。
- 已有接续记录报告前端 96 个测试通过；该记录属于历史验证，本轮尚未复跑。

- 当前 8000 页面已可打开；8081 WeKnora 与 3000 Langfuse 均 HTTP 200。
- /health HTTP 200 但业务 status=degraded：db/redis/weknora 为 ok，模型 domestic/overseas 为 unconfigured，providers_ready 仅 domestic.deepseek。
- 当前源码 graph.py 的 guide_entry 仅设置阶段，图仍 guide_entry → END；34–36 为 claimed，完整步骤反馈闭环不能验收。
- 最新前端凭证记录：117 前端、72 定向后端测试通过，21/39 done，40 真实视觉验收待补；本轮没有复跑测试。
- 37 多轮补充/纠正未完成；42 模型评测进行中，43/45/48/50 未结项；44 监控进行中。
- 当前容器未找到 /srv/app/guide，代码和部署有版本差异；不能把工作区新实现等同当前体验环境。

- 实测消息失败：RulesConfig / RulesError 指向 safety_terms.yaml；会话创建成功，消息流 HTTP 200 不能代表处理成功。
- 容器确实不含 app/warranty/service.py；先前猜测 lookup.py 路径不适合作为依据，已按实际 service.py 验证。
- 凭证参考库为虚构演示数据，不能称为真实订单系统对接。
