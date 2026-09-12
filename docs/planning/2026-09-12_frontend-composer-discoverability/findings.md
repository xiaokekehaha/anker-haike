# 发现

- 用户截图与当前代码一致：ChatPane 含欢迎语、六个分类和四张示例卡，Composer 位于整个 ChatPane 后；输入框没有可见 label，边框与示例卡相近。
- 分类/示例点击仅 setDraft，不聚焦或滚动到输入框，用户不容易发现可继续输入。
- 移动端隐藏了输入区的离线说明，发送按钮不可用原因不明显。
- 当前 App / ChatPane / Composer 来自另一次 UI 改版，改版说明在 docs/claude/spec_frontend_shell_redesign.md；保留其全产品方向。
- Vite 开发页 5173 已运行；8012 是本任务前次启动的静态验收服务。8000 由 ssh 占用，不修改这些服务配置。
