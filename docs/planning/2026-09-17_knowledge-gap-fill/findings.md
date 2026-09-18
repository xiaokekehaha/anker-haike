# 固定处理流程复核记录（config/plans.yaml）

复核对象：改动前的 32 条预写排障计划。逐条看 `symptom_codes` 覆盖、`next_on` 三态去向、安全停用条目与证据来源。

## 1. 症状登记了、计划不存在（已修）

`symptom_taxonomy` 里登记的症状码必须至少有一条同品类计划，否则用户答完问诊仍然只能 R5。实测缺口：

| 品类 | 症状码 | 表现 |
| --- | --- | --- |
| robot_vacuum | `water_leak` | 「漏水」识别成功 → 无计划 → R5 |
| robot_vacuum | `mop_failure` | 「拖布不湿」识别成功 → 无计划 → R5 |
| robot_vacuum | `navigation_failure` | 「回不去基站」识别成功 → 无计划 → R5 |
| robot_vacuum | `app_connection` | 「配网失败」识别成功 → 无计划 → R5，尽管 `official_x10_wifi` 早已入库 |
| headphones | 整个品类 | 无词表、无计划、无故障卡；`official_spaceone_*` 两篇资料检索得到但排障用不上 |

修法：新增 6 条扫地机型号级计划 + 13 条头戴耳机型号级计划，并补 `headphones` 词表与两张 SKU 故障卡。
`tests/test_plans.py::test_every_registered_symptom_code_has_a_plan` 固化为断言，缺口再出现即红。

## 2. `cannot_do` 过早升级（已修）

`cannot_do` 的语义是「这一步我做不了」，不是「整条路走不通」。改动前有 10 处把它直接指向 `EXHAUSTED`，
而后续步骤并不依赖同一前提，等于把用户做得到的检查一起跳过：

| 计划 | 步骤 | 做不到的是 | 被跳过的下一步 |
| --- | --- | --- | --- |
| `rv_suction_hair_wrap` | s2 | 清洁滤网 | s3 检查吸口异物 |
| `pb_port_debris` | s2 | 换线换设备 | s3 长按电源键复位 |
| `pb_input_check` | s1 | 换充电器与线 | s2 静置 30 分钟观察指示灯 |
| `chg_cable_port_check` | s2 | 换插座换设备 | s3 确认插脚插紧 |
| `eb_charging_contacts` | s2 | 重新放回充电盒 | s3 先给充电盒充电 30 分钟 |
| `eb_reset_pair` | s1 | 删除记录并重置 | s2 重新配对 |
| `eb_anc_touch_app` | s1 | 更新固件 | s2 更换耳塞套重做佩戴检测 |
| `spk_power_reset` | s1 | 充电 30 分钟 | s2 长按电源键强制重启 |
| `bp_power_check` | s1 | 充电 30 分钟 | s2 检查充电口与线材 |
| `bp_valve_membrane` | s2 | 检查喇叭罩贴合 | s3 清洗晾干后重新组装 |

规则写进 plans.yaml 头部：**只有后续步骤都依赖同一前提（同一部件、同一现场条件）时才直达 EXHAUSTED**。

保持 `EXHAUSTED` 不改的（后续步骤依赖同一前提）：`rv_suction_filter_clog` s1、`rv_suction_dustbin_full` s1、
`rv_suction_side_brush` s1（都要动同一个部件）、`rv_power_supply` s1/s2、`cam_offline_reconnect` s2（都要在设备旁操作）。

副作用：连续三次 `cannot_do` 现在会先撞上 CP-verify 的 R1b 限额（skipped ≥ 3）再转人工，而不是第二次就切计划。
两种路径给用户的尝试次数一样，但留在同一条计划里更连贯。相关断言已更新。

## 3. 异响一律安全停用（已修）

`abnormal_noise` 改动前只有 `rv_suction_motor_fault` 一条计划，且三态全部指向 `EXHAUSTED`。
结果是用户说「扫地机声音很大」立即被判为「关机停用、等待人工」，而 `faq_rv#q7` 明写吸口异物就会让噪音变大。

修法：
- 新增 `rv_noise_obstruction`（品类通用，吸口 → 滚刷 → 边刷）与 `rv_x10_loud_noise`（X10 官方资料）。
- `rv_suction_motor_fault` 保留不动，故障卡里它的 keywords 收窄为 `焦味 / 过热 / 冒烟 / 烧焦`，`异响` 交给排查计划。
- 真正的安全路径不依赖故障卡：`config/rules/safety_terms.yaml` 的 R4 覆盖冒烟、烧焦、焦味、鼓包等词，在排障之前生效。

## 4. 误报与不录像共用一条计划（已修）

`cam_detection_tune` 原本同时声明 `cam_no_recording` 与 `cam_false_alarm`，第二步是「检查手机通知权限」。
对「误报频繁」来说这一步方向相反——用户要的是少收通知。已拆出单步计划 `cam_false_alarm_tune`（缩小活动区域、降低灵敏度），
`cam_detection_tune` 版本升到 2 并只保留 `cam_no_recording`。

## 5. 地图丢失混在导航异常里（已修）

`rv_map_lost` 引用的官方资料讲的是「App 首页看不到已保存地图」。若它声明 `navigation_failure`，
X9 用户说「找不到基站」会被推给地图计划，而我们对 X9 并没有回基站的资料。
已在词表中拆出 `map_lost` 故障族（`地图没了 / 地图丢了 / 地图不见 / 地图没保存 / 地图被删`），
`地图乱了` 留在导航异常（金标 `symptom-28` 不变）。

## 6. 复核后判定「合理、不改」的项

- **安全停用计划的 `solved` 去向不一致**：`pb_overheat_stop` / `chg_overheat_stop` / `rv_suction_motor_fault` 用 `EXHAUSTED`，
  `spk_water_stop` 用 `DONE`。这是有依据的区分：电池鼓包、焦味、过热属不可逆风险，用户自称好了也应转人工；
  进水晾干后恢复正常是可验证的结果。规则已写进 plans.yaml 头部注释，不再靠读者猜。
- **单步计划**（`cam_doorbell_chime`、`chg_indicator_check`、`hd_q45_power_failure` 等）：资料本身只有一组操作，
  硬凑第二步会引入没有来源的步骤。保留单步。

## 7. 已知边界（本轮没做）

- `hd_anc_failure` 只有 Space Q45 有计划，Space One 官方站没有对应的「降噪效果差」文章；A3035 用户问降噪仍走 R5。
- 扫地机新计划只覆盖 X10 Pro Omni（地图丢失额外覆盖 X9 Pro）。其余机型的漏水 / 拖地 / 导航仍是 R5，
  因为官方文章按型号发布，品类通用计划不能借用型号资料。
- `replay/` 下 9 个录制包在本轮之前就与当前 prompt / models / kb 版本不兼容（recorded interpret=2026-09-14.8、
  models=2026-09-13.5、kb=2026-09-12.1），本轮没有重录，重录需要真实模型调用。
