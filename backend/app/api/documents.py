from typing import List, Optional
from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import Response
from app.schemas.auth import AuthenticatedUser
from app.schemas.document import (
    DocumentDetailResponse,
    DocumentExtractionBundleResponse,
    DocumentPageResponse,
    ExtractedEntityResponse,
    ExtractedTableResponse,
    LayoutRegionResponse,
)
from app.services.auth_service import AuthService, require_authenticated_user
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Document Intelligence"])


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document_detail(
    document_id: str = Path(..., description="Unique Document UUID"),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> DocumentDetailResponse:
    AuthService.check_document_access(
        document_id, current_user, require_write=False
    )
    return DocumentService.get_document_detail(document_id)


@router.get("/{document_id}/download", response_class=Response)
def download_document_binary(
    document_id: str = Path(..., description="Unique Document UUID"),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> Response:
    AuthService.check_document_access(
        document_id, current_user, require_write=False
    )
    file_bytes, mime_type, safe_filename, sha256_hash = (
        DocumentService.get_document_download_bytes(document_id)
    )
    return Response(
        content=file_bytes,
        media_type=mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
            "X-Content-Type-Options": "nosniff",
            "X-Document-SHA256": sha256_hash,
            "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/{document_id}/extraction",
    response_model=DocumentExtractionBundleResponse,
)
def get_document_extraction(
    document_id: str = Path(..., description="Unique Document UUID"),
    page_number: Optional[int] = Query(
        default=None, ge=1, description="Filter by 1-indexed page number"
    ),
    extraction_method: Optional[str] = Query(
        default=None, description="Filter by NATIVE_PDF or VISUAL_OCR"
    ),
    structured_only: bool = Query(
        default=False, description="Return only structured key-value extractions"
    ),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> DocumentExtractionBundleResponse:
    AuthService.check_document_access(
        document_id, current_user, require_write=False
    )
    return DocumentService.get_document_extraction_bundle(
        document_id=document_id,
        page_number=page_number,
        extraction_method=extraction_method,
        structured_only=structured_only,
    )


@router.get(
    "/{document_id}/pages/{page_number}",
    response_model=DocumentPageResponse,
)
def get_document_page(
    document_id: str = Path(..., description="Unique Document UUID"),
    page_number: int = Path(..., ge=1, description="1-indexed page number"),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> DocumentPageResponse:
    AuthService.check_document_access(
        document_id, current_user, require_write=False
    )
    return DocumentService.get_document_page_detail(document_id, page_number)


@router.get(
    "/{document_id}/pages/{page_number}/preview",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
def get_document_page_preview(
    document_id: str = Path(..., description="Unique Document UUID"),
    page_number: int = Path(..., ge=1, description="1-indexed page number"),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> Response:
    AuthService.check_document_access(
        document_id, current_user, require_write=False
    )
    png_bytes = DocumentService.render_document_page_preview_png(
        document_id, page_number
    )
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/{document_id}/layout",
    response_model=List[LayoutRegionResponse],
)
def get_document_layout_regions(
    document_id: str = Path(..., description="Unique Document UUID"),
    page_number: Optional[int] = Query(default=None, ge=1),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> List[LayoutRegionResponse]:
    AuthService.check_document_access(
        document_id, current_user, require_write=False
    )
    bundle = DocumentService.get_document_extraction_bundle(
        document_id=document_id, page_number=page_number
    )
    return bundle.layout_regions


@router.get(
    "/{document_id}/tables",
    response_model=List[ExtractedTableResponse],
)
def get_document_tables(
    document_id: str = Path(..., description="Unique Document UUID"),
    page_number: Optional[int] = Query(default=None, ge=1),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> List[ExtractedTableResponse]:
    AuthService.check_document_access(
        document_id, current_user, require_write=False
    )
    bundle = DocumentService.get_document_extraction_bundle(
        document_id=document_id, page_number=page_number
    )
    return bundle.tables


@router.get(
    "/{document_id}/entities",
    response_model=List[ExtractedEntityResponse],
)
def get_document_entities(
    document_id: str = Path(..., description="Unique Document UUID"),
    page_number: Optional[int] = Query(default=None, ge=1),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> List[ExtractedEntityResponse]:
    AuthService.check_document_access(
        document_id, current_user, require_write=False
    )
    bundle = DocumentService.get_document_extraction_bundle(
        document_id=document_id, page_number=page_number
    )
    return bundle.entities
