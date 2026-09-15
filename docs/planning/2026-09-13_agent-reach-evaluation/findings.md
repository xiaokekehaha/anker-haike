# 发现

- 根据“扩展 AI 搜索能力”的描述，调研对象按 Panniantong/Agent-Reach 确定：https://github.com/Panniantong/Agent-Reach 。另有同名 SSH 工具，不符合本需求。
- 本项目为扫地机器人售后智能服务，后端 FastAPI + LangGraph，Python >=3.12，现有 WeKnora 知识检索。
- 上游事实详见 official-research.md；最终接入建议见 assessment.md。

## 本地实现依据
- `orchestrator/app/knowledge/search.py:search_round` 固定查询 kb_manual/kb_tickets，可选接入本地 FAQ；未见互联网检索 provider。
- `config/retrieval.yaml` 中 multi_query、faq、rerank、parent_expand、grade、query_rewrite 当前仓库默认均关闭；“已实现”不等于“运行中已启用”，尚未读取运行环境覆盖。
- `orchestrator/app/sessions/graph.py:retrieve` 集中执行首轮检索、相关性评分、补检索与 synthesize，已有剩余时间预算和检索 trace。
- `KnowledgeScope` 按产品状态/SKU 限定内部资料；外部页面需要独立验证 SKU/区域/版本，不能仅从 query 推定匹配。
- `diagnose/synthesize.py` 只能选择预写计划，过滤未知 plan_id 和证据 id；外网接入不能自动获得新排障步骤的执行能力。
- `contracts/haike_contracts/common.py:EvidenceItem` 目前以内部文档 id/version/chunk 为主；前端 EvidenceDrawer 无外链、抓取时间、信任等级展示。
- `knowledge/ingest.py` 能导入带 front matter 的 Markdown；但当前 metadata 构造只保留固定字段，外部出处要扩展导入/读回链路。
- 搜索命令曾因 zsh 未匹配到 `orchestrator/app/sessions/nodes*` 返回 1；改为真实路径 `graph.py` 后完成检查。

## 综合结论
- 上游 v1.5.0 Beta 的统一能力是配置与健康检查；存在局部 helper，但没有全平台 search/read SDK。自带 MCP 仅 get_status。
- 推荐在线业务使用本项目拥有的 Exa HTTP/MCP provider，必要时补 Jina；Agent-Reach 的 CLI 工具集合更适合独立采集环境。
- 系统安装可能修改用户级工具和多个 Agent Skill 目录，不能视为仓库内局部开关。此次未执行安装。
- Exa/Jina 的匿名入口有配额；平台登录、部署网络和实际检索效果仍待验证。具体依据见 official-research.md。
