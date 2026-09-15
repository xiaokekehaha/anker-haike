# 52: 模拟后端：BackendClient 协议、演示表、seed 与故障注入

**What to build:** `app/backends/protocol.py`（`get_order / get_shipment / create_service_order / get_service_order`，异常 `NotFound / Conflict / Unavailable / Timeout`）；`mock.py` 基于 Postgres：`orders_mock` 增列 `region_purchase, platform, amount, currency`，新表 `shipments_mock`、`service_orders_mock`（迁移 0006 第一部分）；`config/backends_mock.yaml` seed（≥ 10 订单覆盖 CN/EU/UK × 官方/平台/授权/非授权 × 保内/保外，≥ 6 运单，含 A6 的 UK 订单与故障注入订单 `DEMO-FAIL-*`）；`faults` 配置按 op+order_no 注入 timeout / unavailable / conflict；`haike-seed backends` 与 `make seed WHAT=backends`；`create_service_order` 对同 (order_no, type) 幂等返回既有单。

**Blocked by:** —

**Status:** done

**Owner:** —

- [ ] 单测：四个方法正常 / NotFound / 三种注入；幂等创建
- [ ] seed 幂等（重复执行不重复插入）；`receipt_reference.yaml` 既有两订单迁入并保持 A3 通过
- [ ] runbook/database.md 增加表与 seed 说明；数据文件头部标「虚构演示」

**设计依据：** 03 §5；07 §1；00 D-L3-1
