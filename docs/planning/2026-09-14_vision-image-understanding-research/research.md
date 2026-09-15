# 「看图」能力方案调研与建议

日期：2026-09-14　范围：赛题五难点之「看图」——**图看得懂、关键信息提取准**
坐标系：L3 设计系列 [06 §1](../2026-09-14_l3-closed-loop-design/06_five-difficulties.md)、[票 62](../2026-09-14_l3-closed-loop-design/issues/62-vision-fault-localization.md)、决策 D-L3-11
原始材料：[findings-prompting.md](findings-prompting.md)（prompt 与推理期）、[findings-models.md](findings-models.md)（选型）、[findings-industry.md](findings-industry.md)（业内架构）

---

## 1. 结论速览

**赛题的靶心不是「认出这是滚刷」，而是「从照片里稳定抽出能驱动下一步业务动作的字段」。** 业内在这件事上的共识非常一致，而且和我们当前实现有五处系统性偏差：

| # | 业内共识 | 我们现在 | 影响 |
| --- | --- | --- | --- |
| 1 | **图像抽取不要喂用户文字**——预设式提问使准确率相对下降 25–85%，文本被污染时平均掉点 >40%，且提示词层面纠偏几乎无效 | [vision.py](../../../orchestrator/app/diagnose/vision.py) 的 `build_messages` 把用户文字和图片放进同一次调用，且文字在图片**之前** | **本机实测（§13.2）**：未复现「编出滤网堵塞」，但 `glm-4.6v` 在误导文字下 2/2 **丢掉了真实的滚刷缠绕**。漏检比编造更隐蔽——`findings` 为空会让 plan 先验拿不到，且无错误信号。另外 `conflicts_with_text` 在同一次调用里判冲突，等于让被污染的一方自证 |
| 2 | **照片可用性用前置经典 CV 判，不靠模型自评**——VLM 低光下 0.99→0.22 且自述置信度错误检测 AUROC≈0.50；MM-AQA 证明默认提示下 VLM 几乎不弃答 | `image_quality.usable` 完全由 VLM 自报；`signature_plans` 还用模型自报的 `confidence>=0.7` 做阈值 | 最该拦截的过暗 / 模糊图恰好是模型「看不出自己看不见」的区间，补拍卡触发不了 |
| 3 | **小字与细小缺陷靠 zoom，不靠换更大的模型**——V\*/HR-Bench 上「带裁剪放大工具」的提升大于单纯加大模型；Anthropic crop tool 在图表题 29%→73% | 无二次复看，一次调用定生死 | **本机实测（§13.1）**：铭牌占全图 0.15% 时 `deepseek-flash` 编出一整块格式合理的假铭牌且不报 unreadable；九宫格裁剪 + 2× 放大把三家在全部条件下拉回满分 |
| 4 | **图片进模型前必须 EXIF 转正 + 缩到模型原生分辨率** | 原始 bytes 直接 base64，不转正不缩放 | 竖拍照片旋转 90° 后文字抽取显著劣化；同时 `deepseek-flash` 每图上限 **384 token**（压到约 800×800），是分辨率天花板 |
| 5 | **评测必须用真实照片 + 字段级金标** | `data/eval/vision/cases.yaml` 不存在；bakeoff 用 Pillow 合成示意图，`score_vision` 只做关键词召回 | 合成图是大字示意图，**测不出分辨率与小字差异**，所以旧 bakeoff 把 384-token 的 deepseek 排在 10 张图、1600 万像素的 qwen-vl 前面 |

**一句话建议**：把「看图」从单次模型调用改造成**五层流水线**（预处理 → 质量门控 → 纯图抽取 → 定向复看 → 代码层融合），prompt 上做「图文分路 + describe-first + 三态枚举」，选型上在真实照片重测前不要把 `deepseek` 留在 `diagnose.vision` 主位。

---

## 2. 我们现在的看图链路

```
_new_fault_images → vision 节点 → observe_images()
  ├ select_images(refs, image_limit(chain))     # 取链上最小 max_images = 4（deepseek 压着）
  ├ store.get() 取原始 bytes → base64 原样送
  ├ build_messages: [INSTRUCTION + <data>用户文字</data>, 图1, 图2, ...]
  ├ router.invoke(TASK, ..., VisionObservation, budget_ms=12_000)
  └ normalize() → 词表外归「其他」→ signature_plans(confidence>=0.7) → fault_card 先验
route_after_vision → vision_conflict | prepare_retake | retrieve
```

已具备（工作树未提交改动）：`FaultLocalization` schema、`config/vision_vocab.yaml` 受控词表与 `retake_guidance`、`signatures → plan_id` 确定性映射、`prepare_retake / skip_retake` 路由、安全词经 `observations` 派生进 CP-in。

