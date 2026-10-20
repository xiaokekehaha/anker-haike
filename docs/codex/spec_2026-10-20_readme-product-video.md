# README 产品演示视频

## 目标

在项目简介后展示 37 秒、2 倍速、1080p 的产品演示，覆盖物流查询、服务单提交、后台追踪和带官方视频链接的排障卡片。

## 方案

- 参考 [Presenton 的 README](https://github.com/presenton/presenton)，将视频放在简介后、技术说明前。
- 使用 GitHub 视频附件地址触发原生播放器；Git 仓库保存 README 引用，不保存 MP4。
- 上传版为 H.264、1920×1080、30 fps、37 秒、9,121,221 字节，无音轨。保留 2 倍速与演示数据说明。
- 通过独立的 `codex/readme-product-video` 分支提交，检查后合并 main。

## 验证

- 本地视频完整解码通过，共 1,110 帧；抽帧检查后台记录文字。
- `APP_ENV=dev` 下运行 `scripts/ci-local.sh` 通过：后端 1,411 项通过、6 项跳过，契约 91 项通过，前端 267 项通过；契约生成检查、前端构建与密钥扫描通过。使用独立项目测试数据库并关闭真实模型和知识库。
- 额外使用 `APP_ENV=ci` 检查时，main 基线有 3 个后台审批相关测试返回 `403 admin_identity_required`；本次未修改鉴权实现或测试。
- GitHub 分支 README 已显示原生播放器并成功播放；浏览器读取时长 37 秒、分辨率 1920×1080。

## 依据

- [GitHub README 支持视频上传](https://github.blog/changelog/2021-05-13-video-uploads-now-generally-available/)
- [视频格式与附件大小限制](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files)
