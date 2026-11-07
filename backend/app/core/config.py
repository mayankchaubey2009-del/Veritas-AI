import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables from backend/.env if present
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "VERITAS AI Forensic Intelligence Engine")
    app_version: str = os.getenv("APP_VERSION", "2.0.0-phase6")
    environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))

    # CORS configuration
    cors_origins_raw: str = os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    )

    # SQLite path
    database_path: str = os.getenv(
        "DATABASE_PATH", str(BASE_DIR / "data" / "veritas_forensics.db")
    )
    backups_dir: str = os.getenv(
        "BACKUPS_DIR", str(BASE_DIR / "storage" / "backups")
    )

    # Secure private document storage (strictly outside frontend/)
    storage_dir: str = os.getenv(
        "STORAGE_DIR", str(BASE_DIR / "storage" / "documents")
    )
    forensics_artifacts_dir: str = os.getenv(
        "FORENSICS_ARTIFACTS_DIR", str(BASE_DIR / "storage" / "forensics_artifacts")
    )
    dossiers_storage_dir: str = os.getenv(
        "DOSSIERS_STORAGE_DIR", str(BASE_DIR / "storage" / "dossiers")
    )
    max_upload_size_mb: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "25"))
    max_files_per_upload: int = int(os.getenv("MAX_FILES_PER_UPLOAD", "10"))
    max_pdf_pages: int = int(os.getenv("MAX_PDF_PAGES", "100"))
    max_image_pixels: int = int(os.getenv("MAX_IMAGE_PIXELS", "36000000"))
    request_timeout_seconds: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "120"))
    native_pdf_min_chars_per_page: int = int(
        os.getenv("NATIVE_PDF_MIN_CHARS_PER_PAGE", "15")
    )
    forensics_max_image_dimension: int = int(
        os.getenv("FORENSICS_MAX_IMAGE_DIMENSION", "2000")
    )

    # Authentication, Session & Access Control Settings
    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "veritas_session")
    session_ttl_seconds: int = int(os.getenv("SESSION_TTL_SECONDS", "28800"))  # 8 hours
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "false").lower() in ("true", "1", "yes")
    cookie_samesite: str = os.getenv("COOKIE_SAMESITE", "lax")
    login_rate_limit_attempts: int = int(os.getenv("LOGIN_RATE_LIMIT_ATTEMPTS", "5"))
    login_rate_limit_window_seconds: int = int(
        os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300")
    )
    allow_self_dossier_approval: bool = (
        os.getenv("ALLOW_SELF_DOSSIER_APPROVAL", "false").lower() in ("true", "1", "yes")
    )
    enable_demo_mode: bool = (
        os.getenv("ENABLE_DEMO_MODE", "true").lower() in ("true", "1", "yes")
    )

    # Server-side AI credentials & feature flags (Never serialized to public responses)
    gemini_api_key_configured: bool = bool(os.getenv("GEMINI_API_KEY", "").strip())
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    enable_ocr_pipeline: bool = (
        os.getenv("ENABLE_OCR_PIPELINE", "true").lower() == "true"
    )
    enable_cv_forensics: bool = (
        os.getenv("ENABLE_CV_FORENSICS", "true").lower() == "true"
    )
    enable_gemini_reasoning: bool = (
        os.getenv("ENABLE_GEMINI_REASONING", "false").lower() == "true"
    )

    @staticmethod
    def get_server_gemini_api_key() -> str:
        """Retrieves GEMINI_API_KEY strictly on the server without storing it on serialized model fields."""
        return os.getenv("GEMINI_API_KEY", "").strip()

    @staticmethod
    def get_bootstrap_token() -> str:
        """Retrieves optional VERITAS_BOOTSTRAP_TOKEN from server environment."""
        return os.getenv("VERITAS_BOOTSTRAP_TOKEN", "").strip()

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def effective_cookie_secure(self) -> bool:
        return True if self.is_production else self.cookie_secure

    @property
    def resolved_backups_dir(self) -> Path:
        bk_p = Path(self.backups_dir)
        if not bk_p.is_absolute():
            bk_p = (BASE_DIR / bk_p).resolve()
        bk_p.mkdir(parents=True, exist_ok=True)
        return bk_p

    def validate_startup_config(self) -> List[str]:
        """Validates configuration invariants at startup and returns any warnings."""
        warnings: List[str] = []
        if self.is_production:
            if self.debug:
                warnings.append("DEBUG mode should be disabled in production.")
            if "*" in self.cors_origins:
                warnings.append("Wildcard CORS origin '*' is prohibited in production.")
            if self.enable_demo_mode:
                warnings.append("ENABLE_DEMO_MODE is ignored when ENVIRONMENT=production.")
        if self.max_upload_size_mb <= 0 or self.max_upload_size_mb > 100:
            warnings.append(f"Unusual MAX_UPLOAD_SIZE_MB={self.max_upload_size_mb}.")
        return warnings

    @property
    def cors_origins(self) -> List[str]:
        return [
            origin.strip()
            for origin in self.cors_origins_raw.split(",")
            if origin.strip()
        ]

    @property
    def resolved_db_path(self) -> Path:
        db_p = Path(self.database_path)
        if not db_p.is_absolute():
            db_p = (BASE_DIR / db_p).resolve()
        db_p.parent.mkdir(parents=True, exist_ok=True)
        return db_p

    @property
    def resolved_sqlite_path(self) -> Path:
        return self.resolved_db_path

    @property
    def resolved_storage_dir(self) -> Path:
        st_p = Path(self.storage_dir)
        if not st_p.is_absolute():
            st_p = (BASE_DIR / st_p).resolve()
        st_p.mkdir(parents=True, exist_ok=True)
        return st_p

    @property
    def resolved_forensics_artifacts_dir(self) -> Path:
        fa_p = Path(self.forensics_artifacts_dir)
        if not fa_p.is_absolute():
            fa_p = (BASE_DIR / fa_p).resolve()
        fa_p.mkdir(parents=True, exist_ok=True)
        return fa_p

    @property
    def resolved_dossiers_storage_dir(self) -> Path:
        ds_p = Path(self.dossiers_storage_dir)
        if not ds_p.is_absolute():
            ds_p = (BASE_DIR / ds_p).resolve()
        ds_p.mkdir(parents=True, exist_ok=True)
        return ds_p

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


settings = Settings()