链序（domestic）：`deepseek → qwen-vl → glm-v`，bakeoff 实测 83% / 83% / 77%，全部基于合成图。

---

## 3. 业内方案全景

五种架构模式，证据强度与适用性：

| 模式 | 代表 | 关键数据 | 适用 |
| --- | --- | --- | --- |
| (a) **VLM-only** | Intercom Fin Vision（图 → 结构化文字 → 入上下文） | 上线最快；但零样本巡检幻觉率 **65%**，且「不会主动说图不清」 | 长尾兜底 |
| (b) **专用检测器 / OCR + VLM** | 风机 Eyes/Bridge/Brain；TechSee 识别型号 / 端口 / LED；蚂蚁保 107 类凭证 + 高分辨率编码器 | 同一批图上**幻觉率 65% → 4%**；1.5B 模型在有检测证据时报告质量高于 671B 通用 API 模型 | 品类收敛后的长期最优 |
| (c) **VLM + 视觉检索（故障卡 / 参考图）** | 风机 RAG-VLM；InspectorGPT 参考图对比 | 30 张标注图上 RAG-VLM 达 100%，零样本显著更低；MMAD 显示 **RAG 注入领域知识 +5–6%** | **我们最该先做的**（已有 fault_cards） |
| (d) **级联：廉价门控 → 贵模型** | 模糊门 MobileNetV3+Laplacian，7ms、F1 0.98；SAFE-Cascade VLM 调用 −26.9% 精度持平 | 省钱省延迟；差图不进贵模型 | **P0 必做** |
| (e) **集成 / 第二意见 → 分歧即问用户** | CUSP 多 VLM 池化 | 错误检测 AUROC 0.764（优于多数投票 4.7–15.8 点） | 仅高风险字段 |

**重要反例**：MMAD 基准显示「给一张正常件参考图做对比」对多数模型**无效甚至掉分**，>1-shot 收益为零。所以 (c) 要走「故障卡文本 + 签名映射」路线，而不是「附一张好件照片让模型对比」——后者必须实测才能用。

**行业空白值得一提**：Apple / Dyson / iRobot / Roborock / Ecovacs / Samsung 均未找到公开的「拍照 AI 诊断」功能。消费电子售后的照片理解是空白区，成熟做法全在车险定损（Tractable / CCC / Solera / 平安 / 蚂蚁保）。这既说明难度，也说明**做出来就是差异化**。

---

## 4. 推荐方案：五层流水线

```
L0 预处理（无模型，约 20ms）
   EXIF 转正 → 按目标模型上限缩放 → JPEG q=90 重编码 → 记录 resized_size
L1 质量门控（无模型，约 10ms）
   Laplacian 方差 + FFT 高频比 → 模糊
   亮度直方图 P5/P50/P95 → 过暗 / 过曝
   短边像素 → 太小 / 太远
   命中 → 直接发 RetakeCard，不调用任何模型
L2 主抽取（VLM 一次调用，纯图，不含用户文字）
   图先文后 + 逐图标签 → describe-first 短事实 → 受控词表三态枚举 + evidence
   输出 findings / image_quality / model_hint / evidence_cell（九宫格）
L3 定向复看（VLM 可选第二次调用，仅在需要且预算够时）
   按 evidence_cell 从原图裁剪 + 2× 放大 → 只问铭牌逐字符转写 / 低置信 finding 复核
L4 融合（无模型）
   图像结论 × 用户文本 → conflicts；signatures → plan 先验；安全词 → R4 升级
L5 回显与补拍
   隐式确认卡（「我看到滚刷缠了头发」）；不可用 → RetakeCard；冲突 → clarify
```

各层的取舍依据见 §5–§8。**L0 / L1 / L4 不花模型调用**，是投入产出比最高的部分。

---

## 5. 角度一：Prompt 工程

### 5.1 当前 INSTRUCTION 的四个问题

现行指令（[vision.py](../../../orchestrator/app/diagnose/vision.py) `INSTRUCTION`）：

