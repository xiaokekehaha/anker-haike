"""与产品/计划库一致：冻结配置进内存，seed 将同一份参考数据写入数据库。"""

from functools import lru_cache

from app.warranty.service import ReceiptLookup, ReferenceData


@lru_cache(maxsize=1)
def get_receipt_lookup() -> ReceiptLookup:
    from app.settings import settings

    return ReceiptLookup(ReferenceData.from_yaml(settings.receipt_reference_config_path))
