import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import status
from app.core.database import get_db_connection
from app.core.exceptions import (
    InvalidDocumentException,
    ResourceNotFoundException,
    VeritasException,
)
from app.models.entities import BackgroundJobStatus, BackgroundJobType
from app.schemas.auth import AuthenticatedUser
from app.schemas.job import (
    BackgroundJobEnqueueRequest,
    BackgroundJobResponse,
    StartupRecoveryReport,
)
from app.services.audit_service import AuditService
from app.services.context_service import ContextService
from app.services.dossier_service import DossierService
from app.services.forensics_service import ForensicsService


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_loads(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _row_to_job_response(row: Any) -> BackgroundJobResponse:
    return BackgroundJobResponse(
        id=row["id"],
        investigation_id=row["investigation_id"],
        document_id=row["document_id"],
        job_type=row["job_type"],
        status=row["status"],
        stage_label=row["stage_label"] or "QUEUED",
        progress_percent=int(row["progress_percent"] or 0),
        attempt_count=int(row["attempt_count"] or 0),
        max_attempts=int(row["max_attempts"] or 3),
        idempotency_key=row["idempotency_key"],
        error_summary=row["error_summary"],
        payload=_safe_json_loads(row["payload_json"], {}),
        result_summary=_safe_json_loads(row["result_summary_json"], {}),
        created_by_user_id=row["created_by_user_id"],
        created_by_actor=row["created_by_actor"] or "SYSTEM",
        queued_at=row["queued_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        updated_at=row["updated_at"],
    )


class JobService:
    @staticmethod
    def _update_stage(
        job_id: str,
        stage_label: str,
        progress_percent: int,
        status_val: Optional[str] = None,
    ) -> None:
        now = _utc_now_iso()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if status_val:
                cursor.execute(
                    """
                    UPDATE background_jobs
                    SET status = ?, stage_label = ?, progress_percent = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (status_val, stage_label, progress_percent, now, job_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE background_jobs
                    SET stage_label = ?, progress_percent = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (stage_label, progress_percent, now, job_id),
                )

    @staticmethod
    def enqueue_job(
        payload: BackgroundJobEnqueueRequest,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> BackgroundJobResponse:
        allowed_types = {t.value for t in BackgroundJobType}
        norm_type = payload.job_type.strip().upper()
        if norm_type not in allowed_types:
            raise InvalidDocumentException(
                message=f"Unsupported job_type '{payload.job_type}'. Allowed: {sorted(allowed_types)}.",
                code="INVALID_JOB_TYPE",
            )

        idempotency_key = (
            f"{norm_type}:{payload.investigation_id}:{payload.document_id or 'ALL'}"
        )

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, case_code FROM investigations WHERE id = ?;",
                (payload.investigation_id,),
            )
            inv_row = cursor.fetchone()
            if not inv_row:
                raise ResourceNotFoundException("Investigation", payload.investigation_id)

            if payload.document_id:
                cursor.execute(
                    "SELECT id FROM documents WHERE id = ? AND investigation_id = ?;",
                    (payload.document_id, payload.investigation_id),
                )
                if not cursor.fetchone():
                    raise ResourceNotFoundException("Document", payload.document_id)

            # Prevent duplicate active job launches for the same document/investigation
            cursor.execute(
                """
                SELECT * FROM background_jobs
                WHERE idempotency_key = ?
                  AND status IN ('QUEUED', 'RUNNING')
                ORDER BY queued_at DESC
                LIMIT 1;
                """,
                (idempotency_key,),
            )
            existing_active = cursor.fetchone()
            if existing_active:
                raise VeritasException(
                    message=(
                        f"An active '{norm_type}' job ({existing_active['id']}) is already "
                        f"{existing_active['status']} for this target."
                    ),
                    code="DUPLICATE_ACTIVE_JOB",
                    status_code=status.HTTP_409_CONFLICT,
                    details={
                        "existing_job_id": existing_active["id"],
                        "status": existing_active["status"],
                        "idempotency_key": idempotency_key,
                    },
                )

            job_id = str(uuid.uuid4())
            now = _utc_now_iso()
            actor_label = (
                f"{current_user.full_name} ({current_user.title})"
                if current_user
                else "SYSTEM"
            )
            job_payload = {
                "simulate_failure_once": payload.simulate_failure_once,
            }

            cursor.execute(
                """
                INSERT INTO background_jobs (
                    id, investigation_id, document_id, job_type, status,
                    stage_label, progress_percent, attempt_count, max_attempts,
                    idempotency_key, error_summary, payload_json, result_summary_json,
                    created_by_user_id, created_by_actor, queued_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'QUEUED', 0, 0, 3, ?, NULL, ?, '{}', ?, ?, ?, ?);
                """,
                (
                    job_id,
                    payload.investigation_id,
                    payload.document_id,
                    norm_type,
                    BackgroundJobStatus.QUEUED.value,
                    idempotency_key,
                    json.dumps(job_payload),
                    current_user.id if current_user else None,
                    actor_label,
                    now,
                    now,
                ),
            )

            AuditService.append_event_with_cursor(
                cursor,
                investigation_id=payload.investigation_id,
                action="BACKGROUND_JOB_QUEUED",
                entity_type="BACKGROUND_JOB",
                entity_id=job_id,
                actor=actor_label,
                summary=f"Queued background job {norm_type} for case {inv_row['case_code']}",
                metadata={
                    "job_id": job_id,
                    "job_type": norm_type,
                    "document_id": payload.document_id,
                    "idempotency_key": idempotency_key,
                },
                actor_user_id=current_user.id if current_user else None,
                actor_role=current_user.role if current_user else "SYSTEM",
                event_origin="AUTHENTICATED_HUMAN" if current_user else "BACKGROUND_WORKER",
                created_at=now,
            )

        if payload.execute_immediately:
            return JobService.execute_job(job_id, current_user=current_user)

        return JobService.get_job(job_id)

    @staticmethod
    def execute_job(
        job_id: str,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> BackgroundJobResponse:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM background_jobs WHERE id = ?;", (job_id,))
            job_row = cursor.fetchone()
            if not job_row:
                raise ResourceNotFoundException("BackgroundJob", job_id)

            inv_id = job_row["investigation_id"]
            doc_id = job_row["document_id"]
            job_type = job_row["job_type"]
            attempt = int(job_row["attempt_count"] or 0) + 1
            max_attempts = int(job_row["max_attempts"] or 3)
            job_payload = _safe_json_loads(job_row["payload_json"], {})

            if attempt > max_attempts:
                raise InvalidDocumentException(
                    message=f"Job '{job_id}' has reached maximum retry attempts ({max_attempts}).",
                    code="JOB_MAX_ATTEMPTS_EXCEEDED",
                )

            started_at = _utc_now_iso()
            cursor.execute(
                """
                UPDATE background_jobs
                SET status = 'RUNNING',
                    stage_label = 'INITIALIZING_WORKER_PIPELINE',
                    progress_percent = 10,
                    attempt_count = ?,
                    error_summary = NULL,
                    started_at = ?,
                    completed_at = NULL,
                    updated_at = ?
                WHERE id = ?;
                """,
                (attempt, started_at, started_at, job_id),
            )

        try:
            # Support deterministic failure simulation on attempt 1 so retry recovery is testable
            if job_payload.get("simulate_failure_once") and attempt == 1:
                JobService._update_stage(job_id, "EXECUTING_PIPELINE_STAGE_1", 35)
                raise RuntimeError(
                    "Simulated transient worker interruption on attempt 1."
                )

            result_summary: Dict[str, Any] = {"attempt": attempt}

            if job_type == BackgroundJobType.VISUAL_FORENSICS_ANALYSIS.value:
                JobService._update_stage(job_id, "RUNNING_7_MODULE_VISUAL_FORENSICS", 45)
                if doc_id:
                    fa = ForensicsService.run_document_forensic_analysis(
                        doc_id, current_user=current_user
                    )
                    result_summary["forensic_analysis_id"] = fa.analysis_id
                    result_summary["findings_count"] = fa.findings_count
                else:
                    with get_db_connection() as conn:
                        d_ids = [
                            r["id"]
                            for r in conn.execute(
                                "SELECT id FROM documents WHERE investigation_id = ? AND processing_status = 'COMPLETED';",
                                (inv_id,),
                            ).fetchall()
                        ]
                    analyzed = 0
                    for d in d_ids:
                        ForensicsService.run_document_forensic_analysis(
                            d, current_user=current_user
                        )
                        analyzed += 1
                    result_summary["documents_analyzed"] = analyzed

            elif job_type == BackgroundJobType.CONTEXTUAL_INTELLIGENCE_ANALYSIS.value:
                JobService._update_stage(
                    job_id, "RUNNING_CROSS_DOCUMENT_CONTEXTUAL_ENGINE", 55
                )
                ctx = ContextService.run_investigation_context_analysis(
                    inv_id, current_user=current_user
                )
                result_summary["contextual_analysis_id"] = ctx.analysis_id
                result_summary["findings_count"] = len(ctx.findings)

            elif job_type == BackgroundJobType.DOSSIER_GENERATION.value:
                JobService._update_stage(
                    job_id, "COMPILING_EVIDENCE_GROUNDED_DOSSIER", 65
                )
                dos = DossierService.generate_investigation_dossier(
                    inv_id, current_user=current_user
                )
                result_summary["dossier_id"] = dos.dossier_id
                result_summary["version_number"] = dos.version_number

            else:
                # FULL_INVESTIGATION_PIPELINE or DOCUMENT_INGESTION_AND_EXTRACTION
                JobService._update_stage(job_id, "STAGE_1_VISUAL_FORENSICS_SWEEP", 30)
                with get_db_connection() as conn:
                    d_ids = [
                        r["id"]
                        for r in conn.execute(
                            "SELECT id FROM documents WHERE investigation_id = ? AND processing_status = 'COMPLETED';",
                            (inv_id,),
                        ).fetchall()
                    ]
                for d in d_ids:
                    ForensicsService.run_document_forensic_analysis(
                        d, current_user=current_user
                    )
                result_summary["documents_forensics_completed"] = len(d_ids)

                JobService._update_stage(
                    job_id, "STAGE_2_CROSS_DOCUMENT_CONTEXTUAL_ANALYSIS", 65
                )
                if d_ids:
                    ctx = ContextService.run_investigation_context_analysis(
                        inv_id, current_user=current_user
                    )
                    result_summary["contextual_analysis_id"] = ctx.analysis_id
                    result_summary["contextual_findings_count"] = len(ctx.findings)

                JobService._update_stage(
                    job_id, "STAGE_3_EVIDENCE_REASONING_SYNTHESIS", 85
                )
                if d_ids:
                    reas = DossierService.generate_investigation_reasoning(
                        inv_id, current_user=current_user
                    )
                    result_summary["reasoning_run_id"] = reas.reasoning_run_id
                    result_summary["validated_claims_count"] = len(reas.claims)

            completed_at = _utc_now_iso()
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE background_jobs
                    SET status = 'COMPLETED',
                        stage_label = 'COMPLETED',
                        progress_percent = 100,
                        error_summary = NULL,
                        result_summary_json = ?,
                        completed_at = ?,
                        updated_at = ?
                    WHERE id = ?;
                    """,
                    (json.dumps(result_summary), completed_at, completed_at, job_id),
                )
                AuditService.append_event_with_cursor(
                    cursor,
                    investigation_id=inv_id,
                    action="BACKGROUND_JOB_COMPLETED",
                    entity_type="BACKGROUND_JOB",
                    entity_id=job_id,
                    actor="VERITAS Background Worker",
                    summary=f"Background job {job_type} completed on attempt {attempt}",
                    metadata={
                        "job_id": job_id,
                        "job_type": job_type,
                        "attempt": attempt,
                        "result_summary": result_summary,
                    },
                    actor_user_id=current_user.id if current_user else None,
                    actor_role=current_user.role if current_user else "SYSTEM",
                    event_origin="BACKGROUND_WORKER",
                    created_at=completed_at,
                )

        except Exception as exc:
            failed_at = _utc_now_iso()
            safe_err = str(exc)[:300]
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE background_jobs
                    SET status = 'FAILED',
                        stage_label = 'FAILED',
                        error_summary = ?,
                        completed_at = ?,
                        updated_at = ?
                    WHERE id = ?;
                    """,
                    (safe_err, failed_at, failed_at, job_id),
                )
                AuditService.append_event_with_cursor(
                    cursor,
                    investigation_id=inv_id,
                    action="BACKGROUND_JOB_FAILED",
                    entity_type="BACKGROUND_JOB",
                    entity_id=job_id,
                    actor="VERITAS Background Worker",
                    summary=f"Background job {job_type} failed on attempt {attempt}: {safe_err}",
                    metadata={
                        "job_id": job_id,
                        "job_type": job_type,
                        "attempt": attempt,
                        "error_summary": safe_err,
                    },
                    actor_user_id=current_user.id if current_user else None,
                    actor_role=current_user.role if current_user else "SYSTEM",
                    event_origin="BACKGROUND_WORKER",
                    created_at=failed_at,
                )

        return JobService.get_job(job_id)

    @staticmethod
    def retry_job(
        job_id: str,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> BackgroundJobResponse:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM background_jobs WHERE id = ?;", (job_id,))
            row = cursor.fetchone()
            if not row:
                raise ResourceNotFoundException("BackgroundJob", job_id)
            if row["status"] not in ("FAILED", "CANCELLED"):
                raise InvalidDocumentException(
                    message=f"Only FAILED or CANCELLED jobs can be retried (current status: {row['status']}).",
                    code="JOB_NOT_RETRYABLE",
                )
        return JobService.execute_job(job_id, current_user=current_user)

    @staticmethod
    def cancel_job(
        job_id: str,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> BackgroundJobResponse:
        now = _utc_now_iso()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM background_jobs WHERE id = ?;", (job_id,))
            row = cursor.fetchone()
            if not row:
                raise ResourceNotFoundException("BackgroundJob", job_id)
            if row["status"] not in ("QUEUED", "RUNNING"):
                raise InvalidDocumentException(
                    message=f"Cannot cancel job in state '{row['status']}'.",
                    code="JOB_NOT_CANCELLABLE",
                )
            cursor.execute(
                """
                UPDATE background_jobs
                SET status = 'CANCELLED',
                    stage_label = 'CANCELLED_BY_USER',
                    completed_at = ?,
                    updated_at = ?
                WHERE id = ?;
                """,
                (now, now, job_id),
            )
            AuditService.append_event_with_cursor(
                cursor,
                investigation_id=row["investigation_id"],
                action="BACKGROUND_JOB_CANCELLED",
                entity_type="BACKGROUND_JOB",
                entity_id=job_id,
                actor=(
                    f"{current_user.full_name} ({current_user.title})"
                    if current_user
                    else "SYSTEM"
                ),
                summary=f"Cancelled background job {row['job_type']} ({job_id})",
                metadata={"job_id": job_id, "previous_status": row["status"]},
                actor_user_id=current_user.id if current_user else None,
                actor_role=current_user.role if current_user else "SYSTEM",
                event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                created_at=now,
            )
        return JobService.get_job(job_id)

    @staticmethod
    def recover_interrupted_jobs_on_startup() -> StartupRecoveryReport:
        """
        Detects any background_jobs left in RUNNING state due to an unexpected
        process termination or restart, marks them FAILED with a clear recovery state,
        and records an immutable audit event.
        """
        now = _utc_now_iso()
        recovered_ids: List[str] = []
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM background_jobs WHERE status = 'RUNNING';"
            )
            interrupted_rows = cursor.fetchall()
            for r in interrupted_rows:
                j_id = r["id"]
                recovered_ids.append(j_id)
                cursor.execute(
                    """
                    UPDATE background_jobs
                    SET status = 'FAILED',
                        stage_label = 'INTERRUPTED_ON_SERVER_RESTART',
                        error_summary = 'Job was interrupted by server restart while RUNNING; ready for retry.',
                        completed_at = ?,
                        updated_at = ?
                    WHERE id = ?;
                    """,
                    (now, now, j_id),
                )
                AuditService.append_event_with_cursor(
                    cursor,
                    investigation_id=r["investigation_id"],
                    action="BACKGROUND_JOB_INTERRUPTED_RECOVERED",
                    entity_type="BACKGROUND_JOB",
                    entity_id=j_id,
                    actor="VERITAS Startup Recovery Supervisor",
                    summary=f"Recovered interrupted RUNNING job {r['job_type']} ({j_id}) -> marked FAILED (retryable)",
                    metadata={
                        "job_id": j_id,
                        "job_type": r["job_type"],
                        "interrupted_stage": r["stage_label"],
                    },
                    actor_user_id=None,
                    actor_role="SYSTEM",
                    event_origin="SYSTEM",
                    created_at=now,
                )

        return StartupRecoveryReport(
            interrupted_jobs_found=len(recovered_ids),
            recovered_job_ids=recovered_ids,
            timestamp=now,
        )

    @staticmethod
    def get_job(job_id: str) -> BackgroundJobResponse:
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT * FROM background_jobs WHERE id = ?;", (job_id,)
            ).fetchone()
            if not row:
                raise ResourceNotFoundException("BackgroundJob", job_id)
            return _row_to_job_response(row)

    @staticmethod
    def list_jobs(
        investigation_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[BackgroundJobResponse]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if investigation_id:
                cursor.execute(
                    """
                    SELECT * FROM background_jobs
                    WHERE investigation_id = ?
                    ORDER BY queued_at DESC
                    LIMIT ?;
                    """,
                    (investigation_id, max(1, min(limit, 200))),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM background_jobs
                    ORDER BY queued_at DESC
                    LIMIT ?;
                    """,
                    (max(1, min(limit, 200)),),
                )
            return [_row_to_job_response(r) for r in cursor.fetchall()]
