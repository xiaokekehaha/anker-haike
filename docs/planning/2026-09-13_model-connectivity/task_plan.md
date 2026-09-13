# 模型连通性列表

## Goal
点击顶部「模型」查看当前通道模型及折叠的其他模型，手动真实检测、逐项展示结果。移除对话区笼统告警。保持业务路由不变。

### Phase 1: 调查与设计
**Status:** complete
- 复用启动时 ModelRegistry；仅列聊天模型，embedding/rerank 不用对话探测冒充验证。
- GET /models/status 只读；POST /models/{alias}/probe 直连指定模型，最小文本请求，无备用链和 SDK 重试。
- 结果进程内保留 5 分钟，显式时间；最多 2 个并发探测；不返回原始厂商异常和密钥。

### Phase 2: 接口与弹窗
**Status:** complete
- 可访问弹窗、当前通道列表、其他模型折叠、单项重测、当前通道批量检测。
- 五种状态：未配置、未检测、检测中、已连通、连接失败；失败原因可读。
- 保留知识库/数据库灯和回放徽标，模型入口不使用配置齐全度亮灯。

### Phase 3: 验证与交付
**Status:** complete
- 后端验证真实指定调用、不降级、不重试、缺密钥跳过、缓存/过期、错误脱敏、并发与超时。
- 前端验证打开不探测、逐行刷新、关闭/重开、失败、未配置跳过；运行类型检查和构建。
- 浏览器验收桌面/手机弹窗，并验证当前环境的真实探测。

### Phase 4: 按用户要求再次部署服务
**Status:** complete
- 重建当前工作区镜像，更新本机 orchestrator，核对存活、模型接口和静态资源。

## Next Step
部署已确认完成，本机 http://localhost:8000 可直接使用。

## Errors Encountered
- 初次读取 frontend/src/test/setup.ts 路径不存在；通过文件检索确定实际测试配置。
- 读取 global.css/globals.css 路径不存在，已定位 base.css/tokens.css。
- TypeScript 索引可能为 undefined、Ruff 要求 UTC 别名：已修复。
- jsdom 缺少原生 dialog.showModal，测试中补最小 dialog polyfill；真实焦点/布局在浏览器验证。
- 全量前端测试并行时凭证备注断言失败，单独运行通过；降低并发核对完整套件。
