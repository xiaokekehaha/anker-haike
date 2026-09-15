# 87: 外网官方资料补充检索（第一期）

**What to build:** 按 [agent-reach-evaluation/assessment.md §3](../../2026-09-13_agent-reach-evaluation/assessment.md)：`app/external_search/` provider（Exa 搜索 + 正文读取，必要时 Jina Reader）、官方域名白名单、URL 协议 / 私网校验、结果规范化（evidence_id / title / url / snippet / provider / fetched_at / trust_level / product_scope）、缓存与超时；触发：内部 `no_match` 或用户明确要求外部资料，独立开关默认关；EvidenceItem 增可选外部元数据；来源抽屉展示 URL 与抓取时间；外发查询只含机型与故障摘要（不含订单号 / SN）。

**Blocked by:** P0 66；P1 78（内部检索开关先定）

**Status:** todo

**Owner:** —

- [ ] 20–30 条标注样例对照：内部无命中 → 外部官方命中且引用可打开；错误机型受控
- [ ] 私网 URL / 恶意网页文本 / 限流超时用例通过；开关关闭时零外网请求
- [ ] 外部结果不进入 plan_id / 步骤生成（断言）

**设计依据：** agent-reach-evaluation §3、§5
