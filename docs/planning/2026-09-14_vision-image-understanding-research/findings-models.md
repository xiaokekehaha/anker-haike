# 调研 B：VLM 选型（原始材料）

来源：后台调研 agent，2026-09-14 检索。**【未验证】** = 仅二手来源；**【自报】** = 厂商技术报告数据。

## 一句话结论

- **综合最强、可结构化输出、坐标可控**：Claude Sonnet 5 / Opus 5（高分辨率档 2576px / 4784 视觉 token；Vision Arena 榜首群；官方给出精确的 bbox 像素坐标规则）。缺点：**Bedrock 上不支持 structured outputs**（需 tool-use strict schema 替代），高分辨率档单图 token 是标准档约 3 倍。
- **国内可直连、grounding / OCR 最强**：Qwen 系（Qwen3-VL-Plus/Flash 与原生多模态 Qwen3.6/3.8）。OCRBench v2、HallusionBench 榜单被 Qwen 家族刷满；RefCOCO 92+ 远超 GPT/Gemini；百炼 ¥1/M 输入。缺点：Qwen3.8-Max 第三方实测 OCR 抽取排第 10、延迟高。
- **性价比**：Gemini 3.x Flash（默认 1120 token/图、原生 bbox/分割 API、$0.75/M）；DeepSeek V4 Flash Vision（≤384 token/图，分辨率压到约 800×800，**不适合小字铭牌与细小缺陷**）。
- **公开基准与真实场景差距明显**：工业异常基准 MMAD 上 GPT-4o 平均 74.9%、「是否有异常」仅 68.6%，人类专家 86.7%；VLM 在低光下会崩溃（0.99→0.22）、自述置信度几乎无信息量（AUROC≈0.5）。→ **照片可用性必须用独立前置质量门控 + 结构化「不可见/不确定」选项，不能靠模型自评。**

## 1. 国内可访问模型

| 模型 | 细粒度识别 / OCR | Grounding | 图像限制 | 结构化输出 | 价格（约） |
| --- | --- | --- | --- | --- | --- |
| **Qwen3-VL-Plus / Flash**（百炼） | 官方称 OCR 支持 32 语种、低光/模糊/倾斜鲁棒。235B-Instruct【自报】OCRBench 920、OCRBench v2 en/zh 67.1/61.8（GPT-5 high 53.0/43.2，Gemini 2.5 Pro 54.3/48.5，Claude Opus 4.1 48.4/43.7）；CC-OCR 82.2 | 2D bbox（相对 0–1000）、3D bbox；RefCOCO-avg 92.1；ODinW-13 48.6 mAP（Gemini 2.5 Pro 74.6） | 单图最高 1600 万像素，token = h×w/(32×32)+2；上下文 262K | JSON / json_schema ✓ | plus ¥1 / ¥10 per M（≤32K 档）；1000×1000 图 ≈ 978 token ≈ ¥0.001 |
| **Qwen3.5 / 3.6 / 3.7-Plus / 3.8**（原生多模态） | OCRBench v2 官方榜 2026.06：Qwen3.6-35B-A3B en 65.5、Qwen3.5-9B zh 64.1。**Roboflow 实测：Qwen3.8-Max 目标检测第一、计数并列第一，但 OCR 抽取排第 10，落后 Gemini 3.5 Flash / Claude Sonnet 约 10pp，偶有幻觉数值，延迟属最慢之一** | XYXY 归一化 0–1000 效果最好 | 3.8-27B 上下文 262K | ✓ | Qwen3.8-Max $2/$6 per M【第三方】 |
| **GLM-4.6V / GLM-5V-Turbo / GLM-5.3-Flash**（智谱） | 4.6V 自报同规模开源 SOTA；5V-Turbo 官方基准偏 design-to-code / GUI agent，**未公开 OCR / 幻觉 / 细粒度分数** | 坐标归一化 ×1000，特殊 token 包裹 | 5V-Turbo 上下文约 200K；单图像素限制未公开 | function calling ✓；JSON schema 未说明 | 5V-Turbo $1.2 / $4 per M |
| **DeepSeek V4 Flash Vision** | 官方仅称适合文档 / 图表 / VQA；第三方称「小字、反光、倾斜、模糊、密集表格仍需人工核验」，无公开基准 | 未见 | **每图上限 384 token，大图压缩到约 800×800 等效**；单次最多 600 图 | JSON ✓ | $0.30/$1.2 per M 峰时；单图约 $0.0001 |
| **Doubao Seed 2.0 / 2.1**（火山方舟） | 自报 VLMsAreBlind、BabyVision、VLMsAreBiased 最高分；ChartQAPro / OmniDocBench 顶尖；Seed 2.0 Mini HallusionBench 0.651 | 是否支持 bbox 未确认【未验证】 | max_pixels 上限约 9MP | — | Pro ¥3.2/¥16，Lite ¥0.6/¥3.6，Mini ¥0.2/¥2 |
| **Kimi K2.5 / K2.6** | K2.5 自报 OCRBench 92.3（Gemini 3 Pro 90.3、Claude 4.5 Opus 86.5）、OmniDocBench 88.8 | GUI grounding 强；通用 bbox 未见报告 | 256K 上下文 | — | K2.6 $0.95/$4 per M |
| **InternVL3.5 / MiniCPM-V 4.5 / Step 3.7 Flash / HunyuanOCR** | InternVL3.5-241B【自报】OCRBench 907、HallusionBench 57.3、MME-RealWorld 65.1；MiniCPM-o 4.5 OCRBench 876、HallusionBench 63.2（RLAIF-V 专降幻觉）；Step 3.7 Flash HR-Bench 4K 89.13 / 8K 86.34；HunyuanOCR 1B OCRBench 860、OmniDocBench 94.1 | InternVL RefCOCO 92.4 | InternVL 动态 tile；MiniCPM 最高 1.8MP | — | 均开源，可私有化 |

