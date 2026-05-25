from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Together"
    secret_key: str = "dev-secret-change-me"
    database_url: str = "sqlite:///./dev.db"
    uploads_dir: str = "./dev_uploads"
    session_cookie_name: str = "together_session"
    session_days: int = 30
    grace_hours: int = 6
    debug: bool = True


settings = Settings()

UPLOADS_PATH = Path(settings.uploads_dir)
UPLOADS_PATH.mkdir(parents=True, exist_ok=True)
