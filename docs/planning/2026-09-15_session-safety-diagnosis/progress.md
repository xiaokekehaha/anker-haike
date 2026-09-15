# 进度

- 已读取 AGENTS.md 和 diagnosing-bugs、planning-with-files 技能。
- 已确认管理页面连通并定位固定回复、规则服务入口。
- 已确认工作区已有大量修改，保持原样。
- 读取管理 journey API 与会话结构化日志，保存必要证据字段到 evidence.json。
- 建立离线 repro.py：真实 prepare_step 返回 R4；原始输入无命中；删除「焦味」后检查返回 ok。
- 完成三项候选原因验证：计划原文为必要触发源，无需历史状态或改写模型。
- 编写 report.md，包含上游低置信度选计划、规则来源混淆、摘要丢失真实词及建议。
- 完成诊断。未修改业务代码、数据库或运行服务。

## 最小修复
- 修改前，3 项回归用例失败，均复现计划文字被升级为 R4。
- 两处业务文件修改：pre-step R4 改为 drop，并记录真实检查来源与命中词；prepare_step 使用现有推进逻辑，记录 safety_term_in_step。
- 35 项相关测试通过；原工作区 test_unfaithful_rewrite_falls_back_to_source_text 因模型调用次数 2/1 不符失败，在临时副本恢复两个业务文件为 HEAD 后仍同样失败，确认与此次修改无关。
- 修复触及的测试文件已有 import 排序问题，已自动整理；Ruff 全部通过。
- 当前运行镜像中这两个业务文件均与 HEAD 一致，以该镜像为基础只覆盖两个修复文件，保留原镜像标签以备回退。
- 当前无 active run（只读查询）。部署预检发现旧镜像与当前 plans.yaml 的 symptom_codes 不兼容，验证容器退出失败；停止部署动作，原服务未动。
- 使用镜像内匹配版本配置复验：runtime_probe passed=true；原排名返回 R2，合格备选继续尘盒步骤，三种真实风险输入仍拦截。
- 当前 /health/live 返回 status=ok。当前服务没有重启，补丁尚未部署。
- 更新计划时内联 Python 遇到编码错误，改用 apply_patch 完成文档更新。
