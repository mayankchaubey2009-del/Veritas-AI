from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import register_exception_handlers
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.context_service import ContextService
from app.services.document_service import DocumentService
from app.services.dossier_service import DossierService
from app.services.forensics_service import ForensicsService
from app.services.job_service import JobService


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    settings.validate_startup_config()
    init_db()
    if settings.enable_demo_mode and not settings.is_production:
        AuthService.ensure_demo_personas()
    JobService.recover_interrupted_jobs_on_startup()
    DocumentService.backfill_phase2b_structure_for_existing_documents()
    ForensicsService.backfill_phase3_forensics_for_existing_documents()
    ContextService.backfill_phase4_context_for_existing_investigations()
    DossierService.backfill_phase5_dossiers_for_existing_investigations()
    AuditService.ensure_hash_chain_backfilled()
    yield


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "VERITAS AI — Enterprise Document Forensics & Contextual Intelligence Engine. "
            "Phase 6 Production Readiness, Security, Reliability & Deployment API."
        ),
        lifespan=lifespan,
    )

    # Configure CORS securely for local development origins with credentials support
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With"],
    )

    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/", tags=["Root"])
    def root() -> Dict[str, Any]:
        return {
            "product": "VERITAS AI",
            "service": settings.app_name,
            "version": settings.app_version,
            "phase": "Phase 6 — Production Readiness, Security, Reliability & Deployment Preparation",
            "docs_url": "/docs",
            "health_url": "/api/health",
        }

    return app


app = create_application()
