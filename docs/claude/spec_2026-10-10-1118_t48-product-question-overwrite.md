# T48 补型号覆盖原咨询问题

## 问题

用户问「What does this green light mean」，系统要型号；用户回「The product is S1 Pro Breast Pump, model T8D04.」后，
保存的咨询问题和 kb_qa 检索 query 都变成型号句，绿灯目标丢失。

## 追踪

```
第 1 轮  primary_intent=product_question
         → answer_product_question 新建任务 {question: "What does this green light mean", status: awaiting_product}
第 2 轮  模型把型号回答判成 product_question（提示词要求判 supplement，模型没遵守）
         → answer_product_question 第一行：intent == product_question 就无条件重建任务
           task = {question: state["text"], ...}   ← 原问题在这里被覆盖
         → _candidates 从型号句解析出 T8D04，确认产品
         → query = task["question"] = 型号句 → 检索、回答都围绕型号句
```

服务端没有核对「等型号时收到的是身份还是新问题」，完全信任模型意图。intent=supplement 时走同一函数但不重建，所以只有模型判错时出问题。

## 方案

`answers_identity`：任务处于 awaiting_product、本轮原话能解析出产品（PN / 目录型号别名 / 品类词）、且没有提问形式（问号或句首疑问词）时，
本轮是在补身份，不重建任务，原问题保留。带新问题的型号句（「如何设置节奏？型号 T8D04」）仍按新问题处理。

## 验证

- tests/test_product_questions.py 新增 2 项：T48 型号句判成 product_question 仍用原问题检索（去掉修复即失败）；等型号时带型号的新问题替换原问题。
- 后端全量 1184 passed / 2 skipped，lint 清零。
- make up 后真实复跑 T48：kb_qa query 为 `What does this green light mean`；回复说明官方资料只覆盖红灯（电量）与充电白灯，没有绿灯含义。
  官方 QA 确实没有 S1 Pro 绿灯条目（bp 标题只有 flashing red light 与 temperature indicator），这是知识覆盖缺口，不是检索问题。
