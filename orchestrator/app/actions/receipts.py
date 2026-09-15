from haike_contracts.common import Receipt


def render_receipt(receipt: Receipt) -> str:
    number = receipt.service_order_no or receipt.tracking_no or receipt.order_no or ""
    return f"{number}：{receipt.status}。{receipt.next_step}（来源：{receipt.source}）"
