# 49: 生产就绪：CI/CD 与版本冻结

**What to build:** CI 跑单元测试、contracts 比对、前端构建、fixtures 回归；构建带版本 tag 的镜像；发布脚本写 RELEASE.md（prompt_ver、models.yaml、rules_ver、kb_ver、WeKnora 镜像 tag、回放包清单）；回滚为切回上一版 config 目录并重启。

**Blocked by:** 04（前端 TS 类型生成、CI 比对与 fixtures 骨架）、42（bake-off 评测与模型 ID 冻结）

**Status:** done（2026-09-12；模型 ID 冻结项随票 42：RELEASE.md 会统计 models.yaml 的 TBD 数，当前 9，为 0 才算冻结）

**Owner:** Claude Code A（2026-09-12 认领；`.github/workflows/`（后端 / contracts / 前端 / db-check 四条 CI）、RELEASE.md 骨架；模型 ID 冻结项等票 42）

- [x] 每次提交触发 CI，失败阻止合并（backend.yml：ruff → 密钥扫描 → 空库迁移 + db-check（Postgres service）→ pytest → 镜像构建；contracts.yml 由 Codex 票 04。「阻止合并」是 GitHub 分支保护设置，命令在 docs/runbook/release.md §2，需仓库管理员执行一次）
- [x] 镜像 tag 与 RELEASE.md 版本一一对应（release_id = <UTC 日期>-<7 位 sha>；CI image job 与 scripts/release.sh 用同一公式；RELEASE.md 记录 ghcr 镜像 tag、prompt_ver、models.yaml、rules_ver、kb_ver、WeKnora tag、回放包、迁移 head、config 快照）
- [x] 回滚脚本 5 分钟内切回上一版并通过健康检查（`make rollback REL=`：换 config/ + 重启 orchestrator + 等 /health；config 以只读卷挂入容器。演练：坏发布改 models.yaml 版本 → 容器内生效 → 回滚 2 s 内 /health 200、容器与宿主机 config 均回到上一版）
- [x] 灰度验证顺序（bake-off → fixture → 重录回放）写入发布清单（RELEASE.md 与 runbook/release.md §4）

**设计依据：** 04 §4

**实现记录（2026-09-12，Claude Code A）：** `.github/workflows/backend.yml`、`scripts/release.sh`（RELEASE.md + `releases/<id>/config/` 快照）、`scripts/rollback.sh`（保留回滚前 config 于 releases/_pre-rollback/）、`scripts/ci-local.sh`、compose 把 `./config` 只读挂进 orchestrator、Makefile release / rollback / ci-local、docs/runbook/release.md。

**演练暴露并修掉的容器问题：** ① 旧镜像 + 新 config 直接配置校验失败进入重启循环 → 「镜像与 config 成对冻结」写进手册；② 容器内 REPO_ROOT 解析为 /，B 的 catalog / plans / rules / fault_cards 默认路径在容器里不存在，Dockerfile 补全 *_CONFIG_PATH 环境变量；③ 票 47 的 alembic.ini / migrations 未 COPY 进镜像，已补；④ colima 内拉 PyPI 卡死，Dockerfile / compose 增加 UV_INDEX_URL / NPM_REGISTRY 构建参数。
