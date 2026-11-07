import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from app.core.config import settings
from app.core.database import get_db_connection
from app.core.exceptions import InvalidDocumentException, ResourceNotFoundException
from app.models.entities import (
    ForensicAnalysisStatus,
    ForensicFindingSeverity,
    ForensicReviewStatus,
)
from app.schemas.auth import AuthenticatedUser
from app.schemas.document import BoundingBoxSchema
from app.schemas.forensics import (
    DocumentMetadataInspectionSchema,
    ForensicAnalysisDetailResponse,
    ForensicAnalysisRequest,
    ForensicArtifactResponse,
    ForensicFindingResponse,
    ForensicReviewRecordResponse,
    ForensicReviewRequest,
    ModuleExecutionSummarySchema,
)
from app.services.audit_service import AuditService
from app.services.document_service import DocumentService, _parse_bbox
from app.services.visual_forensics_engine import VisualForensicsEngine


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_loads(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _row_to_artifact_response(row: Any) -> ForensicArtifactResponse:
    return ForensicArtifactResponse(
        artifact_id=row["id"],
        analysis_id=row["analysis_id"],
        investigation_id=row["investigation_id"],
        document_id=row["document_id"],
        page_number=int(row["page_number"] or 1),
        artifact_type=row["artifact_type"],
        module_name=row["module_name"],
        title=row["title"],
        description=row["description"] or "",
        mime_type=row["mime_type"] or "image/png",
        file_size_bytes=int(row["file_size_bytes"] or 0),
        sha256_hash=row["sha256_hash"] or "",
        source_document_sha256=row["source_document_sha256"] or "",
        is_derived_from_pdf_render=bool(row["is_derived_from_pdf_render"]),
        parameters=_safe_json_loads(row["parameters_json"], {}),
        stats=_safe_json_loads(row["stats_json"], {}),
        created_at=row["created_at"],
    )


def _row_to_finding_response(
    row: Any, reviews: Optional[List[ForensicReviewRecordResponse]] = None
) -> ForensicFindingResponse:
    bbox_raw = row["bounding_box_json"]
    bbox_obj: Optional[BoundingBoxSchema] = (
        _parse_bbox(bbox_raw) if bbox_raw else None
    )
    return ForensicFindingResponse(
        finding_id=row["id"],
        investigation_id=row["investigation_id"],
        document_id=row["document_id"],
        document_sha256=row["document_sha256"],
        analysis_id=row["analysis_id"],
        module_name=row["module_name"],
        finding_category=row["finding_category"],
        severity=row["severity"],
        title=row["title"],
        observation=row["observation"],
        technical_explanation=row["technical_explanation"],
        possible_benign_explanations=_safe_json_loads(
            row["possible_benign_explanations_json"], []
        ),
        confidence_score=round(float(row["confidence_score"] or 0.0), 4),
        confidence_interpretation=row["confidence_interpretation"] or "",
        limitations=row["limitations"] or "",
        page_number=int(row["page_number"] or 1),
        bounding_box=bbox_obj,
        evidence_reference=row["evidence_reference"],
        artifact_id=row["artifact_id"],
        analysis_parameters=_safe_json_loads(row["analysis_parameters_json"], {}),
        evidence_metrics=_safe_json_loads(row["evidence_metrics_json"], {}),
        recommended_human_action=row["recommended_human_action"],
        review_status=row["review_status"],
        reviewer=row["reviewer"],
        review_notes=row["review_notes"],
        reviewed_at=row["reviewed_at"],
        review_history=reviews or [],
        created_at=row["created_at"],
    )


class ForensicsService:
    @staticmethod
    def run_document_forensic_analysis(
        document_id: str,
        request_payload: Optional[ForensicAnalysisRequest] = None,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> ForensicAnalysisDetailResponse:
        req = request_payload or ForensicAnalysisRequest()

        # 1. Load document detail and verify existence + original file immutability
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE id = ?;", (document_id,))
            doc_row = cursor.fetchone()
            if not doc_row:
                raise ResourceNotFoundException("Document", document_id)

            investigation_id = doc_row["investigation_id"]
            filename = doc_row["filename"]
            file_type = doc_row["file_type"]
            recorded_sha256 = doc_row["sha256_hash"] or ""
            storage_path_str = doc_row["storage_path"] or ""

            cursor.execute(
                "SELECT case_code, lead_investigator FROM investigations WHERE id = ?;",
                (investigation_id,),
            )
            inv_row = cursor.fetchone()
            case_code = inv_row["case_code"] if inv_row else "UNKNOWN"
            actor = (
                f"{current_user.full_name} ({current_user.title})"
                if current_user
                else (
                    req.actor.strip()
                    if req.actor and req.actor.strip()
                    else (inv_row["lead_investigator"] if inv_row else "Lead Forensic Analyst")
                )
            )

        # If force_reanalyze is False and a completed analysis already exists, return it
        if not req.force_reanalyze and doc_row["latest_analysis_id"]:
            try:
                return ForensicsService.get_analysis_by_id(doc_row["latest_analysis_id"])
            except Exception:
                pass

        storage_path = Path(storage_path_str).resolve()
        allowed_root = settings.resolved_storage_dir.resolve()
        if not str(storage_path).startswith(str(allowed_root)) or not storage_path.exists():
            raise InvalidDocumentException(
                message=f"Original document binary for '{document_id}' is unavailable on secure storage.",
                code="DOCUMENT_STORAGE_MISSING",
            )

        file_bytes = storage_path.read_bytes()
        live_sha256 = hashlib.sha256(file_bytes).hexdigest()
        if recorded_sha256 and live_sha256 != recorded_sha256:
            raise InvalidDocumentException(
                message="Original document SHA-256 fingerprint mismatch detected; aborting to preserve chain of custody.",
                code="CHAIN_OF_CUSTODY_HASH_MISMATCH",
            )

        # Load Phase 2A/2B structured document data for cross-module forensic inspection
        doc_detail = DocumentService.get_document_detail(document_id)
        pages_db_data = [p.model_dump() for p in doc_detail.pages]
        layout_regions_db = [r.model_dump() for r in doc_detail.layout_regions]
        tables_db = [t.model_dump() for t in doc_detail.tables]
        entities_db = [e.model_dump() for e in doc_detail.entities]

        analysis_id = str(uuid.uuid4())
        started_at = _utc_now_iso()
        params_dict = {
            "ela_jpeg_quality": req.ela_jpeg_quality,
            "ela_amplification_scale": req.ela_amplification_scale,
            "max_image_dimension": settings.forensics_max_image_dimension,
            "triggered_by": actor,
        }

        # Log FORENSIC_ANALYSIS_STARTED
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO forensic_analyses (
                    id, investigation_id, document_id, document_sha256, status,
                    parameters_json, started_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    analysis_id,
                    investigation_id,
                    document_id,
                    live_sha256,
                    ForensicAnalysisStatus.RUNNING.value,
                    json.dumps(params_dict),
                    started_at,
                    started_at,
                ),
            )
            cursor.execute(
                "UPDATE documents SET forensic_status = 'RUNNING' WHERE id = ?;",
                (document_id,),
            )
            AuditService.append_event_with_cursor(
                cursor,
                investigation_id=investigation_id,
                action="FORENSIC_ANALYSIS_STARTED",
                entity_type="FORENSIC_ANALYSIS",
                entity_id=analysis_id,
                actor=actor,
                summary=f"Started Phase 3 Visual Forensics analysis on '{filename}' (SHA-256: {live_sha256[:16]}...)",
                metadata={
                    "case_code": case_code,
                    "document_id": document_id,
                    "analysis_id": analysis_id,
                    "filename": filename,
                    "document_sha256": live_sha256,
                    "parameters": params_dict,
                },
                actor_user_id=current_user.id if current_user else None,
                actor_role=current_user.role if current_user else None,
                event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                created_at=started_at,
            )

        try:
            run_result = VisualForensicsEngine.analyze_document(
                document_id=document_id,
                file_bytes=file_bytes,
                file_type=file_type,
                filename=filename,
                document_sha256=live_sha256,
                pages_db_data=pages_db_data,
                layout_regions_db=layout_regions_db,
                tables_db=tables_db,
                entities_db=entities_db,
                ela_jpeg_quality=req.ela_jpeg_quality,
                ela_amplification_scale=req.ela_amplification_scale,
            )

            # Verify original file was never modified during analysis
            post_sha256 = hashlib.sha256(storage_path.read_bytes()).hexdigest()
            if post_sha256 != live_sha256:
                raise RuntimeError("Original file SHA-256 changed during analysis!")

            completed_at = _utc_now_iso()

            # Write derived forensic artifacts to separate storage directory
            artifact_dir = (
                settings.resolved_forensics_artifacts_dir
                / investigation_id
                / document_id
                / analysis_id
            )
            artifact_dir.mkdir(parents=True, exist_ok=True)

            with get_db_connection() as conn:
                cursor = conn.cursor()

                # Remove prior analyses for this document on re-analysis so counts stay clean
                cursor.execute(
                    "DELETE FROM forensic_analyses WHERE document_id = ? AND id != ?;",
                    (document_id, analysis_id),
                )
                cursor.execute(
                    "DELETE FROM findings WHERE document_id = ? AND finding_type LIKE 'MODULE_%';",
                    (document_id,),
                )

                for art in run_result.artifacts:
                    art_filename = f"{art.artifact_id}_{art.artifact_type.lower()}_p{art.page_number}.png"
                    art_path = artifact_dir / art_filename
                    art_path.write_bytes(art.png_bytes)
                    try:
                        os.chmod(art_path, 0o600)
                    except OSError:
                        pass

                    cursor.execute(
                        """
                        INSERT INTO forensic_artifacts (
                            id, analysis_id, investigation_id, document_id, page_number,
                            artifact_type, module_name, title, description, mime_type,
                            storage_path, file_size_bytes, sha256_hash, source_document_sha256,
                            is_derived_from_pdf_render, parameters_json, stats_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            art.artifact_id,
                            analysis_id,
                            investigation_id,
                            document_id,
                            art.page_number,
                            art.artifact_type,
                            art.module_name,
                            art.title,
                            art.description,
                            art.mime_type,
                            str(art_path),
                            len(art.png_bytes),
                            art.sha256_hash,
                            live_sha256,
                            1 if art.is_derived_from_pdf_render else 0,
                            json.dumps(art.parameters),
                            json.dumps(art.stats),
                            completed_at,
                        ),
                    )

                high_cnt = 0
                med_cnt = 0
                low_cnt = 0
                info_cnt = 0

                for fnd in run_result.findings:
                    if fnd.severity == ForensicFindingSeverity.HIGH.value:
                        high_cnt += 1
                    elif fnd.severity == ForensicFindingSeverity.MEDIUM.value:
                        med_cnt += 1
                    elif fnd.severity == ForensicFindingSeverity.LOW.value:
                        low_cnt += 1
                    else:
                        info_cnt += 1

                    # Informational baseline observations default to REVIEWED so analysts focus on actionable signals,
                    # whereas LOW/MEDIUM/HIGH anomalies default to REQUIRES_REVIEW
                    initial_review_status = (
                        ForensicReviewStatus.REVIEWED.value
                        if fnd.severity == ForensicFindingSeverity.INFORMATIONAL.value
                        else ForensicReviewStatus.REQUIRES_REVIEW.value
                    )

                    cursor.execute(
                        """
                        INSERT INTO forensic_findings (
                            id, investigation_id, document_id, document_sha256, analysis_id,
                            module_name, finding_category, severity, title, observation,
                            technical_explanation, possible_benign_explanations_json,
                            confidence_score, confidence_interpretation, limitations,
                            page_number, bounding_box_json, evidence_reference, artifact_id,
                            analysis_parameters_json, evidence_metrics_json,
                            recommended_human_action, review_status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            fnd.finding_id,
                            investigation_id,
                            document_id,
                            live_sha256,
                            analysis_id,
                            fnd.module_name,
                            fnd.finding_category,
                            fnd.severity,
                            fnd.title,
                            fnd.observation,
                            fnd.technical_explanation,
                            json.dumps(fnd.possible_benign_explanations),
                            fnd.confidence_score,
                            fnd.confidence_interpretation,
                            fnd.limitations,
                            fnd.page_number,
                            json.dumps(fnd.bounding_box) if fnd.bounding_box else None,
                            fnd.evidence_reference,
                            fnd.artifact_id,
                            json.dumps(fnd.analysis_parameters),
                            json.dumps(fnd.evidence_metrics),
                            fnd.recommended_human_action,
                            initial_review_status,
                            completed_at,
                        ),
                    )

                    # Mirror non-informational findings into the case-level `findings` table for Phase 1 dashboard counters
                    if fnd.severity != ForensicFindingSeverity.INFORMATIONAL.value:
                        cursor.execute(
                            """
                            INSERT INTO findings (
                                id, investigation_id, document_id, finding_type, severity,
                                review_status, title, description, confidence_score, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                            """,
                            (
                                fnd.finding_id,
                                investigation_id,
                                document_id,
                                f"{fnd.module_name}:{fnd.finding_category}",
                                fnd.severity,
                                initial_review_status,
                                fnd.title,
                                fnd.observation,
                                fnd.confidence_score,
                                completed_at,
                            ),
                        )

                    # Audit log FORENSIC_FINDING_CREATED for actionable findings
                    if fnd.severity != ForensicFindingSeverity.INFORMATIONAL.value:
                        AuditService.append_event_with_cursor(
                            cursor,
                            investigation_id=investigation_id,
                            action="FORENSIC_FINDING_CREATED",
                            entity_type="FORENSIC_FINDING",
                            entity_id=fnd.finding_id,
                            actor=actor,
                            summary=f"[{fnd.severity}] {fnd.title} on '{filename}' (Page {fnd.page_number})",
                            metadata={
                                "case_code": case_code,
                                "document_id": document_id,
                                "analysis_id": analysis_id,
                                "finding_id": fnd.finding_id,
                                "module_name": fnd.module_name,
                                "finding_category": fnd.finding_category,
                                "severity": fnd.severity,
                                "page_number": fnd.page_number,
                                "evidence_reference": fnd.evidence_reference,
                            },
                            actor_user_id=current_user.id if current_user else None,
                            actor_role=current_user.role if current_user else None,
                            event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                            created_at=completed_at,
                        )

                module_summaries_dicts = [
                    {
                        "module_name": m.module_name,
                        "display_name": m.display_name,
                        "status": m.status,
                        "findings_count": m.findings_count,
                        "duration_ms": m.duration_ms,
                        "methodology_summary": m.methodology_summary,
                        "limitations_note": m.limitations_note,
                    }
                    for m in run_result.module_summaries
                ]

                cursor.execute(
                    """
                    UPDATE forensic_analyses
                    SET status = ?,
                        modules_executed_json = ?,
                        module_summaries_json = ?,
                        pdf_metadata_json = ?,
                        findings_count = ?,
                        high_severity_count = ?,
                        medium_severity_count = ?,
                        low_severity_count = ?,
                        informational_count = ?,
                        processing_duration_ms = ?,
                        completed_at = ?
                    WHERE id = ?;
                    """,
                    (
                        ForensicAnalysisStatus.COMPLETED.value,
                        json.dumps(run_result.modules_executed),
                        json.dumps(module_summaries_dicts),
                        json.dumps(run_result.metadata_inspection),
                        len(run_result.findings),
                        high_cnt,
                        med_cnt,
                        low_cnt,
                        info_cnt,
                        run_result.processing_duration_ms,
                        completed_at,
                        analysis_id,
                    ),
                )

                cursor.execute(
                    """
                    UPDATE documents
                    SET forensic_status = 'COMPLETED',
                        latest_analysis_id = ?,
                        forensic_findings_count = ?,
                        forensic_analyzed_at = ?
                    WHERE id = ?;
                    """,
                    (
                        analysis_id,
                        len(run_result.findings),
                        completed_at,
                        document_id,
                    ),
                )

                cursor.execute(
                    "UPDATE investigations SET updated_at = ? WHERE id = ?;",
                    (completed_at, investigation_id),
                )

                AuditService.append_event_with_cursor(
                    cursor,
                    investigation_id=investigation_id,
                    action="FORENSIC_ANALYSIS_COMPLETED",
                    entity_type="FORENSIC_ANALYSIS",
                    entity_id=analysis_id,
                    actor=actor,
                    summary=(
                        f"Completed 7-module Visual Forensics analysis on '{filename}' "
                        f"in {run_result.processing_duration_ms}ms: {len(run_result.findings)} observation(s) "
                        f"({high_cnt} HIGH, {med_cnt} MEDIUM, {low_cnt} LOW, {info_cnt} INFO)"
                    ),
                    metadata={
                        "case_code": case_code,
                        "document_id": document_id,
                        "analysis_id": analysis_id,
                        "filename": filename,
                        "document_sha256": live_sha256,
                        "findings_count": len(run_result.findings),
                        "high_severity_count": high_cnt,
                        "medium_severity_count": med_cnt,
                        "low_severity_count": low_cnt,
                        "informational_count": info_cnt,
                        "artifacts_generated": len(run_result.artifacts),
                        "processing_duration_ms": run_result.processing_duration_ms,
                    },
                    actor_user_id=current_user.id if current_user else None,
                    actor_role=current_user.role if current_user else None,
                    event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                    created_at=completed_at,
                )

            return ForensicsService.get_analysis_by_id(analysis_id)

        except Exception as exc:
            failed_at = _utc_now_iso()
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE forensic_analyses
                    SET status = ?, error_message = ?, completed_at = ?
                    WHERE id = ?;
                    """,
                    (
                        ForensicAnalysisStatus.FAILED.value,
                        str(exc),
                        failed_at,
                        analysis_id,
                    ),
                )
                cursor.execute(
                    "UPDATE documents SET forensic_status = 'FAILED' WHERE id = ?;",
                    (document_id,),
                )
                AuditService.append_event_with_cursor(
                    cursor,
                    investigation_id=investigation_id,
                    action="FORENSIC_ANALYSIS_FAILED",
                    entity_type="FORENSIC_ANALYSIS",
                    entity_id=analysis_id,
                    actor=actor,
                    summary=f"Visual Forensics analysis failed on '{filename}': {exc}",
                    metadata={
                        "case_code": case_code,
                        "document_id": document_id,
                        "analysis_id": analysis_id,
                        "error": str(exc),
                    },
                    actor_user_id=current_user.id if current_user else None,
                    actor_role=current_user.role if current_user else None,
                    event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                    created_at=failed_at,
                )
            raise InvalidDocumentException(
                message=f"Visual Forensics analysis failed for '{filename}': {exc}",
                code="FORENSIC_ANALYSIS_FAILED",
                details={"document_id": document_id, "analysis_id": analysis_id},
            ) from exc

    @staticmethod
    def get_document_forensics(document_id: str) -> ForensicAnalysisDetailResponse:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, latest_analysis_id FROM documents WHERE id = ?;", (document_id,))
            doc_row = cursor.fetchone()
            if not doc_row:
                raise ResourceNotFoundException("Document", document_id)

            cursor.execute(
                """
                SELECT id FROM forensic_analyses
                WHERE document_id = ?
                ORDER BY created_at DESC
                LIMIT 1;
                """,
                (document_id,),
            )
            fa_row = cursor.fetchone()

        if not fa_row:
            # Automatically run initial analysis if none exists yet
            return ForensicsService.run_document_forensic_analysis(document_id)

        return ForensicsService.get_analysis_by_id(fa_row["id"])

    @staticmethod
    def get_analysis_by_id(analysis_id: str) -> ForensicAnalysisDetailResponse:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT fa.*, d.filename, d.file_type, d.storage_path, d.sha256_hash AS current_doc_sha256
                FROM forensic_analyses fa
                JOIN documents d ON d.id = fa.document_id
                WHERE fa.id = ?;
                """,
                (analysis_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ResourceNotFoundException("ForensicAnalysis", analysis_id)

            # Verify original file on disk is still intact and matches SHA-256
            storage_path = Path(row["storage_path"] or "")
            original_intact = False
            if storage_path.exists():
                disk_sha = hashlib.sha256(storage_path.read_bytes()).hexdigest()
                original_intact = disk_sha == row["document_sha256"]

            cursor.execute(
                """
                SELECT * FROM forensic_artifacts
                WHERE analysis_id = ?
                ORDER BY page_number ASC, created_at ASC;
                """,
                (analysis_id,),
            )
            artifacts = [_row_to_artifact_response(r) for r in cursor.fetchall()]

            cursor.execute(
                """
                SELECT * FROM forensic_reviews
                WHERE analysis_id = ?
                ORDER BY created_at DESC;
                """,
                (analysis_id,),
            )
            reviews_by_finding: Dict[str, List[ForensicReviewRecordResponse]] = {}
            for rev_row in cursor.fetchall():
                reviews_by_finding.setdefault(rev_row["finding_id"], []).append(
                    ForensicReviewRecordResponse(
                        review_id=rev_row["id"],
                        finding_id=rev_row["finding_id"],
                        analysis_id=rev_row["analysis_id"],
                        investigation_id=rev_row["investigation_id"],
                        document_id=rev_row["document_id"],
                        previous_status=rev_row["previous_status"],
                        new_status=rev_row["new_status"],
                        reviewer=rev_row["reviewer"],
                        notes=rev_row["notes"] or "",
                        created_at=rev_row["created_at"],
                    )
                )

            cursor.execute(
                """
                SELECT * FROM forensic_findings
                WHERE analysis_id = ?
                ORDER BY
                    CASE severity
                        WHEN 'HIGH' THEN 1
                        WHEN 'MEDIUM' THEN 2
                        WHEN 'LOW' THEN 3
                        ELSE 4
                    END ASC,
                    page_number ASC,
                    created_at ASC;
                """,
                (analysis_id,),
            )
            findings = [
                _row_to_finding_response(r, reviews_by_finding.get(r["id"], []))
                for r in cursor.fetchall()
            ]

            pending_cnt = sum(
                1
                for f in findings
                if f.review_status == ForensicReviewStatus.REQUIRES_REVIEW.value
            )
            reviewed_cnt = len(findings) - pending_cnt

            raw_meta = _safe_json_loads(row["pdf_metadata_json"], {})
            meta_schema = DocumentMetadataInspectionSchema(
                source_format=str(raw_meta.get("source_format", row["file_type"])),
                is_pdf=bool(raw_meta.get("is_pdf", row["file_type"] == "PDF")),
                creator=str(raw_meta.get("creator", "")),
                producer=str(raw_meta.get("producer", "")),
                creation_date_raw=str(raw_meta.get("creation_date_raw", "")),
                modification_date_raw=str(raw_meta.get("modification_date_raw", "")),
                title=str(raw_meta.get("title", "")),
                author=str(raw_meta.get("author", "")),
                subject=str(raw_meta.get("subject", "")),
                keywords=str(raw_meta.get("keywords", "")),
                pdf_version=str(raw_meta.get("pdf_version", "")),
                is_encrypted=bool(raw_meta.get("is_encrypted", False)),
                incremental_Save_eof_count=int(
                    raw_meta.get("incremental_save_eof_count", 1)
                ),
                xref_object_count=int(raw_meta.get("xref_object_count", 0)),
                page_dimensions=raw_meta.get("page_dimensions", []),
                embedded_images=raw_meta.get("embedded_images", []),
                font_resources=raw_meta.get("font_resources", []),
                annotations=raw_meta.get("annotations", []),
                raster_header_info=raw_meta.get("raster_header_info", {}),
            )

            mod_summaries = [
                ModuleExecutionSummarySchema(**m)
                for m in _safe_json_loads(row["module_summaries_json"], [])
            ]

            return ForensicAnalysisDetailResponse(
                analysis_id=row["id"],
                investigation_id=row["investigation_id"],
                document_id=row["document_id"],
                filename=row["filename"],
                file_type=row["file_type"],
                document_sha256=row["document_sha256"],
                original_file_intact=original_intact,
                status=row["status"],
                modules_executed=_safe_json_loads(row["modules_executed_json"], []),
                module_summaries=mod_summaries,
                parameters=_safe_json_loads(row["parameters_json"], {}),
                metadata_inspection=meta_schema,
                findings_count=int(row["findings_count"] or len(findings)),
                high_severity_count=int(row["high_severity_count"] or 0),
                medium_severity_count=int(row["medium_severity_count"] or 0),
                low_severity_count=int(row["low_severity_count"] or 0),
                informational_count=int(row["informational_count"] or 0),
                pending_review_count=pending_cnt,
                reviewed_count=reviewed_cnt,
                processing_duration_ms=round(float(row["processing_duration_ms"] or 0.0), 2),
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                error_message=row["error_message"],
                created_at=row["created_at"],
                artifacts=artifacts,
                findings=findings,
            )

    @staticmethod
    def list_document_findings(
        document_id: str,
        severity: Optional[str] = None,
        module_name: Optional[str] = None,
        review_status: Optional[str] = None,
    ) -> List[ForensicFindingResponse]:
        analysis = ForensicsService.get_document_forensics(document_id)
        items = analysis.findings
        if severity:
            items = [f for f in items if f.severity.upper() == severity.upper()]
        if module_name:
            items = [f for f in items if f.module_name.upper() == module_name.upper()]
        if review_status:
            items = [f for f in items if f.review_status.upper() == review_status.upper()]
        return items

    @staticmethod
    def get_finding_by_id(finding_id: str) -> ForensicFindingResponse:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM forensic_findings WHERE id = ?;", (finding_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise ResourceNotFoundException("ForensicFinding", finding_id)

            cursor.execute(
                """
                SELECT * FROM forensic_reviews
                WHERE finding_id = ?
                ORDER BY created_at DESC;
                """,
                (finding_id,),
            )
            reviews = [
                ForensicReviewRecordResponse(
                    review_id=r["id"],
                    finding_id=r["finding_id"],
                    analysis_id=r["analysis_id"],
                    investigation_id=r["investigation_id"],
                    document_id=r["document_id"],
                    previous_status=r["previous_status"],
                    new_status=r["new_status"],
                    reviewer=r["reviewer"],
                    notes=r["notes"] or "",
                    created_at=r["created_at"],
                )
                for r in cursor.fetchall()
            ]
            return _row_to_finding_response(row, reviews)

    @staticmethod
    def review_finding(
        finding_id: str,
        payload: ForensicReviewRequest,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> ForensicFindingResponse:
        valid_statuses = {s.value for s in ForensicReviewStatus}
        norm_status = payload.review_status.strip().upper()
        if norm_status not in valid_statuses:
            raise InvalidDocumentException(
                message=(
                    f"Invalid review_status '{payload.review_status}'. "
                    f"Allowed values: {sorted(valid_statuses)}."
                ),
                code="INVALID_REVIEW_STATUS",
            )

        now = _utc_now_iso()
        review_id = str(uuid.uuid4())
        reviewer_clean = (
            f"{current_user.full_name} ({current_user.title})"
            if current_user
            else (payload.reviewer.strip() or "Lead Forensic Analyst")
        )
        reviewer_user_id = current_user.id if current_user else None
        notes_clean = payload.notes.strip()

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM forensic_findings WHERE id = ?;", (finding_id,)
            )
            f_row = cursor.fetchone()
            if not f_row:
                raise ResourceNotFoundException("ForensicFinding", finding_id)

            prev_status = f_row["review_status"]
            inv_id = f_row["investigation_id"]
            doc_id = f_row["document_id"]
            analysis_id = f_row["analysis_id"]

            cursor.execute(
                "SELECT case_code FROM investigations WHERE id = ?;", (inv_id,)
            )
            inv_row = cursor.fetchone()
            case_code = inv_row["case_code"] if inv_row else "UNKNOWN"

            cursor.execute(
                """
                UPDATE forensic_findings
                SET review_status = ?,
                    reviewer = ?,
                    reviewer_user_id = ?,
                    review_notes = ?,
                    reviewed_at = ?
                WHERE id = ?;
                """,
                (
                    norm_status,
                    reviewer_clean,
                    reviewer_user_id,
                    notes_clean,
                    now,
                    finding_id,
                ),
            )

            # Synchronize review_status in the case-level `findings` table
            mapped_case_status = (
                "REQUIRES_REVIEW"
                if norm_status == "REQUIRES_REVIEW"
                else ("CONFIRMED" if norm_status == "CONFIRMED" else "DISMISSED")
            )
            cursor.execute(
                "UPDATE findings SET review_status = ? WHERE id = ?;",
                (mapped_case_status, finding_id),
            )

            cursor.execute(
                """
                INSERT INTO forensic_reviews (
                    id, finding_id, analysis_id, investigation_id, document_id,
                    previous_status, new_status, reviewer, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    review_id,
                    finding_id,
                    analysis_id,
                    inv_id,
                    doc_id,
                    prev_status,
                    norm_status,
                    reviewer_clean,
                    notes_clean,
                    now,
                ),
            )

            cursor.execute(
                "UPDATE investigations SET updated_at = ? WHERE id = ?;",
                (now, inv_id),
            )

            AuditService.append_event_with_cursor(
                cursor,
                investigation_id=inv_id,
                action="FORENSIC_FINDING_REVIEWED",
                entity_type="FORENSIC_FINDING",
                entity_id=finding_id,
                actor=reviewer_clean,
                summary=(
                    f"Human review recorded on finding '{f_row['title']}': "
                    f"{prev_status} -> {norm_status}"
                    + (f" ({notes_clean[:80]})" if notes_clean else "")
                ),
                metadata={
                    "case_code": case_code,
                    "finding_id": finding_id,
                    "document_id": doc_id,
                    "analysis_id": analysis_id,
                    "previous_status": prev_status,
                    "new_status": norm_status,
                    "reviewer": reviewer_clean,
                    "reviewer_user_id": reviewer_user_id,
                    "notes": notes_clean,
                },
                actor_user_id=reviewer_user_id,
                actor_role=current_user.role if current_user else None,
                event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                created_at=now,
            )

        return ForensicsService.get_finding_by_id(finding_id)

    @staticmethod
    def get_artifact_bytes(artifact_id: str) -> Tuple[bytes, str, str]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM forensic_artifacts WHERE id = ?;", (artifact_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise ResourceNotFoundException("ForensicArtifact", artifact_id)

            storage_path = Path(row["storage_path"] or "").resolve()
            allowed_root = settings.resolved_forensics_artifacts_dir.resolve()
            if (
                not str(storage_path).startswith(str(allowed_root))
                or not storage_path.exists()
            ):
                raise ResourceNotFoundException("ForensicArtifactFile", artifact_id)

            data = storage_path.read_bytes()
            return data, row["mime_type"] or "image/png", storage_path.name

    @staticmethod
    def backfill_phase3_forensics_for_existing_documents() -> None:
        """
        Ensures any existing COMPLETED documents in SQLite that have not yet run
        Phase 3 Visual Forensics are analyzed on startup.
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id FROM documents
                WHERE processing_status = 'COMPLETED'
                  AND (forensic_status IS NULL OR forensic_status = 'NOT_ANALYZED');
                """
            )
            pending_doc_ids = [r["id"] for r in cursor.fetchall()]

        for doc_id in pending_doc_ids:
            try:
                ForensicsService.run_document_forensic_analysis(doc_id)
            except Exception:
                pass
