# 线上客服流程实测记录

采集日期：2026-09-17。方式：浏览器只读走查，未提交任何表单、未登录、未发起 Live Chat 会话。
所有条款为采集时页面原文的转述，页面可能随时变更；落 config 时必须带 `fetched_at` 与 URL。

## 1. 受理入口与分流

`https://service.anker.com/` → Contact Us → Create a Ticket，第一步是**受理类型五选一**：

| 选项 | 含义 |
| --- | --- |
| Need Help with My Product | 产品故障 / 使用问题 |
| Questions About a Product | 售前或功能咨询 |
| Returns/Exchanges for Product Issues | 退换货 |
| Order Support (Shipments & Orders) | 订单与物流 |
| Feedback | 意见反馈 |

选「Need Help with My Product」→ Next，**直接跳转到 `https://www.anker.com/` 的「Process a Warranty」表单**，不先做任何排障。

## 2. 质保受理表单（Anker / soundcore 同一套模板）

实测 `anker.com`（Process a Warranty）与 `soundcore.com/exchange` 字段完全一致，判断为集团统一表单。

三段，顺序固定：

1. **Order Verification**
   - 渠道单选：Anker Store / Amazon / eBay / Walmart / BestBuy / Target / Others（soundcore 站首项为 soundcore Store）
   - `Order Number*`，独立 Submit 先校验，校验通过才继续
2. **Basic Information**
   - `Email Address*`、`Confirm Email Address*`、`First Name*`、`Last Name*`
   - Current Address，页面注明「(If applying for a replacement, we will arrange for it to be sent to this address.)」；soundcore 站 `Address line 1*` 为必填
   - Country（欧洲为主的长列表 + 日本、墨西哥、加拿大、美国等）、State/Territory、City、Zip Code、Phone Number
3. **Issue Details**
   - `Describe the issue.*`
   - `Upload Proof of Purchase*` —— **必填**，PNG/JPG/GIF，单张 ≤10MB，最多 6 张

## 3. Live Chat 准入（未进入会话）

`service.anker.com` → Live Chat → Contact Online Customer Service，弹出第三方组件（页脚标 `Livechat Built with solvea`）。

开场白原文：

> Hello! Welcome to Anker Support! To better assist you, please describe your product model and [the problems] you encountered in detail [in one message]. e.g. My 715 Charger can not charge my phone.

进入会话前必填 `Valid email address*` + `Your name*`，并默认勾选「Anker may record this chat」+ 隐私政策链接。

**本次没有进入会话**：填入真实邮箱与姓名会在 Anker 生产客服系统产生一条实名会话记录，用户已离线无法逐条确认。门槛本身已构成可用结论：

- 线上把「身份（邮箱+姓名）」放在对话之前，会话天然可回溯、可转邮件工单；
- 线上对首轮信息密度有明示要求：**一条消息里同时给出型号与问题**；
- 会话录制有显式告知与同意。

## 4. 案件进度查询

`service.anker.com/service`（Service Progress Inquiry）→ 302 到 `passport.anker.com` 登录页。案件进度绑定账号，游客无法查询。首页也有「Log in to view your service history.」。

## 5. 便民自助入口（不经人工）

| 入口 | 路径 | 说明 |
| --- | --- | --- |
| Order Tracking | `passport.anker.com/search-orders` | 订单实时状态与配送更新 |
| Self-Service Returns | 同上（登录态） | 自助发起退货，快速退款 |
| Download Invoice | `service.anker.com/invoice` | 自助下载发票 |
| Warranty Registration | `anker.com/warranty-registration` | 注册设备确认所有权 |
| Parts and Accessories | `service.anker.com/recommended?otherType=Anker_EN_Extemal_Accessories` | 原厂配件 |
| Manuals / Videos / Compatibility / Shipping FAQ / Product FAQ | service.anker.com 各入口 | 自助资料 |

## 6. 政策要点（三站）

