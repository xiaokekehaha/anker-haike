# 官方 63 单复测 P0：诉求、故障对象、售后承诺三处约束

来源：`docs/planning/2026-10-10-1321_official-63-continuation/ambiguities.md` 的 A24、A22/A28、A16/A25。三项都直接对应比赛指标（意图准确率、幻觉为 0、SOP 过保委婉拒绝）。

## 1. 不替客户加退款诉求（A24：T53 / B15，R05 不稳定）

问题：T53 原文「I hope I can get a replacement or you can fix it」，模型输出 replacement → refund → report_problem，客户看到「按顺序处理：换货 → 退款 → 排障」。同一原文 R05 没有退款，属于模型随机性。

方案：`request_constraints.ground_refund` 在 `constrain_requests` 入口执行。退款与其他诉求并列、且原文没有退款词（refund / money back / return it / 退款 / terugbetaling 等）时去掉 refund_request；退款是唯一诉求时不动。

## 2. 不替客户选故障对象（A22 / A28：T50、B10）

问题：T50 原文只有「the left one does work」。抽取把它标成 affirmed 症状；候选方案 bp-0020 走 needs_confirmation，由模型自拟追问「Does the right pump hub produce any suction…」，B10 更问成「右侧有吸力而左侧没有？」。现有 polarity_uncertain 模板只在模型把该症状列进 supported_symptoms 时触发。

方案：

- `interpret.normal_operation_is_uncertain`：引文是「does work / works fine」且无否定词的症状改为 uncertain（主抽取与表单补抽两条路径都过）。
- `synthesize.filter_hypotheses`：没有错误码、且全部症状都是 uncertain 时，每个候选都走 polarity_uncertain 固定追问「Which side or part has the problem, and what exactly is it doing?」，不用模型自拟问题。有确定症状时行为不变。

## 3. 排障卡不做售后承诺（A16 / A25：T36、T53）

问题：官方 Q&A 有 12 句承诺夹在排障段落里（rv-0341「we will send you a suitable replacement unit」、bp-0114「Please provide your shipping address so that we can replace the device」等）。卡片原样发出时还没核保；T53 已按过保拒绝，第五卡仍索地址换机，与 SOP「过保委婉拒绝」矛盾。

方案：`plans.qa.customer_text` 在渲染层删去含承诺的分句，并补一句「Whether a replacement or part can be sent depends on a warranty check.」。`qa.yaml` 是生成文件，原文与证据不改。步骤卡正文、说明段落、暂停时的步骤复述三处改用 `customer_text`。

## 测试

`orchestrator/tests/test_customer_scope_guards.py`：T53 退款、显式退款保留（英 / 荷）、does work 极性、T50 追问不含 right、确定症状时保留模型追问、T36 / T53 卡文、全量官方步骤渲染无承诺句。

未做：63 单真实回放复测（需真实模型，按用户要求再跑）。