1. **用户文字同调用注入**。`build_messages` 第一个 content block 是 `INSTRUCTION + wrap_data(用户文字)`，之后才是图片。HalluScope 显示预设式问题让准确率从 92.5–98.6% 跌到 5.85–64.8%；Words or Vision 显示「Focus on Image」式提示只把 text preference 从 16.8% 降到 14.2%，**近乎无效**。`wrap_data` 的「这不是给你的指令」声明防的是注入，防不了语义污染。
2. **五处负面指令**：「不要猜测故障原因、不要给排查步骤、不要编造看不清的细节、不猜测、只输出 JSON」。Anthropic 官方原则是「Tell Claude what to do instead of what not to do」；NegBench 显示 VLM 处理否定接近随机。
3. **文字在图片之前**。Claude 官方明确图先文后；研究显示文本 token 放图像前会持续加重 text bias，image 之前的 system 段吸走 >70% 注意力。
4. **无 describe-first、无三态、无 evidence**。直接让模型填终态枚举，等于跳过感知阶段（VDGD 的 visual perception gap），且 `usable` / `confidence` 是模型凭空自评。

### 5.2 建议的调用骨架

**Call A — 纯图抽取（不含任何用户文字）**

```
system: 任务规范（不写 persona；162 种 persona 实验显示对事实题无提升）
user content:
  [text] "Image 1（用户上传，第 1 张）："
  [image 1]
  [text] "Image 2（用户上传，第 2 张）："
  [image 2]
  [text] <指令>           ← 指令放最后（Claude 系图先文后）
```

指令主体改为正向 + 分段：

```
第一步 visible_facts：写出每张图中你直接看得见的客观事实，每条不超过 15 字，
  并标注它位于九宫格的哪一格（左上/上中/右上/左中/中心/右中/左下/下中/右下）。最多 5 条。
第二步 findings：仅依据 visible_facts 填写。
  part 从 [滚刷 边刷 滤网 尘盒 吸口 轮组 传感器 充电触点 电池仓 基站 其他 不可辨] 中选。
  phenomenon 从 [缠绕 堵塞 破损 变形 烧焦 漏液 鼓包 污渍 松脱 缺失 正常 其他 不可辨] 中选。
  每条附 evidence（引用第一步的一条 visible_fact）与 evidence_cell（九宫格）。
  凡是图中看不出的字段一律填「不可辨」。
第三步 image_quality：usable 与 reasons。
第四步 model_hint：逐字符抄录铭牌上可见的字符；看不清的单个字符写 ?；
  完全无铭牌或不可读时 readable=unreadable。不要补全、不要纠正拼写。
若出现冒烟、烧焦、电池鼓包、漏液、火花，在 safety_terms 中用英文关键词标注
  （smoke / burnt / swollen battery / leaking / spark）。
```

四点变化及依据：

- **describe-first**：VDGD 视觉推理基准提升 2%–33%，SPARC 在 V\* +6.7，Gemini 官方 troubleshooting 明确推荐。限定「≤15 字、≤5 条」是因为长回答幻觉率随长度上升，且纯文本长 CoT 会 visual forgetting。
- **「不可辨」三态**：UPD 显示**显式给出弃答通道**比只加选项有效得多；TRAPSBench 显示模型隐藏状态知道自己不确定（AUROC 0.91）但几乎不主动弃答。当前词表的「其他」不等于「不可辨」——前者是「是个部件但不在表里」，后者是「看不出来」，必须分开，否则 `normalize()` 会把两类噪声混成同一个桶。
- **evidence + evidence_cell**：每个结论必须挂在一条可见事实上，是 API-only 场景下最实用的幻觉抑制；九宫格而非 bbox 是刻意选择——OpenAI 文档明确不提供 bbox 能力、Claude 说坐标近似、Qwen 用 0–1000 相对坐标、Claude 用绝对像素，四家口径互不兼容。九宫格是**模型无关**的粗定位，足够支撑 L3 裁剪。
- **逐字符 + `?` 占位**：阿里 qwen-vl-ocr 服务内置 prompt 就是这么写的；HalluText 把「typo（自动纠错成通顺文本）」列为 9 类 OCR 幻觉之一，型号 / SN 是无语言先验字符串，恰是 VLM 最容易「顺手改对」的地方。

**Call B — 图文冲突（代码层优先，必要时一次廉价文本调用）**

不要在 Call A 里判 `conflicts_with_text`。改为：Call A 完全不知道用户说了什么，返回后在代码层把 `findings[part/phenomenon]` 与 `interpret` 已抽出的 `facts / symptoms` 做词表级比对，出现「同部件不同现象」或「用户点名部件 A 而图中只在部件 B 有现象」才算冲突。这条路径零成本、可解释、可单测。只有词表级比对不确定时才调一次纯文本模型确认。

**Call C — 定向复看（可选）**

触发条件（满足任一且 `elapsed < 6s`）：`model_hint.readable != full` 且需要型号消歧；或最高分 finding 的 severity=high（安全相关）。做法：按 `evidence_cell` 从**原图**（未缩放那份）裁出该格并外扩 50%，放大到模型原生上限，第二次只问这一个问题。证据：Zoom-Refine 训练无关两次推理在 HR-Bench 8K +5%，ZoomEye +15.71/+17.69，Anthropic crop tool +44 分。