来源：`anker.com/policies/refund-policy`、`us.eufy.com/policies/refund-policy`、`soundcore.com/policies/refund-policy`。

### 6.1 两条互斥路径

| | 30-Day Money Back | Warranty Claim |
| --- | --- | --- |
| 适用 | 任何原因（非质量） | 质量缺陷 |
| 时限 | 购买后 30 天内；开单后 30 天内提退款 | 保修期内；开单后 90 天内提交 |
| 商品状态 | 未损坏、无使用痕迹、全部原厂配件、原包装 | 不限 |
| 运费 | 买家承担 | 公司承担（Anker 提供预付标签时承担运输损失） |
| 退款范围 | 仅货款 | 见处置阶梯 |
| 排除 | 企业/大宗订单（同款 ≥10 件）、赠品、众筹订单、盲盒与早鸟活动 | 见不保清单 |
| 特例 | soundcore 投影仪开封未使用扣 10% 重新包装费 | —— |

### 6.2 质量问题处置阶梯

eufy 原文顺序（"at eufy's sole discretion"）：评估产品类型 → **提供更换配件** → 维修 → 换翻新机（若有）→ 换新机。
Anker 侧：翻新机（若有）→ 新机 → 若无法更换或客户不愿更换，**按使用时长给部分退款**。
过保的 RoboVac / HomeVac / Vacuum Cleaner **可付费维修**。

换新后保修 = `max(原保修剩余期, 换货后 3 个月)`；全额退款后保修失效。

### 6.3 受理的三个必要条件（Anker 原文 Notes）

1. 买家必须提供**充分的购买凭证**；
2. **Anker 必须记录买家已执行的排障步骤及其结果**（"Anker must document the outcome of any troubleshooting steps taken by the buyer."）；
3. 需要**故障品序列号，和/或能清楚显示缺陷的影像证据**；
4. 部分情况需寄回做质量检验；若寄错件或不寄回，换货件保修失效。

### 6.4 有效购买凭证（Anker 原文 Valid Proof of Purchase）

- 官网订单：订单号 + **原始收货地址**
- 含卖家名称与 Anker 产品的销售发票
- 授权经销商出具的、带日期、含产品描述与购买价格的销售收据

### 6.5 不保清单（Anker 原文 Not Covered）

正常老化与磨损（含电池容量衰减、颜色变化）/ 无有效购买凭证 / 丢失或被盗 / 已过保修期 / 非质量问题超过购买后 30 天 / 赠品与促销品 / 第三方维修或改装 / 外部因素导致的损坏 / 误用（跌落、极端温度、进液、不当操作）/ 非授权经销商购买。

另：未授权拆修改装或使用非核准部件造成的损坏不保；保修**限购买国**，携出或从授权线上订单国际转运即失效。

### 6.6 付费延保与运输险

部分型号可另购延保至最长 3 年，覆盖机械与内部元件、电气故障、**意外损坏（跌落、泼溅）**；下单时可购 Worry-Free Purchase 运输险（丢件、破损、延误）。

## 7. 真实保修期表（品类 × 系列 × 部件三级）

### 7.1 Anker（US）

| 品类 | 系列 | 保修期 |
| --- | --- | --- |
| Power Banks | GaNPrime / Prime / MagGo | 24 个月 |
| Power Banks | PowerCore Reserve | 36 个月 |
| Power Banks | 其他 | 18 个月 |
| Chargers | GaNPrime / AnkerPrime；511 Charger (Nano 3, 30W)；Nano (30W) A2337 | 24 个月 |
| Chargers | 其他 | 18 个月 |
| Wireless Charger | Zolo (Magnetic, Pad)；MagGo（737 MagGo Charger 除外） | 24 个月 |
| Wireless Charger | 其他 | 18 个月 |
| AC Power | GaNPrime / Prime / Nano / MagGo Charging Station | 24 个月 |
| AC Power | 其他 | 18 个月 |
| Hubs and Adapters | 全部 | 18 个月 |
| Cables | 按系列 | 18 个月 / 24 个月 / 终身（PowerLine II 系列、Premium Nylon 等多款为终身） |
| Screen Protector / Phone Case | 全部 | 12 个月 |
| Mouse and Keyboard | 全部 | 18 个月 |
| Solar Generator / Portable Power Station / Solar Panel / Powered Cooler | —— | 独立政策页 `anker.com/anker-portable-power-station-warranty-policy`（**本次未采集**） |

