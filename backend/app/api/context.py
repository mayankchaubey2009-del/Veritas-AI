from typing import List, Optional
from fastapi import APIRouter, Body, Depends, Query
from app.models.entities import UserRole
from app.schemas.auth import AuthenticatedUser
from app.schemas.context import (
    ContextualAnalysisBundleResponse,
    ContextualAnalysisRequest,
    ContextualFindingResponse,
    ContextualReviewRequest,
    FinancialValidationResultResponse,
    InvestigationEntityGraphResponse,
)
from app.services.auth_service import (
    AuthService,
    require_authenticated_user,
    require_roles,
)
from app.services.context_service import ContextService

router = APIRouter(tags=["Contextual Intelligence & Cross-Document Analysis"])


@router.post(
    "/investigations/{investigation_id}/context/analyze",
    response_model=ContextualAnalysisBundleResponse,
    summary="Execute or re-run Phase 4 Cross-Document Contextual Intelligence analysis for an investigation",
)
def analyze_investigation_context(
    investigation_id: str,
    payload: Optional[ContextualAnalysisRequest] = Body(default=None),
    current_user: AuthenticatedUser = Depends(
        require_roles(
            UserRole.ADMIN.value,
            UserRole.INVESTIGATOR.value,
            UserRole.REVIEWER.value,
        )
    ),
) -> ContextualAnalysisBundleResponse:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=True
    )
    return ContextService.run_investigation_context_analysis(
        investigation_id=investigation_id,
        payload=payload,
        current_user=current_user,
    )


@router.get(
    "/investigations/{investigation_id}/context",
    response_model=ContextualAnalysisBundleResponse,
    summary="Get complete Contextual Intelligence analysis for an investigation (summary, findings, entity resolution, financial validation, graph, timeline)",
)
def get_investigation_context(
    investigation_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> ContextualAnalysisBundleResponse:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=False
    )
    return ContextService.get_investigation_context(investigation_id=investigation_id)


@router.get(
    "/investigations/{investigation_id}/context/findings",
    response_model=List[ContextualFindingResponse],
    summary="List cross-document contextual findings for an investigation with optional filtering",
)
def get_investigation_contextual_findings(
    investigation_id: str,
    severity: Optional[str] = Query(
        default=None,
        description="Filter by severity (HIGH, MEDIUM, LOW, INFO).",
    ),
    status: Optional[str] = Query(
        default=None,
        description="Filter by evaluation status (CONFIRMED_DATA_MISMATCH, POTENTIAL_INCONSISTENCY, MISSING_INFORMATION, CONSISTENT_EVIDENCE, INCONCLUSIVE_RESULT).",
    ),
    review_status: Optional[str] = Query(
        default=None,
        description="Filter by human review status (REQUIRES_REVIEW, REVIEWED, INCONCLUSIVE, CONFIRMED, DISMISSED).",
    ),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> List[ContextualFindingResponse]:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=False
    )
    return ContextService.list_investigation_contextual_findings(
        investigation_id=investigation_id,
        severity=severity,
        status=status,
        review_status=review_status,
    )


@router.get(
    "/investigations/{investigation_id}/context/graph",
    response_model=InvestigationEntityGraphResponse,
    summary="Get the investigation entity relationship graph (nodes and cross-document edges)",
)
def get_investigation_context_graph(
    investigation_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> InvestigationEntityGraphResponse:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=False
    )
    return ContextService.get_investigation_graph(investigation_id=investigation_id)


@router.get(
    "/investigations/{investigation_id}/context/financial-validation",
    response_model=List[FinancialValidationResultResponse],
    summary="Get deterministic Decimal financial validation results (invoice line-item arithmetic and bank statement reconciliation)",
)
def get_investigation_financial_validation(
    investigation_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> List[FinancialValidationResultResponse]:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=False
    )
    return ContextService.get_investigation_financial_validations(
        investigation_id=investigation_id
    )


@router.get(
    "/context/findings/{finding_id}",
    response_model=ContextualFindingResponse,
    summary="Get detailed cross-document contextual finding with full evidence coordinates and review history",
)
def get_contextual_finding(
    finding_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> ContextualFindingResponse:
    finding = ContextService.get_contextual_finding_by_id(finding_id=finding_id)
    AuthService.check_investigation_access(
        finding.investigation_id, current_user, require_write=False
    )
    return finding


@router.post(
    "/context/findings/{finding_id}/review",
    response_model=ContextualFindingResponse,
    summary="Record human investigator review decision and notes for a contextual finding",
)
def review_contextual_finding(
    finding_id: str,
    payload: ContextualReviewRequest,
    current_user: AuthenticatedUser = Depends(
        require_roles(
            UserRole.ADMIN.value,
            UserRole.INVESTIGATOR.value,
            UserRole.REVIEWER.value,
        )
    ),
) -> ContextualFindingResponse:
    finding = ContextService.get_contextual_finding_by_id(finding_id=finding_id)
    AuthService.check_investigation_access(
        finding.investigation_id, current_user, require_write=True
    )
    return ContextService.review_contextual_finding(
        finding_id=finding_id,
        payload=payload,
        current_user=current_user,
    )
