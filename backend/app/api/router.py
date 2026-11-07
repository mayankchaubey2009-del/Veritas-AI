from fastapi import APIRouter
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.context import router as context_router
from app.api.dashboard import router as dashboard_router
from app.api.documents import router as documents_router
from app.api.dossiers import router as dossiers_router
from app.api.forensics import router as forensics_router
from app.api.health import router as health_router
from app.api.investigations import router as investigations_router
from app.api.jobs import router as jobs_router

api_router = APIRouter(prefix="/api")

api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(dashboard_router)
api_router.include_router(investigations_router)
api_router.include_router(documents_router)
api_router.include_router(forensics_router)
api_router.include_router(context_router)
api_router.include_router(dossiers_router)
api_router.include_router(jobs_router)
api_router.include_router(audit_router)
