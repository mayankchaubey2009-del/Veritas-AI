from typing import List, Optional
from fastapi import APIRouter, Body, Depends
from fastapi.responses import FileResponse
from app.models.entities import UserRole
from app.schemas.auth import AuthenticatedUser
from app.schemas.dossier import (
    DossierDetailResponse,
    DossierGenerateRequest,
    DossierReviewRequest,
    DossierSummaryResponse,
    InvestigationReasoningResponse,
    ReasoningGenerateRequest,
)
from app.services.auth_service import (
    AuthService,
    require_authenticated_user,
    require_roles,
)
from app.services.dossier_service import DossierService

router = APIRouter(tags=["AI Investigation Reasoning & Dossier Generation"])


@router.post(
    "/investigations/{investigation_id}/reasoning/generate",
    response_model=InvestigationReasoningResponse,
    summary="Execute Phase 5 Evidence-Grounded Investigation Reasoning across Phases 1–4 artifacts",
)
def generate_investigation_reasoning(
    investigation_id: str,
    payload: Optional[ReasoningGenerateRequest] = Body(default=None),
    current_user: AuthenticatedUser = Depends(
        require_roles(
            UserRole.ADMIN.value,
            UserRole.INVESTIGATOR.value,
            UserRole.REVIEWER.value,
        )
    ),
) -> InvestigationReasoningResponse:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=True
    )
    return DossierService.generate_investigation_reasoning(
        investigation_id=investigation_id,
        payload=payload,
        current_user=current_user,
    )


@router.get(
    "/investigations/{investigation_id}/reasoning",
    response_model=InvestigationReasoningResponse,
    summary="Get the latest Evidence-Grounded Investigation Reasoning run (sections A–N, validated claims, manifest, questions, verification steps)",
)
def get_investigation_reasoning(
    investigation_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> InvestigationReasoningResponse:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=False
    )
    return DossierService.get_investigation_reasoning(
        investigation_id=investigation_id
    )


@router.post(
    "/investigations/{investigation_id}/dossiers/generate",
    response_model=DossierDetailResponse,
    summary="Compile and persist a new immutable PDF & JSON Investigation Dossier version",
)
def generate_investigation_dossier(
    investigation_id: str,
    payload: Optional[DossierGenerateRequest] = Body(default=None),
    current_user: AuthenticatedUser = Depends(
        require_roles(
            UserRole.ADMIN.value,
            UserRole.INVESTIGATOR.value,
            UserRole.REVIEWER.value,
        )
    ),
) -> DossierDetailResponse:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=True
    )
    return DossierService.generate_investigation_dossier(
        investigation_id=investigation_id,
        payload=payload,
        current_user=current_user,
    )


@router.get(
    "/investigations/{investigation_id}/dossiers",
    response_model=List[DossierSummaryResponse],
    summary="List all immutable dossier versions generated for an investigation",
)
def list_investigation_dossiers(
    investigation_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> List[DossierSummaryResponse]:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=False
    )
    return DossierService.list_investigation_dossiers(
        investigation_id=investigation_id
    )


@router.get(
    "/dossiers/{dossier_id}",
    response_model=DossierDetailResponse,
    summary="Get detailed Investigation Dossier metadata, full grounded reasoning, and review history",
)
def get_dossier_detail(
    dossier_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> DossierDetailResponse:
    detail = DossierService.get_dossier_detail(dossier_id=dossier_id)
    AuthService.check_investigation_access(
        detail.investigation_id, current_user, require_write=False
    )
    return detail


@router.get(
    "/dossiers/{dossier_id}/pdf",
    summary="Download the immutable PDF Investigation Dossier artifact",
)
def download_dossier_pdf(
    dossier_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> FileResponse:
    detail = DossierService.get_dossier_detail(dossier_id=dossier_id)
    AuthService.check_investigation_access(
        detail.investigation_id, current_user, require_write=False
    )
    pdf_path, filename = DossierService.get_dossier_pdf_path(dossier_id=dossier_id)
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=filename,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get(
    "/dossiers/{dossier_id}/json",
    summary="Download the machine-readable JSON Evidence Dossier artifact",
)
def download_dossier_json(
    dossier_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> FileResponse:
    detail = DossierService.get_dossier_detail(dossier_id=dossier_id)
    AuthService.check_investigation_access(
        detail.investigation_id, current_user, require_write=False
    )
    json_path, filename = DossierService.get_dossier_json_path(
        dossier_id=dossier_id
    )
    return FileResponse(
        path=str(json_path),
        media_type="application/json",
        filename=filename,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post(
    "/dossiers/{dossier_id}/review",
    response_model=DossierDetailResponse,
    summary="Record human investigator review and approval disposition for an Investigation Dossier",
)
def review_dossier(
    dossier_id: str,
    payload: DossierReviewRequest,
    current_user: AuthenticatedUser = Depends(
        require_roles(
            UserRole.ADMIN.value,
            UserRole.REVIEWER.value,
            UserRole.INVESTIGATOR.value,
        )
    ),
) -> DossierDetailResponse:
    detail = DossierService.get_dossier_detail(dossier_id=dossier_id)
    AuthService.check_investigation_access(
        detail.investigation_id, current_user, require_write=True
    )
    # Only REVIEWER or ADMIN may mark a dossier as APPROVED
    if payload.review_status.strip().upper() == "APPROVED" and current_user.role not in (
        UserRole.ADMIN.value,
        UserRole.REVIEWER.value,
    ):
        from app.core.exceptions import AuthorizationException

        raise AuthorizationException(
            message=(
                f"Role '{current_user.role}' cannot approve an investigation dossier. "
                "Dossier sign-off requires REVIEWER or ADMIN role."
            ),
            code="DOSSIER_APPROVAL_ROLE_REQUIRED",
        )
    return DossierService.review_dossier(
        dossier_id=dossier_id,
        payload=payload,
        current_user=current_user,
    )
