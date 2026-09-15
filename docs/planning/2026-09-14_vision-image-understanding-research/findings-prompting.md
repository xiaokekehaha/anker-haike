# 调研 A：prompt 模式与推理期技术（原始材料）

来源：后台调研 agent，2026-09-14 检索。⚠️ 标记为二手或未核实原文数字的条目。

## 结论先行（针对售后看故障照片）

1. **图先文后 + 逐图标签**：Claude 官方明确「images come before text」；Gemini 两处官方文档自相矛盾需自测；OpenAI 反而建议指令在前。跨厂商不可照搬。
2. **两阶段：先 grounded 描述（只写看得见的），再受控分类**（VDGD / SPARC / Gemini 官方 troubleshooting）。但**不要用长篇纯文本 CoT 做感知题**——多篇 2025–2026 论文显示会「visual forgetting」，反而降低识别准确率。
3. **绝不把用户文字描述当成前提喂给视觉调用**：预设式提问使准确率相对下降 25–85%（HalluScope）；文本被污染时平均掉点 >40%，而「Focus on image」式提示几乎无效（Words or Vision）。做法是图像抽取与用户文本分两路，再由代码做冲突检测。
4. **用 visible / not_visible / not_determinable 三态代替 yes/no**，每字段附 evidence 区域。verbalized confidence 校准差（ECE 常 >0.25），只能当弱信号。
5. **小字（铭牌/序列号）靠 zoom，不靠滤镜**：crop-and-re-ask 是唯一有强证据的推理期手段（Anthropic crop tool 在图表题 29%→73%；Zoom-Refine 两次推理 HR-Bench 8K +5%）。EXIF 方向必须客户端先烤进像素。
6. **序列号/型号：VLM 转写 + 正则/白名单校验**，看不清的字符用 `?` 占位（阿里 qwen-vl-ocr 服务内置 prompt 就是这么写的）。
7. **多图 ≤3–4 张/次**，明确标注「参考图 vs 用户图」；更稳的是单图各抽一次再合并。

## 1. 官方文档要点

