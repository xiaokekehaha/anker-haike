# 发现

- 当前路由图片主位 deepseek-flash，备用 qwen3-vl-plus、glm-4.6v。
- 用户截图四类：GLM-Image 生成图片；GLM-OCR 提取文字；GLM-ASR 语音识别；GLM-TTS 语音合成。
- 官方 GLM-OCR 文档使用 layout_parsing 接口，不能直接当聊天视觉模型接入现有路由。来源：https://docs.bigmodel.cn/cn/guide/models/vlm/glm-ocr
- 官方 GLM-4.6V 文档确认图像理解和关闭思考模式。来源：https://docs.bigmodel.cn/cn/guide/models/vlm/glm-4.6v
- 工作区有其他会话正在改动 vision.py、vision_vocab.yaml、quality.py 等。评测必须记录代码快照摘要，不把变动归入本任务。
- 现有 runner 的 judge 函数在添加 hard_gates 原因后重新清空 reasons；不能直接采信其主备推荐，需以原始指标独立解释。暂不修改该代码。
- 已查看官方资料的全部 10 张附件：T14/T20/T30/T42/T48 为实物照片，T38/T45/T46/T53/T55 为订单或发票截图。T48 明显有外壳裂纹；T30 有红色灯环；T20 只有基站，不能推断机器故障。原始附件已有部分个人信息遮盖。
- 历史 baseline 为 DeepSeek 65%、Qwen 80%、GLM 69%；stage4 业务流程为 96%、93%、91%。不是同一提示词或流程，不能据此把提升全部归因于模型。
- 现有订单评分会删除订单号字母，并接受双向子串；例如只抄一部分编号也可能算对。本次须保留字母、完整匹配。
- 官方 OCR 页面说明图片可输入，使用 POST /api/paas/v4/layout_parsing，model=glm-ocr。页面自报基准分与吞吐不当作项目实测。
- 官方目录确认 GLM-5.3-Flash 支持图片，且 thinking.type 只能 enabled；基础 GLM-5.3 的输入仍为文本。新增 5.3-Flash 做补充候选，参数与旧三家不同，单独说明。来源：https://docs.bigmodel.cn/cn/guide/models/vlm/glm-5.3-flash 和 https://docs.bigmodel.cn/cn/guide/start/pricing
- 人工复核：T42 的 DeepSeek 观察误写 DREAME STATION，实际可见 UNICLEAN STATION；Qwen 在 T48 描述了不存在的 10/22 数字。预设字段得分没有覆盖每条自由文本事实，不能将高字段命中率解释为无幻觉。
- T42 是设备底部局部图，未知品类是可接受的保守回答；本次 strict 命中仍计作未识别，报告须区分漏识别和错误断言，不将两者都称作幻觉。
- 独立四字段抽取：DeepSeek 与 Qwen 均 40/40；DeepSeek 全文转录失败并不代表实际订单字段抽取失败。
- DeepSeek 与 Qwen 的同区域裁剪铭牌均 6/6 型号正确、24/24 关键字命中。裁剪使用预先已知位置，仅为读字实验。
