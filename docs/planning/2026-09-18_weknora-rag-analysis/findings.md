# 证据记录

- 项目 docker-compose.yml 默认固定 WeKnora v0.8.0，实际容器版本待确认。
- 项目独立提供 WeKnoraKnowledgeAdapter，通过 hybrid-search 接入；原生聊天与业务问答应分开追踪。
- 上游 main 仍在变化，分析以本地镜像对应 tag/commit 为准。

## 已核实的运行证据
- Docker 镜像 `wechatopenai/weknora-app:v0.8.0` 的 OCI revision 为 `1edcd54b43606d9079bb36650efe3f68707a79ea`，与 tag 精确匹配。
- 指定会话标题「电池掉电很快问题」，本地时间 2026-09-18 08:24:55，用户消息「电池掉电很快」。request_id=`1mrR9LDxgQ0Z`。
- Quick Answer；agent_enabled=false；web=false；原生 Agent 配置 kb_selection_mode=all，解析出全部 3 个知识库，无 knowledge_ids 限制。
- 历史 0 轮，memory 因 workspace_disabled 跳过。查询理解改写为「电池掉电很快是什么原因」，intent=kb_search。
- text-embedding-v4 1024 维；3 库相同模型，一次向量化后合并检索。两路候选各上限150，向量返回128，关键词150，RRF合并215，取10。
- 重排明确 `skip reason=empty_model_id`，不能因存在 gte-rerank-v2 模型就认为本轮调用了它。
- Merge 扩展父块并消除6条内容高度重叠记录；FilterTopK输入已为4条，不是只召回4条。
- 最终证据为 T0223（power_bank/ANKER-A1289/unsolved）、Q45电池官方摘要（headphones）、摄像头演示手册、T0343摄像头工单（solved）。回答将T0223归入耳机，说明携带metadata不等于业务硬约束。
- 主回答模型deepseek-flash；生成输入1637 token，输出742 token；日志TTFB首回答4241ms；消息更新约6秒。不计查询改写和并行标题生成的额外token。
- 数据库只读计数：manual35份/104子块/35父块；tickets380份/380文本块；faq1容器/116条FAQ。
- 项目当前 config/retrieval.yaml 的multi_query、faq、rerank、parent_expand、grade、query_rewrite均false，不能把已实现可选路径写成已启用。
- 最终模型请求确认不含power_bank/category/scope；原因是references.go构造模型rows时遗漏knowledge_metadata，替换了原始RenderedContexts。前述metadata存在指数据库及中间快照，不代表最终模型收到这些字段。
- 已确认6条去重记录跨SKU与工单结果；Q45父块277字符被后续短块扩展覆盖成154字符，均有源码与运行日志交叉证据。

## 链路B修改必要性
- 当前每次API请求match_count=15，但adapter先裁到每库5条/每条400字符，多查询融合又裁5条；rerank无法看到被丢弃候选。
- grade返回insufficient不直接驱动补查；有一条relevant或故障卡可挡住文本rewrite，已有quality-first-retrieval-rescue规格尚未完整落地。
- 第二轮不rerank，首轮优先、新候选追加；synthesize只选前12条，每条300/800字符。新增正确证据可能进不了模型。
- 多查询存在已记录的“小刷子”到“小滚刷”替换副作用；全局同义词表不适合直接扩展到多品类。
- 9月16日基线58条仅2条人工标注，当前eval不走真实第二轮与完整intake；当前多品类大语料须重新冻结版本、标注并分项验证。
- 详细结论见chain-b-recommendations.md，运行编排与评测口径分别见chain-b-runtime.md、chain-b-evaluation.md。
