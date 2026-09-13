# 效果优先的检索补救规格

## Goal
将当前对话整理为可执行规格；确认测试边界和项目 issue tracker 后，发布并应用 ready-for-agent 标签。本任务不修改业务代码或运行配置。

## Phases
1. 核对现有实现、历史评测、D15 / D19 与已有测试边界。**Status:** complete
2. 按 to-spec 模板完成规格和验收方案。**Status:** complete
3. 确认测试边界与 tracker 配置后发布 issue。**Status:** pending

## Decisions
- 用户已明确：耗时先忽略，效果优先；不能将 grade 误删导致的退化归因于尚未触发的 query 改写。
- 采用当前对话提出的补救方向：证据不足也能触发补查，评分不再硬删除原始候选，两轮合并后诊断。
- 主测试边界复用会话 HTTP API → SSE / 快照；外部依赖沿用 ModelRouter 和 KnowledgeAdapter 的替身。
- 真实效果沿用现有评测入口，并要求与线上补救编排一致。
- 不因为存在 GitHub remote 或旧的本地 issue 文件，就自行认定当前指定的 issue tracker。

## Next Step
请用户确认规格中的测试边界，并通过 /setup-matt-pocock-skills 提供尚未找到的 tracker / triage 约定；随后发布规格并应用 ready-for-agent。

## Errors Encountered
- 初始搜索包含不存在的可选目录，rg 返回 2；后续对已存在的项目文件做定向读取，无内容丢失。
