# 01: Compose 骨架与 /health 聚合

**What to build:** 从零 `docker compose up` 拉起 orchestrator（FastAPI）、postgres（pgvector）、weknora-app、redis 四个容器，编排服务提供健康接口，按组件（db / weknora / redis / models 按通道）分别报告可用状态。这是所有后续票的运行底座。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 在干净机器上一条命令拉起全部容器，编排服务可访问
- [ ] 健康接口返回每个组件独立的 ok / down 状态，任一组件停掉后状态变化在 10 s 内可见
- [ ] Python ≥ 3.11、依赖锁定文件、WeKnora 镜像 tag 固定并记录
- [ ] 有一页 README 说明启动、停止、重置数据的方法

**设计依据：** 02 §6、04 §5、06 部署段
