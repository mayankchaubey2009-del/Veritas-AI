import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, Depends, status
from app.core.config import settings
from app.core.database import check_db_health
from app.models.entities import UserRole
from app.schemas.auth import AuthenticatedUser
from app.schemas.system import HealthResponse, SubsystemStatus
from app.services.audit_service import AuditService
from app.services.auth_service import require_authenticated_user, require_roles
from app.services.backup_service import BackupService
from app.services.benchmark_service import BenchmarkService

router = APIRouter(tags=["System, Health, Benchmark & Backup"])

PROCESS_START_TIME = time.monotonic()


def _get_subsystems(db_connected: bool) -> List[SubsystemStatus]:
    return [
        SubsystemStatus(
            name="Core API Gateway",
            status="OPERATIONAL",
            phase="Phase 1",
            description="FastAPI REST transport & sanitized error handler active.",
        ),
        SubsystemStatus(
            name="SQLite Forensic Store",
            status="OPERATIONAL" if db_connected else "DEGRADED",
            phase="Phase 1",
            description="Relational WAL persistence for investigations, documents, findings, and audit trail.",
        ),
        SubsystemStatus(
            name="Audit & Telemetry Ledger",
            status="OPERATIONAL" if db_connected else "DEGRADED",
            phase="Phase 1",
            description="Append-only SHA-256 hash-chained ledger for case, review, and security events.",
        ),
        SubsystemStatus(
            name="Document Ingestion & Dual-Path OCR",
            status="OPERATIONAL" if settings.enable_ocr_pipeline else "STANDBY",
            phase="Phase 2A",
            description="PyMuPDF Native PDF extraction (Path A) and PaddleOCR Visual OCR (Path B).",
        ),
        SubsystemStatus(
            name="Structure & Classification Intelligence",
            status="OPERATIONAL" if settings.enable_ocr_pipeline else "STANDBY",
            phase="Phase 2B",
            description="Automated document classification, layout tree, table grid & entity normalization.",
        ),
        SubsystemStatus(
            name="Visual Forensics (OpenCV / PyMuPDF)",
            status="OPERATIONAL" if settings.enable_cv_forensics else "STANDBY",
            phase="Phase 3",
            description="Pixel-level ELA, clone detection, and metadata anomaly inspection.",
        ),
        SubsystemStatus(
            name="Contextual Intelligence & Cross-Document Engine",
            status="OPERATIONAL",
            phase="Phase 4",
            description="Entity resolution, Decimal financial validation, cross-document contradiction detection, and evidence graph.",
        ),
        SubsystemStatus(
            name="Evidence-Grounded Reasoning & Dossier Engine",
            status="OPERATIONAL",
            phase="Phase 5",
            description="Strict evidence-manifest claim validation, AI/deterministic synthesis (A–N), and immutable PDF/JSON dossiers.",
        ),
        SubsystemStatus(
            name="Authentication, RBAC & Security Hardening",
            status="OPERATIONAL",
            phase="Phase 6",
            description="PBKDF2-HMAC-SHA256 / scrypt authentication, role-based access control, rate limiting, and upload containment.",
        ),
    ]


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    db_health = check_db_health()
    db_connected = bool(db_health.get("connected", False))
    uptime = round(time.monotonic() - PROCESS_START_TIME, 2)

    return HealthResponse(
        status="healthy" if db_connected else "degraded",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        uptime_seconds=uptime,
        timestamp=datetime.now(timezone.utc).isoformat(),
        database=db_health,
        subsystems=_get_subsystems(db_connected),
    )


@router.get("/system/config")
def get_sanitized_system_config(
    _current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Returns safe, non-sensitive configuration metadata for the Settings panel."""
    db_health = check_db_health()
    audit_verification = AuditService.verify_audit_chain()
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "environment": settings.environment,
        "cors_origins": settings.cors_origins,
        "database": {
            "engine": "SQLite (WAL Mode)",
            "file_name": db_health.get("database_file"),
            "sqlite_version": db_health.get("sqlite_version"),
            "schema_version": db_health.get("schema_version"),
            "connected": db_health.get("connected"),
            "latency_ms": db_health.get("latency_ms"),
        },
        "security": {
            "api_keys_exposed_to_client": False,
            "gemini_key_configured_on_server": settings.gemini_api_key_configured,
            "cors_restricted": True,
            "authentication_enforced": True,
            "password_kdf": "PBKDF2-HMAC-SHA256 (310,000 iterations) / scrypt",
            "allow_self_dossier_approval": settings.allow_self_dossier_approval,
            "demo_mode_enabled": settings.enable_demo_mode
            and not settings.is_production,
            "max_upload_size_mb": settings.max_upload_size_mb,
            "max_pdf_pages": settings.max_pdf_pages,
            "max_image_pixels": settings.max_image_pixels,
        },
        "audit_integrity": {
            "verified": audit_verification.get("verified"),
            "total_events_checked": audit_verification.get("total_events_checked"),
            "latest_event_hash": audit_verification.get("latest_event_hash"),
        },
        "feature_flags": {
            "ocr_pipeline_enabled": settings.enable_ocr_pipeline,
            "cv_forensics_enabled": settings.enable_cv_forensics,
            "gemini_reasoning_enabled": settings.enable_gemini_reasoning,
        },
    }


@router.post("/system/benchmark")
def run_extraction_quality_benchmark(
    _current_user: AuthenticatedUser = Depends(
        require_roles(
            UserRole.ADMIN.value,
            UserRole.INVESTIGATOR.value,
            UserRole.REVIEWER.value,
        )
    ),
) -> Dict[str, Any]:
    """Executes the isolated 10-specimen synthetic extraction & analysis quality benchmark suite."""
    return BenchmarkService.run_quality_benchmark()


@router.get("/system/backups")
def list_database_backups(
    _admin: AuthenticatedUser = Depends(require_roles(UserRole.ADMIN.value)),
) -> List[Dict[str, Any]]:
    return BackupService.list_backups()


@router.post("/system/backups", status_code=status.HTTP_201_CREATED)
def create_database_backup(
    payload: Optional[Dict[str, Any]] = Body(default=None),
    admin_user: AuthenticatedUser = Depends(require_roles(UserRole.ADMIN.value)),
) -> Dict[str, Any]:
    label = (payload or {}).get("label") if isinstance(payload, dict) else None
    return BackupService.create_backup(label=label, current_user=admin_user)


@router.post("/system/backups/{backup_id}/verify")
def verify_or_restore_database_backup(
    backup_id: str,
    payload: Optional[Dict[str, Any]] = Body(default=None),
    admin_user: AuthenticatedUser = Depends(require_roles(UserRole.ADMIN.value)),
) -> Dict[str, Any]:
    perform_restore = bool(
        (payload or {}).get("perform_restore", False)
        if isinstance(payload, dict)
        else False
    )
    return BackupService.verify_or_restore_backup(
        backup_id=backup_id,
        perform_restore=perform_restore,
        current_user=admin_user,
    )
