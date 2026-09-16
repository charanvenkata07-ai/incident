from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "IncidentFlow"
    DEBUG: bool = False
    DATABASE_URL: str = "postgresql+asyncpg://incidentflow:incidentflow_dev@localhost:5432/incidentflow"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET: str = "dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 480
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    SERVICENOW_URL: str = ""
    SERVICENOW_USERNAME: str = ""
    SERVICENOW_PASSWORD: str = ""
    SERVICENOW_CLIENT_ID: str = ""
    SERVICENOW_CLIENT_SECRET: str = ""
    SERVICENOW_MOCK: bool = True
    DEFAULT_TIMEZONE: str = "Asia/Kolkata"
    AUTO_ASSIGNMENT_ENABLED: bool = True
    ASSIGNMENT_STRATEGY: str = "SKILL_PLUS_WORKLOAD"
    DRY_RUN_MODE: bool = False
    SHADOW_MODE: bool = False
    LOG_LEVEL: str = "INFO"
    # Email settings (MOCK, SMTP)
    EMAIL_PROVIDER: str = "MOCK"  # "MOCK" or "SMTP"
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "notifications@incidentflow.dev"
    SMTP_TLS: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
