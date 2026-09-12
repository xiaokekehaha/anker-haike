# 01: Compose 骨架与 /health 聚合

**What to build:** 从零 `docker compose up` 拉起 orchestrator（FastAPI）、postgres（pgvector）、weknora-app、redis 四个容器，编排服务提供健康接口，按组件（db / weknora / redis / models 按通道）分别报告可用状态。这是所有后续票的运行底座。

**Blocked by:** None (can start immediately)

**Status:** done（2026-09-12，Docker 实测通过）

- [x] 在干净机器上一条命令拉起全部容器，编排服务可访问（colima + docker 29.8，`make up` 首次拉取并构建后五容器全部 healthy）
- [x] 健康接口返回每个组件独立的 ok / down 状态，任一组件停掉后状态变化在 10 s 内可见（探测超时 2 s + 缓存 3 s；容器级实测：停 redis / weknora-app / postgres 后分别 3 s / 4 s / 3 s 可见 down，恢复同样 3–4 s；postgres 停机时 /health 返回 503）
- [x] Python ≥ 3.11、依赖锁定文件、WeKnora 镜像 tag 固定并记录（Python 3.12，orchestrator/uv.lock，WeKnora v0.8.0，见 README「版本锁定」）
- [x] 有一页 README 说明启动、停止、重置数据的方法（根目录 README.md）

**设计依据：** 02 §6、04 §5、06 部署段

**实现记录（2026-09-12）：** 根目录 docker-compose.yml / Makefile / README.md；orchestrator/app/health（checks.py 逐组件探测，router.py 聚合 + 3 s 缓存 + `?force=`，`/health/live` 存活探针）；deploy/postgres/init 在 WeKnora 的 PostgreSQL 实例内额外建 haike 库。与票面差异：WeKnora v0.8.0 的 app 依赖 docreader，Compose 为五个业务容器；postgres 用 WeKnora 官方 paradedb 镜像（含 pgvector）。

**Docker 实测记录（2026-09-12）：** 本机 colima（4 CPU / 8 GiB）+ docker 29.8 + compose 插件。`make up` 一条命令拉起 orchestrator / postgres / redis / weknora-app / weknora-docreader 五容器；`make down` 后再 `make up`，haike 库数据保留、/health 恢复 200；haike 库内 vector 扩展已建；首页同源静态返回 200。编排服务日志无 error / warn。已知：默认通道 domestic 因 dashscope / zhipu / anthropic key 未配置报 unconfigured，整体 status 为 degraded，属预期（key 在票 42 bake-off 前补齐）。
