"""产品目录（票 19）：配置化 seed、products 表、L4 内存缓存与 lookup_product 匹配。"""

from app.catalog.service import CatalogError, ProductCatalog, ProductRecord, load_catalog_config

__all__ = ["CatalogError", "ProductCatalog", "ProductRecord", "load_catalog_config"]