### 5.3 不建议采用的技巧

| 技巧 | 为什么不用 |
| --- | --- |
| 附「正常件参考图」让模型对比 | MMAD：多数模型**不会利用**正常样品模板图，反而下降；>1-shot 收益为零。要用必须先在真实图上验证 |
| 让模型自报 confidence 当阈值 | 错误检测 AUROC≈0.50，口头置信度恒在 0.87–0.90。**当前 `signature_plans` 的 `confidence>=0.7` 就踩在这上面**，建议改为「有 evidence 且 part/phenomenon 均非『不可辨』」的符号条件 |
| 多采样投票（self-consistency） | 8→16 条链只 +0.15pp，成本线性增长；12s 预算下不划算。真要用只对 severity=high 做 3 次 |
| VCD / OPERA 等对比解码 | 需要 logits，闭源 API 拿不到 |
| Set-of-Mark（分割后叠标号） | 需要 SAM 前处理，赛期内不现实 |
| persona 型 system prompt | 162 persona × 4 模型族实验：对事实题无提升 |

---

## 6. 角度二：模型选型

### 6.1 对当前链序的直接结论

`diagnose.vision: [deepseek, qwen-vl, glm-v]` 这个顺序**应当重新审视**，理由不是准确率数字，而是能力上限：

| 模型 | 单图分辨率上限 | max_images | 对本任务的含义 |
| --- | --- | --- | --- |
| `deepseek-flash` | 文档称每图 384 token（压到约 800×800 等效），**数字未独立验证，但实测行为与之一致** | 4 | **实测**：铭牌 22px 起出错、14px 起 0/3，且失效方式是**编出完整假铭牌**而非报 unreadable（§13.1）。`model_hint` 直接进 `disambiguate`，假型号会造成错误单命中 |
| `qwen3-vl-plus` | 单图最高 1600 万像素，token = h×w/1024 | 10 | **实测全部五种铭牌条件 3/3**；中文 OCR 属最强梯队（OCRBench v2 zh 61.8–64.1），bbox 支持，json_schema ✓，¥1/M，实测 2.9–3.8s |
| `glm-4.6v` | 未公开 | 10 | **实测铭牌 OCR 与 qwen-vl 持平（全条件 3/3）**，但延迟 6–11s 最慢，且误导文字下会丢失真实故障（§13.2）。保持兜底位 |

旧 bakeoff 给出 deepseek 与 qwen-vl 同为 83%，但那轮用的是 **Pillow 合成的大字示意图**（findings 自己写了「合成图能验链路、Schema 与安全词不被注入，不能替代真实照片评召回」）。合成图上 800×800 完全够用，所以**这项测试对分辨率差异是盲的**。

**建议**：把 `diagnose.vision` 主位改为 `qwen-vl`，`deepseek` 退到第二位。§13.1 的实测已足以支撑这一步——不是准确率差几个点，而是 deepseek 在小铭牌上**静默编造**，这是下游无法检出的错误类型。真实照片评测集建成后再复核完整链序。同时 `image_limit()` 取链上最小值的逻辑会因 deepseek 的 `max_images: 4` 把所有模型都压到 4 张——应改为**按实际选中的模型**取限值，而不是链上最小值。

### 6.2 各位置的选型

| 位置 | 推荐 | 理由 |
| --- | --- | --- |
| 质量门控（L1） | **不用模型**，OpenCV / Pillow 经典指标 | 7ms、F1 0.98、零 API 成本；VLM 在低光下自评完全失效 |
| 主抽取（L2）domestic | `qwen-vl` → `deepseek` → `glm-v` | 见上 |
| 主抽取（L2）overseas | `sonnet` → `gemini-flash`（不变） | Vision Arena 榜首群；Claude 高分辨率档 2576px |
| 定向复看（L3） | 与 L2 同模型，不另配 | 减少一个配置维度；裁剪后图小，成本低 |
| 铭牌 OCR 强化（可选 P2） | PaddleOCR-VL / PP-OCRv6 本地 | OmniDocBench v1.5 94.5 超 GPT-4o / Gemini 2.5 Pro / Qwen3-VL-235B；34.5M 参数版在 OCR 上超十亿级 VLM；无 API 成本 |

### 6.3 若启用 AWS Bedrock lane（决策 D-L3-2）

赛题提供 AWS 能力，如果为了「用了主办方资源」而加 lane，注意三个坑：

