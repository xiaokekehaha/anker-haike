# 输入框：回车发送与图片粘贴

范围：`frontend/src/components/Composer.tsx`、新增 `frontend/src/lib/device.ts`。仅前端交互，不涉及协议与后端。

## 1. 回车发送

- 桌面端（非触屏）：`Enter` 发送，`Shift+Enter` 换行。
- `Cmd/Ctrl+Enter` 在任何设备都发送，方便平板外接键盘。
- 触屏端（`(hover: none) and (pointer: coarse)`）：`Enter` 保持换行，发送仍走按钮——手机虚拟键盘上回车是换行键，改成发送会造成大量误发。
- 设备判定跟随媒体查询变化（`change` 监听），外接键盘/平板切换后提示与行为同步。无 `matchMedia` 时按桌面处理。
- 中文输入法选词时的回车是候选确认，不能当发送：同时判 `isComposing`、`keyCode === 229` 与 `compositionstart/end` 标记。
- 走的仍是原有 `submit()`，因此草稿为空、离线、运行中、正在提交等禁发条件与发送按钮完全一致。

## 2. 图片粘贴

- 在输入框粘贴截图即作为附件加入待发送列表，与"照片"按钮选图走同一条 `addFiles` 路径：同样压缩到长边 1600 px、同样 5 MB 与张数上限、同样的内联错误提示。
- 剪贴板取图兼容两种形态：多数浏览器给 `clipboardData.files`，Safari 只给 `clipboardData.items`（`kind === 'file'`）。
- 只有取到图片时才 `preventDefault()`，纯文本粘贴保持浏览器默认行为。

## 3. 提示文案

桌面且在线时，在原提示下方另起一行："Enter 发送，Shift+Enter 换行，截图可直接粘贴到输入框。"
单独成段而非拼接到原提示，`aria-describedby` 同时引用两段；离线与触屏端不显示。

## 4. 验收

- 单测：`frontend/src/components/Composer.test.tsx` 的 `Composer keyboard sending`（Enter 发送 / Shift+Enter 不发 / 输入法回车不发 / 空草稿不发 / 触屏端 Enter 不发但 Cmd+Enter 发 / 桌面提示）与 `Composer clipboard images`（files 路径、items 兜底、纯文本不拦截、超限提示）共 10 条。
- 浏览器实测（dev 5173）：Enter 触发 `POST /sessions/{id}/messages` 并清空草稿；粘贴 PNG 出现待发送缩略图。
  注：自动化的 `shift+Enter` 合成事件不会插入换行（对空白 textarea 同样如此），该项以单测覆盖。
