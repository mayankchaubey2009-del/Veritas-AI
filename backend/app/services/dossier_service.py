import hashlib
import json
import os
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import fitz
from app.core.config import settings
from app.core.database import get_db_connection
from app.core.exceptions import (
    AuthorizationException,
    InvalidDocumentException,
    ResourceNotFoundException,
)
from app.models.entities import DossierReviewStatus
from app.schemas.auth import AuthenticatedUser
from app.schemas.dossier import (
    DossierDetailResponse,
    DossierGenerateRequest,
    DossierReviewRecordSchema,
    DossierReviewRequest,
    DossierSummaryResponse,
    EvidenceGroundedClaimSchema,
    EvidenceManifestItemSchema,
    InvestigationQuestionSchema,
    InvestigationReasoningResponse,
    ReasoningGenerateRequest,
    ReasoningSectionSchema,
    RejectedClaimLogSchema,
    SourceDocumentHashItemSchema,
    VerificationStepSchema,
)
from app.services.audit_service import AuditService
from app.services.context_service import ContextService
from app.services.document_service import DocumentService, _verify_storage_containment
from app.services.forensics_service import ForensicsService
from app.services.investigation_reasoning_engine import InvestigationReasoningEngine


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_loads(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _row_to_reasoning_response(
    row: Any, inv_title: str
) -> InvestigationReasoningResponse:
    raw_manifest = _safe_json_loads(row["evidence_manifest_json"], {})
    manifest = {
        k: EvidenceManifestItemSchema(**v) for k, v in raw_manifest.items()
    }
    raw_hashes = _safe_json_loads(row["source_document_hashes_json"], [])
    doc_hashes = [SourceDocumentHashItemSchema(**dh) for dh in raw_hashes]
    raw_sections = _safe_json_loads(row["sections_json"], [])
    sections = [ReasoningSectionSchema(**s) for s in raw_sections]
    raw_claims = _safe_json_loads(row["claims_json"], [])
    claims = [EvidenceGroundedClaimSchema(**c) for c in raw_claims]
    raw_rejected = _safe_json_loads(row["rejected_claims_log_json"], [])
    rejected_log = [RejectedClaimLogSchema(**rc) for rc in raw_rejected]
    raw_questions = _safe_json_loads(row["questions_json"], [])
    questions = [InvestigationQuestionSchema(**q) for q in raw_questions]
    raw_steps = _safe_json_loads(row["verification_steps_json"], [])
    steps = [VerificationStepSchema(**st) for st in raw_steps]

    return InvestigationReasoningResponse(
        reasoning_run_id=row["id"],
        investigation_id=row["investigation_id"],
        case_code=row["case_code"],
        investigation_title=inv_title,
        reasoning_engine_version=row["reasoning_engine_version"],
        ai_provider=row["ai_provider"],
        ai_model=row["ai_model"],
        prompt_version=row["prompt_version"],
        ai_assisted=bool(row["ai_assisted"]),
        fallback_used=bool(row["fallback_used"]),
        fallback_reason=row["fallback_reason"],
        source_analysis_ids=_safe_json_loads(row["source_analysis_ids_json"], {}),
        source_document_hashes=doc_hashes,
        evidence_manifest=manifest,
        sections=sections,
        claims=claims,
        rejected_claims_count=int(row["rejected_claims_count"] or 0),
        rejected_claims_log=rejected_log,
        questions=questions,
        verification_steps=steps,
        processing_duration_ms=round(float(row["processing_duration_ms"] or 0.0), 2),
        created_at=row["created_at"],
    )


def _row_to_dossier_summary(row: Any, case_code: str) -> DossierSummaryResponse:
    keys = row.keys()
    return DossierSummaryResponse(
        dossier_id=row["id"],
        investigation_id=row["investigation_id"],
        case_code=case_code,
        reasoning_run_id=row["reasoning_run_id"],
        version_number=int(row["version_number"] or 1),
        title=row["title"],
        status=row["status"],
        reasoning_engine_version=row["reasoning_engine_version"],
        ai_provider=row["ai_provider"],
        ai_model=row["ai_model"],
        prompt_version=row["prompt_version"],
        pdf_size_bytes=int(row["pdf_size_bytes"] or 0),
        pdf_sha256_hash=row["pdf_sha256_hash"],
        json_size_bytes=int(row["json_size_bytes"] or 0),
        json_sha256_hash=row["json_sha256_hash"],
        dossier_sha256_hash=row["dossier_sha256_hash"],
        review_status=row["review_status"],
        reviewed_by=row["reviewed_by"],
        reviewed_by_user_id=(
            row["reviewed_by_user_id"] if "reviewed_by_user_id" in keys else None
        ),
        review_notes=row["review_notes"],
        reviewed_at=row["reviewed_at"],
        generated_by=row["generated_by"],
        generated_by_user_id=(
            row["generated_by_user_id"] if "generated_by_user_id" in keys else None
        ),
        created_at=row["created_at"],
    )


class DossierService:
    @staticmethod
    def _collect_investigation_artifacts(
        investigation_id: str,
    ) -> Tuple[
        Dict[str, Any],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        Optional[Dict[str, Any]],
        int,
    ]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM investigations WHERE id = ?;", (investigation_id,)
            )
            inv_row = cursor.fetchone()
            if not inv_row:
                raise ResourceNotFoundException("Investigation", investigation_id)
            inv_dict = dict(inv_row)

            cursor.execute(
                """
                SELECT id FROM documents
                WHERE investigation_id = ? AND processing_status = 'COMPLETED'
                ORDER BY uploaded_at ASC;
                """,
                (investigation_id,),
            )
            doc_ids = [r["id"] for r in cursor.fetchall()]

            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM audit_logs WHERE investigation_id = ?;",
                (investigation_id,),
            )
            audit_cnt = int(cursor.fetchone()["cnt"] or 0)

        documents_bundle: List[Dict[str, Any]] = []
        forensic_analyses: List[Dict[str, Any]] = []
        forensic_findings: List[Dict[str, Any]] = []

        for d_id in doc_ids:
            doc_detail = DocumentService.get_document_detail(d_id)
            documents_bundle.append(doc_detail.model_dump())
            try:
                fa_detail = ForensicsService.get_document_forensics(d_id)
                fa_dump = fa_detail.model_dump()
                forensic_analyses.append(fa_dump)
                for ff in fa_dump.get("findings", []):
                    ff["filename"] = doc_detail.filename
                    forensic_findings.append(ff)
            except Exception:
                pass

        contextual_bundle: Optional[Dict[str, Any]] = None
        if doc_ids:
            try:
                ctx_resp = ContextService.get_investigation_context(investigation_id)
                contextual_bundle = ctx_resp.model_dump()
            except Exception:
                pass

        return (
            inv_dict,
            documents_bundle,
            forensic_analyses,
            forensic_findings,
            contextual_bundle,
            audit_cnt,
        )

    @staticmethod
    def generate_investigation_reasoning(
        investigation_id: str,
        payload: Optional[ReasoningGenerateRequest] = None,
        custom_ai_callable: Optional[
            Callable[[Dict[str, EvidenceManifestItemSchema]], Dict[str, Any]]
        ] = None,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> InvestigationReasoningResponse:
        req = payload or ReasoningGenerateRequest()
        (
            inv_dict,
            documents_bundle,
            forensic_analyses,
            forensic_findings,
            contextual_bundle,
            audit_cnt,
        ) = DossierService._collect_investigation_artifacts(investigation_id)

        run_out = InvestigationReasoningEngine.generate_investigation_reasoning(
            investigation_row=inv_dict,
            documents_bundle=documents_bundle,
            forensic_analyses=forensic_analyses,
            forensic_findings=forensic_findings,
            contextual_bundle=contextual_bundle,
            audit_logs_count=audit_cnt,
            use_ai_provider_if_available=req.use_ai_provider_if_available,
            custom_ai_callable=custom_ai_callable,
        )

        run_id = str(uuid.uuid4())
        now = _utc_now_iso()
        case_code = inv_dict["case_code"]
        inv_title = inv_dict["title"]
        actor = (
            f"{current_user.full_name} ({current_user.title})"
            if current_user
            else (req.actor.strip() or "Lead Forensic Analyst")
        )

        manifest_serialized = {
            k: v.model_dump() for k, v in run_out.evidence_manifest.items()
        }
        hashes_serialized = [
            dh.model_dump() for dh in run_out.source_document_hashes
        ]
        sections_serialized = [s.model_dump() for s in run_out.sections]
        claims_serialized = [c.model_dump() for c in run_out.claims]
        rejected_serialized = [
            rc.model_dump() for rc in run_out.rejected_claims_log
        ]
        questions_serialized = [q.model_dump() for q in run_out.questions]
        steps_serialized = [st.model_dump() for st in run_out.verification_steps]

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO investigation_reasoning_runs (
                    id, investigation_id, case_code, reasoning_engine_version,
                    ai_provider, ai_model, prompt_version, ai_assisted,
                    fallback_used, fallback_reason, source_analysis_ids_json,
                    source_document_hashes_json, evidence_manifest_json,
                    sections_json, claims_json, rejected_claims_count,
                    rejected_claims_log_json, questions_json,
                    verification_steps_json, processing_duration_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    run_id,
                    investigation_id,
                    case_code,
                    run_out.reasoning_engine_version,
                    run_out.ai_provider,
                    run_out.ai_model,
                    run_out.prompt_version,
                    1 if run_out.ai_assisted else 0,
                    1 if run_out.fallback_used else 0,
                    run_out.fallback_reason,
                    json.dumps(run_out.source_analysis_ids),
                    json.dumps(hashes_serialized),
                    json.dumps(manifest_serialized),
                    json.dumps(sections_serialized),
                    json.dumps(claims_serialized),
                    run_out.rejected_claims_count,
                    json.dumps(rejected_serialized),
                    json.dumps(questions_serialized),
                    json.dumps(steps_serialized),
                    run_out.processing_duration_ms,
                    now,
                ),
            )

            AuditService.append_event_with_cursor(
                cursor,
                investigation_id=investigation_id,
                action="INVESTIGATION_REASONING_GENERATED",
                entity_type="REASONING_RUN",
                entity_id=run_id,
                actor=actor,
                summary=(
                    f"Generated Phase 5 Evidence-Grounded Reasoning for {case_code}: "
                    f"{len(run_out.sections)} sections (A–N), {len(run_out.claims)} validated claims, "
                    f"{run_out.rejected_claims_count} unsupported claims rejected, "
                    f"{len(run_out.questions)} investigation questions "
                    f"(Provider: {run_out.ai_provider})"
                ),
                metadata={
                    "case_code": case_code,
                    "reasoning_run_id": run_id,
                    "ai_provider": run_out.ai_provider,
                    "ai_model": run_out.ai_model,
                    "prompt_version": run_out.prompt_version,
                    "fallback_used": run_out.fallback_used,
                    "validated_claims_count": len(run_out.claims),
                    "rejected_claims_count": run_out.rejected_claims_count,
                    "evidence_manifest_size": len(run_out.evidence_manifest),
                },
                actor_user_id=current_user.id if current_user else None,
                actor_role=current_user.role if current_user else None,
                event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                created_at=now,
            )

            cursor.execute(
                "SELECT * FROM investigation_reasoning_runs WHERE id = ?;",
                (run_id,),
            )
            saved_row = cursor.fetchone()

        return _row_to_reasoning_response(saved_row, inv_title)

    @staticmethod
    def get_investigation_reasoning(
        investigation_id: str,
    ) -> InvestigationReasoningResponse:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, title FROM investigations WHERE id = ?;",
                (investigation_id,),
            )
            inv_row = cursor.fetchone()
            if not inv_row:
                raise ResourceNotFoundException("Investigation", investigation_id)
            inv_title = inv_row["title"]

            cursor.execute(
                """
                SELECT * FROM investigation_reasoning_runs
                WHERE investigation_id = ?
                ORDER BY created_at DESC
                LIMIT 1;
                """,
                (investigation_id,),
            )
            r_row = cursor.fetchone()

        if not r_row:
            return DossierService.generate_investigation_reasoning(investigation_id)

        return _row_to_reasoning_response(r_row, inv_title)

    @staticmethod
    def generate_investigation_dossier(
        investigation_id: str,
        payload: Optional[DossierGenerateRequest] = None,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> DossierDetailResponse:
        req = payload or DossierGenerateRequest()
        actor = (
            f"{current_user.full_name} ({current_user.title})"
            if current_user
            else (req.actor.strip() or "Dr. Elena Rostova (Principal Forensic Analyst)")
        )
        generated_by_user_id = current_user.id if current_user else None

        if req.regenerate_reasoning:
            reasoning = DossierService.generate_investigation_reasoning(
                investigation_id=investigation_id,
                payload=ReasoningGenerateRequest(actor=actor),
                current_user=current_user,
            )
        else:
            reasoning = DossierService.get_investigation_reasoning(investigation_id)

        (
            inv_dict,
            documents_bundle,
            forensic_analyses,
            forensic_findings,
            contextual_bundle,
            _audit_cnt,
        ) = DossierService._collect_investigation_artifacts(investigation_id)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(MAX(version_number), 0) + 1 AS next_ver
                FROM investigation_dossiers
                WHERE investigation_id = ?;
                """,
                (investigation_id,),
            )
            version_number = int(cursor.fetchone()["next_ver"] or 1)

        dossier_id = str(uuid.uuid4())
        created_at = _utc_now_iso()
        case_code = inv_dict["case_code"]
        inv_title = inv_dict["title"]
        dossier_title = (
            req.title.strip()
            if req.title and req.title.strip()
            else f"{case_code} — Evidence-Backed Investigation Dossier (v{version_number})"
        )

        inv_dossier_dir = _verify_storage_containment(
            settings.resolved_dossiers_storage_dir / investigation_id,
            settings.resolved_dossiers_storage_dir,
        )
        inv_dossier_dir.mkdir(parents=True, exist_ok=True)

        # 1. Build Machine-Readable JSON Evidence Dossier
        json_dossier_payload = {
            "dossier_metadata": {
                "product": "VERITAS AI — Enterprise Document Forensics & Contextual Intelligence Platform",
                "synthetic_demonstration_label": "SYNTHETIC DEMONSTRATION MATERIAL — FORENSIC EVALUATION SPECIMEN",
                "dossier_id": dossier_id,
                "investigation_id": investigation_id,
                "case_code": case_code,
                "investigation_title": inv_title,
                "version_number": version_number,
                "title": dossier_title,
                "generated_at": created_at,
                "generated_by": actor,
                "generated_by_user_id": generated_by_user_id,
                "review_status": DossierReviewStatus.UNAPPROVED_AI_ASSISTED.value,
                "approval_notice": "AI-ASSISTED SYNTHESIS — UNAPPROVED UNTIL REVIEWED BY QUALIFIED HUMAN INVESTIGATOR",
                "reasoning_engine_version": reasoning.reasoning_engine_version,
                "ai_provider": reasoning.ai_provider,
                "ai_model": reasoning.ai_model,
                "prompt_version": reasoning.prompt_version,
                "source_analysis_ids": reasoning.source_analysis_ids,
                "source_document_hashes": [
                    dh.model_dump() for dh in reasoning.source_document_hashes
                ],
            },
            "reasoning_sections": [s.model_dump() for s in reasoning.sections],
            "evidence_grounded_claims": [c.model_dump() for c in reasoning.claims],
            "rejected_claims_audit": {
                "rejected_claims_count": reasoning.rejected_claims_count,
                "rejected_claims_log": [
                    rc.model_dump() for rc in reasoning.rejected_claims_log
                ],
            },
            "investigation_questions": [q.model_dump() for q in reasoning.questions],
            "recommended_human_verification_steps": [
                st.model_dump() for st in reasoning.verification_steps
            ],
            "financial_validation_results": (
                contextual_bundle.get("financial_validations", [])
                if contextual_bundle
                else []
            ),
            "contextual_contradiction_findings": (
                contextual_bundle.get("findings", []) if contextual_bundle else []
            ),
            "visual_forensic_findings": forensic_findings,
            "entity_resolution_clusters": (
                contextual_bundle.get("entity_matches", [])
                if contextual_bundle
                else []
            ),
            "investigation_timeline": (
                contextual_bundle.get("timeline_events", [])
                if contextual_bundle
                else []
            ),
            "evidence_reference_manifest": {
                k: v.model_dump() for k, v in reasoning.evidence_manifest.items()
            },
        }

        json_bytes = json.dumps(
            json_dossier_payload, indent=2, sort_keys=True
        ).encode("utf-8")
        json_sha256 = hashlib.sha256(json_bytes).hexdigest()
        json_filename = f"{case_code}_v{version_number}_{dossier_id[:8]}_dossier.json"
        json_path = _verify_storage_containment(
            inv_dossier_dir / json_filename,
            settings.resolved_dossiers_storage_dir,
        )
        json_path.write_bytes(json_bytes)
        try:
            os.chmod(json_path, 0o600)
        except OSError:
            pass

        # 2. Build Professional Multi-Page PDF Investigation Dossier
        pdf_bytes = DossierService._render_pdf_dossier(
            dossier_id=dossier_id,
            version_number=version_number,
            dossier_title=dossier_title,
            created_at=created_at,
            generated_by=actor,
            inv_dict=inv_dict,
            reasoning=reasoning,
            documents_bundle=documents_bundle,
            forensic_findings=forensic_findings,
            contextual_bundle=contextual_bundle,
            json_sha256=json_sha256,
        )
        pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        pdf_filename = f"{case_code}_v{version_number}_{dossier_id[:8]}_dossier.pdf"
        pdf_path = _verify_storage_containment(
            inv_dossier_dir / pdf_filename,
            settings.resolved_dossiers_storage_dir,
        )
        pdf_path.write_bytes(pdf_bytes)
        try:
            os.chmod(pdf_path, 0o600)
        except OSError:
            pass

        combined_fingerprint = hashlib.sha256(
            f"{pdf_sha256}:{json_sha256}:{version_number}".encode("utf-8")
        ).hexdigest()

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO investigation_dossiers (
                    id, investigation_id, reasoning_run_id, version_number,
                    title, status, reasoning_engine_version, ai_provider,
                    ai_model, prompt_version, source_analysis_ids_json,
                    source_document_hashes_json, evidence_manifest_json,
                    pdf_storage_path, pdf_size_bytes, pdf_sha256_hash,
                    json_storage_path, json_size_bytes, json_sha256_hash,
                    dossier_sha256_hash, review_status, generated_by,
                    generated_by_user_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    dossier_id,
                    investigation_id,
                    reasoning.reasoning_run_id,
                    version_number,
                    dossier_title,
                    DossierReviewStatus.UNAPPROVED_AI_ASSISTED.value,
                    reasoning.reasoning_engine_version,
                    reasoning.ai_provider,
                    reasoning.ai_model,
                    reasoning.prompt_version,
                    json.dumps(reasoning.source_analysis_ids),
                    json.dumps(
                        [dh.model_dump() for dh in reasoning.source_document_hashes]
                    ),
                    json.dumps(
                        {
                            k: v.model_dump()
                            for k, v in reasoning.evidence_manifest.items()
                        }
                    ),
                    str(pdf_path),
                    len(pdf_bytes),
                    pdf_sha256,
                    str(json_path),
                    len(json_bytes),
                    json_sha256,
                    combined_fingerprint,
                    DossierReviewStatus.UNAPPROVED_AI_ASSISTED.value,
                    actor,
                    generated_by_user_id,
                    created_at,
                ),
            )

            cursor.execute(
                "UPDATE investigations SET updated_at = ? WHERE id = ?;",
                (created_at, investigation_id),
            )

            AuditService.append_event_with_cursor(
                cursor,
                investigation_id=investigation_id,
                action="INVESTIGATION_DOSSIER_GENERATED",
                entity_type="INVESTIGATION_DOSSIER",
                entity_id=dossier_id,
                actor=actor,
                summary=(
                    f"Compiled immutable Investigation Dossier v{version_number} for {case_code} "
                    f"(PDF SHA-256: {pdf_sha256[:12]}..., JSON SHA-256: {json_sha256[:12]}..., "
                    f"{len(reasoning.claims)} grounded claims)"
                ),
                metadata={
                    "case_code": case_code,
                    "dossier_id": dossier_id,
                    "version_number": version_number,
                    "reasoning_run_id": reasoning.reasoning_run_id,
                    "pdf_sha256_hash": pdf_sha256,
                    "json_sha256_hash": json_sha256,
                    "dossier_sha256_hash": combined_fingerprint,
                    "ai_provider": reasoning.ai_provider,
                    "ai_model": reasoning.ai_model,
                    "generated_by_user_id": generated_by_user_id,
                },
                actor_user_id=generated_by_user_id,
                actor_role=current_user.role if current_user else None,
                event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                created_at=created_at,
            )

        return DossierService.get_dossier_detail(dossier_id)

    @staticmethod
    def list_investigation_dossiers(
        investigation_id: str,
    ) -> List[DossierSummaryResponse]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, case_code FROM investigations WHERE id = ?;",
                (investigation_id,),
            )
            inv_row = cursor.fetchone()
            if not inv_row:
                raise ResourceNotFoundException("Investigation", investigation_id)
            case_code = inv_row["case_code"]

            cursor.execute(
                """
                SELECT * FROM investigation_dossiers
                WHERE investigation_id = ?
                ORDER BY version_number DESC, created_at DESC;
                """,
                (investigation_id,),
            )
            rows = cursor.fetchall()

        return [_row_to_dossier_summary(r, case_code) for r in rows]

    @staticmethod
    def get_dossier_detail(dossier_id: str) -> DossierDetailResponse:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM investigation_dossiers WHERE id = ?;",
                (dossier_id,),
            )
            d_row = cursor.fetchone()
            if not d_row:
                raise ResourceNotFoundException("InvestigationDossier", dossier_id)

            inv_id = d_row["investigation_id"]
            cursor.execute(
                "SELECT case_code, title FROM investigations WHERE id = ?;",
                (inv_id,),
            )
            inv_row = cursor.fetchone()
            case_code = inv_row["case_code"] if inv_row else "UNKNOWN"
            inv_title = inv_row["title"] if inv_row else "Investigation"

            cursor.execute(
                "SELECT * FROM investigation_reasoning_runs WHERE id = ?;",
                (d_row["reasoning_run_id"],),
            )
            r_row = cursor.fetchone()

            cursor.execute(
                """
                SELECT * FROM dossier_review_history
                WHERE dossier_id = ?
                ORDER BY created_at DESC;
                """,
                (dossier_id,),
            )
            revs = [
                DossierReviewRecordSchema(
                    review_id=rr["id"],
                    dossier_id=rr["dossier_id"],
                    investigation_id=rr["investigation_id"],
                    previous_status=rr["previous_status"],
                    new_status=rr["new_status"],
                    reviewer=rr["reviewer"],
                    reviewer_user_id=(
                        rr["reviewer_user_id"]
                        if "reviewer_user_id" in rr.keys()
                        else None
                    ),
                    notes=rr["notes"] or "",
                    created_at=rr["created_at"],
                )
                for rr in cursor.fetchall()
            ]

        reasoning_resp = (
            _row_to_reasoning_response(r_row, inv_title)
            if r_row
            else DossierService.get_investigation_reasoning(inv_id)
        )
        summary = _row_to_dossier_summary(d_row, case_code)
        raw_hashes = _safe_json_loads(d_row["source_document_hashes_json"], [])

        return DossierDetailResponse(
            **summary.model_dump(),
            source_analysis_ids=_safe_json_loads(
                d_row["source_analysis_ids_json"], {}
            ),
            source_document_hashes=[
                SourceDocumentHashItemSchema(**dh) for dh in raw_hashes
            ],
            reasoning=reasoning_resp,
            review_history=revs,
        )

    @staticmethod
    def get_dossier_pdf_path(dossier_id: str) -> Tuple[Path, str]:
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT pdf_storage_path, title FROM investigation_dossiers WHERE id = ?;",
                (dossier_id,),
            ).fetchone()
            if not row:
                raise ResourceNotFoundException("InvestigationDossier", dossier_id)
            p = _verify_storage_containment(
                Path(row["pdf_storage_path"]),
                settings.resolved_dossiers_storage_dir,
            )
            if not p.exists():
                raise ResourceNotFoundException("DossierPDFArtifact", dossier_id)
            return p, p.name

    @staticmethod
    def get_dossier_json_path(dossier_id: str) -> Tuple[Path, str]:
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT json_storage_path, title FROM investigation_dossiers WHERE id = ?;",
                (dossier_id,),
            ).fetchone()
            if not row:
                raise ResourceNotFoundException("InvestigationDossier", dossier_id)
            p = _verify_storage_containment(
                Path(row["json_storage_path"]),
                settings.resolved_dossiers_storage_dir,
            )
            if not p.exists():
                raise ResourceNotFoundException("DossierJSONArtifact", dossier_id)
            return p, p.name

    @staticmethod
    def review_dossier(
        dossier_id: str,
        payload: DossierReviewRequest,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> DossierDetailResponse:
        allowed_statuses = {s.value for s in DossierReviewStatus}
        norm_status = payload.review_status.strip().upper()
        if norm_status not in allowed_statuses:
            raise InvalidDocumentException(
                message=(
                    f"Invalid dossier review_status '{payload.review_status}'. "
                    f"Allowed values: {sorted(allowed_statuses)}."
                ),
                code="INVALID_DOSSIER_REVIEW_STATUS",
            )

        now = _utc_now_iso()
        # Enforce reviewer identity from authenticated session when present
        reviewer = (
            f"{current_user.full_name} ({current_user.title})"
            if current_user
            else payload.reviewer.strip()
        )
        reviewer_user_id = current_user.id if current_user else None
        notes = payload.notes.strip()

        if not reviewer or len(reviewer) < 3:
            raise InvalidDocumentException(
                message="A valid human investigator identity (min 3 characters) is required to record a review decision.",
                code="MISSING_HUMAN_REVIEWER",
            )

        # Prohibit automated bots or AI self-approval
        reviewer_lower = reviewer.lower()
        if any(
            bot_tag in reviewer_lower
            for bot_tag in ("ai_system", "system_bot", "automated_agent", "gemini_api", "auto_approver")
        ):
            raise InvalidDocumentException(
                message="Automated or AI systems cannot approve dossiers. A genuine human investigator must review and sign off.",
                code="NON_HUMAN_APPROVAL_PROHIBITED",
            )

        if norm_status == DossierReviewStatus.APPROVED.value:
            if not notes or len(notes) < 5:
                raise InvalidDocumentException(
                    message="Dossier approval requires human investigator review notes documenting the sign-off rationale (min 5 characters).",
                    code="MISSING_REVIEW_NOTES",
                )
        elif norm_status == DossierReviewStatus.REQUIRES_REVISION.value:
            if not notes or len(notes) < 5:
                raise InvalidDocumentException(
                    message="Marking a dossier as REQUIRES_REVISION requires explanatory notes detailing required evidence or corrections (min 5 characters).",
                    code="MISSING_REVIEW_NOTES",
                )

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM investigation_dossiers WHERE id = ?;",
                (dossier_id,),
            )
            d_row = cursor.fetchone()
            if not d_row:
                raise ResourceNotFoundException("InvestigationDossier", dossier_id)

            prev_status = d_row["review_status"]
            inv_id = d_row["investigation_id"]
            ver_num = d_row["version_number"]
            d_keys = d_row.keys()
            gen_by_user_id = (
                d_row["generated_by_user_id"]
                if "generated_by_user_id" in d_keys
                else None
            )
            gen_by_label = (d_row["generated_by"] or "").strip()

            # Prevent a user from approving a dossier they generated themselves unless explicitly configured otherwise
            if (
                norm_status == DossierReviewStatus.APPROVED.value
                and not settings.allow_self_dossier_approval
            ):
                is_same_user_id = bool(
                    gen_by_user_id
                    and reviewer_user_id
                    and gen_by_user_id == reviewer_user_id
                )
                is_same_persona_name = bool(
                    current_user
                    and gen_by_label
                    and current_user.full_name.lower() in gen_by_label.lower()
                )
                if is_same_user_id or is_same_persona_name:
                    raise AuthorizationException(
                        message=(
                            "Self-approval of an AI-assisted investigation dossier is prohibited "
                            f"(generated by '{gen_by_label}', review attempted by '{reviewer}'). "
                            "An independent Reviewer or Administrator must review and sign off."
                        ),
                        code="SELF_DOSSIER_APPROVAL_PROHIBITED",
                        details={
                            "dossier_id": dossier_id,
                            "generated_by": gen_by_label,
                            "attempted_reviewer": reviewer,
                        },
                    )

            cursor.execute(
                "SELECT case_code FROM investigations WHERE id = ?;",
                (inv_id,),
            )
            inv_row = cursor.fetchone()
            case_code = inv_row["case_code"] if inv_row else "UNKNOWN"

            cursor.execute(
                """
                UPDATE investigation_dossiers
                SET status = ?,
                    review_status = ?,
                    reviewed_by = ?,
                    reviewed_by_user_id = ?,
                    review_notes = ?,
                    reviewed_at = ?
                WHERE id = ?;
                """,
                (
                    norm_status,
                    norm_status,
                    reviewer,
                    reviewer_user_id,
                    notes,
                    now,
                    dossier_id,
                ),
            )

            cursor.execute(
                """
                INSERT INTO dossier_review_history (
                    id, dossier_id, investigation_id, previous_status,
                    new_status, reviewer, reviewer_user_id, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(uuid.uuid4()),
                    dossier_id,
                    inv_id,
                    prev_status,
                    norm_status,
                    reviewer,
                    reviewer_user_id,
                    notes,
                    now,
                ),
            )

            AuditService.append_event_with_cursor(
                cursor,
                investigation_id=inv_id,
                action="INVESTIGATION_DOSSIER_REVIEWED",
                entity_type="INVESTIGATION_DOSSIER",
                entity_id=dossier_id,
                actor=reviewer,
                summary=(
                    f"Human review recorded on Investigation Dossier v{ver_num} ({case_code}): "
                    f"{prev_status} -> {norm_status}"
                    + (f" ({notes[:80]})" if notes else "")
                ),
                metadata={
                    "case_code": case_code,
                    "dossier_id": dossier_id,
                    "version_number": ver_num,
                    "previous_status": prev_status,
                    "new_status": norm_status,
                    "reviewer": reviewer,
                    "reviewer_user_id": reviewer_user_id,
                    "notes": notes,
                },
                actor_user_id=reviewer_user_id,
                actor_role=current_user.role if current_user else None,
                event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                created_at=now,
            )

        return DossierService.get_dossier_detail(dossier_id)

    @staticmethod
    def _render_pdf_dossier(
        dossier_id: str,
        version_number: int,
        dossier_title: str,
        created_at: str,
        generated_by: str,
        inv_dict: Dict[str, Any],
        reasoning: InvestigationReasoningResponse,
        documents_bundle: List[Dict[str, Any]],
        forensic_findings: List[Dict[str, Any]],
        contextual_bundle: Optional[Dict[str, Any]],
        json_sha256: str,
    ) -> bytes:
        """
        Generates a multi-page enterprise PDF Investigation Dossier containing all 16
        required sections (Cover page, Investigation ID, Executive Summary, Scope & Methodology,
        Documents Examined, Key Findings, Evidence Comparison Tables, Financial Validation,
        Visual Forensics, Entity Relationship Summary, Timeline, Supporting vs. Contradicting
        Evidence, Unresolved Questions, Verification Steps, Limitations & Disclaimer, and
        Evidence Reference Appendix).
        """
        doc = fitz.open()
        case_code = str(inv_dict.get("case_code") or "UNKNOWN")
        inv_title = str(inv_dict.get("title") or "Investigation")

        # =====================================================================
        # PAGE 1: COVER PAGE & INVESTIGATION IDENTIFICATION (Sections 1 & 2)
        # =====================================================================
        cover = doc.new_page(width=595, height=842)
        # Deep Midnight Navy Cover Header Banner
        cover.draw_rect(
            fitz.Rect(0, 0, 595, 195),
            color=(0.03, 0.06, 0.12),
            fill=(0.03, 0.06, 0.12),
        )
        # Synthetic Demonstration Banner
        cover.draw_rect(
            fitz.Rect(40, 22, 555, 42),
            color=(0.05, 0.65, 0.85),
            fill=(0.06, 0.15, 0.28),
            width=1.0,
        )
        cover.insert_text(
            fitz.Point(52, 35),
            "SYNTHETIC DEMONSTRATION MATERIAL — VERITAS AI PHASE 5 INVESTIGATION DOSSIER",
            fontsize=8.0,
            fontname="hebo",
            color=(0.35, 0.88, 0.98),
        )
        cover.insert_text(
            fitz.Point(40, 82),
            "VERITAS AI — FORENSIC INTELLIGENCE PLATFORM",
            fontsize=11.0,
            fontname="hebo",
            color=(0.25, 0.82, 0.96),
        )
        cover.insert_text(
            fitz.Point(40, 112),
            "EVIDENCE-BACKED INVESTIGATION DOSSIER",
            fontsize=20.0,
            fontname="hebo",
            color=(1.0, 1.0, 1.0),
        )
        cover.insert_text(
            fitz.Point(40, 138),
            f"Case {case_code}: {inv_title[:68]}",
            fontsize=11.5,
            fontname="helv",
            color=(0.82, 0.88, 0.95),
        )
        cover.insert_text(
            fitz.Point(40, 165),
            f"Dossier Version: v{version_number}  |  Dossier ID: {dossier_id}  |  Generated: {created_at[:19]}Z",
            fontsize=8.5,
            fontname="cour",
            color=(0.65, 0.78, 0.90),
        )

        # Unapproved AI-Assisted Notice Box
        cover.draw_rect(
            fitz.Rect(40, 215, 555, 255),
            color=(0.85, 0.55, 0.10),
            fill=(0.99, 0.96, 0.90),
            width=1.0,
        )
        cover.insert_text(
            fitz.Point(50, 231),
            "NOTICE: AI-ASSISTED EVIDENCE SYNTHESIS — UNAPPROVED UNTIL HUMAN REVIEW",
            fontsize=9.0,
            fontname="hebo",
            color=(0.65, 0.32, 0.05),
        )
        cover.insert_text(
            fitz.Point(50, 246),
            "Every factual claim in this dossier is bound to persisted Evidence IDs (EVID-*). Do not treat as a legal conclusion.",
            fontsize=8.0,
            fontname="helv",
            color=(0.35, 0.25, 0.10),
        )

        # Section 2: Investigation Identification & Traceability Metadata Table
        cover.insert_text(
            fitz.Point(40, 282),
            "1. INVESTIGATION IDENTIFICATION & TRACEABILITY MANIFEST",
            fontsize=11.0,
            fontname="hebo",
            color=(0.06, 0.12, 0.24),
        )
        meta_rows = [
            ("Investigation ID", str(inv_dict.get("id"))),
            ("Case Code & Classification", f"{case_code}  |  {inv_dict.get('classification')}  |  Priority: {inv_dict.get('priority')}"),
            ("Lead Investigator / Generated By", f"{inv_dict.get('lead_investigator')}  /  {generated_by}"),
            ("Dossier ID & Version", f"{dossier_id}  (Immutable Version v{version_number})"),
            ("Reasoning Engine Version", reasoning.reasoning_engine_version),
            ("AI Provider & Model", f"{reasoning.ai_provider}  ({reasoning.ai_model})"),
            ("Prompt Version", reasoning.prompt_version),
            ("JSON Dossier SHA-256 Fingerprint", json_sha256),
            ("Evidence Manifest Records", f"{len(reasoning.evidence_manifest)} verifiable evidence records  |  {len(reasoning.claims)} grounded claims"),
        ]
        y_m = 294.0
        for label_k, val_v in meta_rows:
            cover.draw_rect(
                fitz.Rect(40, y_m, 210, y_m + 20),
                color=(0.75, 0.80, 0.86),
                fill=(0.94, 0.96, 0.99),
                width=0.6,
            )
            cover.draw_rect(
                fitz.Rect(210, y_m, 555, y_m + 20),
                color=(0.75, 0.80, 0.86),
                fill=(1.0, 1.0, 1.0),
                width=0.6,
            )
            cover.insert_text(
                fitz.Point(46, y_m + 13),
                label_k,
                fontsize=8.0,
                fontname="hebo",
                color=(0.12, 0.18, 0.28),
            )
            cover.insert_text(
                fitz.Point(216, y_m + 13),
                str(val_v)[:66],
                fontsize=8.0,
                fontname="cour",
                color=(0.10, 0.14, 0.20),
            )
            y_m += 20.0

        # Helper for subsequent multi-page flowing sections
        state = {"page": cover, "y": y_m + 24.0, "page_num": 1}

        def _draw_footer(pg: Any, p_num: int) -> None:
            pg.draw_line(
                fitz.Point(40, 804),
                fitz.Point(555, 804),
                color=(0.75, 0.80, 0.86),
                width=0.6,
            )
            pg.insert_text(
                fitz.Point(40, 818),
                f"SYNTHETIC DEMONSTRATION DOSSIER — VERITAS AI  |  Case {case_code} (v{version_number})",
                fontsize=7.5,
                fontname="helv",
                color=(0.45, 0.50, 0.58),
            )
            pg.insert_text(
                fitz.Point(500, 818),
                f"Page {p_num}",
                fontsize=7.5,
                fontname="hebo",
                color=(0.35, 0.40, 0.50),
            )

        _draw_footer(cover, 1)

        def _ensure_space(needed: float) -> None:
            if state["y"] + needed > 785.0:
                new_p = doc.new_page(width=595, height=842)
                state["page_num"] += 1
                new_p.draw_rect(
                    fitz.Rect(40, 18, 555, 36),
                    color=(0.10, 0.20, 0.35),
                    fill=(0.94, 0.97, 1.0),
                    width=0.6,
                )
                new_p.insert_text(
                    fitz.Point(48, 30),
                    f"VERITAS AI INVESTIGATION DOSSIER — {case_code} (v{version_number}) — SYNTHETIC DEMONSTRATION MATERIAL",
                    fontsize=7.5,
                    fontname="hebo",
                    color=(0.10, 0.22, 0.42),
                )
                _draw_footer(new_p, state["page_num"])
                state["page"] = new_p
                state["y"] = 54.0

        def _pdf_safe(txt: str) -> str:
            return (
                str(txt)
                .replace("—", "-")
                .replace("–", "-")
                .replace("→", "->")
                .replace("Δ", "Delta")
                .replace("•", "*")
            )

        def _add_heading(title_str: str) -> None:
            _ensure_space(34.0)
            pg = state["page"]
            y = state["y"]
            pg.draw_rect(
                fitz.Rect(40, y, 555, y + 20),
                color=(0.08, 0.18, 0.34),
                fill=(0.08, 0.18, 0.34),
            )
            pg.insert_text(
                fitz.Point(48, y + 14),
                _pdf_safe(title_str),
                fontsize=9.5,
                fontname="hebo",
                color=(1.0, 1.0, 1.0),
            )
            state["y"] = y + 28.0

        def _add_paragraph(text_str: str, font: str = "helv", size: float = 8.5, indent: float = 44.0) -> None:
            wrapped = textwrap.wrap(_pdf_safe(text_str), width=92)
            for line in wrapped:
                _ensure_space(13.0)
                state["page"].insert_text(
                    fitz.Point(indent, state["y"]),
                    line,
                    fontsize=size,
                    fontname=font,
                    color=(0.12, 0.15, 0.22),
                )
                state["y"] += 12.0
            state["y"] += 4.0

        # =====================================================================
        # SECTIONS 3–15: STRUCTURED REASONING SECTIONS (A through N)
        # =====================================================================
        for sec in reasoning.sections:
            _add_heading(f"SECTION {sec.section_code}: {sec.title.upper()}")
            _add_paragraph(sec.narrative)
            if sec.evidence_ids:
                _add_paragraph(
                    f"Referenced Evidence IDs: {', '.join(sec.evidence_ids[:12])}",
                    font="cour",
                    size=7.8,
                    indent=48.0,
                )

        # =====================================================================
        # DOCUMENTS EXAMINED TABLE (Section 5)
        # =====================================================================
        _add_heading("DOCUMENTS EXAMINED & SHA-256 INTEGRITY FINGERPRINTS")
        for idx, doc_b in enumerate(documents_bundle, start=1):
            _add_paragraph(
                f"{idx}. {doc_b['filename']} | Type: {doc_b.get('document_type')} "
                f"({float(doc_b.get('classification_confidence', 0.0)) * 100:.0f}%) | "
                f"Method: {doc_b.get('extraction_method_summary')} | Pages: {doc_b.get('page_count', 1)} | "
                f"SHA-256: {doc_b.get('sha256_hash')}",
                font="cour",
                size=7.8,
            )

        # =====================================================================
        # KEY EVIDENCE-GROUNDED CLAIMS & SIDE-BY-SIDE COMPARISONS (Sections 6, 7, 12)
        # =====================================================================
        _add_heading("EVIDENCE-GROUNDED CLAIMS & SUPPORTING VS. CONTRADICTING EVIDENCE")
        for clm in reasoning.claims:
            page_str = ", ".join(
                f"{pr.filename} (p.{pr.page_number})" for pr in clm.page_references
            )
            _add_paragraph(
                f"[{clm.claim_id}] ({clm.claim_type}) {clm.claim_text}",
                font="hebo",
                size=8.2,
            )
            _add_paragraph(
                f"   Supporting IDs: {clm.supporting_evidence_ids or ['None']} | "
                f"Contradicting IDs: {clm.contradicting_evidence_ids or ['None']} | "
                f"Source Pages: {page_str or 'Investigation Scope'} | "
                f"Method: {clm.reasoning_method}",
                font="cour",
                size=7.5,
                indent=52.0,
            )

        # =====================================================================
        # DETERMINISTIC FINANCIAL VALIDATION TABLE (Section 8)
        # =====================================================================
        if contextual_bundle and contextual_bundle.get("financial_validations"):
            _add_heading("DETERMINISTIC DECIMAL FINANCIAL VALIDATION RESULTS")
            for fv in contextual_bundle.get("financial_validations", []):
                _add_paragraph(
                    f"• [{fv.get('status')}] {fv.get('filename')} (p.{fv.get('page_number', 1)}) — {fv.get('check_type')}: "
                    f"Expected={fv.get('expected_value')} | Observed={fv.get('observed_value')} | "
                    f"Discrepancy={fv.get('discrepancy_amount')} {fv.get('currency')} | Formula: {fv.get('formula_used')}",
                    font="cour",
                    size=7.8,
                )

        # =====================================================================
        # UNRESOLVED INVESTIGATION QUESTIONS & VERIFICATION STEPS (Sections 13 & 14)
        # =====================================================================
        _add_heading("INVESTIGATION QUESTIONS FOR HUMAN FOLLOW-UP")
        for q in reasoning.questions:
            _add_paragraph(
                f"[{q.question_id}] ({q.priority}) {q.question_text} "
                f"(Evidence: {', '.join(q.related_evidence_ids)}) — Rationale: {q.rationale}",
                font="helv",
                size=8.2,
            )

        _add_heading("RECOMMENDED HUMAN VERIFICATION STEPS")
        for st in reasoning.verification_steps:
            _add_paragraph(
                f"Step {st.step_number} [{st.priority}] {st.title}: {st.action_description} "
                f"(Target Evidence: {', '.join(st.target_evidence_ids)})",
                font="helv",
                size=8.2,
            )

        # =====================================================================
        # SECTION 16: APPENDIX WITH COMPLETE EVIDENCE REFERENCE MANIFEST
        # =====================================================================
        _add_heading("APPENDIX — COMPLETE EVIDENCE REFERENCE MANIFEST")
        for eid, item in reasoning.evidence_manifest.items():
            _add_paragraph(
                f"{eid} | {item.source_type} | Doc: {item.filename} (p.{item.page_number}) | "
                f"SHA-256: {item.document_sha256[:12]}... | Review: {item.review_status} | {item.summary}",
                font="cour",
                size=7.4,
            )

        pdf_bytes = doc.tobytes(garbage=4, deflate=True)
        doc.close()
        return pdf_bytes

    @staticmethod
    def backfill_phase5_dossiers_for_existing_investigations() -> None:
        """
        Ensures VRT-2026-0003 (and any active investigation with completed documents)
        has an initial v1 Evidence-Backed Investigation Dossier ready on startup.
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT i.id
                FROM investigations i
                JOIN documents d ON d.investigation_id = i.id
                WHERE d.processing_status = 'COMPLETED';
                """
            )
            inv_ids = [r["id"] for r in cursor.fetchall()]

        for inv_id in inv_ids:
            try:
                with get_db_connection() as conn:
                    has_dossier = conn.execute(
                        "SELECT 1 FROM investigation_dossiers WHERE investigation_id = ? LIMIT 1;",
                        (inv_id,),
                    ).fetchone()
                if not has_dossier:
                    DossierService.generate_investigation_dossier(inv_id)
            except Exception:
                pass