## 2. 海外模型

| 模型 | 视觉规格 | 细粒度 / OCR / 幻觉 | Grounding | 图像限制 | 结构化输出 | 单图价格（1000×1000） |
| --- | --- | --- | --- | --- | --- | --- |
| **Claude Opus 5 / Sonnet 5 / Fable 5.1** | 28×28 px = 1 视觉 token；高分辨率档长边 2576px、上限 4784 token（标准档 1568/1568）；手机原图 4032×3024 → 4784 token | Vision Arena 2026-09-13：claude-fable-5 1310 第 1，opus-4-7 1301，opus-5-high 1289。官方限制：低质 / 旋转 / <200px 小图易幻觉，计数近似 | 返回**绝对像素坐标**，官方明确不要用 0–1000 归一化；可配 structured outputs 输出 `[x1,y1,x2,y2]` | 一方 API 单图 ≤10MB、8000×8000；**Bedrock / Vertex 单图 ≤5MB**；>20 图时每图边长 ≤2000px | 一方 API ✓；**Bedrock 模型卡：Sonnet 5 不支持 structured outputs** | Opus 5 $5/M ≈ $0.0065；Sonnet 5 $2/M ≈ $0.0026；手机原图 Sonnet 5 ≈ $0.0096 |
| **Gemini 3.1 Pro / 3.5–3.8 Flash** | `media_resolution`：low 280 / medium 560 / high 1120 token（默认 1120） | OCRBench v2 2026.06：Gemini 3 Pro Preview en 63.4 / zh 63.8（专有模型最高）；Roboflow 实测 3.5 Flash OCR 抽取领先 | **原生目标检测 / 分割 API**，`[ymin,xmin,ymax,xmax]` 0–1000，可输出多边形 mask | 单请求最多 3600 图 | Pydantic / Zod JSON schema ✓ | 3.1 Pro ≈ $0.0022；3.8 Flash ≈ $0.00084；3.5 Flash-Lite ≈ $0.00034 |
| **GPT-5.x / 6** | 32×32 patch，每图上限 30000 patch；`detail` low/high/**original** | 官方限制：非拉丁文字、小字、旋转、**精确空间定位困难**、计数近似 | **文档未提供 bbox / 定位能力** | 单请求 1500 图 | JSON schema ✓ | Terra $2/M ≈ $0.0025 |
| **Amazon Nova 2 Lite / Pro** | 自动重缩放到一边 ≥896px；**每图固定计费 230 token** | 官方自认：多语言图像「可能在简单任务上挣扎或幻觉」、小字需裁剪、空间推理有限 | bbox 0–1000 ✓ | **内联最多 5 张 / 25MB**；S3 1000 张 | Converse tool-use | Nova 2 Pro 预览 $2.19/$17.5【第三方】 |

**延迟**：公开可比数据稀少。可确认的定性信息——Qwen3.8-Max 属最慢之一（Roboflow）；Claude 高分辨率档 token ×3 会直接推高首字延迟；Gemini `media_resolution: low` 与 DeepSeek 384 token 封顶是低延迟路线。其余未验证。

## 3. 相关公开基准

| 基准 | 考察点 | 对应本任务 | 最新数据 |
| --- | --- | --- | --- |
| **OCRBench v2**（en/zh，9 维） | 场景文字与文档 OCR 含定位 | 铭牌型号 / 序列号 | 官方榜 2026.06：en 第一 73.4（专有）、Qwen3.6-35B 65.5、Gemini 3 Pro 63.4；zh 第一 66.2、Qwen3.5-9B 64.1。**所有模型 <75，中文更难** |
| **HallusionBench**（346 图、1129 是/否配对） | 语言先验 vs 视觉证据 | 「不编细节」、是/否判断 | llm-stats 2026-09-14 前 8 名全是 Qwen：Qwen3.5-27B 0.700。**GPT-5.x / Gemini 3 / Claude 5 未上榜** |
| **MME-RealWorld**（13366 张平均 2000×1500 真实图） | 高分辨率真实场景感知 | 最贴近用户随手拍 | 论文结论「最先进模型未超过 60%」；InternVL3.5-38B 66.0。**缺 2026 前沿模型公开数据** |
| **V\* / HR-Bench 4K/8K** | 高分辨率图中小目标搜索 | 小缺陷、小铭牌 | Qwen3-VL-235B **带工具（裁剪放大）** V\* 93.7、HRBench-4K 85.3；Step 3.7 Flash 89.13/86.34。**工具式「放大再看」带来的提升大于单纯加大模型** |
| **MMAD**（ICLR'25，8366 张工业图、7 子任务） | 工业异常检测：异常判别 / 缺陷分类 / 定位 / 描述 | **与「识别部件与现象」最接近** | GPT-4o 平均 74.9%（异常判别 68.6%、缺陷定位 55.6%、物体分类 95.0%）；Claude 3.5 Sonnet 68.4；**人类专家 86.7、普通人 78.7**。关键发现：多数模型**不会利用正常样品参考图**（反而下降）；>1-shot 收益为零甚至下降；**RAG 注入领域知识 +5–6%** |
| **RefCOCO / ODinW-13** | 指代定位 / 开放词汇检测 | 圈出「烧黑的接口」 | Qwen3-VL 92.1 / 48.6 mAP，InternVL3.5 92.4；Gemini 2.5 Pro 74.6；GPT-5 66.8。**开源中文系 grounding 明显强于 GPT/Claude** |
| **CountBench** | 计数 | 缠绕根数、缺失螺丝数 | 前沿模型 91–94；小数目尚可，大数目崩 |
| **Q-Bench / Q-Align** | 低层画质判断 | 照片可用性 | LMM 在两图比较下有能力，**单图绝对打分弱** |

## 4. 真实用户照片上的失效模式

| 失效模式 | 证据 | 含义 |
| --- | --- | --- |
| **低光崩溃**（其他退化相对温和） | arXiv 2607.22034：JPEG q=7、运动模糊 r=7、旋转 20°、0.15× 重采样下准确率仍 0.87–1.00，但**亮度 ×0.15 时 0.99→0.22**（≈随机） | 过暗照片必须在进模型前拦截，模型自己「看不出自己看不见」 |
| **自述置信度无效** | 同上：口头置信度恒在 0.87–0.90，错误检测 **AUROC≈0.50**；内部 token 概率 AUROC 0.92–0.99 | 不要用「你有多确定」做门控；闭源 API 拿不到 logprob 时只能靠外部 IQA |
| **空间脆弱、语义强** | VLM-RobustBench（2603.06148，11 模型 133 扰动）：低强度 glass blur 掉约 8pp；高倍上采样掉 26–34pp；**上下翻转 −10.3pp**；Qwen3-VL-30B 最鲁棒 | EXIF 旋转丢失、截图二次放大都会伤 |
| **Yes-bias / 迎合** | 2601.12430：HallusionBench 上 yes 率与真值差 **112.95pp**（LLaVA-1.5）；2507.03123：**模型越大越迎合** | 「电池是不是鼓包了？」这类引导式问题会诱发 yes；用中性开放题 + 含 `not_visible / uncertain` 的枚举 |
| **否定理解接近随机** | NegBench（CVPR 2025，79k 例）：现代 VLM 在含否定的检索 / 选择题上接近 chance | 提示词与 schema 避免「没有…的」「除…之外」；用正向枚举 |
| **计数在分布外崩溃** | GroundCount 2603.10978：数量越大越差，用检测框约束可修复 | 需要精确数量时用检测器 |
| **精确定位差** | OpenAI「精确空间定位困难」；Claude「坐标近似，小目标缩放后精度下降，建议裁剪后再问」 | 两步：先粗 bbox → 裁剪 → 再识别 / OCR |
| **参考图 / 少样本帮助有限** | MMAD：多数模型不会利用正常样品模板图；>1-shot 无收益 | 「对比正常件」策略需实测，别默认有效 |
| **长回答更易幻觉** | 2510.20229：LVLM 幻觉率随回复长度增长 | 要求短、字段化输出 |

## 5. AWS Bedrock

| 项目 | 事实 |
| --- | --- |
| Claude 可用性 | Sonnet 5（2026-06-30，1M 上下文、图像输入 ✓）、Opus 5、Opus 4.8/4.7/4.6、Haiku 4.5、Fable 5.1 均在目录中 |
| Claude 图像限制 | **Bedrock / Vertex 单图 ≤5MB**（一方 API 10MB）、请求体 25MB；>20 个 image block 时每图边长 ≤2000px；仅支持 base64 |
| **Claude 结构化输出** | **Bedrock 模型卡：Sonnet 5 在 bedrock-runtime 与 bedrock-mantle 均不支持 structured outputs** → 需改用 tool-use + `strict: true` 或提示词 JSON |
| Claude 定价 | Sonnet 5 $2/$10、Opus 4.8 $5/$25（Global profile）；区域端点 +10% |
| Nova 2 Lite | 内联 **5 图 / 25MB**；重缩放到一边 ≥896px；**固定计 230 token/图**；bbox 0–1000；官方自认多语言图像会幻觉、小字需裁剪 |
| 其他 | 目录含 Qwen3-VL-235B、Pixtral Large、Llama 4 Maverick；**无 Gemini** |

**评估**：Bedrock 上 Claude 是唯一同时满足「高分辨率 + 强综合视觉 + 像素坐标」的选项；Nova 2 Lite 便宜且 bbox 原生，但官方自认小字弱，不适合中文铭牌 OCR 主路径，可作预筛 / 兜底。

## 6. 未验证项

Doubao Seed 2.0 的 token 公式与 bbox 支持；GLM-5V-Turbo / Kimi K2.6 的 OCR 与幻觉分数；Claude 5 系在 OCRBench v2 / HallusionBench / MME-RealWorld 的公开数据缺失；Nova 2 Pro 是否 GA；各模型端到端延迟无可比公开数据。

## 主要来源

[Claude Vision](https://platform.claude.com/docs/en/build-with-claude/vision) · [Claude Coordinates](https://platform.claude.com/docs/en/build-with-claude/vision-coordinates) · [Sonnet 5 Bedrock 模型卡](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html) · [Gemini Image understanding](https://ai.google.dev/gemini-api/docs/image-understanding) · [Gemini Media resolution](https://ai.google.dev/gemini-api/docs/media-resolution) · [OpenAI Images & Vision](https://developers.openai.com/api/docs/guides/images-vision) · [Nova 2 多模态](https://docs.aws.amazon.com/nova/latest/nova2-userguide/using-multimodal-models.html) · [百炼 qwen3-vl-plus](https://help.aliyun.com/zh/model-studio/qwen3-vl-plus) · [Qwen3-VL GitHub](https://github.com/QwenLM/Qwen3-VL) · [GLM-V](https://github.com/zai-org/GLM-V) · [DeepSeek 定价](https://api-docs.deepseek.com/quick_start/pricing/) · [OCRBench v2 榜](https://99franklin.github.io/ocrbench_v2/) · [HallusionBench 榜](https://llm-stats.com/benchmarks/hallusion-bench) · [MME-RealWorld](https://github.com/MME-Benchmarks/MME-RealWorld) · [MMAD](https://arxiv.org/html/2410.09453) · [Vision Arena](https://arena.ai/leaderboard/vision) · [Roboflow Qwen3.8-Max 实测](https://blog.roboflow.com/qwen3-8-max/) · [小 VLM 真实退化下置信度](https://arxiv.org/html/2607.22034) · [VLM-RobustBench](https://arxiv.org/html/2603.06148) · [Yes-bias 机理](https://arxiv.org/html/2601.12430v2) · [NegBench](https://arxiv.org/abs/2501.09425) · [GroundCount](https://arxiv.org/pdf/2603.10978)
