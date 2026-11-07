import hashlib
import io
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import fitz  # PyMuPDF
from PIL import Image
from fastapi import status
from app.core.config import settings
from app.core.database import get_db_connection
from app.core.exceptions import InvalidDocumentException, ResourceNotFoundException
from app.schemas.auth import AuthenticatedUser
from app.schemas.document import (
    BoundingBoxSchema,
    ClassificationCandidateSchema,
    DocumentClassificationSchema,
    DocumentDetailResponse,
    DocumentExtractionBundleResponse,
    DocumentPageResponse,
    DocumentSummaryResponse,
    ExtractedEntityResponse,
    ExtractedTableResponse,
    ExtractionRecordResponse,
    FontMetadataItem,
    LayoutRegionResponse,
    TableCellResponse,
)
from app.services.audit_service import AuditService
from app.services.extraction_engine import DualPathExtractionEngine
from app.services.structure_intelligence_engine import (
    DISPLAY_LABELS,
    StructureAnalysisBundle,
    StructureIntelligenceEngine,
)

ALLOWED_MIME_TYPES: Dict[str, str] = {
    "application/pdf": "PDF",
    "application/x-pdf": "PDF",
    "image/png": "PNG",
    "image/jpeg": "JPG",
    "image/jpg": "JPG",
}

ALLOWED_EXTENSIONS: Dict[str, str] = {
    ".pdf": "PDF",
    ".png": "PNG",
    ".jpg": "JPG",
    ".jpeg": "JPEG",
}

