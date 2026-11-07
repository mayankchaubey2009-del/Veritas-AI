import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.core.database import get_db_connection
from app.core.exceptions import InvalidDocumentException, ResourceNotFoundException
from app.schemas.auth import AuthenticatedUser
from app.services.audit_service import AuditService
from app.services.document_service import _verify_storage_containment


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BackupService:
    """
    Phase 6 Module F — SQLite Online Backup, Integrity Verification & Restore Utility.
    Uses SQLite's native C backup API (`sqlite3.Connection.backup`) so backups are
    transactionally consistent even while WAL mode is active.
    """

    @staticmethod
    def create_backup(
        label: Optional[str] = None,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> Dict[str, Any]:
        backups_dir = settings.resolved_backups_dir
        backups_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc)
        ts_slug = now.strftime("%Y%m%d_%H%M%S")
        backup_id = f"bkp_{ts_slug}_{uuid.uuid4().hex[:8]}"
        db_filename = f"{backup_id}.db"
        meta_filename = f"{backup_id}.meta.json"

        backup_db_path = _verify_storage_containment(
            backups_dir / db_filename, backups_dir
        )
        backup_meta_path = _verify_storage_containment(
            backups_dir / meta_filename, backups_dir
        )

        src_path = settings.resolved_sqlite_path
        src_conn = sqlite3.connect(str(src_path), timeout=30.0)
        dst_conn = sqlite3.connect(str(backup_db_path), timeout=30.0)
        try:
            with dst_conn:
                src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()

        try:
            os.chmod(backup_db_path, 0o600)
        except OSError:
            pass

        backup_bytes = backup_db_path.read_bytes()
        sha256_hash = hashlib.sha256(backup_bytes).hexdigest()

        # Inspect row counts inside the newly created backup
        chk_conn = sqlite3.connect(str(backup_db_path))
        try:
            integrity = chk_conn.execute("PRAGMA integrity_check;").fetchone()[0]
            inv_cnt = chk_conn.execute(
                "SELECT COUNT(*) FROM investigations;"
            ).fetchone()[0]
            doc_cnt = chk_conn.execute("SELECT COUNT(*) FROM documents;").fetchone()[0]
            aud_cnt = chk_conn.execute("SELECT COUNT(*) FROM audit_logs;").fetchone()[0]
        finally:
            chk_conn.close()

        actor_label = (
            f"{current_user.full_name} ({current_user.title})"
            if current_user
            else "SYSTEM"
        )
        created_iso = now.isoformat()
        manifest = {
            "backup_id": backup_id,
            "label": (label or "Manual Forensic Store Snapshot").strip(),
            "filename": db_filename,
            "size_bytes": len(backup_bytes),
            "sha256_hash": sha256_hash,
            "sqlite_integrity_check": integrity,
            "investigations_count": inv_cnt,
            "documents_count": doc_cnt,
            "audit_logs_count": aud_cnt,
            "created_by": actor_label,
            "created_at": created_iso,
        }
        backup_meta_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        with get_db_connection() as conn:
            cursor = conn.cursor()
            AuditService.append_event_with_cursor(
                cursor,
                investigation_id=None,
                action="DATABASE_BACKUP_CREATED",
                entity_type="SYSTEM_BACKUP",
                entity_id=backup_id,
                actor=actor_label,
                summary=f"Created SQLite online backup '{backup_id}' ({len(backup_bytes)} bytes, SHA-256: {sha256_hash[:16]}...)",
                metadata=manifest,
                actor_user_id=current_user.id if current_user else None,
                actor_role=current_user.role if current_user else "SYSTEM",
                event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                created_at=created_iso,
            )

        return {**manifest, "integrity_verified": integrity == "ok"}

    @staticmethod
    def list_backups() -> List[Dict[str, Any]]:
        backups_dir = settings.resolved_backups_dir
        if not backups_dir.exists():
            return []

        items: List[Dict[str, Any]] = []
        for meta_file in sorted(backups_dir.glob("*.meta.json"), reverse=True):
            try:
                manifest = json.loads(meta_file.read_text(encoding="utf-8"))
                db_file = backups_dir / manifest.get("filename", "")
                verified = False
                if db_file.exists():
                    live_sha = hashlib.sha256(db_file.read_bytes()).hexdigest()
                    verified = live_sha == manifest.get("sha256_hash")
                items.append({**manifest, "integrity_verified": verified})
            except Exception:
                continue
        return items

    @staticmethod
    def verify_or_restore_backup(
        backup_id: str,
        target_db_path: Optional[Path] = None,
        perform_restore: bool = False,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> Dict[str, Any]:
        backups_dir = settings.resolved_backups_dir
        clean_id = os.path.basename(backup_id).replace(".db", "").replace(".meta.json", "")
        db_file = _verify_storage_containment(
            backups_dir / f"{clean_id}.db", backups_dir
        )
        meta_file = _verify_storage_containment(
            backups_dir / f"{clean_id}.meta.json", backups_dir
        )

        if not db_file.exists() or not meta_file.exists():
            raise ResourceNotFoundException("DatabaseBackup", clean_id)

        manifest = json.loads(meta_file.read_text(encoding="utf-8"))
        live_sha = hashlib.sha256(db_file.read_bytes()).hexdigest()
        if live_sha != manifest.get("sha256_hash"):
            raise InvalidDocumentException(
                message=f"Backup '{clean_id}' failed SHA-256 integrity verification.",
                code="BACKUP_HASH_MISMATCH",
            )

        chk_conn = sqlite3.connect(str(db_file))
        try:
            pragma_res = chk_conn.execute("PRAGMA integrity_check;").fetchone()[0]
        finally:
            chk_conn.close()

        if pragma_res != "ok":
            raise InvalidDocumentException(
                message=f"Backup '{clean_id}' failed SQLite PRAGMA integrity_check: {pragma_res}",
                code="BACKUP_CORRUPTED",
            )

        restored_to: Optional[str] = None
        if perform_restore:
            dest_path = target_db_path or settings.resolved_sqlite_path
            bkp_conn = sqlite3.connect(str(db_file), timeout=30.0)
            dst_conn = sqlite3.connect(str(dest_path), timeout=30.0)
            try:
                with dst_conn:
                    bkp_conn.backup(dst_conn)
            finally:
                dst_conn.close()
                bkp_conn.close()
            restored_to = str(dest_path)

            if dest_path == settings.resolved_sqlite_path:
                actor_label = (
                    f"{current_user.full_name} ({current_user.title})"
                    if current_user
                    else "SYSTEM"
                )
                with get_db_connection() as conn:
                    AuditService.append_event_with_cursor(
                        conn.cursor(),
                        investigation_id=None,
                        action="DATABASE_BACKUP_RESTORED",
                        entity_type="SYSTEM_BACKUP",
                        entity_id=clean_id,
                        actor=actor_label,
                        summary=f"Restored SQLite database from verified backup '{clean_id}'",
                        metadata={"backup_id": clean_id, "sha256_hash": live_sha},
                        actor_user_id=current_user.id if current_user else None,
                        actor_role=current_user.role if current_user else "SYSTEM",
                        event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                    )

        return {
            "backup_id": clean_id,
            "sha256_verified": True,
            "sqlite_integrity_check": pragma_res,
            "perform_restore": perform_restore,
            "restored_to": restored_to,
            "manifest": manifest,
        }
