from typing import List, Optional
from fastapi import APIRouter, Body, Depends, Query, Response
from app.core.database import get_db_connection
from app.core.exceptions import ResourceNotFoundException
from app.models.entities import UserRole
from app.schemas.auth import AuthenticatedUser
from app.schemas.forensics import (
    ForensicAnalysisDetailResponse,
    ForensicAnalysisRequest,
    ForensicFindingResponse,
    ForensicReviewRequest,
)
from app.services.auth_service import (
    AuthService,
    require_authenticated_user,
    require_roles,
)
from app.services.forensics_service import ForensicsService

router = APIRouter(tags=["Phase 3 — Visual Forensics & Authenticity Signal Analysis"])


@router.post(
    "/documents/{document_id}/forensics/analyze",
    response_model=ForensicAnalysisDetailResponse,
)
def analyze_document_forensics(
    document_id: str,
    payload: Optional[ForensicAnalysisRequest] = Body(default=None),
    current_user: AuthenticatedUser = Depends(
        require_roles(
            UserRole.ADMIN.value,
            UserRole.INVESTIGATOR.value,
            UserRole.REVIEWER.value,
        )
    ),
) -> ForensicAnalysisDetailResponse:
    """
    Executes or re-executes the 7-module Phase 3 Visual Forensics Engine on a document,
    persisting findings, derived evidence artifacts, and audit trail records.
    """
    AuthService.check_document_access(
        document_id, current_user, require_write=True
    )
    return ForensicsService.run_document_forensic_analysis(
        document_id=document_id,
        request_payload=payload,
        current_user=current_user,
    )


@router.get(
    "/documents/{document_id}/forensics",
    response_model=ForensicAnalysisDetailResponse,
)
def get_document_forensics(
    document_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> ForensicAnalysisDetailResponse:
    """
    Retrieves the latest Visual Forensics analysis bundle for a document
    (automatically triggering initial analysis if not yet analyzed).
    """
    AuthService.check_document_access(
        document_id, current_user, require_write=False
    )
    return ForensicsService.get_document_forensics(document_id=document_id)


@router.get(
    "/documents/{document_id}/forensics/findings",
    response_model=List[ForensicFindingResponse],
)
def list_document_forensic_findings(
    document_id: str,
    severity: Optional[str] = Query(
        default=None,
        description="Filter by severity: INFORMATIONAL, LOW, MEDIUM, HIGH",
    ),
    module_name: Optional[str] = Query(
        default=None,
        description="Filter by forensic module name",
    ),
    review_status: Optional[str] = Query(
        default=None,
        description="Filter by review status: REQUIRES_REVIEW, REVIEWED, INCONCLUSIVE, CONFIRMED, DISMISSED",
    ),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> List[ForensicFindingResponse]:
    """Lists structured forensic findings for a document with optional filters."""
    AuthService.check_document_access(
        document_id, current_user, require_write=False
    )
    return ForensicsService.list_document_findings(
        document_id=document_id,
        severity=severity,
        module_name=module_name,
        review_status=review_status,
    )


@router.get(
    "/forensics/analyses/{analysis_id}",
    response_model=ForensicAnalysisDetailResponse,
)
def get_forensic_analysis_by_id(
    analysis_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> ForensicAnalysisDetailResponse:
    """Retrieves a specific forensic analysis run by its analysis_id."""
    detail = ForensicsService.get_analysis_by_id(analysis_id=analysis_id)
    AuthService.check_investigation_access(
        detail.investigation_id, current_user, require_write=False
    )
    return detail


@router.get(
    "/forensics/findings/{finding_id}",
    response_model=ForensicFindingResponse,
)
def get_forensic_finding_by_id(
    finding_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> ForensicFindingResponse:
    """Retrieves a single forensic finding and its human review history."""
    finding = ForensicsService.get_finding_by_id(finding_id=finding_id)
    AuthService.check_investigation_access(
        finding.investigation_id, current_user, require_write=False
    )
    return finding


@router.post(
    "/forensics/findings/{finding_id}/review",
    response_model=ForensicFindingResponse,
)
def review_forensic_finding(
    finding_id: str,
    payload: ForensicReviewRequest,
    current_user: AuthenticatedUser = Depends(
        require_roles(
            UserRole.ADMIN.value,
            UserRole.INVESTIGATOR.value,
            UserRole.REVIEWER.value,
        )
    ),
) -> ForensicFindingResponse:
    """
    Records a human analyst review disposition (REVIEWED, INCONCLUSIVE, CONFIRMED, DISMISSED,
    or REQUIRES_REVIEW) with authenticated session reviewer attribution, notes, and immutable audit logging.
    """
    finding = ForensicsService.get_finding_by_id(finding_id=finding_id)
    AuthService.check_investigation_access(
        finding.investigation_id, current_user, require_write=True
    )
    return ForensicsService.review_finding(
        finding_id=finding_id,
        payload=payload,
        current_user=current_user,
    )


@router.get("/forensics/artifacts/{artifact_id}")
def get_forensic_artifact_image(
    artifact_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> Response:
    """
    Streams a derived forensic evidence artifact image (e.g., ELA map, local variance heatmap,
    or signature/stamp crop) after validating storage boundaries and ownership.
    """
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT investigation_id FROM forensic_artifacts WHERE id = ?;",
            (artifact_id,),
        ).fetchone()
        if not row:
            raise ResourceNotFoundException("ForensicArtifact", artifact_id)
        AuthService.check_investigation_access(
            row["investigation_id"], current_user, require_write=False
        )

    data, mime_type, filename = ForensicsService.get_artifact_bytes(
        artifact_id=artifact_id
    )
    return Response(
        content=data,
        media_type=mime_type,
        headers={
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