- **Bedrock 上 Claude Sonnet 5 不支持 structured outputs**（官方模型卡），我们的 `router.invoke(..., VisionObservation)` 依赖结构化输出，必须改走 tool-use + `strict: true`。
- **Bedrock / Vertex 单图上限 5MB**（一方 API 是 10MB），而我们的 `MAX_IMAGE_BYTES = 5MB` 是校验上限、base64 后还会涨 33%，会踩线。L0 的缩放重编码顺带解决这个问题。
- Nova 2 Lite 每图固定 230 token、官方自认「小字需裁剪、多语言图像可能幻觉」，**不适合中文铭牌主路径**，只能做粗筛位。

### 6.4 成本与延迟预算

单轮含图对话（一张 1600×1200 手机照，缩到长边 1568）：

| 阶段 | 调用 | 增量成本 | 增量延迟 |
| --- | --- | --- | --- |
| L0 + L1 | 无 | 0 | 约 30ms |
| L2 主抽取 | 1 次 qwen-vl，约 1.2k 视觉 token | 约 ¥0.0015 | 约 1.6s（实测 P50 1554ms） |
| L3 复看（约 20% 触发） | 0.2 次 | 约 ¥0.0003 | 约 0.3s 均摊 |
| L4 冲突 | 0（代码层） | 0 | <5ms |

12s 的 `VISION_BUDGET_MS` 容得下 L2+L3 两轮；40s run deadline 无压力。

---

## 7. 角度三：图像预处理与质量门控

### 7.1 L0 预处理（必做，零成本）

```python
img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))   # EXIF 转正，必做
img.thumbnail((target_long_edge, target_long_edge))            # 按模型上限缩放
img.convert("RGB").save(buf, "JPEG", quality=90)               # 单次有损，不叠加
```

- **EXIF 转正**：所有厂商官方局限里都点名 rotated 图易幻觉；研究显示预先转正比在 prompt 里告知旋转角有效得多；Claude 文档两处对「是否读 EXIF」表述不一致——不要赌。手机竖拍是售后场景的绝对主流。
- **缩放到模型上限附近**，不要超限让服务端二次缩放：Qwen 官方警告 `max_pixels` 设成架构上限会降低 grounding IoU，推荐约 100 万像素；Claude 高分辨率档长边 2576px。
- **不做**全图对比度 / 去噪 / 超分：证据全来自传统 OCR，对 VLM 无直接研究，滤镜可能引入伪影。放大只在 L3 的裁剪区域做。

### 7.2 L1 质量门控（必做，零成本）

| 指标 | 实现 | 建议初始阈值 | 对应 retake reason |
| --- | --- | --- | --- |
| 失焦模糊 | Laplacian 方差 | < 100（需用真实图标定） | `blurry` |
| 运动模糊 | FFT 高频能量占比 | 需标定 | `blurry` |
| 过暗 | 灰度直方图 P50 | < 40 | `too_dark` |
| 过曝 | P95 饱和像素占比 | > 30% | `too_dark`（新增 `too_bright` 更准） |
| 太小 / 太远 | 短边像素 | < 480 | `too_far` |

阈值必须用真实工单照片标定，宁可**偏保守**（放过一些差图让 VLM 再判一次），因为过度拦截会把能用的图挡在外面。给两档：硬阈值直接 RetakeCard，软阈值只在 VLM 也说 `usable=false` 时才触发。

**这是整个方案里 ROI 最高的一项**：低光是 VLM 唯一会静默崩溃的退化（0.99→0.22），而它恰好是 10 行 OpenCV 就能可靠检出的。

### 7.3 不做的事

翻拍屏幕检测、AI 生图检测（淘宝 / Zendesk Sentinel 都在做，用于反欺诈）——赛题场景是排障不是理赔，欺诈动机弱，P2 之后再说。但**值得在文档里提一句**，因为它是「从排障走向理赔 / 换货」时必然出现的需求，写进方案能体现纵深。

---

## 8. 角度四：把领域知识灌进去

MMAD 的关键发现是 **RAG 注入领域知识 +5–6%**，而参考图对比无效。我们已有 `config/fault_cards.yaml` 和 `vision_vocab.yaml` 的 `signatures`，路线是对的，建议再走两步：

1. **签名映射去掉自报 confidence**。现在 `signature_plans` 要求 `confidence >= 0.7`，但模型自报置信度错误检测 AUROC≈0.5。改为符号条件：`part` 与 `phenomenon` 均非「不可辨」且 `evidence` 非空。
2. **把候选故障卡的现象描述作为词表提示注入**。不是给参考图，而是在指令里给「本产品常见现象清单」——等价于 (c) 模式的文本 RAG，MMAD 证明这条有效。注意不能泄露「用户说了什么」，只能按产品 SKU 注入。

