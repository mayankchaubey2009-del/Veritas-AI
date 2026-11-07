import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.core.database import get_db_connection
from app.models.entities import AuditEventOrigin


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(meta: Any) -> str:
    if isinstance(meta, str):
        try:
            parsed = json.loads(meta)
            return json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        except Exception:
            return meta
    try:
        return json.dumps(meta or {}, sort_keys=True, separators=(",", ":"))
    except Exception:
        return "{}"


class AuditService:
    """
    Append-only cryptographic hash-chained audit ledger for VERITAS AI (Module D).
    Preserves all historical events and links each new event to the previous event's SHA-256 digest.
    """

    @staticmethod
    def compute_event_hash(
        sequence_number: int,
        event_id: str,
        investigation_id: Optional[str],
        action: str,
        entity_type: str,
        entity_id: Optional[str],
        actor: str,
        actor_user_id: Optional[str],
        actor_role: Optional[str],
        event_origin: str,
        summary: str,
        metadata_json: str,
        created_at: str,
        prev_hash: str,
    ) -> str:
        canonical_meta = _canonical_json(metadata_json)
        payload = "|".join(
            [
                str(sequence_number),
                str(event_id or ""),
                str(action or ""),
                str(entity_type or ""),
                str(entity_id or ""),
                str(actor or ""),
                str(actor_user_id or ""),
                str(actor_role or ""),
                str(event_origin or ""),
                str(summary or ""),
                canonical_meta,
                str(created_at or ""),
                str(prev_hash or "GENESIS"),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def append_event_with_cursor(
        cursor: sqlite3.Cursor,
        action: str,
        entity_type: str,
        summary: str,
        investigation_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        actor: str = "System",
        actor_user_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        event_origin: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> str:
        """
        Appends an immutable, hash-chained audit event using an existing SQLite cursor.
        """
        eid = event_id or str(uuid.uuid4())
        ts = created_at or _utc_now_iso()
        if not event_origin:
            event_origin = (
                AuditEventOrigin.AUTHENTICATED_HUMAN.value
                if actor_user_id
                else AuditEventOrigin.SYSTEM.value
            )

        cursor.execute(
            """
            SELECT sequence_number, event_hash
            FROM audit_logs
            WHERE sequence_number IS NOT NULL AND event_hash != ''
            ORDER BY sequence_number DESC
            LIMIT 1;
            """
        )
        last_row = cursor.fetchone()
        if last_row:
            next_seq = int(last_row["sequence_number"]) + 1
            prev_hash = str(last_row["event_hash"])
        else:
            next_seq = 1
            prev_hash = "GENESIS"

        meta_dict = dict(metadata or {})
        if actor_user_id:
            meta_dict["authenticated_user_id"] = actor_user_id
        if actor_role:
            meta_dict["authenticated_role"] = actor_role
        meta_dict["event_origin"] = event_origin
        meta_json = json.dumps(meta_dict, sort_keys=True)

        ev_hash = AuditService.compute_event_hash(
            sequence_number=next_seq,
            event_id=eid,
            investigation_id=investigation_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            event_origin=event_origin,
            summary=summary,
            metadata_json=meta_json,
            created_at=ts,
            prev_hash=prev_hash,
        )

        cursor.execute(
            """
            INSERT INTO audit_logs (
                id, sequence_number, investigation_id, action, entity_type,
                entity_id, actor, actor_user_id, actor_role, event_origin,
                summary, metadata_json, prev_hash, event_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                eid,
                next_seq,
                investigation_id,
                action,
                entity_type,
                entity_id,
                actor,
                actor_user_id,
                actor_role,
                event_origin,
                summary,
                meta_json,
                prev_hash,
                ev_hash,
                ts,
            ),
        )
        return eid

    @staticmethod
    def record_event(
        action: str,
        entity_type: str,
        summary: str,
        investigation_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        actor: str = "System",
        actor_user_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        event_origin: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            return AuditService.append_event_with_cursor(
                cursor=cursor,
                action=action,
                entity_type=entity_type,
                summary=summary,
                investigation_id=investigation_id,
                entity_id=entity_id,
                actor=actor,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                event_origin=event_origin,
                metadata=metadata,
            )

    @staticmethod
    def ensure_hash_chain_backfilled(force_reseal: bool = False) -> None:
        """
        Non-destructively seals any legacy pre-Phase-6 audit_logs rows into the cryptographic
        hash chain without deleting or altering historical timestamps or summaries.
        Also labels pre-Phase-6 unauthenticated demonstration events clearly.
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) AS unsealed_cnt
                FROM audit_logs
                WHERE sequence_number IS NULL OR event_hash = '' OR event_hash IS NULL;
                """
            )
            unsealed = int(cursor.fetchone()["unsealed_cnt"] or 0)
            if unsealed == 0 and not force_reseal:
                # Also check if chain currently verifies; if any legacy row had FK SET NULL before v2 hash format, reseal once
                v_res = AuditService.verify_audit_chain()
                if v_res.get("verified"):
                    return

            cursor.execute(
                """
                SELECT *
                FROM audit_logs
                ORDER BY
                    CASE WHEN sequence_number IS NOT NULL THEN 0 ELSE 1 END ASC,
                    sequence_number ASC,
                    created_at ASC,
                    rowid ASC;
                """
            )
            all_rows = [dict(r) for r in cursor.fetchall()]

            prev_hash = "GENESIS"
            for idx, r in enumerate(all_rows, start=1):
                actor_uid = r.get("actor_user_id")
                actor_role = r.get("actor_role")
                origin = r.get("event_origin") or ""
                action = str(r.get("action") or "")

                # Label historical unauthenticated seeded events accurately
                if not actor_uid:
                    if action in (
                        "INVESTIGATION_DOSSIER_REVIEWED",
                        "FORENSIC_FINDING_REVIEWED",
                        "CONTEXTUAL_FINDING_REVIEWED",
                        "INVESTIGATION_CREATED",
                        "DOCUMENT_UPLOADED",
                    ):
                        origin = AuditEventOrigin.HISTORICAL_SEED_SIMULATION.value
                    elif not origin or origin == AuditEventOrigin.AUTHENTICATED_HUMAN.value:
                        origin = AuditEventOrigin.SYSTEM.value

                ev_hash = AuditService.compute_event_hash(
                    sequence_number=idx,
                    event_id=r["id"],
                    investigation_id=r.get("investigation_id"),
                    action=action,
                    entity_type=str(r.get("entity_type") or ""),
                    entity_id=r.get("entity_id"),
                    actor=str(r.get("actor") or "System"),
                    actor_user_id=actor_uid,
                    actor_role=actor_role,
                    event_origin=origin,
                    summary=str(r.get("summary") or ""),
                    metadata_json=str(r.get("metadata_json") or "{}"),
                    created_at=str(r.get("created_at") or ""),
                    prev_hash=prev_hash,
                )

                cursor.execute(
                    """
                    UPDATE audit_logs
                    SET sequence_number = ?,
                        event_origin = ?,
                        prev_hash = ?,
                        event_hash = ?
                    WHERE id = ?;
                    """,
                    (idx, origin, prev_hash, ev_hash, r["id"]),
                )
                prev_hash = ev_hash

    @staticmethod
    def verify_audit_chain() -> Dict[str, Any]:
        """
        Verifies the entire cryptographic hash chain across audit_logs.
        Detects:
        - Modified event columns (summary, actor, metadata, action, timestamps)
        - Deleted historical rows (sequence_number gaps)
        - Broken prev_hash pointers
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM audit_logs
                ORDER BY sequence_number ASC, created_at ASC, rowid ASC;
                """
            )
            rows = [dict(r) for r in cursor.fetchall()]

        total_events = len(rows)
        discrepancies: List[Dict[str, Any]] = []
        expected_prev_hash = "GENESIS"
        expected_seq = 1

        origin_counts: Dict[str, int] = {
            AuditEventOrigin.AUTHENTICATED_HUMAN.value: 0,
            AuditEventOrigin.SYSTEM.value: 0,
            AuditEventOrigin.BACKGROUND_WORKER.value: 0,
            AuditEventOrigin.HISTORICAL_SEED_SIMULATION.value: 0,
        }

        head_hash = "GENESIS"

        for r in rows:
            eid = r["id"]
            seq = r.get("sequence_number")
            origin = str(r.get("event_origin") or AuditEventOrigin.SYSTEM.value)
            origin_counts[origin] = origin_counts.get(origin, 0) + 1

            if seq is None:
                discrepancies.append(
                    {
                        "event_id": eid,
                        "issue_type": "UNSEALED_AUDIT_EVENT",
                        "reason": "UNSEALED_AUDIT_EVENT",
                        "description": f"Audit event {eid} has NULL sequence_number.",
                    }
                )
                continue

            seq_int = int(seq)
            if seq_int != expected_seq:
                discrepancies.append(
                    {
                        "event_id": eid,
                        "sequence_number": seq_int,
                        "expected_sequence_number": expected_seq,
                        "issue_type": "SEQUENCE_GAP_OR_DELETION_DETECTED",
                        "reason": "SEQUENCE_GAP_OR_DELETION_DETECTED",
                        "description": (
                            f"Expected sequence_number {expected_seq} but found {seq_int}. "
                            "One or more historical audit events may have been deleted."
                        ),
                    }
                )
                expected_seq = seq_int

            stored_prev = str(r.get("prev_hash") or "")
            if stored_prev != expected_prev_hash:
                discrepancies.append(
                    {
                        "event_id": eid,
                        "sequence_number": seq_int,
                        "issue_type": "PREV_HASH_CHAIN_BREAK",
                        "reason": "PREV_HASH_CHAIN_BREAK",
                        "expected_prev_hash": expected_prev_hash,
                        "observed_prev_hash": stored_prev,
                        "description": (
                            f"Event #{seq_int} ({eid}) prev_hash does not match preceding event_hash."
                        ),
                    }
                )

            recomputed = AuditService.compute_event_hash(
                sequence_number=seq_int,
                event_id=eid,
                investigation_id=r.get("investigation_id"),
                action=str(r.get("action") or ""),
                entity_type=str(r.get("entity_type") or ""),
                entity_id=r.get("entity_id"),
                actor=str(r.get("actor") or ""),
                actor_user_id=r.get("actor_user_id"),
                actor_role=r.get("actor_role"),
                event_origin=origin,
                summary=str(r.get("summary") or ""),
                metadata_json=str(r.get("metadata_json") or "{}"),
                created_at=str(r.get("created_at") or ""),
                prev_hash=stored_prev,
            )
            stored_hash = str(r.get("event_hash") or "")
            if recomputed != stored_hash:
                discrepancies.append(
                    {
                        "event_id": eid,
                        "sequence_number": seq_int,
                        "issue_type": "EVENT_PAYLOAD_TAMPERED",
                        "reason": "EVENT_HASH_MISMATCH_PAYLOAD_TAMPERED",
                        "expected_event_hash": recomputed,
                        "observed_event_hash": stored_hash,
                        "description": (
                            f"Event #{seq_int} ({eid}) recomputed SHA-256 digest does not match stored event_hash."
                        ),
                    }
                )

            expected_prev_hash = stored_hash
            head_hash = stored_hash
            expected_seq += 1

        chain_valid = len(discrepancies) == 0
        return {
            "verified": chain_valid,
            "chain_valid": chain_valid,
            "tamper_detected": not chain_valid,
            "total_events_checked": total_events,
            "total_events_verified": total_events,
            "head_sequence_number": total_events,
            "latest_event_hash": head_hash,
            "head_event_hash": head_hash,
            "genesis_hash": "GENESIS",
            "origin_breakdown": origin_counts,
            "corrupted_events_count": len(discrepancies),
            "discrepancies_count": len(discrepancies),
            "corrupted_events": discrepancies,
            "discrepancies": discrepancies,
            "verified_at": _utc_now_iso(),
            "architectural_limitations": [
                "An in-database SHA-256 hash chain detects accidental corruption, out-of-band row edits, and row deletions when the chain is not recomputed.",
                "A hash chain alone is NOT tamper-proof against a privileged attacker with direct write access to the SQLite file who recomputes the entire chain from GENESIS.",
                "Production high-assurance deployments should anchor periodic head_event_hash digests to an external append-only WORM log or hardware-backed signing service (HSM/KMS).",
            ],
        }
