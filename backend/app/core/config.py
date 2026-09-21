from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "IncidentFlow"
    DEBUG: bool = False
    DATABASE_URL: str = "postgresql+asyncpg://incidentflow:incidentflow_dev@localhost:5432/incidentflow"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET: str = "dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 480
    APP_BASE_URL: str = "http://localhost:3000"
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://10.94.126.64:3000",
        "http://10.44.141.64:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    CORS_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|10\..*|192\.168\..*|172\..*)(:[0-9]+)?$"
    MAX_IMAGE_SIZE_MB: int = 15
    MAX_AUDIO_SIZE_MB: int = 25
    MAX_VIDEO_SIZE_MB: int = 50
    MAX_DOCUMENT_SIZE_MB: int = 25
    MAX_PROFILE_IMAGE_SIZE_MB: int = 5
    MAX_AUDIO_DURATION_SECONDS: int = 300
    ALLOWED_DOCUMENT_EXTENSIONS: list[str] = [
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".txt", ".csv", ".json", ".zip", ".tar", ".gz", ".log"
    ]
    UPLOAD_DIR: str = "uploads"
    SERVICENOW_URL: str = ""
    SERVICENOW_USERNAME: str = ""
    SERVICENOW_PASSWORD: str = ""
    SERVICENOW_CLIENT_ID: str = ""
    SERVICENOW_CLIENT_SECRET: str = ""
    SERVICENOW_WEBHOOK_SECRET: str = ""
    SERVICENOW_MOCK: bool = True
    ASSIGNMENT_GROUP: str = "Analytics – MDM L3"
    DEFAULT_TIMEZONE: str = "Asia/Kolkata"
    AUTO_ASSIGNMENT_ENABLED: bool = True
    ASSIGNMENT_STRATEGY: str = "SKILL_PLUS_WORKLOAD"
    DRY_RUN_MODE: bool = False
    SHADOW_MODE: bool = False
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "DEVELOPMENT" # "DEVELOPMENT", "STAGING", "PRODUCTION"
    AUTOMATION_MODE: str = "DRY_RUN" # "DRY_RUN", "SHADOW", "LIVE"
    # Live Pilot Controlled Configuration
    LIVE_PILOT_ENABLED: bool = False
    LIVE_PILOT_ASSIGNMENT_GROUP: str = "Analytics – MDM L3"
    LIVE_PILOT_MAX_ACTIVE_ASSIGNMENTS: int = 5
    LIVE_PILOT_ALLOWED_EMPLOYEES: list[str] = ["kiran@incidentflow.dev", "ravi@incidentflow.dev"]
    LIVE_PILOT_REQUIRE_ELIGIBILITY: bool = True
    LIVE_PILOT_REQUIRE_SERVICE_NOW_SYNC: bool = True
    # Email settings (MOCK, SMTP)
    EMAIL_PROVIDER: str = "MOCK"
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_TLS: bool = True
    # Accept both SMTP_USERNAME and SMTP_USER (legacy) — USERNAME takes precedence
    SMTP_USERNAME: str = ""
    SMTP_USER: str = ""          # legacy alias kept for backward compat
    # Accept both SMTP_FROM_EMAIL and SMTP_FROM (legacy)
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM: str = "notifications@incidentflow.dev"   # legacy alias
    SMTP_FROM_NAME: str = "IncidentFlow"
    # NOTE: SMTP_PASSWORD is intentionally left without a default so it
    # must be set explicitly in the environment. Never log this value.
    SMTP_PASSWORD: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ── computed accessors (no secrets in logs/repr) ───────────────────────────

    @property
    def smtp_username(self) -> str:
        """Resolved SMTP username: SMTP_USERNAME > SMTP_USER > ""."""
        return self.SMTP_USERNAME or self.SMTP_USER

    @property
    def smtp_password(self) -> str:
        """SMTP password. NEVER include in logs or API responses."""
        return self.SMTP_PASSWORD

    @property
    def smtp_from_address(self) -> str:
        """Resolved From address: SMTP_FROM_EMAIL > SMTP_FROM."""
        return self.SMTP_FROM_EMAIL or self.SMTP_FROM

    @property
    def smtp_from_name(self) -> str:
        """Display name used in the From header."""
        return self.SMTP_FROM_NAME or "IncidentFlow"

    def validate_production_safety(self):
        """Refuses startup if running in production with unsafe settings."""
        if self.ENVIRONMENT.upper() == "PRODUCTION":
            if self.JWT_SECRET == "dev-secret-change-in-production":
                raise ValueError("FATAL: Cannot run in PRODUCTION with default JWT_SECRET!")
            if not self.DATABASE_URL or "sqlite" in self.DATABASE_URL.lower():
                raise ValueError("FATAL: PostgreSQL DATABASE_URL must be configured in PRODUCTION!")
            if not self.REDIS_URL:
                raise ValueError("FATAL: REDIS_URL must be configured in PRODUCTION!")
            if self.DEBUG:
                raise ValueError("FATAL: DEBUG cannot be True in PRODUCTION!")
            if not self.SERVICENOW_MOCK and not (self.SERVICENOW_URL and self.SERVICENOW_USERNAME and self.SERVICENOW_PASSWORD):
                raise ValueError("FATAL: ServiceNow credentials missing for PRODUCTION environment!")

    def validate_environment_isolation(self):
        """Refuses startup if staging environment targets production ServiceNow instance, production DB/Redis, or insecure settings."""
        env = self.ENVIRONMENT.upper()
        if env in ("STAGING", "PRODUCTION"):
            # Check SQLite is not used in staging or production
            if "sqlite" in self.DATABASE_URL.lower():
                raise ValueError(f"FATAL: Database must be PostgreSQL in {env}. SQLite is strictly prohibited!")
            
            # Insecure configuration checks
            if self.DEBUG:
                raise ValueError(f"FATAL: DEBUG cannot be True in {env}!")
                
        if env == "STAGING":
            # Check production database or redis is not targeted in staging
            if "production" in self.DATABASE_URL.lower() or "prod_db" in self.DATABASE_URL.lower():
                raise ValueError("FATAL ENVIRONMENT ISOLATION ERROR: Staging cannot target production database!")
                
            if "prod-redis" in self.REDIS_URL.lower() or "production" in self.REDIS_URL.lower():
                raise ValueError("FATAL ENVIRONMENT ISOLATION ERROR: Staging cannot target production Redis!")

            if self.EMAIL_PROVIDER.upper() in ("PRODUCTION", "LIVE"):
                raise ValueError("FATAL ENVIRONMENT ISOLATION ERROR: Staging cannot use PRODUCTION email provider!")

            if self.SERVICENOW_URL:
                from urllib.parse import urlparse
                parsed = urlparse(self.SERVICENOW_URL)
                hostname = (parsed.hostname or "").lower()
                
                # Prohibit production instance names in staging
                prod_indicators = ["-prod.", ".prod.", "production"]
                if any(ind in hostname for ind in prod_indicators) or (hostname.endswith(".service-now.com") and not any(tag in hostname for tag in ("dev", "stage", "staging", "test", "qa", "uat", "sandbox"))):
                    raise ValueError(f"FATAL ENVIRONMENT ISOLATION ERROR: Staging cannot target production ServiceNow instance '{hostname}'!")
                
                # Prohibit targeting localhost in staging
                if hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
                    raise ValueError("FATAL: Staging cannot configure ServiceNow URL as localhost!")

settings = Settings()
