# 88: 生产就绪收口（遗留问题清单）

**What to build:** 清理 [overall-acceptance/report.md §三](../../2026-09-13_overall-acceptance/report.md) 遗留：RELEASE.md 与部署镜像一致性自动校验（CI 比对 manifest 与镜像标签）；告警 sink 实配（webhook / SMTP）并消除 `health_check_failed` 缺 key 误报（缺 key 标 skipped）；前端分包（用户端 / 管理端 / 依赖 vendor 拆分，首包 < 250 kB）；集成测试改用独立 schema 并清理；票 46 HTTPS 入口、47 恢复演练、49 远程 CI 的验收补跑；bake-off 7/10 任务缺合规备链的补测或明确豁免记录。

**Blocked by:** P0 66

**Status:** todo

**Owner:** —

- [ ] CI：RELEASE 漂移即失败；健康灯无误报持续 24 h
- [ ] 前端 build 体积报告；Lighthouse 首屏对照
- [ ] 恢复演练记录（db-restore 到新环境 A1–A9 通过）

**设计依据：** overall-acceptance §三、§五
