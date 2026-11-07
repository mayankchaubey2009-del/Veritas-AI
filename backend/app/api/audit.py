from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from app.schemas.auth import AuthenticatedUser
from app.schemas.investigation import AuditLogResponse
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService, require_authenticated_user
from app.services.investigation_service import InvestigationService

router = APIRouter(prefix="/audit-logs", tags=["Audit History"])


@router.get("", response_model=List[AuditLogResponse])
def list_audit_logs(
    investigation_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> List[AuditLogResponse]:
    if investigation_id:
        AuthService.check_investigation_access(
            investigation_id, current_user, require_write=False
        )
    return InvestigationService.list_audit_logs(
        limit=limit,
        investigation_id=investigation_id,
        current_user=current_user,
    )


@router.get(
    "/verify",
    summary="Verify cryptographic SHA-256 hash-chain integrity across the append-only audit ledger",
)
def verify_audit_ledger_integrity(
    _current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> Dict[str, Any]:
    return AuditService.verify_audit_chain()
