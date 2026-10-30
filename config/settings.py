"""
Application configuration and logging management.
Loads environment variables safely, defines system constants, and sets up structured logging.
"""

import os
import logging
import secrets
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
REPORTS_DIR = BASE_DIR / "reports"
SAMPLE_DATA_DIR = BASE_DIR / "sample_data"

# Ensure directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Load .env if present
env_file = BASE_DIR / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    load_dotenv(BASE_DIR / ".env.example")


@dataclass(frozen=True)
class Settings:
    # App general
    APP_NAME: str = os.getenv("APP_NAME", "Intelligent Business Process Monitoring & Auto-Alert System")
    APP_ENV: str = os.getenv("APP_ENV", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
    SEED_DEMO_DATA: bool = os.getenv(
        "SEED_DEMO_DATA",
        "true" if os.getenv("APP_ENV", "development").lower() == "development" else "false",
    ).lower() in ("true", "1", "yes")
    TIMEZONE: str = os.getenv("TIMEZONE", "UTC")
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'business_monitor.db'}")
    API_TOKEN_SECRET: str = os.getenv("API_TOKEN_SECRET") or secrets.token_urlsafe(32)
    API_TOKEN_TTL_MINUTES: int = int(os.getenv("API_TOKEN_TTL_MINUTES", "480"))
    API_CORS_ORIGINS: str = os.getenv(
        "API_CORS_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501"
    )

    # Monitoring & thresholds
    DEFAULT_MONITORING_INTERVAL_MINUTES: int = int(os.getenv("DEFAULT_MONITORING_INTERVAL_MINUTES", "60"))
    TRANSACTION_FAILURE_THRESHOLD_PCT: float = float(os.getenv("TRANSACTION_FAILURE_THRESHOLD_PCT", "5.0"))
    COST_ANOMALY_ZSCORE_THRESHOLD: float = float(os.getenv("COST_ANOMALY_ZSCORE_THRESHOLD", "2.5"))
    COST_BUDGET_OVERRUN_THRESHOLD_PCT: float = float(os.getenv("COST_BUDGET_OVERRUN_THRESHOLD_PCT", "20.0"))
    DEPARTMENT_SLA_MIN_COMPLETION_RATE: float = float(os.getenv("DEPARTMENT_SLA_MIN_COMPLETION_RATE", "80.0"))
    INCIDENT_RESOLUTION_SLA_HOURS: int = int(os.getenv("INCIDENT_RESOLUTION_SLA_HOURS", "48"))

    # SMTP & Alert Email
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "alerts@businessmonitor.local")
    ALERT_RECIPIENT_EMAIL: str = os.getenv("ALERT_RECIPIENT_EMAIL", "ops-manager@businessmonitor.local")
    ALERT_MIN_SEVERITY: str = os.getenv("ALERT_MIN_SEVERITY", "High")
    ENABLE_EMAIL_ALERTS: bool = os.getenv("ENABLE_EMAIL_ALERTS", "False").lower() in ("true", "1", "yes")

    @property
    def is_smtp_configured(self) -> bool:
        """Determines if valid SMTP credentials and host are configured."""
        return bool(self.SMTP_HOST and self.SMTP_USERNAME and self.SMTP_PASSWORD)


settings = Settings()
if settings.API_TOKEN_TTL_MINUTES < 1:
    raise ValueError("API_TOKEN_TTL_MINUTES must be a positive integer.")
if settings.APP_ENV.lower() in ("production", "prod") and not os.getenv("API_TOKEN_SECRET"):
    raise RuntimeError("API_TOKEN_SECRET must be set outside development environments.")

# Severity & Status Constants
SEVERITIES = ["Critical", "High", "Medium", "Low"]
ALERT_STATUSES = ["New", "Acknowledged", "In Progress", "Resolved", "Dismissed"]
INCIDENT_STATUSES = ["Open", "In Progress", "Resolved"]
CATEGORIES = [
    "Tasks",
    "Orders",
    "Transactions",
    "Expenses",
    "Department Performance",
    "Recurring Issues",
    "SLA Breaches",
]

# Configure root logger
LOG_FILE = LOGS_DIR / "app.log"
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("business_monitor")
