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

    health_timeout_s: float = Field(default=2.0, alias="HEALTH_TIMEOUT_S")
    static_dir: str = Field(default=str(REPO_ROOT / "frontend" / "dist"), alias="STATIC_DIR")

    def redacted(self) -> dict[str, str]:
        """用于启动日志：去掉口令与 key。"""
        return {
            "app_env": self.app_env,
            "database_url": _redact_url(self.database_url),
            "redis_url": _redact_url(self.redis_url),
            "weknora_base_url": self.weknora_base_url,
            "weknora_api_key": "set" if self.weknora_api_key else "missing",
            "model_lane": self.model_lane,
        }


def _redact_url(url: str) -> str:
    if "@" not in url:
        return url
    scheme_and_creds, rest = url.split("@", 1)
    scheme = scheme_and_creds.split("//", 1)[0]
    return f"{scheme}//***@{rest}"


settings = Settings()
