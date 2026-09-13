# 运行手册：发布、回滚与 CI

整理日期：2026-09-12（票 49）。数据库部分见 [database.md](database.md)。

## 1. 版本对应关系

一次发布 = 一个 `release_id`（格式 `<UTC 日期>-<git 7 位 sha>`，如 `20260912-14f3d16`），它同时是：

- CI 构建的镜像 tag：`ghcr.io/<owner>/haike-orchestrator:<release_id>`（另打 `sha-<完整 sha>`）
- `RELEASE.md` 标题与「冻结版本」表（prompt_ver、models.yaml、rules_ver、kb_ver、WeKnora 镜像 tag、回放包清单、迁移 head）
- `releases/<release_id>/config/`：该版 config 目录快照（回滚素材）

生成：`make release`（本机，任何人可跑；CI 里的 image job 用同一公式算 id，二者一一对应）。

## 2. CI（.github/workflows）

| workflow | 触发 | 内容 |
| --- | --- | --- |
| `backend.yml` | PR、push 到 main / feat/** | ruff → 空库 `haike-db upgrade` + `haike-db check`（Postgres service 容器，与 compose 同镜像）→ pytest（含真实 Postgres 集成测试）→ 构建镜像并按 release_id 打 tag（非 PR 推 GHCR） |
| `contracts.yml`（Codex，票 04） | contracts / frontend 变更 | Schema 漂移、TS/zod 生成比对、fixtures 校验、前端测试与构建 |

本机复现全部检查：`make ci-local`。

**「失败阻止合并」需要在 GitHub 上开分支保护**（仓库设置 → Branches → main → Require status checks：`ruff + pytest + db-check`、`Contract consistency`）。命令行等价：

```bash
gh api -X PUT repos/<owner>/anker-haike/branches/main/protection \
  -F required_status_checks.strict=true \
  -f 'required_status_checks.contexts[]=ruff + pytest + db-check' \
  -f 'required_status_checks.contexts[]=contracts' \
  -F enforce_admins=false -F required_pull_request_reviews=null -F restrictions=null
```

## 3. 回滚

前提：`docker-compose.yml` 把宿主机 `./config` 以只读卷挂到 `/srv/config`，所以换目录 + 重启即生效，不重建镜像。

```bash
ls releases/                       # 可回滚的版本
make rollback REL=<上一版 release_id>   # 复制 config → 重启 orchestrator → 等 /health 200（默认 300 s 超时）
```

- 回滚前的 config 自动留在 `releases/_pre-rollback/config/`（gitignore），误回滚可再回来。
- **镜像与 config 必须是同一 release 的成对物**：把新版 config 挂到旧镜像（或反过来）会因配置校验失败。跨 release 回滚时先 `docker compose pull` / 切镜像 tag，再换 config。
  - 注意失败形态：`config/retrieval.yaml` 等是**首次使用时懒加载**的，不匹配不会让容器起不来——`/health` 照样 200、`docker compose ps` 照样 healthy，只有走到对应节点的请求会以 `error/node_failed` 结束（2026-09-13 实测：新版 retrieval.yaml + 旧镜像 → 诊断节点 ValidationError，会话直接失败）。因此换 config 后必须发一条真实会话验活，不能只看 /health。
- 迁移只前向：回滚代码不回滚数据库；新版若加了列，旧代码不读它即可（迁移设计约束，见 database.md §4）。
- 知识库回滚：`make kb-snapshot DIR=data/knowledge/snapshots/<ts>`。
- 共享开发机上回滚会覆盖工作区里未提交的 config 修改——先 `git status config/`。

## 4. 灰度验证顺序（04 §4，写入每份 RELEASE.md）

1. 新 Prompt / 模型 → bake-off 金标实测达标（票 42）
2. 结构化 fixture 跑协议与规则测试（两条 CI 绿）
3. 重录回放包并更新清单（票 43）
4. 演示机 `make up` → `make health` 全 ok → `make db-backup`