### 7.2 eufy（US）

| 品类 | 保修期 |
| --- | --- |
| StickVac with Mop | 24 个月 |
| RoboVac | 12 个月 |
| HomeVac | 18 个月 |
| Robot lawn mower | 24 个月 |
| Security Camera | 12 个月 |
| Smart Lock | 18 个月（机械部件 36 个月） |
| Breast Pump | 12 个月（配件 3 个月） |
| Smart Lights | 18 个月 |
| Permanent Outdoor Light E120 / E22 | 12 / 24 个月 |
| Smart Scales | 24 个月 |
| Network Video Recorder / PoE Camera | 36 个月 |
| HomeBase / Sensor | 12 个月 |
| Accessories / Smart Home | NA |

PoE NVR 套装另有部件级表：NVR 与 PoE 摄像头 36、硬盘与支架 24、电源适配器 18、AC 线/鼠标/网线/HDMI/防水套 12、其他配件不保。

### 7.3 soundcore（US）

| 品类 | 系列 | 保修期 |
| --- | --- | --- |
| Speaker | 全系 | 18 个月 |
| Headphones | 全系 | 18 个月 |
| LED Light Strip | 全系 | 12 个月 |
| Projectors | Nebula X 系列（X1 / X1S / X1 Pro） | 主机 2 年；无线音箱与麦克风 1 年 |
| Projectors | Nebula X 系列以外 | 12 个月 |
| Projectors | 翻新机 | 3 个月 |
| Accessories | Space Flow | 1 年 |
| Accessories | 充气幕布（120″/200″） | 幕布 2 年；气泵 1 年 |

### 7.4 中国区

`anker.com.cn` 是集团官网，无消费者售后政策页（`/pages/after-sales` 404，页脚只有使用条款与隐私政策）。国内销售走电商平台，**公开渠道拿不到等价的中国区保修政策**。

## 8. 与仓库现状直接冲突的事实

| 线上事实 | 仓库现状 |
| --- | --- |
| 保修期按品类 × 系列 × 部件三级，跨度 3 个月 ~ 终身 | `config/policy/warranty_policy.yaml` 只有 `category: robot_vacuum`，单一 `warranty_months` |
| 主要公开市场为 US/EU/UK 等，CN 无公开政策 | `config/policy/regions.yaml` 有 CN 且 `warranty_policy.yaml` 以 CN 为首条政策、12 个月 |
| 处置阶梯第一档是「寄配件」 | `RemedyDecision.remedy` 仅 repair / replace / refund / none |
| 质保受理必须记录 SN 或清晰缺陷影像 | 全仓库无序列号字段 |
| Proof of Purchase 必填，无凭证直接不保 | `skip_receipt` 动作 + `receipt_status: not_collected` 可继续 |
| 30 天无理由退货是独立路径（非质量，30 天） | 唯一 refund 规则是 `fault_class: quality` + `days_since_purchase_lte: 7` |
| 换货需收货地址 | `replacement.create` 参数无地址 |
| 受理先分五类 | 默认进故障排障，非故障意图靠 8 个关键词降级词表 |
| 不保清单 9 条 + 跨国失效 + 非授权拆修 | `exclusions` 3 条（user_damage / unauthorized_dealer / safety） |
| 案件进度查询为登录态，绑账号 | 会话匿名，无身份字段 |
