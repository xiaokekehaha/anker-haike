# 41: 订单与渠道核对 L1–L6 与 A3 完成

**What to build:** orders_mock 与 dealers seed；lookup 规则 L1–L6：订单命中须核对 order.sku 与 product_confirmed.sku，低置信未修改字段命中降为 needs_manual_check，未命中订单但渠道在名录 → channel_in_directory；输出 receipt 的 status / verified_facts / conflicts / next_step，文案由规则表给出；summarize 用 escalate.summary 任务润色字段内文本，失败直渲染。不输出质保资格结论。

**Blocked by:** 40（凭证识别与 ReceiptCard 字段确认）

**Status:** done（2026-09-12；Codex，50 项相关后端测试通过、前端摘要回归与构建通过）

**Owner:** Codex（2026-09-12 接续认领；订单/渠道 seed、L1–L6、凭证确认后摘要与测试；记录见 ../../2026-09-12_receipt-lookup-continuation/）

- [x] A3：订单未命中、经销商命中 → 摘要 receipt.status=channel_in_directory 与 next_step
- [x] 上传另一台设备的订单 → order_product_mismatch 并列出 conflicts
- [x] 低置信订单号恰好命中他人订单且未修改 → needs_manual_check
- [x] 摘要文本中不出现「可保」「标准质保」等资格结论（字符串断言）

**设计依据：** 09 §5.2；03 §1.8；00 D16

## 实现与验证

- `app/warranty/`：冻结 YAML 演示名录的内存查询，orders_mock / dealers 事务 seed 与数据库加载；迁移 0003，容器显式配置路径。
- `haike-seed receipts --config-dir ../config` 或 `make seed WHAT=receipts`；默认 all 同时包含凭证参考数据。数据文件 `config/receipt_reference.yaml` 均为虚构演示记录，不能当作真实授权名录。
- `confirmed_receipt` 接入 L1–L6；低置信字段仅声明 edited 但未实际修改仍降级；SKU 未确认时人工核实；低置信命中不将订单渠道/日期列为已核实事实。
- 摘要采用规则定义的 next_step，前端与复制文本展示已核实事实、冲突、下一步。authorized 按现有 string 字典契约编码 true/false，界面显示已授权/未授权。
- `escalate.summary` 以 internal / 最多 3 s 可选整理问题字段，仅接受保留整句内容和顺序的空白/标点调整；失败或校验拒绝直渲染。凭证、规则、步骤、产品不交给模型修改；R3/R4 即时摘要不等待润色。
- 后端相关 50 项通过（含独立 Postgres schema seed 更新/幂等、迁移 head=0003、四条 A3 API→SSE→快照→重复动作重放、模型失败/取消/不当输出）；前端全量 97 项通过，摘要相关最终 5 项通过，TypeScript/构建/contracts:check 通过。
- 全量后端除摘要测试独立运行外 326 通过 / 9 失败：均为当前 guide.step 的四模型链超过 chain_max=3；摘要 6 项另跑全通过。本票不修改其他任务的模型路由。全局 lint 另有 guide/steps.py、rules/service.py、test_sessions_cancel_stream.py 的 3 处既有问题；本票文件 lint 通过。
- 未进行真实视觉厂商识别或部署；真实订单截图评测仍归票 42。
