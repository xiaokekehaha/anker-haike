# 照片先验进候选集 + 部件推品类

## 目标

修掉 2026-09-17 重放 9db 场景（会话 10c5eeaf46004f2dbdf951fd0d4d65e4）暴露的「照片读了、没用上」：

1. 照片签名命中的计划（滚刷+缠绕 → rv_suction_hair_wrap）能进入候选集，不再被文字症状过滤掉；
   异响对应的安全停机计划 rv_suction_motor_fault 仍在候选中且不被挤掉。
2. 照片里可辨的品类特有部件（滚刷 / 边刷 / 尘盒 / 吸口 / 基站）成为**待确认**的品类线索，
   沿用现有 expected_category「是 / 不是」确认，不静默锁定。

## 阶段

1. 复现与定位：fault_localization 在第 5 轮是否仍在状态、三处 symptom_codes 过滤点：complete
2. 设计：图片签名如何进 symptom_codes / 事实，与 decide_symptoms 共同计划、decide_next 候选规则一致：complete
3. 实现方案 1（签名 → 症状码），补回归（不调真实模型）：complete
4. 实现方案 2（部件 → 品类线索，配置化），补回归：complete
5. make lint、相关测试、实机重放 9db 场景：complete（ci-local 见 progress.md）

## 边界

- 不改 evidence-next-action 的决策：图片品类只是线索，必须向用户显式确认。
- 不改 vision 提示词与模型调用；只改确定性映射层与状态写入。
- 不动历史会话、不做数据迁移。

## 决策

- 签名写成 `kind=symptom` 事实而不是改三处过滤；用 `plans.yaml` 的 `symptom_codes`；不强制安全停机计划排前。理由见 findings.md §3。

## Errors

- 实机 smoke 先跑到无图的症状多选场景就挂：模型没把「效果不好」解析成判别题回答（与本次无关，旧断言过严）。
  scratch 副本里去掉该段只跑图片场景，未改规划目录里的原脚本。
