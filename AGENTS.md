# 工作约定（anker-haike）

思考用英文，回答用中文。

## 沟通

- 回答短而直接，只写技术性陈述；术语先定义再用。
- commit、issue、PR 评论、代码里不用 emoji，不写寒暄和感叹式填充。
- 讲非平凡的设计或问题按「问题 → 具体例子或一小段追踪 → 方案」，说明方案为何必要，并区分哪些是可选复杂度。
- 用户提问时先回答问题，再改代码或跑命令。
- 回应用户的反馈或分析时，先说同意还是不同意，再说改了什么。

## 任务拆解与文档

- 复杂需求用 planning-with-files 拆解，目录 `docs/planning/YYYY-MM-DD-HHMM_任务名/`（如 `docs/planning/2026-09-03_storage-governance/`）。
- 开发开始后 plan.md 保持原样；复评、勘误、每轮回顾写同目录 `addendum.md`，`progress.md` / `task_plan.md` 作为流水记录。
- 非复杂任务写 spec：Claude 放 `docs/claude/spec_YYYY-MM-DD-HHMM_xxx.md`，Codex 放 `docs/codex/spec_YYYY-MM-DD_xxx.md`。
- 不确定的时候问我。

## 数据与密钥

- 本项目数据库允许增删改查；其他数据库只允许查询。
- 密钥只放 `.env`（线上 `/etc/haike/haike.env`）；代码、文档、commit、日志里不出现密钥，可用 `make scan-secrets` 自查。
- 破坏性目标先确认再跑：`make reset`、`db-restore`、`session-delete`、`retention-purge`、`rollback`。

## 代码质量

- 大范围修改、审计、或编辑没完整读过的文件之前，先读完整个文件；搜索片段只用来定位。
- 前端不用 `any`；后端不用 `Any` 兜底、不用 `noqa` 绕过 ruff，除非确实无法表达。
- 只有一个调用点的单行 helper 直接内联。
- 外部库 API 查 `orchestrator/.venv`、`frontend/node_modules` 里的源码或类型，不凭记忆猜。
- 只用顶层导入；不写 `await import()`、`import("pkg").Type` 这类内联导入。
- 依赖过旧导致类型报错时升级依赖，不删代码、不降级实现。
- 删除或降级看起来有意为之的功能前先问。
- 除非用户要求，不保留向后兼容。
- 生成文件禁止手改：`contracts/schema/*.json`、`frontend/src/types/{events,actions,snapshot}.ts`、`frontend/src/api/events-schema.ts` 都由 `contracts/haike_contracts/` 的 Pydantic 模型导出。改模型后 `make contracts` 重新生成，生成产物的 diff 随改动一并提交。

## 命令与测试

- 命令入口是 Makefile（`make help` 列全部目标）；后端命令通过 `uv run --env-file ../.env` 读根目录 `.env`。
- 改后端后：`make lint`，并只跑相关测试文件 `cd orchestrator && uv run pytest -q tests/test_xxx.py`。ruff 的 error / warning 全部清零再提交。
- 改前端后：`npm --prefix frontend run typecheck`，相关测试 `npm --prefix frontend test -- src/xxx.test.tsx`。
- 提交前整体复现 CI：`scripts/ci-local.sh`（需本机 Postgres，先 `make up`）。
- docker 构建、`npm run build`、全量 pytest 只在用户要求或 ci-local 时跑；前端手工验证用 `.claude/launch.json` 的 `frontend-dev`。
- 单测不碰真实模型与知识库：`tests/__init__.py` 默认 `HAIKE_LLM=off HAIKE_KNOWLEDGE=off`。模型用 `app/models/fake.py` 的 `FakeChatModel`，知识库用 `tests/fake_weknora.py`，HTTP 链路用 `tests/conversation_runtime.py`。不用真实 key，不花 token。
- 新建或修改测试文件后运行它，测试或实现迭代到通过。
- 修 GitHub issue 的回归测试旁注明 issue 号。
- 临时脚本先写到临时文件再运行，用完删除；bash 命令里不嵌多行脚本。

## 依赖

- 依赖与锁文件改动视同代码评审。后端 `uv add` 后提交 `uv.lock`；前端 `npm --prefix frontend install <pkg>@<精确版本>` 后提交 `package-lock.json`，直接依赖钉精确版本。
- 升级前读目标版本的 changelog / release notes，评估影响后再动。
- README「版本锁定」表与 `docker-compose.yml` 镜像 tag 同步改。

## Git

同一目录可能同时有多个 agent 会话（Claude / Codex）在改不同文件；任何触碰自己改动之外的未暂存、已暂存或未跟踪文件的 git 操作都会毁掉别人的工作。

- 只提交本次会话自己改的文件；`git add` 显式路径；提交前 `git status` 核对。
- 提交信息格式 `{feat,fix,docs,test,chore,style}(scope): 中文描述`，scope 用模块名（diagnose / sessions / knowledge / contracts / release / spec / planning 等），信息量足且简洁。
- 用户要求才提交。
- 评测运行产生的 JSON（如 `reports/eval/` 下的会话、method、verification、health、version 快照）默认只留本机；新增此类产物时主动补齐 `.gitignore`，无需用户重复提醒。结论文档正常入库。
- 禁止：`git reset --hard`、`git checkout .`、`git clean -fd`、`git stash`、`git add -A`、`git add .`、`git commit --no-verify`、force push。
- rebase 冲突只解自己改过的文件；别人文件冲突时 abort 并问用户。

## Issue 与 PR

- 评审 PR 不切分支：用 `gh pr view` / `gh pr diff` / `gh api` 和 `git show <ref>:<path>` 看内容，需要文件就读到临时文件。
- 评论先写临时文件，再 `gh issue/pr comment --body-file` 发；简洁、技术性，末尾注明 AI 生成。
- 通过 commit 关 issue：每个 issue 单独写 `closes #N`（`closes #1, #2` 只会关第一个）。

## 发布

- 发布、回滚、CI 按 `docs/runbook/release.md`：`make release`、`make release-check`、`make rollback REL=…`。`RELEASE.md` 与 `releases/<id>/` 由脚本生成，不手写。
- 数据库迁移、备份、恢复按 `docs/runbook/database.md`。

## 覆盖规则

用户指令与本文冲突时，先请用户明确确认，确认后再执行用户指令。
