# 工作记录

## 2026-09-19 凌晨
- 通读观测台前端 6 页 7 组件与 api / types / l3 / format，后端 `admin/router.py`、`admin/l3_router.py`、`analytics/{schema,derive,queries,l3}.py`，以及 `cases/store.py` 的 `queue()`。
- 对照 `2026-09-13_admin-observability-console` 的 01_design / 02_hackathon-scope / progress，确认哪些是蓝图、哪些已做、哪些（export-case）没做。
- 本会话 dev 服务器 5174 在 1360 px 走查 `/admin/`、`/sessions`、`/sessions/7a0077bb…`、`/approvals`、`/cases`，无控制台错误。
- 抓真实接口：overview 近 7 天 157 会话 / 放弃 92 / self_service 2.4%；l3 managed_rate 16.2%；队列 18 条含 tracking / open；复盘标注 0 条。
- 产出 findings.md、plan.md、task_plan.md。
- 落地 P0 + P1：路由改为 /desk /board /sessions /lab；新增 Desk / Board / Lab 页、SessionView（复用聊天端 Timeline + RecordPanel）、Difficulties 五难点证据；CaseDetail 重写三栏与决定表单枚举化；Sessions 补筛选与案件列；Journey 默认对话 + 五难点 tab；删除 Approvals / Dashboard / Cases / ReadonlyTimeline。
- 聊天端：Timeline 加 readOnly；ToolRow 补工具名。
- 验证：typecheck 通过；前端 26 文件 222 用例通过；5174 走查全部页面无控制台错误。取舍见 addendum.md。
