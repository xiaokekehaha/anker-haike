"""运行配置：全部来自环境变量，密钥不落日志。"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 仓库根目录：本机开发时 .env、config/、frontend/dist 都以它为基准；容器内由环境变量覆盖
REPO_ROOT = Path(__file__).resolve().parents[2]
# 把 .env 也放进 os.environ：模型厂商 key 按 models.yaml 的 api_key_env 名从环境读取，已有环境变量优先
load_dotenv(REPO_ROOT / ".env", override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = Field(default="dev", alias="APP_ENV")
    port: int = Field(default=8000, alias="PORT")

    database_url: str = Field(
        default="postgresql://haike:haike@localhost:5432/haike", alias="DATABASE_URL"
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    weknora_base_url: str = Field(default="http://localhost:8080", alias="WEKNORA_BASE_URL")
    weknora_api_key: str = Field(default="", alias="WEKNORA_API_KEY")

    model_lane: str = Field(default="domestic", alias="MODEL_LANE")
    models_config_path: str = Field(
        default=str(REPO_ROOT / "config" / "models.yaml"), alias="MODELS_CONFIG_PATH"
    )

    catalog_config_path: str = Field(
        default=str(REPO_ROOT / "config" / "products.yaml"), alias="CATALOG_CONFIG_PATH"
    )
    plans_config_path: str = Field(
        default=str(REPO_ROOT / "config" / "plans.yaml"), alias="PLANS_CONFIG_PATH"
    )
    receipt_reference_config_path: str = Field(
        default=str(REPO_ROOT / "config" / "receipt_reference.yaml"),
        alias="RECEIPT_REFERENCE_CONFIG_PATH",
    )
    fault_cards_config_path: str = Field(
        default=str(REPO_ROOT / "config" / "fault_cards.yaml"), alias="FAULT_CARDS_CONFIG_PATH"
    )
    rules_config_path: str = Field(
        default=str(REPO_ROOT / "config" / "rules" / "safety_terms.yaml"), alias="RULES_CONFIG_PATH"
    )

    observability_log_path: str = Field(
        default=str(REPO_ROOT / "logs" / "events.jsonl"), alias="OBSERVABILITY_LOG_PATH"
    )
    langfuse_enabled: bool = Field(default=False, alias="LANGFUSE_ENABLED")
    langfuse_base_url: str = Field(default="http://localhost:3000", alias="LANGFUSE_BASE_URL")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")

    # 票 43：回放模式。REPLAY_CASE_ID 非空即启用：ReplayRouter / ReplayKnowledgeAdapter 只按 replay/<case_id>/ 录制包命中；
    # 清单 {prompt_ver, models_ver, kb_ver, rules_ver} 与当前不符时启动报 replay_incompatible。
    replay_case_id: str = Field(default="", alias="REPLAY_CASE_ID")
    replay_dir: str = Field(default=str(REPO_ROOT / "replay"), alias="REPLAY_DIR")
    # kb_ver 来源：知识库入库 manifest（票 26）；容器里没有 manifest 时可用 KB_VER 直接给出
    kb_manifest_path: str = Field(
        default=str(REPO_ROOT / "data" / "knowledge" / "manifest.json"), alias="KB_MANIFEST_PATH"
    )
    kb_ver: str = Field(default="", alias="KB_VER")

    health_timeout_s: float = Field(default=2.0, alias="HEALTH_TIMEOUT_S")
    # 票 48：数据保留（07 §12 记忆分类 TTL）与人工删除接口的口令；ADMIN_TOKEN 为空则 DELETE /sessions/{id} 关闭
    retention_session_hours: float = Field(default=24.0, alias="RETENTION_SESSION_HOURS")
    retention_trace_days: float = Field(default=7.0, alias="RETENTION_TRACE_DAYS")
    retention_interval_s: float = Field(default=600.0, alias="RETENTION_INTERVAL_S")
    admin_token: str = Field(default="", alias="ADMIN_TOKEN")
    db_pool_max: int = Field(default=10, alias="DB_POOL_MAX")
    static_dir: str = Field(default=str(REPO_ROOT / "frontend" / "dist"), alias="STATIC_DIR")

    def redacted(self) -> dict[str, str]:
        """用于启动日志：去掉口令与 key。"""
        return {
            "app_env": self.app_env,
            "database_url": _redact_url(self.database_url),
            "redis_url": _redact_url(self.redis_url),
            "weknora_base_url": self.weknora_base_url,
            "weknora_api_key": "set" if self.weknora_api_key else "missing",
            "admin_token": "set" if self.admin_token else "missing",
            "retention": f"sessions={self.retention_session_hours}h traces={self.retention_trace_days}d",
            "model_lane": self.model_lane,
            "replay_case_id": self.replay_case_id or "-",
        }


def _redact_url(url: str) -> str:
    if "@" not in url:
        return url
    scheme_and_creds, rest = url.split("@", 1)
    scheme = scheme_and_creds.split("//", 1)[0]
    return f"{scheme}//***@{rest}"


settings = Settings()
