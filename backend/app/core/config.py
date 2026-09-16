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
    ENVIRONMENT: str = "DEVELOPMENT" # "DEVELOPMENT", "STAGING", "PRODUCTION"
    AUTOMATION_MODE: str = "DRY_RUN" # "DRY_RUN", "SHADOW", "LIVE"
    # Email settings (MOCK, STAGING, PRODUCTION, SMTP)
    EMAIL_PROVIDER: str = "MOCK"
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "notifications@incidentflow.dev"
    SMTP_TLS: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def validate_production_safety(self):
        """Refuses startup if running in production with unsafe settings."""
        if self.ENVIRONMENT.upper() == "PRODUCTION":
            if self.JWT_SECRET == "dev-secret-change-in-production":
                raise ValueError("FATAL: Cannot run in PRODUCTION with default JWT_SECRET!")
            if not self.DATABASE_URL:
                raise ValueError("FATAL: DATABASE_URL must be configured in PRODUCTION!")
            if not self.REDIS_URL:
                raise ValueError("FATAL: REDIS_URL must be configured in PRODUCTION!")
            if not self.SERVICENOW_MOCK and not (self.SERVICENOW_URL and self.SERVICENOW_USERNAME and self.SERVICENOW_PASSWORD):
                raise ValueError("FATAL: ServiceNow credentials missing for PRODUCTION environment!")


settings = Settings()