| 厂商 | 关键建议 | 来源 |
| --- | --- | --- |
| Anthropic Claude | 图在文前；多图用 `Image 1:` / `Image 2:` 文本块引入；视觉 token = ⌈w/28⌉×⌈h/28⌉；标准档长边 1568px，高分档 2576px；局限：低质量、**旋转**、<200px 小图易幻觉，计数与坐标近似；**不读 EXIF**；多次有损压缩伤文字识别；>20 图时每图 ≤2000px。坐标要**绝对像素**不要 0–1000 归一化；小目标先 crop 再送。通用：「Tell Claude what to do instead of what not to do」「数据放前、问题放后」「Ground responses in quotes」，3–5 个 `<example>`。**Crop tool**：给模型 zoom 工具，图表基准 29%→73%（fable-5）、13%→44%（sonnet-5）。 | [Vision](https://platform.claude.com/docs/en/build-with-claude/vision) · [Coordinates](https://platform.claude.com/docs/en/build-with-claude/vision-coordinates) · [Prompting](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) · [Crop tool cookbook](https://platform.claude.com/cookbook/multimodal-crop-tool) |
| OpenAI | `detail`: low / high / original / auto，**OCR、小物体、精确坐标用 `original`**；「put instructions before the image」；局限：小字或**旋转文字**易误读、非拉丁字母较差、精确空间定位差、计数近似。Cookbook：密集扫描 / 手写 / tiny labels / 低对比 → `original`；转写类 → `verbosity: high`；多区域组合 → reasoning effort high；多次放大检查 → 自建 crop-and-rerun pipeline；bbox 用 0..999。 | [Images and vision](https://developers.openai.com/api/docs/guides/images-vision) · [Cookbook](https://developers.openai.com/cookbook/examples/multimodal/document_and_multimodal_understanding_tips) · [Thinking with images](https://openai.com/index/thinking-with-images/) |
| Google Gemini | 单图图文顺序两处官方文档说法相反，需自测。Troubleshooting 明确：输出泛泛时「ask the model to describe the image(s) before providing the task instruction」；多图先让它逐图详述。检测输出 `box_2d=[ymin,xmin,ymax,xmax]` 0–1000。`media_resolution`：low 280 / medium 560 / high 1120 / ultra_high 2240 token，「for standard PDFs quality typically saturates at medium」。Gemini 3 Flash 会自己写 Python crop/zoom 去读远处仪表或序列号。 | [Image understanding](https://ai.google.dev/gemini-api/docs/image-understanding) · [Files guide](https://ai.google.dev/gemini-api/docs/files) · [Media resolution](https://ai.google.dev/gemini-api/docs/interactions/media-resolution.md.txt) |
| Alibaba Qwen-VL | Qwen2.5-VL 输出绝对像素 bbox，Qwen3-VL 改为相对 0–1000；grounding 触发词「with grounding」/「Find」；视觉 token 建议 256–1280（`min_pixels`/`max_pixels`），**默认 max_pixels=12.8M 是架构上限不是推荐值，会降低 grounding IoU，推荐 1,003,520**；Qwen3-VL 有 `image_zoom_in_tool`；**qwen-vl-ocr 内置 prompt 要求模糊或反光字符用 `?` 替代**，支持 `enable_rotate` 与 `key_information_extraction` 出 JSON。 | [Qwen2.5-VL](https://qwenlm.github.io/blog/qwen2.5-vl/) · [Qwen3-VL cookbooks](https://github.com/QwenLM/Qwen3-VL/tree/main/cookbooks) · [qwen-vl-ocr](https://www.alibabacloud.com/help/en/model-studio/qwen-vl-ocr) |

## 2. 各 prompt 模式的证据

**Describe-first / 两阶段**
- VDGD（ICLR 2025）：先生成详细描述再作答，视觉推理基准提升 2%–33%；根因是「visual perception gap」——能认出元素但不会联系到问题。[2405.15683](https://arxiv.org/abs/2405.15683)
- SPARC（2026）：显式「先定位相关区域 → 再基于区域推理」，Qwen3-VL-4B 在 V* +6.7，比 thinking-with-images 少 200× token。[2602.06566](https://arxiv.org/abs/2602.06566)
- 反面：纯文本 CoT 对 vision-centric 任务常降分；「More Thought, Less Accuracy」提出 **visual forgetting**（推理越长越忽视图像）。→ 描述阶段要**短、只写可见事实、可带区域**。[COVT 2511.19418](https://arxiv.org/abs/2511.19418) · [2509.25848](https://arxiv.org/abs/2509.25848)

**Visual CoT / bbox grounding 验证**
- Visual CoT（NeurIPS 2024）：中间 bbox 作为 CoT 步骤，专为「高分辨率 + 关键区域小」设计，但需训练。[2403.16999](https://arxiv.org/abs/2403.16999)
- API 上可行替代：每字段输出 `evidence_region`，再用 bbox 裁图二次核验。
- **Set-of-Mark**：SAM/SEEM 分割后叠数字标记，GPT-4V 直接输坐标仅 25.7，加 SoM 后零样本超过 Grounding DINO（RefCOCOg）；>20 个物体退化。适合「这张图哪个部位坏了 → 选标号」。[2310.11441](https://arxiv.org/abs/2310.11441)

**受控词表 + JSON schema**
- 「Let Me Speak Freely?」：格式约束**损害推理题、帮助分类题**；推荐 free-form scratchpad + 校验后的 final 字段。→ 部位/现象/严重度用枚举 + schema，描述字段留自由文本。[2408.02442](https://arxiv.org/abs/2408.02442)

**Self-consistency / 多采样投票**
- 小 VLM 测试时扩展：8→16 条链只 +0.15pp；PRM 引导 beam search 比朴素 SC 低 0.39pp 且成本 8×。→ 3–5 采样够用，复杂 critic 不值。[2607.09438](https://arxiv.org/abs/2607.09438)

**弃答（not_determinable）**
- UPD：**加显式指令**（「if unsolvable answer X」）比只加「None of the above」选项有效得多；Qwen2.5-VL-7B AAD 32.2→58.5、GPT-4o 45.6→59.3 ⚠️数字为二手摘要；代价是 over-abstention。[2403.20331](https://arxiv.org/html/2403.20331)
- TRAPSBench：16 个 VLM 的隐藏状态可解码「可答性」AUROC 0.91，但**几乎不弃答**。→ 弃答要靠 prompt 显式给通道 + 后处理，不能指望模型自发。[2608.13167](https://arxiv.org/abs/2608.13167)

**负面指令陷阱**
- Anthropic 官方：「Tell Claude what to do instead of what not to do」。→ 写「仅输出图中可直接看到的内容」而非「不要猜测」。

**Few-shot 参考图 / many-shot ICL**
- GPT-4o 与 Gemini 1.5 Pro 上 many-shot（至 ~2000 例）显著优于 few-shot；**开源权重模型（Llama 3.2-Vision）几乎不受益**；批处理可降本不掉点。→ 闭源 API 上「参考好件图 + 典型故障图」作 ICL 有效。[2405.09798](https://arxiv.org/abs/2405.09798)

**图文顺序与 text bias**
- Claude 图先；Gemini 自相矛盾；OpenAI 指令先。研究侧：文本 token 放图像前会持续加重 text bias（Phi3.5）；image 之前的 system 段吸走 >70% 注意力（attention sink）。→ 目标是「防被用户文字带偏」时，倾向**图先、用户文本后，甚至不放同一调用**。[2503.02199](https://arxiv.org/html/2503.02199v1) · [2601.12430](https://arxiv.org/abs/2601.12430)

**Role / persona**
- 162 种 persona × 4 个模型族：persona **不提升**事实题准确率（EMNLP 2024 Findings）。→ system prompt 写任务规范/词表/格式，不要花笔墨在「你是资深售后工程师」。[2311.10054](https://arxiv.org/abs/2311.10054)

**Prompt 诱导幻觉（与图文冲突直接相关）**
- HalluScope（2026）：正常识别 92.5–98.6%，**预设式问题**（「这个充电口的烫痕多大」而图中无烫痕）准确率跌到 5.85–64.8%；结论「hallucinations predominantly driven by textual instructions, even when visual perception remains reliable」。[2604.21911](https://arxiv.org/html/2604.21911v1)
- Words or Vision（10 个 VLM）：文本被污染时平均掉点 >40%；「Focus on Image」指令只把 Qwen2-VL-7B 的 text preference 从 16.8%→14.2%；**Claude Sonnet 最不偏文本（9.58%），GPT-4o 27.09%**，LLaVA-NeXT/Molmo >80%。[2503.02199](https://arxiv.org/abs/2503.02199)

## 3. 推理期图像处理

| 技术 | 证据 | API-only 可行性 |
| --- | --- | --- |
| 分辨率 / 分块（AnyRes、dynamic high-res） | Claude 28px patch 两档上限；OpenAI tile 预算与 `detail`；Gemini `media_resolution`（文档 OCR 在 medium 已饱和）；Qwen `max_pixels` 过大反伤 grounding | 直接可控。把长边缩到模型原生上限附近，**不要**超限让服务端二次缩放 |
| **Zoom-in / crop-and-re-ask** | V*/SEAL（CVPR 2024，V*Bench 75.39%）；**ZoomEye**（EMNLP 2025，训练无关树搜索，InternVL2.5-8B HR-Bench +15.71/+17.69）；**Zoom-Refine**（训练无关两次推理，InternVL3-78B HR-Bench 4K 76.8→81.0、8K 69.1→74.1）；Anthropic crop tool +44/+31 分；o3 thinking-with-images、Gemini 3 写代码 zoom、Qwen3-VL `image_zoom_in_tool` 均已产品化 | **最推荐**。自建 Zoom-Refine：第一次要 bbox，代码从原图裁切放大，第二次只问该区域。[V*](https://arxiv.org/abs/2312.14135) · [ZoomEye](https://arxiv.org/abs/2411.16044) · [Zoom-Refine](https://arxiv.org/abs/2506.01663) |
| ViCrop（注意力引导裁切） | ICLR 2025：MLLM「知道该看哪里但看不清」，用内部 attention 定位后裁切，训练无关 | 需模型内部 attention → **仅自部署** [2502.17422](https://arxiv.org/abs/2502.17422) |
| **EXIF 方向校正** | 官方局限都点名 rotated；研究显示**预先转正比在 prompt 里告知旋转角有效得多**；⚠️第三方博客称 180° 旋转文字抽取 97%→28%；Claude 文档两处对是否读 EXIF 表述不一致——别赌，客户端 `ImageOps.exif_transpose` 后再送 | 必做，零成本 [2605.05045](https://arxiv.org/pdf/2605.05045) |
| 对比度 / 去噪 / 超分 | 证据几乎全来自传统 OCR；VLM 侧只有 Anthropic 警告「多次有损压缩伤文字」⚠️对 VLM 收益未验证，滤镜可能引入伪影 | 只做：转正、裁切、**裁切后放大**、JPEG q≥85、避免二次压缩 |

## 4. 幻觉抑制：闭源 API 可行性

| 方法 | 原理 | API-only? |
| --- | --- | --- |
| VCD / OPERA / 对比解码 | 对比原图 vs 扰动图的 logits；惩罚过度自信 | **不可行**（需 logits）。仅自部署可用 |
| REVERSE（generate-but-verify） | 训练 + 推理期回溯重采样，CHAIR-MSCOCO +12% | 需训练 → 不可行 |
| 注意力再分配抑制 yes-bias | 把 system 段注意力挪回图 | 需内部干预 → 不可行。**替代：不用 yes/no 问法，改三态枚举 + 要求 evidence** |
| **裁图自我核验（Zoom-Refine 式）** | 第二轮只看 ROI 高清图核对第一轮结论 | **可行、证据最强** |
| Describe-first + grounded 抽取 | 先只写可见事实，再从描述填 schema | 可行（2 次调用或一次响应两段） |
| Verbalized confidence | 模型自报 0–1 置信 | 可行但**弱**：系统性过度自信（ECE >0.25）。仅作路由信号，配合多采样一致率 |
| 多采样一致性 | N 次采样看字段一致率 | 可行；3–5 次即可 |
| 第二模型交叉核验 | 另一模型对「图 + 抽取结果」判有无证据支撑 | 可行；**只对高风险字段（严重度=高、判定烧毁）启用** |
| 反预设提问 | 不问「X 有多严重」，先问「图中是否可见 X」 | 可行、零成本 |
| **图文分路 + 代码级冲突检测** | 图像抽取时不喂用户描述，抽完再比对 | 可行、零成本（提示词层面纠偏几乎无效） |

## 5. 多图推理

- **上限**：Claude 100/600 张（>20 张时每图 ≤2000px）；OpenAI 1500 张；Gemini 3600 张——远高于「能用好」的数量。
- **能力现状**：MMIU（52 任务）GPT-4o 仅 55.7%，排序类 21–28%；MuirBench GPT-4o 68.0%、Gemini Pro 49.3%，且**图片在题干中的位置显著影响结果**；MIMIC（2026）：退化主要来自**视觉序列长度**而非图片数，跨图聚合与多概念追踪弱、易受干扰图影响。[MMIU](https://arxiv.org/abs/2408.02718) · [MuirBench](https://muirbench.github.io/) · [MIMIC](https://arxiv.org/abs/2601.07812)
- **做法**：每张图前置文本标签；每次 ≤3–4 张；超过时先单图各抽一次再合并；剔除明显无关图；对比参考图时明确「只报告 Image 2 相对 Image 1 的差异，不确定则 not_determinable」。

## 6. 读铭牌 / 序列号

- **专用 OCR 现状**：PaddleOCR-VL-1.5（0.9B）OmniDocBench v1.5 94.5，超 GPT-4o / Gemini 2.5 Pro / Qwen3-VL-235B；新增 text spotting 与 Real5-OmniDocBench（专测拍照 / 倾斜 / 光照失真）；PP-OCRv6 34.5M 参数在 OCR 任务上超过十亿级 VLM。[PaddleOCR-VL-1.5](https://arxiv.org/abs/2601.21957) · [PP-OCRv6](https://arxiv.org/pdf/2606.13108)
- **VLM OCR 的系统性幻觉**：HalluText 定义 9 类 OCR 幻觉（existence / incompletion / **typo 自动纠错** / position / index / slice…）；历史文档研究发现 VLM「把它认为的拼写错误改成通顺文本」，低 CER 掩盖了语义替换；O/0、I/1 混淆常见。→ **序列号是无语言先验的字符串，恰是 VLM 最弱、专用 OCR 最强的地方**。[HalluText](https://openreview.net/forum?id=LRnt6foJ3q) · [2607.24077](https://arxiv.org/html/2607.24077)
- **提示技巧**：「逐字符转写，仅输出可见字符，不补全、不纠错」；看不清的字符用 `?`；小标签用高分辨率档；铭牌区域先 crop 放大再送；分别输出 `raw` 与 `normalized`，代码用正则 / 型号白名单校验。

## 7. 未核实 / 低置信项

- UPD 各模型具体数字来自二手摘要，需核对原文表格。
- 180° 旋转 97%→28% 来自个人博客，无论文；Claude 服务端是否应用 EXIF 方向校正在两处文档表述不一致。
- 对比度 / 去噪对 VLM 的收益无直接研究。
- HalluText 原文被验证页拦截，细节来自摘要与二手引用。
