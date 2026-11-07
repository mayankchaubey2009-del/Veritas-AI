from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from app.models.entities import UserRole
from app.schemas.auth import AuthenticatedUser, InvestigationMemberGrantRequest
from app.schemas.document import (
    DocumentSummaryResponse,
    MultiDocumentUploadResponse,
)
from app.schemas.investigation import (
    AuditLogResponse,
    CaseNoteCreate,
    InvestigationCreate,
    InvestigationDetailResponse,
    InvestigationResponse,
    InvestigationUpdate,
)
from app.services.auth_service import (
    AuthService,
    require_authenticated_user,
    require_roles,
)
from app.services.document_service import DocumentService
from app.services.investigation_service import InvestigationService

router = APIRouter(prefix="/investigations", tags=["Investigations"])


@router.get("", response_model=List[InvestigationResponse])
def list_investigations(
    status_filter: Optional[str] = Query(
        default=None, alias="status", description="Filter by status"
    ),
    priority: Optional[str] = Query(
        default=None, description="Filter by priority level"
    ),
    search: Optional[str] = Query(
        default=None, description="Search title, case code, description, or analyst"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> List[InvestigationResponse]:
    return InvestigationService.list_investigations(
        status=status_filter,
        priority=priority,
        search=search,
        limit=limit,
        current_user=current_user,
    )


@router.post(
    "",
    response_model=InvestigationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_investigation(
    payload: InvestigationCreate,
    current_user: AuthenticatedUser = Depends(
        require_roles(UserRole.ADMIN.value, UserRole.INVESTIGATOR.value)
    ),
) -> InvestigationResponse:
    return InvestigationService.create_investigation(
        payload, current_user=current_user
    )


@router.get("/{investigation_id}", response_model=InvestigationDetailResponse)
def get_investigation(
    investigation_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> InvestigationDetailResponse:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=False
    )
    return InvestigationService.get_investigation_detail(investigation_id)


@router.patch("/{investigation_id}", response_model=InvestigationResponse)
def update_investigation(
    investigation_id: str,
    payload: InvestigationUpdate,
    current_user: AuthenticatedUser = Depends(
        require_roles(
            UserRole.ADMIN.value,
            UserRole.INVESTIGATOR.value,
            UserRole.REVIEWER.value,
        )
    ),
) -> InvestigationResponse:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=True
    )
    return InvestigationService.update_investigation(
        investigation_id, payload, current_user=current_user
    )


@router.post(
    "/{investigation_id}/notes",
    response_model=AuditLogResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_investigation_note(
    investigation_id: str,
    payload: CaseNoteCreate,
    current_user: AuthenticatedUser = Depends(
        require_roles(
            UserRole.ADMIN.value,
            UserRole.INVESTIGATOR.value,
            UserRole.REVIEWER.value,
        )
    ),
) -> AuditLogResponse:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=True
    )
    return InvestigationService.add_case_note(
        investigation_id, payload, current_user=current_user
    )


@router.delete("/{investigation_id}")
def delete_investigation(
    investigation_id: str,
    current_user: AuthenticatedUser = Depends(
        require_roles(UserRole.ADMIN.value, UserRole.INVESTIGATOR.value)
    ),
) -> Dict[str, Any]:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=True
    )
    return InvestigationService.delete_investigation(
        investigation_id, current_user=current_user
    )


@router.post(
    "/{investigation_id}/members",
    status_code=status.HTTP_201_CREATED,
)
def grant_investigation_member_access(
    investigation_id: str,
    payload: InvestigationMemberGrantRequest,
    current_user: AuthenticatedUser = Depends(
        require_roles(UserRole.ADMIN.value, UserRole.INVESTIGATOR.value)
    ),
) -> Dict[str, Any]:
    return AuthService.grant_investigation_member(
        investigation_id=investigation_id,
        target_user_id=payload.user_id,
        access_level=payload.access_level,
        actor_user=current_user,
    )


@router.post(
    "/{investigation_id}/documents",
    response_model=MultiDocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_investigation_documents(
    investigation_id: str,
    files: List[UploadFile] = File(
        ..., description="One or more PDF, PNG, JPG, or JPEG files"
    ),
    actor: str = Form(default="Lead Forensic Analyst"),
    current_user: AuthenticatedUser = Depends(
        require_roles(UserRole.ADMIN.value, UserRole.INVESTIGATOR.value)
    ),
) -> MultiDocumentUploadResponse:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=True
    )
    files_payload: List[Tuple[str, Optional[str], bytes]] = []
    for upload in files:
        raw_bytes = await upload.read()
        files_payload.append(
            (upload.filename or "document", upload.content_type, raw_bytes)
        )

    processed_docs = DocumentService.ingest_and_extract_documents(
        investigation_id=investigation_id,
        files_payload=files_payload,
        actor=actor,
        current_user=current_user,
    )
    return MultiDocumentUploadResponse(
        investigation_id=investigation_id,
        uploaded_count=len(processed_docs),
        documents=processed_docs,
    )


@router.get(
    "/{investigation_id}/documents",
    response_model=List[DocumentSummaryResponse],
)
def list_investigation_documents(
    investigation_id: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> List[DocumentSummaryResponse]:
    AuthService.check_investigation_access(
        investigation_id, current_user, require_write=False
    )
    return DocumentService.list_investigation_documents(investigation_id)
