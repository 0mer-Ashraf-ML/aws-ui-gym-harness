"""
Application configuration settings (v2 Task Runners Only)
"""
import json
from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # Application settings
    APP_NAME: str = "RL Gym Harness Task Runner"
    VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8000, env="PORT")
    
    # CORS settings
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8080,http://localhost:8501,http://localhost:8503",
        env="ALLOWED_ORIGINS"
    )
    
    @property
    def allowed_origins_list(self) -> List[str]:
        """Convert ALLOWED_ORIGINS string to list"""
        if not self.ALLOWED_ORIGINS.strip():
            return ["http://localhost:3000", "http://localhost:8080", "http://localhost:8501", "http://localhost:8503"]
        try:
            return json.loads(self.ALLOWED_ORIGINS)
        except json.JSONDecodeError:
            # If JSON parsing fails, treat as comma-separated string
            return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(',') if origin.strip()]
    
    # Database settings
    DATABASE_URL: str = Field(
        default="postgresql://app_user:password@localhost:5432/harness_main_aws",
        env="DATABASE_URL"
    )
    
    # Redis settings (for Celery)
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        env="REDIS_URL"
    )
    
    # API Keys
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    OPENAI_API_KEY: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    OPENAI_ORG: Optional[str] = Field(default=None, env="OPENAI_ORG")
    
    # Gemini API Configuration
    GEMINI_API_KEY: Optional[str] = Field(default=None, env="GEMINI_API_KEY")
    GOOGLE_API_KEY: Optional[str] = Field(default=None, env="GOOGLE_API_KEY")  # Alternative key name
    
    # Gemini-specific settings (Google's recommendations - DO NOT MODIFY without testing)
    GEMINI_MODEL: str = "gemini-2.5-computer-use-preview-10-2025"
    GEMINI_SCREEN_WIDTH: int = 1440  # Google recommended resolution
    GEMINI_SCREEN_HEIGHT: int = 900   # Google recommended resolution
    GEMINI_TEMPERATURE: float = 0.0   # Deterministic for automation (Google recommended)
    GEMINI_MAX_SCREENSHOTS: int = 3   # Token optimization (Google recommended)
    GEMINI_MAX_TURNS: int = 100
    GEMINI_TOP_P: float = 0.95
    GEMINI_TOP_K: int = 40
    GEMINI_MAX_OUTPUT_TOKENS: int = 6144  # Reduced from 8192 to discourage verbose outputs
    GEMINI_MAX_API_RETRIES: int = 3
    GEMINI_API_RETRY_DELAY: int = 2  # seconds
    
    # Simple token optimization: keep recent conversation history only
    # NOTE: Gemini tends to use 26-31x more iterations than Anthropic for complex tasks
    # More aggressive trimming helps manage token costs but won't solve efficiency issues
    GEMINI_MAX_CONVERSATION_TURNS: int = Field(
        default=8,  # Reduced from 10 to match Anthropic and optimize tokens
        env="GEMINI_MAX_CONVERSATION_TURNS",
        description="Max conversation turns to keep (reduced due to high iteration counts)"
    )
    
    # Anthropic token optimization
    ANTHROPIC_MAX_TOKENS: int = Field(
        default=3072,  # Reduced from 4096
        env="ANTHROPIC_MAX_TOKENS",
        description="Max output tokens"
    )
    ANTHROPIC_MAX_CONVERSATION_MESSAGES: int = Field(
        default=20,  # Keep last 20 messages (fallback)
        env="ANTHROPIC_MAX_CONVERSATION_MESSAGES",
        description="Max conversation messages to keep (fallback)"
    )
    ANTHROPIC_MAX_CONVERSATION_TURNS: int = Field(
        default=8,  # Keep last 8 complete turns (improved from 3)
        env="ANTHROPIC_MAX_CONVERSATION_TURNS",
        description="Max conversation turns to keep (turn-based retention)"
    )
    
    # Frontend base URL for building deep links (e.g., reports → iteration monitor)
    FRONTEND_BASE_URL: str = Field(default="http://localhost:8503", env="FRONTEND_BASE_URL")
    
    # CUA Container settings (temporary - for compatibility)
    CUA_CONTAINER_BASE_PORT: int = Field(default=9000, env="CUA_CONTAINER_BASE_PORT")
    CUA_CONTAINER_IMAGE: str = Field(default="rl-gym-harness-ui-anthropic-cua", env="CUA_CONTAINER_IMAGE")
    CUA_CONTAINER_NETWORK: str = Field(default="rl-gym-harness-ui_app-network", env="CUA_CONTAINER_NETWORK")
    CUA_CONTAINER_MAX_NAME_LENGTH: int = Field(default=50, env="CUA_CONTAINER_MAX_NAME_LENGTH")
    CONTAINER_READINESS_TIMEOUT: int = Field(default=120, env="CONTAINER_READINESS_TIMEOUT")
    CONTAINER_HEALTH_CHECK_INTERVAL: int = Field(default=5, env="CONTAINER_HEALTH_CHECK_INTERVAL")
    CONTAINER_CLEANUP_INTERVAL: int = Field(default=300, env="CONTAINER_CLEANUP_INTERVAL")
    MAX_CONTAINER_AGE: int = Field(default=3600, env="MAX_CONTAINER_AGE")
    
    # Timeout settings
    MAX_WAIT_TIME: int = Field(default=180, env="MAX_WAIT_TIME")
    CHECK_INTERVAL: int = Field(default=2, env="CHECK_INTERVAL")
    MAX_RETRIES: int = Field(default=3, env="MAX_RETRIES")
    RETRY_DELAY: int = Field(default=2, env="RETRY_DELAY")
    
    # Results directory
    RESULTS_DIR: str = Field(default="results", env="RESULTS_DIR")

    # Tmp directory
    APP_TMP_DIR: str = Field(default="tmp", env="APP_TMP_DIR")

    # Verifiers directory
    VERIFIERS_DIR: str = Field(default="verifiers", env="VERIFIERS_DIR")

    # Task CSV file path
    TASKS_CSV_PATH: str = Field(default="tasks/production_tasks.csv", env="TASKS_CSV_PATH")
    CSV_FILE: str = Field(default="tasks/production_tasks.csv", env="CSV_FILE")
    DEFAULT_TASK_ID: str = Field(default="clear-cart", env="DEFAULT_TASK_ID")
    
    # Celery settings
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/0", env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/0", env="CELERY_RESULT_BACKEND")
    CELERY_WORKER_CONCURRENCY: int = Field(default=20, env="CELERY_WORKER_CONCURRENCY")
    STALE_EXECUTING_THRESHOLD_SECONDS: int = Field(
        default=10 * 60,
        env="STALE_EXECUTING_THRESHOLD_SECONDS"
    )
    AUTO_RECOVER_INTERVAL_SECONDS: int = Field(
        default=10 * 60,
        env="AUTO_RECOVER_INTERVAL_SECONDS",
    )
    
    # Firefox cleanup settings
    FIREFOX_CLEANUP_BUFFER_MINUTES: int = Field(
        default=10,
        env="FIREFOX_CLEANUP_BUFFER_MINUTES",
        description="Unified cleanup threshold (in minutes) for Firefox processes. "
                    "Scenario 1 (orphaned): Kill processes older than this value when no tasks are executing. "
                    "Scenario 2 (dangling): Use as buffer added to oldest executing task age. "
                    "Example: If set to 10 min, orphaned processes > 10 min are killed, "
                    "or if oldest task is 70 min old, kill processes > 80 min."
    )
    
    # WebSocket settings
    WS_HEARTBEAT_INTERVAL: int = Field(default=30, env="WS_HEARTBEAT_INTERVAL")
    
    # Unified Task Runner settings (default to True for new unified strategy)
    USE_UNIFIED_RUNNER: bool = Field(default=True, env="USE_UNIFIED_RUNNER")
    UNIFIED_RUNNER_TIMEOUT: int = Field(default=7200, env="UNIFIED_RUNNER_TIMEOUT")  # 120 minutes (2 hours)
    
    # Task configuration defaults
    DEFAULT_MAX_ITERATIONS: int = Field(default=100, env="DEFAULT_MAX_ITERATIONS")
    DEFAULT_TIMEOUT_MINUTES: int = Field(default=6, env="DEFAULT_TIMEOUT_MINUTES")
    
    # Step limit settings
    MAX_STEPS_LIMIT: int = Field(
        default=400,
        env="MAX_STEPS_LIMIT",
        description="Maximum number of iterations/turns allowed before task termination"
    )
    
    # Authentication settings
    SECRET_KEY: str = Field(default="your-secret-key-change-this-in-production", env="SECRET_KEY")
    ALGORITHM: str = Field(default="HS256", env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")  # 30 minutes
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, env="REFRESH_TOKEN_EXPIRE_DAYS")  # 7 days
    
    # Google OAuth settings
    GOOGLE_CLIENT_ID: Optional[str] = Field(default=None, env="GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: Optional[str] = Field(default=None, env="GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI: str = Field(default="http://localhost:3000/auth/callback", env="GOOGLE_REDIRECT_URI")
    GOOGLE_CLOCK_SKEW_TOLERANCE: int = Field(default=60, env="GOOGLE_CLOCK_SKEW_TOLERANCE")  # seconds
    ACCESS_CONTROL_EXCEL_PATH: str = Field(
        default="../access/Access_sheet.xlsx",
        env="ACCESS_CONTROL_EXCEL_PATH",
        description="Path to Excel file containing Admins/Users sheets with name/email columns for access control. Can be relative to backend directory or absolute. Override via ACCESS_CONTROL_EXCEL_PATH env var.",
    )
    
    # Admin settings
    ADMIN_EMAILS: str = Field(default="", env="ADMIN_EMAILS")  # Comma-separated list of admin emails
    
    # Authentication bypass settings
    DISABLE_AUTH: bool = Field(default=False, env="DISABLE_AUTH")  # Set to True to disable authentication
    
    # Mock states feature flag (temporary - for testing when gyms haven't implemented window.get_states)
    USE_MOCK_STATES_ENDPOINT: bool = Field(
        default=False, 
        env="USE_MOCK_STATES_ENDPOINT",
        description="When True, uses mock data instead of browser automation for window.get_states()"
    )
    
    # Config files feature flag (for testing - load grader_config and simulator_config from JSON files)
    USE_CONFIG_FILES: bool = Field(
        default=False,
        env="USE_CONFIG_FILES",
        description="Load grader_config and simulator_config from JSON files instead of database (for testing)"
    )
    
    @property
    def admin_emails_list(self) -> List[str]:
        """Convert ADMIN_EMAILS string to list"""
        if not self.ADMIN_EMAILS.strip():
            return []
        return [email.strip().lower() for email in self.ADMIN_EMAILS.split(',') if email.strip()]

    @property
    def frontend_base_url(self) -> str:
        """Normalized frontend base URL without trailing slash."""
        return self.FRONTEND_BASE_URL.rstrip('/')
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields from .env file

# Create settings instance
settings = Settings()

# Validate required settings
def validate_settings():
    """Validate required settings"""
    if not settings.ANTHROPIC_API_KEY:
        print("⚠️ ANTHROPIC_API_KEY is not set. Task execution with Anthropic runner will fail.")
    if not settings.OPENAI_API_KEY:
        print("⚠️ OPENAI_API_KEY is not set. Task execution with OpenAI runner will fail.")
    
    # Create results directory if it doesn't exist
    Path(settings.RESULTS_DIR).mkdir(parents=True, exist_ok=True)
    
    # Validate tasks CSV file exists (warn but don't fail)
    if not Path(settings.TASKS_CSV_PATH).exists():
        print(f"⚠️ Tasks CSV file not found: {settings.TASKS_CSV_PATH}")
        print("   The application will still start, but task execution may fail.")

# Validate settings on import
validate_settings()
