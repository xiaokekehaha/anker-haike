# 49: 生产就绪：CI/CD 与版本冻结

**What to build:** CI 跑单元测试、contracts 比对、前端构建、fixtures 回归；构建带版本 tag 的镜像；发布脚本写 RELEASE.md（prompt_ver、models.yaml、rules_ver、kb_ver、WeKnora 镜像 tag、回放包清单）；回滚为切回上一版 config 目录并重启。

**Blocked by:** 04（前端 TS 类型生成、CI 比对与 fixtures 骨架）、42（bake-off 评测与模型 ID 冻结）

**Status:** claimed

**Owner:** Claude Code A（2026-09-12 认领；`.github/workflows/`（后端 / contracts / 前端 / db-check 四条 CI）、RELEASE.md 骨架；模型 ID 冻结项等票 42）

- [ ] 每次提交触发 CI，失败阻止合并
- [ ] 镜像 tag 与 RELEASE.md 版本一一对应
- [ ] 回滚脚本 5 分钟内切回上一版并通过健康检查
- [ ] 灰度验证顺序（bake-off → fixture → 重录回放）写入发布清单

**设计依据：** 04 §4
