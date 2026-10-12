# 已核实信息

- query_rewrite、grade、rerank 均默认关闭，synonyms 为空。
- config/retrieval.yaml 注释与 graph.py 条件均显示：query_rewrite 开启时即会进行充分性评估，并不要求 grade.enabled 同时开启。
- models.yaml 的准确率属于历史 bake-off，不能直接换算为真实工单误改率。
- 工作区已有其他会话改动：synthesize.py、qa_index.py、graph.py 和若干文档；本次不修改这些文件。
- should_rewrite 在证据不足、无相关证据、评估未知或无命中时允许补查；图片补查与文本改写共用一次名额。
- validate_rewrite 的否定、部件、原因词表主要为中文；shares_anchor 用任意相邻两字符重叠，不能证明跨语言语义一致；过滤字符还包含英文缩写可能使用的撇号。
- score_rewrite 把校验拒绝记为 0，再检查 must_contain_any；历史 75% 不是“25% 真实工单被改错”的证据。
- 已有 make kb-eval 和 data/eval/tickets/cases.yaml 的 qa_gold / qa_exact。后者注释记录 2026-10-08 英文官方术语实验 9/12 → 9/12，需区分它与尚未开展的线上抽取、触发和多语言配对评估。
- 活跃 intake 入口为 conversation/interpret.py，经 sessions/graph.py 调用；不能只修改旧 intake/extract.py。
- 已完整阅读 knowledge/eval.py：只执行一次检索，不执行 intake/grade/rewrite；ARM 仅报告名。Hit@k 被命名为 recall@k，无金标案例直接跳过。
- T21、T36、T43 当前没有金标，T20、T37 有金标。T43 原文仅 El robot está desconectado.，不能据此断言路由器或 Wi-Fi 硬件故障。