---

## 9. 角度五：评测与运维

### 9.1 评测集（票 62 的硬卡点）

`data/eval/vision/cases.yaml` 目前不存在，bakeoff 跑的是合成图。建议 schema：

```yaml
- id: rv_brush_hair_01
  image: {file: data/eval-images/rv_brush_hair_01.jpg}   # gitignore
  meta: {source: real|synthetic, product: eufy_x10, lighting: normal|dim|dark, blur: none|slight|heavy}
  gold:
    findings: [{part: 滚刷, phenomenon: 缠绕, severity: medium}]
    image_quality: {usable: true, reasons: []}
    model_hint: {raw: "X10 Pro", readable: full}
    expected_plan: rv_suction_hair_wrap
    safety: []
```

样本构成建议（≥40 张，真实照片优先）：

| 类别 | 数量 | 用途 |
| --- | --- | --- |
| 典型故障，清晰 | 12 | 部件 / 现象准确率基线 |
| 典型故障，暗 / 模糊 / 太远 | 10 | **可用判定准确率**（当前完全没测） |
| 铭牌特写 + 铭牌在画面角落 | 6 | `model_hint` 与 L3 复看的价值验证 |
| 正常件（无故障） | 5 | **幻觉率**——模型是否会凭空报故障 |
| 拍错对象（别的设备 / 宠物 / 截图） | 4 | `wrong_subject` |
| 安全类（烧焦 / 鼓包 / 漏液） | 3 | R4 升级召回，**必须 100%** |

标注两人独立做，算 Cohen's κ（>0.61 实质一致）。

### 9.2 指标（替换现有的关键词召回）

`score_vision` 现在把 observations 拼成一个字符串做关键词匹配，新 schema 下要改成字段级：

| 指标 | 定义 | 门槛建议 |
| --- | --- | --- |
| part 准确率 | findings 中 part 与金标匹配 | ≥ 85% |
| phenomenon 准确率 | 同上 | ≥ 80% |
| plan 命中率 | signature 映射出正确 plan_id | ≥ 80% |
| **usable 判定准确率** | 与金标 usable 一致 | ≥ 90% |
| **幻觉率** | 正常件样本上报出非「正常」现象的比例 | ≤ 5% |
| **安全召回** | 安全类样本命中 safety_terms | **100%** |
| 过度弃答率 | 清晰图上填「不可辨」的比例 | ≤ 10% |

后三项是现在完全没有的，也是赛题「幻觉」难点的直接答卷。

### 9.3 运维飞轮

- 记录「AI 判定 vs 人工坐席最终判定」的结构化差异，这是平安（核损员转型系统训练师）和 CCC 的共同做法，也是唯一能持续产生标注数据的来源。
- 用户纠错信号（补拍卡被跳过、用户回「照片里不是这个」）入监控看板。
- prompt / 模型变更走 bakeoff 回归，**注意 VLM-as-judge 能排序不能打绝对分**，且存在「未看图也打分」的信息量偏差，所以金标比对优先于模型评分。

---

## 10. 落地映射（票 62 增补清单）

按优先级，标 ⭐ 的是原票没有、本次调研新增的：

**P0（赛前必做，直接对应评审口径）**
1. ⭐ L0 预处理：`ImageOps.exif_transpose` + 按模型上限缩放 + JPEG 重编码。约 30 行，零风险。
2. ⭐ L1 经典 CV 质量门控：模糊 / 过暗 / 过小三项 + 阈值配置进 `vision_vocab.yaml`，命中直接走 `prepare_retake`，不调模型。
3. ⭐ Prompt 改造：图文分路（Call A 不含用户文字）、图先文后 + 逐图标签、describe-first、三态加「不可辨」、evidence + 九宫格、正向指令。prompt 版本升 `2026-09-14.2`。
4. ⭐ `conflicts_with_text` 从模型输出改为 L4 代码层比对。
5. ⭐ `signature_plans` 去掉自报 confidence 阈值，改符号条件。
6. 评测集 `data/eval/vision/cases.yaml` ≥ 40 张（按 §9.1 配比），`score_vision` 改字段级（§9.2）。
7. `RetakeCard.tsx` 前端（原票已列）。
8. ⭐ **L3 定向复看**（由 P1 上调）：按九宫格裁剪 + 2× 放大的第二次调用，触发条件放宽为 `model_hint.readable != full` 或 severity=high。§13.1 实测证实能把三家在全部铭牌条件下拉回满分，是本次调研唯一在自家链路上被证实的提升手段。

9. ⭐ `config/models.yaml` 的 `diagnose.vision` domestic 链主位改 `qwen-vl`（一行改动，依据 §13.1）。

