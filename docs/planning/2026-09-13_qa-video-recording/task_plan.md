# 问答交互视频录制
## Goal
打开 http://localhost:8000/，进行约 10 次真实页面问答交互，保存视频。
## Phases
- 页面与录屏准备：complete
- 十轮问答与交互录制：complete
- 验证视频并交付：complete
## Next Step
已完成，交付 anker-10-rounds.mp4。
## Errors
- QuickTime 不在可用应用列表，系统快捷键未显示可控录屏界面，改用 CUA 页面逐帧采集。
- 浏览器枚举在连接变化后从 1 变为 2，重新发现并连接同一标签页。
- 定位最终内容时一次点击失败，使用 End 键滚动后已确认结束画面。
## Deliverable
- anker-10-rounds.mp4：5 分 29 秒，694×780，15 fps，约 6.6 MB，无音频。
- conversation-ax.txt：完整对话可访问性文本。
- README.md：10 轮交互顺序与录制方式说明。

## 后续剪辑
- 去除重复与等待画面，保留关键交互并加速，时长小于 60 秒：complete