CANONICAL_INTERNAL_EXTENSION: Dict[str, str] = {
    "PDF": ".pdf",
    "PNG": ".png",
    "JPG": ".jpg",
    "JPEG": ".jpg",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_filename(filename: str) -> str:
    """
    Normalizes and sanitizes user-supplied filenames, stripping directory components,
    null bytes, and control characters to prevent path traversal and header injection.
    """
    raw = (filename or "document").replace("\x00", "").replace("\\", "/")
    base = os.path.basename(raw).strip()
    cleaned = re.sub(r"[^A-Za-z0-9._\- ]", "_", base).strip(" ._")
    return cleaned[:120] or "document"


def _verify_storage_containment(target_path: Path, allowed_root: Path) -> Path:
    """Ensures target_path resolves strictly inside allowed_root (prevents path traversal)."""
    resolved_target = target_path.resolve()
    resolved_root = allowed_root.resolve()
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError as exc:
        raise InvalidDocumentException(
            message="Storage path traversal or boundary violation detected.",
            code="STORAGE_PATH_BOUNDARY_VIOLATION",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    return resolved_target


def validate_file_signature_and_type(
    filename: str, content_type: Optional[str], file_bytes: bytes
) -> Tuple[str, str]:
    """
    Validates file size, extension, declared MIME type, binary magic signature,
    and structural integrity (page count / pixel bounds / malformed stream checks).
    Returns (file_type, canonical_mime_type).
    """
    if "\x00" in (filename or ""):
        raise InvalidDocumentException(
            message="Filename contains illegal null byte characters.",
            code="INVALID_FILENAME",
        )

    if not file_bytes or len(file_bytes) == 0:
        raise InvalidDocumentException(
            message=f"Uploaded file '{filename}' is empty (0 bytes).",
            code="EMPTY_DOCUMENT_FILE",
        )

    if len(file_bytes) > settings.max_upload_size_bytes:
        raise InvalidDocumentException(
            message=(
                f"File '{filename}' exceeds the maximum allowed size of "
                f"{settings.max_upload_size_mb} MB."
            ),
            code="FILE_SIZE_LIMIT_EXCEEDED",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            details={
                "filename": _sanitize_filename(filename),
                "size_bytes": len(file_bytes),
                "max_size_bytes": settings.max_upload_size_bytes,
            },
        )

    clean_base = _sanitize_filename(filename)
    ext = Path(clean_base).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidDocumentException(
            message=(
                f"Unsupported file extension '{ext}' for '{clean_base}'. "
                "Supported formats: PDF, PNG, JPG, JPEG."
            ),
            code="UNSUPPORTED_FILE_EXTENSION",
            details={"filename": clean_base, "extension": ext},
        )

    detected_type: Optional[str] = None
    canonical_mime: Optional[str] = None

    if file_bytes.startswith(b"%PDF-"):
        detected_type = "PDF"
        canonical_mime = "application/pdf"
    elif file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        detected_type = "PNG"
        canonical_mime = "image/png"
    elif file_bytes.startswith(b"\xff\xd8\xff"):
        detected_type = "JPEG" if ext == ".jpeg" else "JPG"
        canonical_mime = "image/jpeg"

    if not detected_type or not canonical_mime:
        raise InvalidDocumentException(
            message=(
                f"File '{clean_base}' failed binary magic-signature verification. "
                "File header does not match a valid PDF, PNG, or JPEG signature."
            ),
            code="INVALID_FILE_SIGNATURE",
            details={"filename": clean_base},
        )

    ext_family = (
        "JPG" if ALLOWED_EXTENSIONS[ext] == "JPEG" else ALLOWED_EXTENSIONS[ext]
    )
    sig_family = "JPG" if detected_type == "JPEG" else detected_type
    if ext_family != sig_family:
        raise InvalidDocumentException(
            message=(
                f"File '{clean_base}' has extension '{ext}' ({ext_family}) but binary "
                f"signature indicates '{sig_family}'."
            ),
            code="SIGNATURE_EXTENSION_MISMATCH",
            details={
                "filename": clean_base,
                "extension_type": ext_family,
                "signature_type": sig_family,
            },
        )

    if content_type:
        lower_mime = content_type.split(";")[0].strip().lower()
        if lower_mime and lower_mime != "application/octet-stream":
            if lower_mime not in ALLOWED_MIME_TYPES:
                raise InvalidDocumentException(
                    message=f"Unsupported MIME type '{lower_mime}' for '{clean_base}'.",
                    code="UNSUPPORTED_MIME_TYPE",
                    details={"filename": clean_base, "mime_type": lower_mime},
                )
            mime_family = ALLOWED_MIME_TYPES[lower_mime]
            if mime_family != sig_family:
                raise InvalidDocumentException(
                    message=(
                        f"Declared MIME type '{lower_mime}' does not match binary "
                        f"signature '{sig_family}' for '{clean_base}'."
                    ),
                    code="MIME_SIGNATURE_MISMATCH",
                )

    # Defensive structural parsing & resource exhaustion checks
    if detected_type == "PDF":
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as pdf_doc:
                if pdf_doc.needs_pass:
                    raise InvalidDocumentException(
                        message=f"PDF '{clean_base}' is password-encrypted and cannot be inspected.",
                        code="ENCRYPTED_PDF_UNSUPPORTED",
                    )
                page_cnt = len(pdf_doc)
                if page_cnt < 1:
                    raise InvalidDocumentException(
                        message=f"PDF '{clean_base}' contains 0 pages.",
                        code="EMPTY_PDF_DOCUMENT",
                    )
                if page_cnt > settings.max_pdf_pages:
                    raise InvalidDocumentException(
                        message=(
                            f"PDF '{clean_base}' has {page_cnt} pages, exceeding the "
                            f"configured maximum of {settings.max_pdf_pages} pages."
                        ),
                        code="PDF_PAGE_LIMIT_EXCEEDED",
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        details={
                            "page_count": page_cnt,
                            "max_pdf_pages": settings.max_pdf_pages,
                        },
                    )
        except InvalidDocumentException:
            raise
        except Exception as exc:
            raise InvalidDocumentException(
                message=f"File '{clean_base}' is a malformed or corrupted PDF document.",
                code="CORRUPTED_PDF_DOCUMENT",
            ) from exc
    else:
        try:
            Image.MAX_IMAGE_PIXELS = settings.max_image_pixels
            with Image.open(io.BytesIO(file_bytes)) as img:
                width, height = img.size
                total_pixels = int(width) * int(height)
                if width <= 0 or height <= 0 or total_pixels > settings.max_image_pixels:
                    raise InvalidDocumentException(
                        message=(
                            f"Image '{clean_base}' dimensions ({width}x{height} = {total_pixels} px) "
                            f"exceed the safe pixel limit of {settings.max_image_pixels}."
                        ),
                        code="IMAGE_PIXEL_LIMIT_EXCEEDED",
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    )
                img.verify()
        except InvalidDocumentException:
            raise
        except Image.DecompressionBombError as exc:
            raise InvalidDocumentException(
                message=f"Image '{clean_base}' exceeds safe decompression pixel limits.",
                code="IMAGE_PIXEL_LIMIT_EXCEEDED",
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            ) from exc
        except Exception as exc:
            raise InvalidDocumentException(
                message=f"File '{clean_base}' is a malformed or corrupted image file.",
                code="CORRUPTED_IMAGE_DOCUMENT",
            ) from exc

    return detected_type, canonical_mime


def _parse_bbox(raw_json: str) -> BoundingBoxSchema:
    try:
        bbox_raw = json.loads(raw_json or "{}")
    except Exception:
        bbox_raw = {}
    return BoundingBoxSchema(
        x0=float(bbox_raw.get("x0", 0.0)),
        y0=float(bbox_raw.get("y0", 0.0)),
        x1=float(bbox_raw.get("x1", 0.0)),
        y1=float(bbox_raw.get("y1", 0.0)),
        page_width=float(bbox_raw.get("page_width", 0.0)),
        page_height=float(bbox_raw.get("page_height", 0.0)),
    )


def _row_to_document_summary(row: Any) -> DocumentSummaryResponse:
    keys = row.keys()
    doc_type = (
        row["document_type"]
        if "document_type" in keys and row["document_type"]
        else "OTHER_UNKNOWN"
    )
    try:
        signals = (
            json.loads(row["classification_signals_json"] or "[]")
            if "classification_signals_json" in keys
            else []
        )
    except Exception:
        signals = []

    return DocumentSummaryResponse(
        id=row["id"],
        investigation_id=row["investigation_id"],
        filename=row["filename"],
        file_type=row["file_type"],
        mime_type=(
            row["mime_type"]
            if "mime_type" in keys and row["mime_type"]
            else "application/octet-stream"
        ),
        file_size_bytes=int(row["file_size_bytes"] or 0),
        sha256_hash=row["sha256_hash"] or "",
        page_count=int(
            row["page_count"]
            if "page_count" in keys and row["page_count"] is not None
            else 1
        ),
        extraction_method_summary=(
            row["extraction_method_summary"]
            if "extraction_method_summary" in keys
            and row["extraction_method_summary"]
            else "PENDING"
        ),
        is_scanned=bool(row["is_scanned"]) if "is_scanned" in keys else False,
        average_confidence=round(
            float(
                row["average_confidence"]
                if "average_confidence" in keys
                and row["average_confidence"] is not None
                else 0.0
            ),
            4,
        ),
        extracted_char_count=int(
            row["extracted_char_count"]
            if "extracted_char_count" in keys
            and row["extracted_char_count"] is not None
            else 0
        ),
        document_type=doc_type,
        document_type_label=DISPLAY_LABELS.get(doc_type, "Other / Unknown"),
        classification_confidence=round(
            float(
                row["classification_confidence"]
                if "classification_confidence" in keys
                and row["classification_confidence"] is not None
                else 0.0
            ),
            4,
        ),
        classification_is_certain=(
            bool(row["classification_is_certain"])
            if "classification_is_certain" in keys
            else False
        ),
        classification_signals=signals,
        layout_region_count=int(
            row["layout_region_count"]
            if "layout_region_count" in keys
            and row["layout_region_count"] is not None
            else 0
        ),
        table_count=int(
            row["table_count"]
            if "table_count" in keys and row["table_count"] is not None
            else 0
        ),
        entity_count=int(
            row["entity_count"]
            if "entity_count" in keys and row["entity_count"] is not None
            else 0
        ),
        forensic_status=(
            row["forensic_status"]
            if "forensic_status" in keys and row["forensic_status"]
            else "NOT_ANALYZED"
        ),
        latest_analysis_id=(
            row["latest_analysis_id"] if "latest_analysis_id" in keys else None
        ),
        forensic_findings_count=int(
            row["forensic_findings_count"]
            if "forensic_findings_count" in keys
            and row["forensic_findings_count"] is not None
            else 0
        ),
        forensic_analyzed_at=(
            row["forensic_analyzed_at"] if "forensic_analyzed_at" in keys else None
        ),
        processing_status=row["processing_status"],
        error_message=row["error_message"] if "error_message" in keys else None,
        uploaded_at=row["uploaded_at"],
        processed_at=row["processed_at"] if "processed_at" in keys else None,
    )


def _row_to_extraction_record(row: Any) -> ExtractionRecordResponse:
    return ExtractionRecordResponse(
        id=row["id"],
        document_id=row["document_id"],
        page_number=int(row["page_number"]),
        block_index=int(row["block_index"] or 0),
        extracted_text=row["extracted_text"] or "",
        field_name=row["field_name"],
        field_value=row["field_value"],
        bounding_box=_parse_bbox(row["bounding_box_json"]),
        extraction_method=row["extraction_method"],
        confidence=round(float(row["confidence"] or 0.0), 4),
        source_reference=row["source_reference"],
        font_name=row["font_name"],
        font_size=float(row["font_size"]) if row["font_size"] is not None else None,
        created_at=row["created_at"],
    )


def _row_to_layout_region(row: Any) -> LayoutRegionResponse:
    return LayoutRegionResponse(
        id=row["id"],
        document_id=row["document_id"],
        page_number=int(row["page_number"]),
        region_type=row["region_type"],
        reading_order=int(row["reading_order"] or 0),
        parent_region_id=row["parent_region_id"],
        label=row["label"],
        text_content=row["text_content"] or "",
        bounding_box=_parse_bbox(row["bounding_box_json"]),
        extraction_method=row["extraction_method"],
        confidence=round(float(row["confidence"] or 0.0), 4),
        created_at=row["created_at"],
    )


def _row_to_entity(row: Any) -> ExtractedEntityResponse:
    return ExtractedEntityResponse(
        id=row["id"],
        document_id=row["document_id"],
        investigation_id=row["investigation_id"],
        page_number=int(row["page_number"]),
        entity_type=row["entity_type"],
        raw_value=row["raw_value"],
        normalized_value=row["normalized_value"],
        bounding_box=_parse_bbox(row["bounding_box_json"]),
        extraction_method=row["extraction_method"],
        confidence=round(float(row["confidence"] or 0.0), 4),
        source_reference=row["source_reference"],
        created_at=row["created_at"],
    )


def _persist_structure_bundle(
    cursor: Any,
    doc_id: str,
    investigation_id: str,
    structure_bundle: StructureAnalysisBundle,
    processed_at: str,
) -> None:
    """Persists Phase 2B layout regions, tables, cells, entities, and classification into SQLite."""
    # Map local region IDs (e.g., LREG-P1-001) to globally unique database IDs
    region_id_map: Dict[str, str] = {}
    for reg in structure_bundle.layout_regions:
        region_id_map[reg.id] = f"{doc_id[:8]}-{reg.id}"

    for reg in structure_bundle.layout_regions:
        db_reg_id = region_id_map[reg.id]
        db_parent_id = (
            region_id_map.get(reg.parent_region_id)
            if reg.parent_region_id
            else None
        )
        cursor.execute(
            """
            INSERT INTO document_layout_regions (
                id, document_id, page_number, region_type, reading_order,
                parent_region_id, label, text_content, bounding_box_json,
                extraction_method, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                db_reg_id,
                doc_id,
                reg.page_number,
                reg.region_type,
                reg.reading_order,
                db_parent_id,
                reg.label,
                reg.text_content,
                json.dumps(reg.bounding_box),
                reg.extraction_method,
                reg.confidence,
                processed_at,
            ),
        )

    for tbl in structure_bundle.tables:
        table_db_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO document_tables (
                id, table_identifier, document_id, page_number,
                row_count, column_count, headers_json, bounding_box_json,
                extraction_method, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                table_db_id,
                tbl.table_identifier,
                doc_id,
                tbl.page_number,
                tbl.row_count,
                tbl.column_count,
                json.dumps(tbl.headers),
                json.dumps(tbl.bounding_box),
                tbl.extraction_method,
                tbl.confidence,
                processed_at,
            ),
        )
        for cell in tbl.cells:
            cursor.execute(
                """
                INSERT INTO document_table_cells (
                    id, table_id, document_id, page_number,
                    row_index, col_index, cell_text, is_header,
                    bounding_box_json, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(uuid.uuid4()),
                    table_db_id,
                    doc_id,
                    tbl.page_number,
                    cell.row_index,
                    cell.col_index,
                    cell.cell_text,
                    1 if cell.is_header else 0,
                    json.dumps(cell.bounding_box),
                    cell.confidence,
                ),
            )

    for ent in structure_bundle.entities:
        cursor.execute(
            """
            INSERT INTO document_entities (
                id, document_id, investigation_id, page_number,
                entity_type, raw_value, normalized_value,
                bounding_box_json, extraction_method, confidence,
                source_reference, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                str(uuid.uuid4()),
                doc_id,
                investigation_id,
                ent.page_number,
                ent.entity_type,
                ent.raw_value,
                ent.normalized_value,
                json.dumps(ent.bounding_box),
                ent.extraction_method,
                ent.confidence,
                ent.source_reference,
                processed_at,
            ),
        )


def _load_tables_for_document(
    cursor: Any, document_id: str, page_number: Optional[int] = None
) -> List[ExtractedTableResponse]:
    if page_number is not None:
        cursor.execute(
            """
            SELECT * FROM document_tables
            WHERE document_id = ? AND page_number = ?
            ORDER BY page_number ASC, table_identifier ASC;
            """,
            (document_id, page_number),
        )
    else:
        cursor.execute(
            """
            SELECT * FROM document_tables
            WHERE document_id = ?
            ORDER BY page_number ASC, table_identifier ASC;
            """,
            (document_id,),
        )
    t_rows = cursor.fetchall()
    if not t_rows:
        return []

    cursor.execute(
        """
        SELECT * FROM document_table_cells
        WHERE document_id = ?
        ORDER BY row_index ASC, col_index ASC;
        """,
        (document_id,),
    )
    cells_by_table: Dict[str, List[TableCellResponse]] = {}
    for c_row in cursor.fetchall():
        t_id = c_row["table_id"]
        cells_by_table.setdefault(t_id, []).append(
            TableCellResponse(
                id=c_row["id"],
                table_id=t_id,
                document_id=c_row["document_id"],
                page_number=int(c_row["page_number"]),
                row_index=int(c_row["row_index"]),
                col_index=int(c_row["col_index"]),
                cell_text=c_row["cell_text"] or "",
                is_header=bool(c_row["is_header"]),
                bounding_box=_parse_bbox(c_row["bounding_box_json"]),
                confidence=round(float(c_row["confidence"] or 0.0), 4),
            )
        )

    tables_out: List[ExtractedTableResponse] = []
    for tr in t_rows:
        try:
            headers = json.loads(tr["headers_json"] or "[]")
        except Exception:
            headers = []
        tables_out.append(
            ExtractedTableResponse(
                id=tr["id"],
                table_identifier=tr["table_identifier"],
                document_id=tr["document_id"],
                page_number=int(tr["page_number"]),
                row_count=int(tr["row_count"] or 0),
                column_count=int(tr["column_count"] or 0),
                headers=[str(h) for h in headers],
                bounding_box=_parse_bbox(tr["bounding_box_json"]),
                extraction_method=tr["extraction_method"],
                confidence=round(float(tr["confidence"] or 0.0), 4),
                cells=cells_by_table.get(tr["id"], []),
                created_at=tr["created_at"],
            )
        )
    return tables_out


class DocumentService:
    @staticmethod
    def ingest_and_extract_documents(
        investigation_id: str,
        files_payload: List[Tuple[str, Optional[str], bytes]],
        actor: str = "Lead Forensic Analyst",
        current_user: Optional[AuthenticatedUser] = None,
    ) -> List[DocumentSummaryResponse]:
        """
        Validates, hashes (SHA-256), stores securely on disk under randomized internal UUID filenames,
        records in SQLite, executes Phase 2A Dual-Path Extraction (PyMuPDF Native Path A / PaddleOCR Visual Path B),
        and executes Phase 2B Structure Intelligence (Classification, Layout, Tables, Entities).
        """
        if not files_payload:
            raise InvalidDocumentException(
                message="At least one document file must be provided for upload.",
                code="NO_FILES_PROVIDED",
            )

        if len(files_payload) > settings.max_files_per_upload:
            raise InvalidDocumentException(
                message=(
                    f"Cannot upload more than {settings.max_files_per_upload} files "
                    "in a single batch."
                ),
                code="BATCH_LIMIT_EXCEEDED",
            )

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, case_code, title, lead_investigator FROM investigations WHERE id = ?;",
                (investigation_id,),
            )
            inv_row = cursor.fetchone()
            if not inv_row:
                raise ResourceNotFoundException("Investigation", investigation_id)
            case_code = inv_row["case_code"]
            default_actor = (
                f"{current_user.full_name} ({current_user.title})"
                if current_user
                else (inv_row["lead_investigator"] or actor)
            )

        validated_items: List[Tuple[str, str, str, bytes, str]] = []
        for orig_filename, content_type, file_bytes in files_payload:
            raw_name = (orig_filename or "unnamed_document").strip()
            detected_type, canonical_mime = validate_file_signature_and_type(
                raw_name, content_type, file_bytes
            )
            clean_name = _sanitize_filename(raw_name)
            sha256_digest = hashlib.sha256(file_bytes).hexdigest()
            validated_items.append(
                (clean_name, detected_type, canonical_mime, file_bytes, sha256_digest)
            )

        results: List[DocumentSummaryResponse] = []
        inv_storage_dir = _verify_storage_containment(
            settings.resolved_storage_dir / investigation_id,
            settings.resolved_storage_dir,
        )
        inv_storage_dir.mkdir(parents=True, exist_ok=True)

        for (
            orig_filename,
            detected_type,
            canonical_mime,
            file_bytes,
            sha256_digest,
        ) in validated_items:
            doc_id = str(uuid.uuid4())
            uploaded_at = _utc_now_iso()
            # Store under randomized internal UUID filename (never user-supplied filename)
            internal_ext = CANONICAL_INTERNAL_EXTENSION.get(detected_type, ".bin")
            randomized_disk_name = f"{doc_id}{internal_ext}"
            disk_path = _verify_storage_containment(
                inv_storage_dir / randomized_disk_name,
                settings.resolved_storage_dir,
            )

            disk_path.write_bytes(file_bytes)
            try:
                os.chmod(disk_path, 0o600)
            except OSError:
                pass

            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO documents (
                        id, investigation_id, filename, file_type, mime_type,
                        file_size_bytes, sha256_hash, storage_path, page_count,
                        extraction_method_summary, is_scanned, average_confidence,
                        extracted_char_count, processing_status, uploaded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'PENDING', 0, 0.0, 0, 'PROCESSING', ?);
                    """,
                    (
                        doc_id,
                        investigation_id,
                        orig_filename,
                        detected_type,
                        canonical_mime,
                        len(file_bytes),
                        sha256_digest,
                        str(disk_path),
                        uploaded_at,
                    ),
                )

                AuditService.append_event_with_cursor(
                    cursor,
                    investigation_id=investigation_id,
                    action="DOCUMENT_UPLOADED",
                    entity_type="DOCUMENT",
                    entity_id=doc_id,
                    actor=default_actor,
                    summary=(
                        f"Ingested {detected_type} document '{orig_filename}' "
                        f"({len(file_bytes)} bytes, SHA-256: {sha256_digest[:16]}...) "
                        f"into case {case_code}"
                    ),
                    metadata={
                        "case_code": case_code,
                        "document_id": doc_id,
                        "filename": orig_filename,
                        "internal_storage_name": randomized_disk_name,
                        "file_type": detected_type,
                        "mime_type": canonical_mime,
                        "file_size_bytes": len(file_bytes),
                        "sha256_hash": sha256_digest,
                    },
                    actor_user_id=current_user.id if current_user else None,
                    actor_role=current_user.role if current_user else None,
                    event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                    created_at=uploaded_at,
                )

            try:
                # Phase 2A: Dual-Path Extraction
                extraction_result = DualPathExtractionEngine.extract_document(
                    file_bytes=file_bytes,
                    file_type=detected_type,
                    document_id=doc_id,
                )

                # Phase 2B: Structure Understanding & Intelligent Classification
                structure_bundle = (
                    StructureIntelligenceEngine.analyze_document_structure(
                        file_bytes=file_bytes,
                        file_type=detected_type,
                        extraction_result=extraction_result,
                    )
                )

                processed_at = _utc_now_iso()

                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    total_blocks = 0
                    structured_count = 0

                    for page_data in extraction_result.pages:
                        page_id = str(uuid.uuid4())
                        cursor.execute(
                            """
                            INSERT INTO document_pages (
                                id, document_id, page_number, width, height,
                                extraction_method, is_scanned_page, raw_text,
                                char_count, block_count, average_confidence,
                                font_summary_json, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                            """,
                            (
                                page_id,
                                doc_id,
                                page_data.page_number,
                                page_data.width,
                                page_data.height,
                                page_data.extraction_method,
                                1 if page_data.is_scanned_page else 0,
                                page_data.raw_text,
                                page_data.char_count,
                                page_data.block_count,
                                page_data.average_confidence,
                                json.dumps(page_data.fonts),
                                processed_at,
                            ),
                        )

                        for blk in page_data.blocks:
                            total_blocks += 1
                            if blk.field_name:
                                structured_count += 1
                            cursor.execute(
                                """
                                INSERT INTO document_extractions (
                                    id, document_id, investigation_id, page_number,
                                    block_index, extracted_text, field_name, field_value,
                                    bounding_box_json, extraction_method, confidence,
                                    source_reference, font_name, font_size, created_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                                """,
                                (
                                    str(uuid.uuid4()),
                                    doc_id,
                                    investigation_id,
                                    blk.page_number,
                                    blk.block_index,
                                    blk.extracted_text,
                                    blk.field_name,
                                    blk.field_value,
                                    json.dumps(blk.bounding_box),
                                    blk.extraction_method,
                                    blk.confidence,
                                    blk.source_reference,
                                    blk.font_name,
                                    blk.font_size,
                                    processed_at,
                                ),
                            )

                    # Persist Phase 2B layout regions, tables, cells, and entities
                    _persist_structure_bundle(
                        cursor=cursor,
                        doc_id=doc_id,
                        investigation_id=investigation_id,
                        structure_bundle=structure_bundle,
                        processed_at=processed_at,
                    )

                    cls_res = structure_bundle.classification
                    cursor.execute(
                        """
                        UPDATE documents
                        SET page_count = ?,
                            extraction_method_summary = ?,
                            is_scanned = ?,
                            average_confidence = ?,
                            extracted_char_count = ?,
                            document_type = ?,
                            classification_confidence = ?,
                            classification_is_certain = ?,
                            classification_signals_json = ?,
                            classification_candidates_json = ?,
                            layout_region_count = ?,
                            table_count = ?,
                            entity_count = ?,
                            processing_status = 'COMPLETED',
                            error_message = NULL,
                            processed_at = ?
                        WHERE id = ?;
                        """,
                        (
                            extraction_result.page_count,
                            extraction_result.extraction_method_summary,
                            1 if extraction_result.is_scanned else 0,
                            extraction_result.average_confidence,
                            extraction_result.extracted_char_count,
                            cls_res.document_type,
                            cls_res.confidence,
                            1 if cls_res.is_certain else 0,
                            json.dumps(cls_res.signals),
                            json.dumps(cls_res.candidates),
                            len(structure_bundle.layout_regions),
                            len(structure_bundle.tables),
                            len(structure_bundle.entities),
                            processed_at,
                            doc_id,
                        ),
                    )

                    cursor.execute(
                        "UPDATE investigations SET updated_at = ? WHERE id = ?;",
                        (processed_at, investigation_id),
                    )

                    AuditService.append_event_with_cursor(
                        cursor,
                        investigation_id=investigation_id,
                        action="DOCUMENT_EXTRACTION_COMPLETED",
                        entity_type="DOCUMENT",
                        entity_id=doc_id,
                        actor="VERITAS Structure Intelligence Engine",
                        summary=(
                            f"Classified '{orig_filename}' as {cls_res.display_label} "
                            f"({cls_res.confidence * 100:.1f}% confidence) via "
                            f"{extraction_result.extraction_method_summary}: "
                            f"{len(structure_bundle.layout_regions)} layout regions, "
                            f"{len(structure_bundle.tables)} table(s), "
                            f"{len(structure_bundle.entities)} normalized entities"
                        ),
                        metadata={
                            "case_code": case_code,
                            "document_id": doc_id,
                            "filename": orig_filename,
                            "extraction_method": extraction_result.extraction_method_summary,
                            "document_type": cls_res.document_type,
                            "classification_confidence": cls_res.confidence,
                            "classification_is_certain": cls_res.is_certain,
                            "page_count": extraction_result.page_count,
                            "total_blocks": total_blocks,
                            "layout_regions": len(
                                structure_bundle.layout_regions
                            ),
                            "tables": len(structure_bundle.tables),
                            "entities": len(structure_bundle.entities),
                            "sha256_hash": sha256_digest,
                        },
                        actor_user_id=current_user.id if current_user else None,
                        actor_role=current_user.role if current_user else "SYSTEM",
                        event_origin="SYSTEM",
                        created_at=processed_at,
                    )

                if settings.enable_cv_forensics:
                    try:
                        from app.services.forensics_service import ForensicsService

                        ForensicsService.run_document_forensic_analysis(doc_id)
                    except Exception:
                        pass

                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM documents WHERE id = ?;", (doc_id,))
                    results.append(_row_to_document_summary(cursor.fetchone()))

            except Exception as exc:
                failed_at = _utc_now_iso()
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        UPDATE documents
                        SET processing_status = 'FAILED',
                            error_message = ?,
                            processed_at = ?
                        WHERE id = ?;
                        """,
                        (str(exc), failed_at, doc_id),
                    )
                    cursor.execute("SELECT * FROM documents WHERE id = ?;", (doc_id,))
                    results.append(_row_to_document_summary(cursor.fetchone()))

        try:
            from app.services.context_service import ContextService

            ContextService.run_investigation_context_analysis(
                investigation_id=investigation_id
            )
        except Exception:
            pass

        return results

    @staticmethod
    def backfill_phase2b_structure_for_existing_documents() -> int:
        """
        Safely backfills Phase 2B classification, layout regions, tables, and entities
        for any existing Phase 2A documents without modifying original extraction records.
        """
        updated_count = 0
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, investigation_id, file_type, storage_path
                FROM documents
                WHERE processing_status = 'COMPLETED'
                  AND layout_region_count = 0;
                """
            )
            docs_to_upgrade = cursor.fetchall()

        for d_row in docs_to_upgrade:
            doc_id = d_row["id"]
            inv_id = d_row["investigation_id"]
            f_type = d_row["file_type"]
            st_path = Path(d_row["storage_path"] or "")
            if not st_path.exists():
                continue

            file_bytes = st_path.read_bytes()
            ext_res = DualPathExtractionEngine.extract_document(
                file_bytes=file_bytes, file_type=f_type, document_id=doc_id
            )
            struct_bundle = (
                StructureIntelligenceEngine.analyze_document_structure(
                    file_bytes=file_bytes,
                    file_type=f_type,
                    extraction_result=ext_res,
                )
            )
            now = _utc_now_iso()
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM document_layout_regions WHERE document_id = ?;",
                    (doc_id,),
                )
                cursor.execute(
                    "DELETE FROM document_tables WHERE document_id = ?;",
                    (doc_id,),
                )
                cursor.execute(
                    "DELETE FROM document_entities WHERE document_id = ?;",
                    (doc_id,),
                )
                _persist_structure_bundle(
                    cursor=cursor,
                    doc_id=doc_id,
                    investigation_id=inv_id,
                    structure_bundle=struct_bundle,
                    processed_at=now,
                )
                cls_res = struct_bundle.classification
                cursor.execute(
                    """
                    UPDATE documents
                    SET document_type = ?,
                        classification_confidence = ?,
                        classification_is_certain = ?,
                        classification_signals_json = ?,
                        classification_candidates_json = ?,
                        layout_region_count = ?,
                        table_count = ?,
                        entity_count = ?
                    WHERE id = ?;
                    """,
                    (
                        cls_res.document_type,
                        cls_res.confidence,
                        1 if cls_res.is_certain else 0,
                        json.dumps(cls_res.signals),
                        json.dumps(cls_res.candidates),
                        len(struct_bundle.layout_regions),
                        len(struct_bundle.tables),
                        len(struct_bundle.entities),
                        doc_id,
                    ),
                )
                updated_count += 1
        return updated_count

    @staticmethod
    def list_investigation_documents(
        investigation_id: str,
    ) -> List[DocumentSummaryResponse]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM investigations WHERE id = ?;", (investigation_id,)
            )
            if not cursor.fetchone():
                raise ResourceNotFoundException("Investigation", investigation_id)

            cursor.execute(
                """
                SELECT * FROM documents
                WHERE investigation_id = ?
                ORDER BY uploaded_at DESC;
                """,
                (investigation_id,),
            )
            return [_row_to_document_summary(r) for r in cursor.fetchall()]

    @staticmethod
    def get_document_detail(document_id: str) -> DocumentDetailResponse:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE id = ?;", (document_id,))
            doc_row = cursor.fetchone()
            if not doc_row:
                raise ResourceNotFoundException("Document", document_id)

            summary = _row_to_document_summary(doc_row)

            # Build Classification Schema
            try:
                raw_candidates = json.loads(
                    doc_row["classification_candidates_json"] or "[]"
                )
            except Exception:
                raw_candidates = []
            candidates = [
                ClassificationCandidateSchema(
                    document_type=str(c.get("document_type", "OTHER_UNKNOWN")),
                    display_label=str(
                        c.get("display_label", "Other / Unknown")
                    ),
                    confidence=round(float(c.get("confidence", 0.0)), 4),
                    matched_signals=[
                        str(s) for s in c.get("matched_signals", [])
                    ],
                )
                for c in raw_candidates
            ]

            status_lbl = (
                "AUTOMATED_CLASSIFICATION — High Signal Match (Unverified)"
                if summary.classification_is_certain
                else "LOW_CONFIDENCE_OR_AMBIGUOUS — Manual Analyst Review Required"
            )
            classification = DocumentClassificationSchema(
                document_type=summary.document_type,
                display_label=summary.document_type_label,
                confidence=summary.classification_confidence,
                is_certain=summary.classification_is_certain,
                status_label=status_lbl,
                signals=summary.classification_signals,
                candidates=candidates,
            )

            cursor.execute(
                """
                SELECT * FROM document_pages
                WHERE document_id = ?
                ORDER BY page_number ASC;
                """,
                (document_id,),
            )
            page_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT * FROM document_extractions
                WHERE document_id = ?
                ORDER BY page_number ASC, block_index ASC;
                """,
                (document_id,),
            )
            all_extractions = [
                _row_to_extraction_record(r) for r in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT * FROM document_layout_regions
                WHERE document_id = ?
                ORDER BY page_number ASC, reading_order ASC;
                """,
                (document_id,),
            )
            all_layout_regions = [
                _row_to_layout_region(r) for r in cursor.fetchall()
            ]

            all_tables = _load_tables_for_document(cursor, document_id)

            cursor.execute(
                """
                SELECT * FROM document_entities
                WHERE document_id = ?
                ORDER BY page_number ASC, created_at ASC;
                """,
                (document_id,),
            )
            all_entities = [_row_to_entity(r) for r in cursor.fetchall()]

            extractions_by_page: Dict[int, List[ExtractionRecordResponse]] = {}
            layout_by_page: Dict[int, List[LayoutRegionResponse]] = {}
            tables_by_page: Dict[int, List[ExtractedTableResponse]] = {}
            entities_by_page: Dict[int, List[ExtractedEntityResponse]] = {}
            structured_fields: List[ExtractionRecordResponse] = []

            for ext_item in all_extractions:
                extractions_by_page.setdefault(ext_item.page_number, []).append(
                    ext_item
                )
                if ext_item.field_name:
                    structured_fields.append(ext_item)

            for lr in all_layout_regions:
                layout_by_page.setdefault(lr.page_number, []).append(lr)

            for tb in all_tables:
                tables_by_page.setdefault(tb.page_number, []).append(tb)

            for en in all_entities:
                entities_by_page.setdefault(en.page_number, []).append(en)

            pages: List[DocumentPageResponse] = []
            for p_row in page_rows:
                try:
                    raw_fonts = json.loads(p_row["font_summary_json"] or "[]")
                except Exception:
                    raw_fonts = []
                fonts = [
                    FontMetadataItem(
                        font_name=str(f.get("font_name", "Unknown")),
                        font_size=float(f.get("font_size", 0.0)),
                        span_count=int(f.get("span_count", 1)),
                    )
                    for f in raw_fonts
                ]
                p_num = int(p_row["page_number"])
                pages.append(
                    DocumentPageResponse(
                        id=p_row["id"],
                        document_id=p_row["document_id"],
                        page_number=p_num,
                        width=float(p_row["width"] or 0.0),
                        height=float(p_row["height"] or 0.0),
                        extraction_method=p_row["extraction_method"],
                        is_scanned_page=bool(p_row["is_scanned_page"]),
                        raw_text=p_row["raw_text"] or "",
                        char_count=int(p_row["char_count"] or 0),
                        block_count=int(p_row["block_count"] or 0),
                        average_confidence=round(
                            float(p_row["average_confidence"] or 0.0), 4
                        ),
                        fonts=fonts,
                        extractions=extractions_by_page.get(p_num, []),
                        layout_regions=layout_by_page.get(p_num, []),
                        tables=tables_by_page.get(p_num, []),
                        entities=entities_by_page.get(p_num, []),
                        created_at=p_row["created_at"],
                    )
                )

            return DocumentDetailResponse(
                **summary.model_dump(),
                classification=classification,
                pages=pages,
                structured_fields=structured_fields,
                layout_regions=all_layout_regions,
                tables=all_tables,
                entities=all_entities,
            )

    @staticmethod
    def get_document_extraction_bundle(
        document_id: str,
        page_number: Optional[int] = None,
        extraction_method: Optional[str] = None,
        structured_only: bool = False,
    ) -> DocumentExtractionBundleResponse:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE id = ?;", (document_id,))
            doc_row = cursor.fetchone()
            if not doc_row:
                raise ResourceNotFoundException("Document", document_id)

            summary = _row_to_document_summary(doc_row)

            query = "SELECT * FROM document_extractions WHERE document_id = ?"
            params: List[Any] = [document_id]

            if page_number is not None:
                query += " AND page_number = ?"
                params.append(page_number)

            if extraction_method:
                query += " AND extraction_method = ?"
                params.append(extraction_method.upper())

            if structured_only:
                query += " AND field_name IS NOT NULL"

            query += " ORDER BY page_number ASC, block_index ASC;"
            cursor.execute(query, tuple(params))
            extractions = [_row_to_extraction_record(r) for r in cursor.fetchall()]

            cursor.execute(
                """
                SELECT raw_text FROM document_pages
                WHERE document_id = ?
                ORDER BY page_number ASC;
                """,
                (document_id,),
            )
            full_text = "\n\n--- PAGE BREAK ---\n\n".join(
                r["raw_text"] for r in cursor.fetchall() if r["raw_text"]
            )

            if page_number is not None:
                cursor.execute(
                    """
                    SELECT * FROM document_layout_regions
                    WHERE document_id = ? AND page_number = ?
                    ORDER BY reading_order ASC;
                    """,
                    (document_id, page_number),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM document_layout_regions
                    WHERE document_id = ?
                    ORDER BY page_number ASC, reading_order ASC;
                    """,
                    (document_id,),
                )
            layout_regions = [
                _row_to_layout_region(r) for r in cursor.fetchall()
            ]

            tables = _load_tables_for_document(cursor, document_id, page_number)

            if page_number is not None:
                cursor.execute(
                    """
                    SELECT * FROM document_entities
                    WHERE document_id = ? AND page_number = ?
                    ORDER BY page_number ASC, created_at ASC;
                    """,
                    (document_id, page_number),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM document_entities
                    WHERE document_id = ?
                    ORDER BY page_number ASC, created_at ASC;
                    """,
                    (document_id,),
                )
            entities = [_row_to_entity(r) for r in cursor.fetchall()]

            structured_fields = [e for e in extractions if e.field_name]

            return DocumentExtractionBundleResponse(
                document_id=summary.id,
                investigation_id=summary.investigation_id,
                filename=summary.filename,
                sha256_hash=summary.sha256_hash,
                page_count=summary.page_count,
                extraction_method_summary=summary.extraction_method_summary,
                is_scanned=summary.is_scanned,
                average_confidence=summary.average_confidence,
                document_type=summary.document_type,
                document_type_label=summary.document_type_label,
                classification_confidence=summary.classification_confidence,
                classification_is_certain=summary.classification_is_certain,
                total_blocks=len(extractions),
                structured_field_count=len(structured_fields),
                layout_region_count=len(layout_regions),
                table_count=len(tables),
                entity_count=len(entities),
                full_text=full_text,
                structured_fields=structured_fields,
                extractions=extractions,
                layout_regions=layout_regions,
                tables=tables,
                entities=entities,
            )

    @staticmethod
    def get_document_page_detail(
        document_id: str, page_number: int
    ) -> DocumentPageResponse:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM documents WHERE id = ?;", (document_id,)
            )
            if not cursor.fetchone():
                raise ResourceNotFoundException("Document", document_id)

            cursor.execute(
                """
                SELECT * FROM document_pages
                WHERE document_id = ? AND page_number = ?;
                """,
                (document_id, page_number),
            )
            p_row = cursor.fetchone()
            if not p_row:
                raise ResourceNotFoundException(
                    "DocumentPage", f"{document_id}:page-{page_number}"
                )

            cursor.execute(
                """
                SELECT * FROM document_extractions
                WHERE document_id = ? AND page_number = ?
                ORDER BY block_index ASC;
                """,
                (document_id, page_number),
            )
            extractions = [_row_to_extraction_record(r) for r in cursor.fetchall()]

            cursor.execute(
                """
                SELECT * FROM document_layout_regions
                WHERE document_id = ? AND page_number = ?
                ORDER BY reading_order ASC;
                """,
                (document_id, page_number),
            )
            layout_regions = [
                _row_to_layout_region(r) for r in cursor.fetchall()
            ]

            tables = _load_tables_for_document(cursor, document_id, page_number)

            cursor.execute(
                """
                SELECT * FROM document_entities
                WHERE document_id = ? AND page_number = ?
                ORDER BY created_at ASC;
                """,
                (document_id, page_number),
            )
            entities = [_row_to_entity(r) for r in cursor.fetchall()]

            try:
                raw_fonts = json.loads(p_row["font_summary_json"] or "[]")
            except Exception:
                raw_fonts = []
            fonts = [
                FontMetadataItem(
                    font_name=str(f.get("font_name", "Unknown")),
                    font_size=float(f.get("font_size", 0.0)),
                    span_count=int(f.get("span_count", 1)),
                )
                for f in raw_fonts
            ]

            return DocumentPageResponse(
                id=p_row["id"],
                document_id=p_row["document_id"],
                page_number=int(p_row["page_number"]),
                width=float(p_row["width"] or 0.0),
                height=float(p_row["height"] or 0.0),
                extraction_method=p_row["extraction_method"],
                is_scanned_page=bool(p_row["is_scanned_page"]),
                raw_text=p_row["raw_text"] or "",
                char_count=int(p_row["char_count"] or 0),
                block_count=int(p_row["block_count"] or 0),
                average_confidence=round(
                    float(p_row["average_confidence"] or 0.0), 4
                ),
                fonts=fonts,
                extractions=extractions,
                layout_regions=layout_regions,
                tables=tables,
                entities=entities,
                created_at=p_row["created_at"],
            )

    @staticmethod
    def get_document_download_bytes(
        document_id: str,
    ) -> Tuple[bytes, str, str, str]:
        """
        Safely retrieves the raw document binary from private storage after verifying
        storage boundary containment and SHA-256 chain of custody.
        Returns (file_bytes, mime_type, safe_filename, sha256_hash).
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT filename, mime_type, storage_path, sha256_hash
                FROM documents
                WHERE id = ?;
                """,
                (document_id,),
            )
            doc_row = cursor.fetchone()
            if not doc_row:
                raise ResourceNotFoundException("Document", document_id)

            storage_path = _verify_storage_containment(
                Path(doc_row["storage_path"] or ""),
                settings.resolved_storage_dir,
            )
            if not storage_path.exists():
                raise ResourceNotFoundException("DocumentFile", document_id)

            file_bytes = storage_path.read_bytes()
            live_sha256 = hashlib.sha256(file_bytes).hexdigest()
            expected_sha256 = doc_row["sha256_hash"] or ""
            if expected_sha256 and live_sha256 != expected_sha256:
                raise InvalidDocumentException(
                    message="Document SHA-256 fingerprint mismatch detected on disk.",
                    code="CHAIN_OF_CUSTODY_HASH_MISMATCH",
                )

            safe_filename = _sanitize_filename(doc_row["filename"] or "document")
            mime_type = doc_row["mime_type"] or "application/octet-stream"
            return file_bytes, mime_type, safe_filename, live_sha256

    @staticmethod
    def render_document_page_preview_png(
        document_id: str, page_number: int
    ) -> bytes:
        """
        Renders a single page of an ingested document as a PNG image for the
        frontend bounding-box overlay inspector without exposing raw storage paths publicly.
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT file_type, storage_path, page_count FROM documents WHERE id = ?;",
                (document_id,),
            )
            doc_row = cursor.fetchone()
            if not doc_row:
                raise ResourceNotFoundException("Document", document_id)

            storage_path = _verify_storage_containment(
                Path(doc_row["storage_path"] or ""),
                settings.resolved_storage_dir,
            )
            if not storage_path.exists():
                raise ResourceNotFoundException("DocumentFile", document_id)

            file_type = str(doc_row["file_type"] or "").upper()
            file_bytes = storage_path.read_bytes()

        if file_type == "PDF":
            with fitz.open(stream=file_bytes, filetype="pdf") as pdf_doc:
                if page_number < 1 or page_number > len(pdf_doc):
                    raise ResourceNotFoundException(
                        "DocumentPage", f"{document_id}:page-{page_number}"
                    )
                page = pdf_doc[page_number - 1]
                pix = page.get_pixmap(dpi=150, alpha=False)
                return pix.tobytes("png")
        else:
            if page_number != 1:
                raise ResourceNotFoundException(
                    "DocumentPage", f"{document_id}:page-{page_number}"
                )
            with Image.open(io.BytesIO(file_bytes)) as pil_img:
                rgb = pil_img.convert("RGB")
                buf = io.BytesIO()
                rgb.save(buf, format="PNG")
                return buf.getvalue()
