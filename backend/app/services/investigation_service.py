import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.core.database import get_db_connection
from app.core.exceptions import ResourceNotFoundException
from app.models.entities import InvestigationStatus
from app.schemas.auth import AuthenticatedUser
from app.schemas.investigation import (
    AuditLogResponse,
    CaseNoteCreate,
    InvestigationCreate,
    InvestigationDetailResponse,
    InvestigationResponse,
    InvestigationUpdate,
)
from app.services.audit_service import AuditService


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_case_code(conn: Any) -> str:
    year = datetime.now(timezone.utc).year
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS cnt FROM investigations;")
    count = cursor.fetchone()["cnt"]
    seq = count + 1
    while True:
        candidate = f"VRT-{year}-{seq:04d}"
        cursor.execute(
            "SELECT 1 FROM investigations WHERE case_code = ?;", (candidate,)
        )
        if not cursor.fetchone():
            return candidate
        seq += 1


def _row_to_investigation(row: Any) -> InvestigationResponse:
    keys = row.keys()
    return InvestigationResponse(
        id=row["id"],
        case_code=row["case_code"],
        title=row["title"],
        description=row["description"] or "",
        status=row["status"],
        priority=row["priority"],
        classification=row["classification"],
        lead_investigator=row["lead_investigator"],
        owner_user_id=row["owner_user_id"] if "owner_user_id" in keys else None,
        document_count=int(row["document_count"] if "document_count" in keys else 0),
        findings_count=int(row["findings_count"] if "findings_count" in keys else 0),
        pending_review_count=int(
            row["pending_review_count"] if "pending_review_count" in keys else 0
        ),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_audit_log(row: Any) -> AuditLogResponse:
    keys = row.keys()
    raw_meta = row["metadata_json"] if "metadata_json" in keys else "{}"
    try:
        metadata = json.loads(raw_meta) if raw_meta else {}
    except Exception:
        metadata = {}

    return AuditLogResponse(
        id=row["id"],
        investigation_id=row["investigation_id"],
        case_code=row["case_code"] if "case_code" in keys else metadata.get("case_code"),
        investigation_title=(
            row["investigation_title"]
            if "investigation_title" in keys
            else metadata.get("title")
        ),
        action=row["action"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        actor=row["actor"],
        actor_user_id=row["actor_user_id"] if "actor_user_id" in keys else None,
        actor_role=row["actor_role"] if "actor_role" in keys else None,
        event_origin=(
            row["event_origin"]
            if "event_origin" in keys and row["event_origin"]
            else "AUTHENTICATED_HUMAN"
        ),
        sequence_number=(
            int(row["sequence_number"])
            if "sequence_number" in keys and row["sequence_number"] is not None
            else None
        ),
        prev_hash=row["prev_hash"] if "prev_hash" in keys else None,
        event_hash=row["event_hash"] if "event_hash" in keys else None,
        summary=row["summary"],
        metadata=metadata,
        created_at=row["created_at"],
    )


class InvestigationService:
    @staticmethod
    def create_investigation(
        payload: InvestigationCreate,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> InvestigationResponse:
        now = _utc_now_iso()
        inv_id = str(uuid.uuid4())
        lead_inv = (
            payload.lead_investigator.strip()
            if payload.lead_investigator
            and payload.lead_investigator.strip() != "Lead Forensic Analyst"
            else (
                f"{current_user.full_name} ({current_user.title})"
                if current_user
                else payload.lead_investigator.strip()
            )
        )
        owner_id = current_user.id if current_user else None
        is_shared_org = 1 if (not current_user or current_user.is_demo_account) else 0

        with get_db_connection() as conn:
            case_code = _generate_case_code(conn)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO investigations (
                    id, case_code, title, description, status, priority,
                    classification, lead_investigator, owner_user_id, is_shared_org, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    inv_id,
                    case_code,
                    payload.title.strip(),
                    payload.description.strip(),
                    InvestigationStatus.OPEN.value,
                    payload.priority.value,
                    payload.classification.value,
                    lead_inv,
                    owner_id,
                    is_shared_org,
                    now,
                    now,
                ),
            )

            metadata = {
                "case_code": case_code,
                "title": payload.title.strip(),
                "priority": payload.priority.value,
                "classification": payload.classification.value,
                "status": InvestigationStatus.OPEN.value,
            }
            AuditService.append_event_with_cursor(
                cursor,
                investigation_id=inv_id,
                action="INVESTIGATION_CREATED",
                entity_type="INVESTIGATION",
                entity_id=inv_id,
                actor=lead_inv,
                summary=f"Initialized investigation {case_code}: {payload.title.strip()}",
                metadata=metadata,
                actor_user_id=current_user.id if current_user else None,
                actor_role=current_user.role if current_user else None,
                event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                created_at=now,
            )

            cursor.execute(
                """
                SELECT i.*,
                       0 AS document_count,
                       0 AS findings_count,
                       0 AS pending_review_count
                FROM investigations i
                WHERE i.id = ?;
                """,
                (inv_id,),
            )
            row = cursor.fetchone()
            return _row_to_investigation(row)

    @staticmethod
    def list_investigations(
        status: Optional[str] = None,
        priority: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> List[InvestigationResponse]:
        query = """
            SELECT
                i.*,
                COALESCE(d.doc_cnt, 0) AS document_count,
                COALESCE(f.find_cnt, 0) AS findings_count,
                COALESCE(f.rev_cnt, 0) AS pending_review_count
            FROM investigations i
            LEFT JOIN (
                SELECT investigation_id, COUNT(*) AS doc_cnt
                FROM documents
                GROUP BY investigation_id
            ) d ON d.investigation_id = i.id
            LEFT JOIN (
                SELECT
                    investigation_id,
                    COUNT(*) AS find_cnt,
                    SUM(CASE WHEN review_status = 'REQUIRES_REVIEW' THEN 1 ELSE 0 END) AS rev_cnt
                FROM findings
                GROUP BY investigation_id
            ) f ON f.investigation_id = i.id
            WHERE 1=1
        """
        params: List[Any] = []

        if current_user and current_user.role != "ADMIN":
            query += """
                AND (
                    i.owner_user_id IS NULL
                    OR i.is_shared_org = 1
                    OR i.owner_user_id = ?
                    OR EXISTS (
                        SELECT 1 FROM investigation_members im
                        WHERE im.investigation_id = i.id AND im.user_id = ?
                    )
                )
            """
            params.extend([current_user.id, current_user.id])

        if status:
            query += " AND i.status = ?"
            params.append(status.upper())

        if priority:
            query += " AND i.priority = ?"
            params.append(priority.upper())

        if search and search.strip():
            term = f"%{search.strip()}%"
            query += " AND (i.title LIKE ? OR i.case_code LIKE ? OR i.description LIKE ? OR i.lead_investigator LIKE ?)"
            params.extend([term, term, term, term])

        query += " ORDER BY i.updated_at DESC, i.created_at DESC LIMIT ?;"
        params.append(max(1, min(limit, 200)))

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [_row_to_investigation(r) for r in rows]

    @staticmethod
    def get_investigation_detail(investigation_id: str) -> InvestigationDetailResponse:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    i.*,
                    COALESCE((SELECT COUNT(*) FROM documents WHERE investigation_id = i.id), 0) AS document_count,
                    COALESCE((SELECT COUNT(*) FROM findings WHERE investigation_id = i.id), 0) AS findings_count,
                    COALESCE((SELECT COUNT(*) FROM findings WHERE investigation_id = i.id AND review_status = 'REQUIRES_REVIEW'), 0) AS pending_review_count
                FROM investigations i
                WHERE i.id = ?;
                """,
                (investigation_id,),
            )
            inv_row = cursor.fetchone()
            if not inv_row:
                raise ResourceNotFoundException("Investigation", investigation_id)

            base_inv = _row_to_investigation(inv_row)

            cursor.execute(
                """
                SELECT a.*, i.case_code, i.title AS investigation_title
                FROM audit_logs a
                LEFT JOIN investigations i ON i.id = a.investigation_id
                WHERE a.investigation_id = ?
                ORDER BY a.created_at DESC
                LIMIT 50;
                """,
                (investigation_id,),
            )
            audit_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT id, investigation_id, filename, file_type, mime_type,
                       file_size_bytes, sha256_hash, page_count,
                       extraction_method_summary, is_scanned, average_confidence,
                       extracted_char_count, processing_status, uploaded_at, processed_at
                FROM documents
                WHERE investigation_id = ?
                ORDER BY uploaded_at DESC;
                """,
                (investigation_id,),
            )
            doc_rows = [dict(r) for r in cursor.fetchall()]

            cursor.execute(
                """
                SELECT id, investigation_id, document_id, finding_type, severity,
                       review_status, title, description, confidence_score, created_at
                FROM findings
                WHERE investigation_id = ?
                ORDER BY created_at DESC;
                """,
                (investigation_id,),
            )
            finding_rows = [dict(r) for r in cursor.fetchall()]

            return InvestigationDetailResponse(
                **base_inv.model_dump(),
                audit_trail=[_row_to_audit_log(r) for r in audit_rows],
                documents=doc_rows,
                findings=finding_rows,
            )

    @staticmethod
    def update_investigation(
        investigation_id: str,
        payload: InvestigationUpdate,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> InvestigationResponse:
        now = _utc_now_iso()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM investigations WHERE id = ?;", (investigation_id,)
            )
            existing = cursor.fetchone()
            if not existing:
                raise ResourceNotFoundException("Investigation", investigation_id)

            updates: List[str] = []
            params: List[Any] = []
            changes: Dict[str, Any] = {}

            if payload.title is not None and payload.title.strip() != existing["title"]:
                updates.append("title = ?")
                params.append(payload.title.strip())
                changes["title"] = {"from": existing["title"], "to": payload.title.strip()}

            if (
                payload.description is not None
                and payload.description.strip() != existing["description"]
            ):
                updates.append("description = ?")
                params.append(payload.description.strip())
                changes["description_updated"] = True

            if payload.status is not None and payload.status.value != existing["status"]:
                updates.append("status = ?")
                params.append(payload.status.value)
                changes["status"] = {
                    "from": existing["status"],
                    "to": payload.status.value,
                }

            if (
                payload.priority is not None
                and payload.priority.value != existing["priority"]
            ):
                updates.append("priority = ?")
                params.append(payload.priority.value)
                changes["priority"] = {
                    "from": existing["priority"],
                    "to": payload.priority.value,
                }

            if (
                payload.classification is not None
                and payload.classification.value != existing["classification"]
            ):
                updates.append("classification = ?")
                params.append(payload.classification.value)
                changes["classification"] = {
                    "from": existing["classification"],
                    "to": payload.classification.value,
                }

            if (
                payload.lead_investigator is not None
                and payload.lead_investigator.strip() != existing["lead_investigator"]
            ):
                updates.append("lead_investigator = ?")
                params.append(payload.lead_investigator.strip())
                changes["lead_investigator"] = {
                    "from": existing["lead_investigator"],
                    "to": payload.lead_investigator.strip(),
                }

            if updates:
                updates.append("updated_at = ?")
                params.append(now)
                params.append(investigation_id)

                cursor.execute(
                    f"UPDATE investigations SET {', '.join(updates)} WHERE id = ?;",
                    tuple(params),
                )

                action_type = (
                    "STATUS_TRANSITION"
                    if "status" in changes
                    else "INVESTIGATION_UPDATED"
                )
                if "status" in changes:
                    summary = (
                        f"Case {existing['case_code']} status transitioned from "
                        f"{changes['status']['from']} to {changes['status']['to']}"
                    )
                else:
                    summary = f"Updated case parameters for {existing['case_code']}"

                actor_name = (
                    f"{current_user.full_name} ({current_user.title})"
                    if current_user
                    else (
                        payload.lead_investigator.strip()
                        if payload.lead_investigator
                        else existing["lead_investigator"]
                    )
                )
                AuditService.append_event_with_cursor(
                    cursor,
                    investigation_id=investigation_id,
                    action=action_type,
                    entity_type="INVESTIGATION",
                    entity_id=investigation_id,
                    actor=actor_name,
                    summary=summary,
                    metadata={
                        "case_code": existing["case_code"],
                        "title": existing["title"],
                        "changes": changes,
                    },
                    actor_user_id=current_user.id if current_user else None,
                    actor_role=current_user.role if current_user else None,
                    event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                    created_at=now,
                )

        return InvestigationService.get_investigation_detail(investigation_id)

    @staticmethod
    def add_case_note(
        investigation_id: str,
        payload: CaseNoteCreate,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> AuditLogResponse:
        now = _utc_now_iso()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, case_code, title FROM investigations WHERE id = ?;",
                (investigation_id,),
            )
            inv = cursor.fetchone()
            if not inv:
                raise ResourceNotFoundException("Investigation", investigation_id)

            actor_name = (
                f"{current_user.full_name} ({current_user.title})"
                if current_user
                else payload.actor.strip()
            )
            metadata = {
                "case_code": inv["case_code"],
                "title": inv["title"],
                "note": payload.note.strip(),
            }
            audit_id = AuditService.append_event_with_cursor(
                cursor,
                investigation_id=investigation_id,
                action="CASE_NOTE_LOGGED",
                entity_type="INVESTIGATION",
                entity_id=investigation_id,
                actor=actor_name,
                summary=f"[{inv['case_code']}] {payload.note.strip()}",
                metadata=metadata,
                actor_user_id=current_user.id if current_user else None,
                actor_role=current_user.role if current_user else None,
                event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                created_at=now,
            )
            cursor.execute(
                "UPDATE investigations SET updated_at = ? WHERE id = ?;",
                (now, investigation_id),
            )
            cursor.execute(
                """
                SELECT a.*, i.case_code, i.title AS investigation_title
                FROM audit_logs a
                LEFT JOIN investigations i ON i.id = a.investigation_id
                WHERE a.id = ?;
                """,
                (audit_id,),
            )
            return _row_to_audit_log(cursor.fetchone())

    @staticmethod
    def delete_investigation(
        investigation_id: str,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> Dict[str, Any]:
        now = _utc_now_iso()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, case_code, title, lead_investigator FROM investigations WHERE id = ?;",
                (investigation_id,),
            )
            inv = cursor.fetchone()
            if not inv:
                raise ResourceNotFoundException("Investigation", investigation_id)

            cursor.execute(
                "DELETE FROM investigations WHERE id = ?;", (investigation_id,)
            )
            actor_name = (
                f"{current_user.full_name} ({current_user.title})"
                if current_user
                else inv["lead_investigator"]
            )
            AuditService.append_event_with_cursor(
                cursor,
                investigation_id=None,
                action="INVESTIGATION_DELETED",
                entity_type="INVESTIGATION",
                entity_id=investigation_id,
                actor=actor_name,
                summary=f"Removed investigation {inv['case_code']}: {inv['title']}",
                metadata={"case_code": inv["case_code"], "title": inv["title"]},
                actor_user_id=current_user.id if current_user else None,
                actor_role=current_user.role if current_user else None,
                event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                created_at=now,
            )
            return {
                "deleted": True,
                "id": investigation_id,
                "case_code": inv["case_code"],
            }

    @staticmethod
    def list_audit_logs(
        limit: int = 40,
        investigation_id: Optional[str] = None,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> List[AuditLogResponse]:
        query = """
            SELECT a.*, i.case_code, i.title AS investigation_title
            FROM audit_logs a
            LEFT JOIN investigations i ON i.id = a.investigation_id
            WHERE 1=1
        """
        params: List[Any] = []
        if investigation_id:
            query += " AND a.investigation_id = ?"
            params.append(investigation_id)
        elif current_user and current_user.role != "ADMIN":
            query += """
                AND (
                    a.investigation_id IS NULL
                    OR i.owner_user_id IS NULL
                    OR i.owner_user_id = ?
                    OR EXISTS (
                        SELECT 1 FROM investigation_members im
                        WHERE im.investigation_id = a.investigation_id AND im.user_id = ?
                    )
                )
            """
            params.extend([current_user.id, current_user.id])

        query += " ORDER BY a.sequence_number DESC, a.created_at DESC LIMIT ?;"
        params.append(max(1, min(limit, 200)))

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            return [_row_to_audit_log(r) for r in cursor.fetchall()]