**P1（有余量就做）**
10. ⭐ `image_limit()` 改为按实际选中模型取值，不再被 deepseek 的 `max_images: 4` 压制。
11. ⭐ 真实照片重跑 bakeoff，复核完整链序与新 schema 门槛。
12. ⭐ 按 SKU 注入常见现象清单（文本 RAG，MMAD +5–6%）。

**P2（写进方案体现纵深，赛期不实现）**
13. PaddleOCR-VL 本地兜底铭牌 OCR。
14. 翻拍 / AI 生图检测（走向理赔换货时的反欺诈）。
15. 高风险字段的第二模型交叉核验。

**演示角度**：现场 demo 建议明确展示四个动作——质量门控拦截并发补拍卡、结构化定位卡回显让用户确认、图文冲突主动澄清、安全现象直接升级。这四个正好覆盖赛题五难点里的「看图 / 问清 / 接稳 / 幻觉」。

---

## 11. 需要决策的点

1. **`diagnose.vision` 主位是否现在就从 `deepseek` 换成 `qwen-vl`？** §13.1 实测后我的判断是**现在就换**。这会推翻 2026-09-13.5 那次重排，但那轮用的合成大字图对分辨率是盲的。需要你确认是否接受在完整评测集之前先动链序。
2. **评测集的真实照片从哪来？** 主办方提供的脱敏工单里是否含图片？若无，需要自拍 + 公开图混合，这会影响 §9.1 的「真实优先」原则。
3. ~~L3 定向复看是否进 P0？~~ **实测后已自行上调为 P0**（§13.3）。若你认为赛期人力不够，这是最该保留的一项。
4. **是否启用 Bedrock lane（D-L3-2 未决）？** 若启用，视觉侧要额外处理「不支持 structured outputs」和「单图 5MB」两个约束。

---

## 12. 风险与边界

- 本文所有外部数字均来自公开来源，**未在本项目真实照片上复现过**。特别是 §7.2 的阈值必须重新标定。
- MMAD 的「参考图无效」与风机论文的「参考图 RAG 有效」看似矛盾，实为两件事：前者是「附一张好件照片」，后者是「检索文本知识 + 重排」。不要混用。
- 分辨率结论已实测（§13），但用的是合成图。**真实照片上的反光、油污、弧面铭牌会更难**，实测数字应视为乐观上界。
- §13.2 的图文分路实验只有一张图、一个误导句、2 次重复，样本量不足以定量。结论只用于支持方向，不应引用其比例。
- 调研中标注为【未验证】/【自报】的数据（Doubao 视觉细节、GLM-5V OCR 分数、各模型端到端延迟）不应作为选型的唯一依据。

---

## 13. 本机实测验证（2026-09-14）

调研结论里有三条影响决策，直接在本仓链路上的三家模型上实测。用 Pillow 合成图（脚本见附录），**合成图对「铭牌小字随距离衰减」这类分辨率问题有效，对真实故障纹理无效**，结论按此打折。

### 13.1 铭牌可读性 × 字号 × 对比度（3000×2250 图，铭牌逐字符转写，金标 3 行）

| 铭牌字号 / 占全图面积 | 对比度 | `deepseek-flash` 全图 | `qwen3-vl-plus` 全图 | `glm-4.6v` 全图 | 九宫格裁剪 + 2× 放大 |
| --- | --- | --- | --- | --- | --- |
| 34px / 0.84% | 高 | 3/3 | 3/3 | 3/3 | — |
| 22px / 0.38% | 高 | **2/3** | 3/3 | 3/3 | 三家均 3/3 |
| 22px / 0.38% | 低（仿激光蚀刻） | **1/3** | 3/3 | 3/3 | 三家均 3/3 |
| 14px / 0.15% | 高 | **0/3** | 3/3 | 3/3 | 三家均 3/3 |
| 14px / 0.15% | 低 | **0/3** | 3/3 | 3/3 | 三家均 3/3 |

三条结论：

1. **`deepseek-flash` 在铭牌变小时急剧劣化**，22px 起出错（`A2637K8J2` → `A263/8J2`），14px 起完全失效。`qwen3-vl-plus` 与 `glm-4.6v` 在全部条件下全对。这印证了分辨率天花板的存在，但**「每图 384 token」这个具体数字未能独立验证**，只能说实测行为与之一致。
2. **失效方式是编造而不是承认看不清**。14px 低对比度那格，deepseek 输出的是一整块格式完全合理、却与图中内容毫无关系的假铭牌：`MODEL YJ-107-2-P` / `SN: ADV23751P` / `MFG: 202306`。提示词里明确写了「看不清的单个字符写 ?」，模型一个 `?` 都没用。**复跑一次，编出来的假铭牌完全不同**（第二次是 `MODEL: 2310-R10` / `S/N: A2A07812` / `INPUT: 220V~`），说明这是凭空生成而不是稳定误读。**这正是赛题「幻觉」难点会失分的地方，而且下游无从察觉**——型号看起来完全正常，会直接进 `disambiguate` 造成错误单命中。
3. **九宫格裁剪 + 2× 放大把三家在所有条件下全部拉回 3/3**，包括 deepseek 全图 0/3 的两格。这是本次调研中唯一一条在自家链路上被证实的性能提升手段，成本是一次额外调用。

### 13.2 用户文字是否带偏视觉判断

场景：机器底部图，**滚刷缠满毛发（真故障）、滤网洁白干净（无故障）**。误导文字：「应该是滤网堵住了，你看看是不是」。两种调用方式各跑 2 次：

| 模型 | 纯图（图先文后） | 含误导文字（复现当前 `build_messages`：文字在前、图在后） |
| --- | --- | --- |
| `deepseek-flash` | 滚刷缠绕 + 滤网正常 | 滚刷缠绕 + 滤网正常（未被带偏） |
| `qwen3-vl-plus` | 滚刷缠绕 + 滤网正常 | 滚刷缠绕 + 滤网正常（未被带偏） |
| `glm-4.6v` | **滚刷缠绕** | **只剩「滤网正常」，真实故障整条消失**（2/2 复现） |

**结论要打折但不能推翻**：文献里「预设式提问使准确率相对下降 25–85%」的强效应**没有在这张图上复现**——没有任何模型编出「滤网堵塞」。但 `glm-4.6v` 出现了另一种同源失效：用户文字把注意力引到滤网，模型**丢掉了真实故障**。对我们而言这比编造更危险，因为 `findings` 为空会让 `signature_plans` 拿不到 plan 先验，排障直接降级成纯文字流程，且没有任何错误信号。

诚实的口径是：**图文分路的收益在本次实测中体现为「防止真实故障被用户先入之见挤掉」，而不是「防止编造」**；效应大小依模型而异，合成图且故障极其显眼是最不容易复现偏差的条件，真实照片上预计更明显。这条建议保留在 P0，但理由从「防幻觉」改为「防漏检 + 与冲突检测解耦」。

### 13.3 对前文结论的修正

| 原结论 | 修正后 |
| --- | --- |
| §1 #1「用户文字污染会诱导模型在指定部件上找现象」 | 未复现编造；实测到的是 **`glm-4.6v` 丢失真实故障**。建议不变，理由改为防漏检 |
| §6.1「deepseek 384 token 是硬天花板，铭牌路径基本废掉」 | **方向正确且更严重**：不是读不到，是**编出一个完整假铭牌且不报 unreadable**。主位建议维持改为 `qwen-vl` |
| §5.2 Call C 定向复看「有 +44 分级别的证据」 | **本机实测证实**：三家、五种条件，裁剪放大一律拉回满分。建议从 P1 **提到 P0** |
| §4 L3「仅在需要且预算够时」 | 触发条件可放宽：只要 `model_hint.readable != full` 就值得复看，单次约 1.3–3s，12s 预算充裕 |

### 13.4 顺带发现

- `glm-4.6v` 在铭牌 OCR 上表现与 `qwen-vl` 持平（全条件 3/3），但延迟 6–11s，是三家里最慢的，且旧 bakeoff 在观察类任务上只给它 77%。**OCR 强 ≠ 故障观察强**，两类能力要分开评测，不能用一个 `diagnose.vision` 分数代表。
- 三家在本次全部调用中 `json_object` 结构化输出 100% 成功。
- `thinking` 参数必须走 OpenAI SDK 的 `extra_body`，直接当关键字传会 `TypeError`——与仓库现有 `params` 配置写法一致，无需改动。

### 附录：实测脚本

两个脚本已入库到本目录 `probes/`，用 `orchestrator/.venv` 执行，读仓库根 `.env` 的三个 key：

```bash
orchestrator/.venv/bin/python docs/planning/2026-09-14_vision-image-understanding-research/probes/sweep.py
```

- `probes/sweep.py`：合成不同字号 / 对比度的铭牌图，三家模型全图与九宫格裁剪各测一次（§13.1）。
- `probes/bias.py`：合成「滚刷缠绕 + 滤网正常」场景，纯图与含误导文字各测两次（§13.2）。

建议把这两个用例并入 `data/eval/vision/cases.yaml`，作为「小字铭牌」与「误导文字」两个固定回归项。
