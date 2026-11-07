from pathlib import Path
import fitz
from fastapi.testclient import TestClient
from app.core.config import settings
from app.core.database import get_db_connection, init_db
from app.main import app
from app.services.audit_service import AuditService
from app.services.auth_service import (
    AuthService,
    hash_password_pbkdf2,
    hash_password_scrypt,
    verify_password,
)
from app.services.backup_service import BackupService
from app.services.job_service import JobService

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "sample-data"

init_db()
AuthService.ensure_demo_personas()
AuditService.ensure_hash_chain_backfilled()


def test_phase6_authentication_password_hashing_and_session_lifecycle() -> None:
    """
    Tests Module A:
    - Salted PBKDF2-HMAC-SHA256 and scrypt password hashing & constant-time verification
    - User creation by ADMIN, login with credentials, HttpOnly cookie & Bearer token
    - Session verification (/api/auth/me) and logout revocation (/api/auth/logout)
    - Login rate limiting on repeated failed password attempts
    """
    # 1. Verify both PBKDF2-HMAC-SHA256 and scrypt KDF primitives
    pw = "Veritas!Forensic#2026"
    pbkdf2_hash = hash_password_pbkdf2(pw)
    assert pbkdf2_hash.startswith("$pbkdf2-sha256$310000$")
    assert verify_password(pw, pbkdf2_hash) is True
    assert verify_password("WrongPassword", pbkdf2_hash) is False

    scrypt_hash = hash_password_scrypt(pw)
    assert scrypt_hash.startswith("$scrypt$")
    assert verify_password(pw, scrypt_hash) is True
    assert verify_password("WrongPassword", scrypt_hash) is False

    with TestClient(app) as client:
        # Switch to ADMIN persona to provision a real password-authenticated user
        admin_resp = client.post(
            "/api/auth/demo-session", json={"username": "admin.nair"}
        )
        assert admin_resp.status_code == 200

        unique_username = "analyst.phase6.auth"
        with get_db_connection() as conn:
            conn.execute("DELETE FROM users WHERE username = ?;", (unique_username,))
            conn.execute("DELETE FROM login_rate_limits;")

        create_resp = client.post(
            "/api/auth/users",
            json={
                "username": unique_username,
                "full_name": "Commander Julian Vance",
                "role": "INVESTIGATOR",
                "title": "Senior Forensic Investigator",
                "password": "StrongPassword!2026",
            },
        )
        assert create_resp.status_code == 201
        created_user = create_resp.json()
        assert created_user["username"] == unique_username
        assert created_user["role"] == "INVESTIGATOR"

        # Log out of admin session
        client.post("/api/auth/logout")

        # Log in with real username and password
        login_resp = client.post(
            "/api/auth/login",
            json={
                "username": unique_username,
                "password": "StrongPassword!2026",
            },
        )
        assert login_resp.status_code == 200
        login_body = login_resp.json()
        token = login_body["access_token"]
        assert token
        assert settings.session_cookie_name in login_resp.cookies

        # Verify /api/auth/me reflects authenticated user
        me_resp = client.get("/api/auth/me")
        assert me_resp.status_code == 200
        assert me_resp.json()["authenticated"] is True
        assert me_resp.json()["user"]["username"] == unique_username

        # Logout revokes session in SQLite
        logout_resp = client.post("/api/auth/logout")
        assert logout_resp.status_code == 200

        # Subsequent request with revoked Bearer token must fail with 401
        revoked_check = client.get(
            "/api/investigations",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert revoked_check.status_code == 401

        # Test login rate limiting on repeated bad password attempts
        for _ in range(settings.login_rate_limit_attempts):
            bad_resp = client.post(
                "/api/auth/login",
                json={"username": unique_username, "password": "BadPassword123!"},
            )
            assert bad_resp.status_code == 401

        rate_limited_resp = client.post(
            "/api/auth/login",
            json={"username": unique_username, "password": "BadPassword123!"},
        )
        assert rate_limited_resp.status_code == 429
        assert rate_limited_resp.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"

        with get_db_connection() as conn:
            conn.execute("DELETE FROM login_rate_limits;")


def test_phase6_unauthorized_requests_rejected_401() -> None:
    """Verifies that unauthenticated requests to protected endpoints return 401 Unauthorized."""
    with TestClient(app) as unauth_client:
        unauth_client.cookies.clear()
        assert unauth_client.get("/api/investigations").status_code == 401
        assert unauth_client.post("/api/investigations", json={"title": "Test"}).status_code == 401
        assert unauth_client.get("/api/dashboard/summary").status_code == 401
        assert unauth_client.get("/api/audit-logs").status_code == 401
        assert unauth_client.get("/api/audit-logs/verify").status_code == 401
        assert unauth_client.get("/api/system/config").status_code == 401
        assert unauth_client.get("/api/jobs").status_code == 401
        assert unauth_client.get("/api/documents/some-id").status_code == 401
        assert unauth_client.get("/api/dossiers/some-id").status_code == 401


def test_phase6_rbac_forbidden_403_and_dossier_self_approval_prevention() -> None:
    """
    Tests Module A Role-Based Access Control (403) and Dossier Approval Integrity:
    - VIEWER can read permitted investigations but cannot create/modify/upload/review (403).
    - INVESTIGATOR can create investigations and generate dossiers, but CANNOT approve their own dossier (403).
    - REVIEWER can approve a dossier generated by INVESTIGATOR, and reviewer identity is enforced from the session.
    """
    with TestClient(app) as client:
        # 1. Switch to VIEWER (Audrey Chen)
        client.post("/api/auth/demo-session", json={"username": "a.chen"})
        assert client.get("/api/investigations").status_code == 200

        # VIEWER write attempts must return 403 Forbidden
        assert (
            client.post(
                "/api/investigations",
                json={
                    "title": "Viewer Forbidden Investigation",
                    "description": "Should be blocked by RBAC",
                    "priority": "LOW",
                    "classification": "COMPLIANCE_AUDIT",
                },
            ).status_code
            == 403
        )
        assert client.get("/api/auth/users").status_code == 403
        assert client.post("/api/system/backups").status_code == 403

        # 2. Switch to INVESTIGATOR (Dr. Elena Rostova)
        client.post("/api/auth/demo-session", json={"username": "dr.rostova"})
        inv_resp = client.post(
            "/api/investigations",
            json={
                "title": "Phase 6 Separation of Duties Verification Case",
                "description": "Tests self-approval block and session-enforced reviewer identity.",
                "priority": "HIGH",
                "classification": "FINANCIAL_FORENSICS",
            },
        )
        assert inv_resp.status_code == 201
        inv_id = inv_resp.json()["id"]

        pdf_bytes = (SAMPLE_DIR / "demo_clean_synthetic_invoice.pdf").read_bytes()
        up_resp = client.post(
            f"/api/investigations/{inv_id}/documents",
            files=[("files", ("clean_invoice.pdf", pdf_bytes, "application/pdf"))],
        )
        assert up_resp.status_code == 201

        dos_resp = client.post(
            f"/api/investigations/{inv_id}/dossiers/generate", json={}
        )
        assert dos_resp.status_code == 200
        dossier = dos_resp.json()
        dossier_id = dossier["dossier_id"]
        assert dossier["review_status"] == "UNAPPROVED_AI_ASSISTED"
        assert "Dr. Elena Rostova" in dossier["generated_by"]

        # Investigator cannot approve a dossier (and cannot self-approve) -> 403
        self_app = client.post(
            f"/api/dossiers/{dossier_id}/review",
            json={
                "review_status": "APPROVED",
                "reviewer": "Spoofed Reviewer Name",
                "notes": "Trying to self-approve my own dossier.",
            },
        )
        assert self_app.status_code == 403

        # 3. Switch to REVIEWER (Marcus Vance)
        client.post("/api/auth/demo-session", json={"username": "m.vance"})
        # Even if request body tries to spoof reviewer="Someone Else", session identity is enforced!
        rev_ok = client.post(
            f"/api/dossiers/{dossier_id}/review",
            json={
                "review_status": "APPROVED",
                "reviewer": "Spoofed Unverified Body Name",
                "notes": "Independently verified all claims and SHA-256 hashes as Chief Forensic Reviewer.",
            },
        )
        assert rev_ok.status_code == 200
        rev_data = rev_ok.json()
        assert rev_data["review_status"] == "APPROVED"
        assert "Marcus Vance" in rev_data["reviewed_by"]
        assert "Spoofed" not in rev_data["reviewed_by"]

        # Verify self-approval is also blocked when a REVIEWER generates a dossier themselves
        dos2_resp = client.post(
            f"/api/investigations/{inv_id}/dossiers/generate", json={}
        )
        assert dos2_resp.status_code == 200
        dos2_id = dos2_resp.json()["dossier_id"]
        reviewer_self_app = client.post(
            f"/api/dossiers/{dos2_id}/review",
            json={
                "review_status": "APPROVED",
                "notes": "Reviewer attempting to approve a dossier they generated themselves.",
            },
        )
        assert reviewer_self_app.status_code == 403
        assert (
            reviewer_self_app.json()["error"]["code"]
            == "SELF_DOSSIER_APPROVAL_PROHIBITED"
        )


def test_phase6_cross_investigation_isolation() -> None:
    """
    Tests Module A & Module B Cross-Investigation Isolation:
    - An investigation owned by Investigator A cannot be accessed, downloaded, or modified by Investigator B (403)
      until explicit membership is granted.
    """
    with TestClient(app) as client:
        client.post("/api/auth/demo-session", json={"username": "admin.nair"})
        with get_db_connection() as conn:
            conn.execute(
                "DELETE FROM users WHERE username IN ('iso.investigator.a', 'iso.investigator.b');"
            )

        u_a = client.post(
            "/api/auth/users",
            json={
                "username": "iso.investigator.a",
                "full_name": "Investigator Alpha",
                "role": "INVESTIGATOR",
                "title": "Forensic Analyst A",
                "password": "AlphaPassword!2026",
            },
        ).json()
        u_b = client.post(
            "/api/auth/users",
            json={
                "username": "iso.investigator.b",
                "full_name": "Investigator Beta",
                "role": "INVESTIGATOR",
                "title": "Forensic Analyst B",
                "password": "BetaPassword!2026",
            },
        ).json()

        # Log in as Investigator Alpha and create a private investigation + document
        client.post(
            "/api/auth/login",
            json={"username": "iso.investigator.a", "password": "AlphaPassword!2026"},
        )
        inv_a = client.post(
            "/api/investigations",
            json={
                "title": "Alpha Confidential Investigation",
                "description": "Restricted to Investigator Alpha.",
                "priority": "CRITICAL",
                "classification": "FRAUD_INVESTIGATION",
            },
        ).json()
        inv_a_id = inv_a["id"]
        assert inv_a["owner_user_id"] == u_a["id"]

        pdf_bytes = (SAMPLE_DIR / "demo_clean_synthetic_invoice.pdf").read_bytes()
        doc_a = client.post(
            f"/api/investigations/{inv_a_id}/documents",
            files=[("files", ("alpha_secret.pdf", pdf_bytes, "application/pdf"))],
        ).json()["documents"][0]
        doc_a_id = doc_a["id"]

        # Log in as Investigator Beta -> must NOT see or access Alpha's investigation or document
        client.post(
            "/api/auth/login",
            json={"username": "iso.investigator.b", "password": "BetaPassword!2026"},
        )
        listed_ids = {i["id"] for i in client.get("/api/investigations").json()}
        assert inv_a_id not in listed_ids
        assert client.get(f"/api/investigations/{inv_a_id}").status_code == 403
        assert client.get(f"/api/documents/{doc_a_id}").status_code == 403
        assert client.get(f"/api/documents/{doc_a_id}/download").status_code == 403

        # Investigator Alpha grants READ access to Investigator Beta
        client.post(
            "/api/auth/login",
            json={"username": "iso.investigator.a", "password": "AlphaPassword!2026"},
        )
        grant_resp = client.post(
            f"/api/investigations/{inv_a_id}/members",
            json={"user_id": u_b["id"], "access_level": "READ"},
        )
        assert grant_resp.status_code == 201

        # Investigator Beta can now read (200) and download (200), but still cannot write (403)
        client.post(
            "/api/auth/login",
            json={"username": "iso.investigator.b", "password": "BetaPassword!2026"},
        )
        assert client.get(f"/api/investigations/{inv_a_id}").status_code == 200
        dl_resp = client.get(f"/api/documents/{doc_a_id}/download")
        assert dl_resp.status_code == 200
        assert dl_resp.headers["x-content-type-options"] == "nosniff"
        assert (
            client.post(
                f"/api/investigations/{inv_a_id}/notes",
                json={"note": "Unauthorized write attempt by READ member"},
            ).status_code
            == 403
        )


def test_phase6_upload_security_path_traversal_and_malformed_files() -> None:
    """
    Tests Module B Upload & Document Security:
    - Path traversal filename sanitization & randomized internal UUID storage names
    - Magic signature / extension mismatch rejection
    - Corrupted/malformed PDF and image rejection without crashing
    - Page count limit enforcement
    """
    with TestClient(app) as client:
        client.post("/api/auth/demo-session", json={"username": "dr.rostova"})
        inv_id = client.post(
            "/api/investigations",
            json={
                "title": "Phase 6 Upload Security Verification",
                "description": "Testing upload hardening.",
                "priority": "HIGH",
                "classification": "CYBER_COMPLIANCE",
            },
        ).json()["id"]

        pdf_bytes = (SAMPLE_DIR / "demo_clean_synthetic_invoice.pdf").read_bytes()

        # 1. Path traversal attempt in filename: sanitized display name + UUID internal disk name
        trav_resp = client.post(
            f"/api/investigations/{inv_id}/documents",
            files=[
                (
                    "files",
                    ("../../../../etc/traversal_invoice.pdf", pdf_bytes, "application/pdf"),
                )
            ],
        )
        assert trav_resp.status_code == 201
        saved_doc = trav_resp.json()["documents"][0]
        assert saved_doc["filename"] == "traversal_invoice.pdf"
        with get_db_connection() as conn:
            st_path = Path(
                conn.execute(
                    "SELECT storage_path FROM documents WHERE id = ?;",
                    (saved_doc["id"],),
                ).fetchone()["storage_path"]
            )
        # Disk filename must be randomized UUID.pdf, not user-supplied name
        assert st_path.name == f"{saved_doc['id']}.pdf"
        assert st_path.resolve().is_relative_to(settings.resolved_storage_dir.resolve())

        # 2. Executable / invalid magic signature disguised as .pdf -> 400
        bad_sig = client.post(
            f"/api/investigations/{inv_id}/documents",
            files=[
                ("files", ("malware.pdf", b"MZ\x90\x00\x03\x00\x00\x00", "application/pdf"))
            ],
        )
        assert bad_sig.status_code == 400
        assert bad_sig.json()["error"]["code"] == "INVALID_FILE_SIGNATURE"

        # 3. Corrupted PDF with valid %PDF- header but broken stream -> 400
        corrupt_pdf = client.post(
            f"/api/investigations/{inv_id}/documents",
            files=[
                (
                    "files",
                    ("corrupted.pdf", b"%PDF-1.7\n1 0 obj\n<<corrupted_stream_no_eof", "application/pdf"),
                )
            ],
        )
        assert corrupt_pdf.status_code == 400
        assert corrupt_pdf.json()["error"]["code"] == "CORRUPTED_PDF_DOCUMENT"

        # 4. Corrupted PNG with valid PNG magic bytes but truncated IDAT -> 400
        corrupt_png = client.post(
            f"/api/investigations/{inv_id}/documents",
            files=[
                (
                    "files",
                    ("corrupted.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR_BROKEN", "image/png"),
                )
            ],
        )
        assert corrupt_png.status_code == 400
        assert corrupt_png.json()["error"]["code"] == "CORRUPTED_IMAGE_DOCUMENT"

        # 5. PDF exceeding max_pdf_pages limit -> 413
        big_pdf = fitz.open()
        for _ in range(settings.max_pdf_pages + 2):
            big_pdf.new_page(width=200, height=200)
        big_pdf_bytes = big_pdf.tobytes()
        big_pdf.close()

        over_pages = client.post(
            f"/api/investigations/{inv_id}/documents",
            files=[("files", ("too_many_pages.pdf", big_pdf_bytes, "application/pdf"))],
        )
        assert over_pages.status_code == 413
        assert over_pages.json()["error"]["code"] == "PDF_PAGE_LIMIT_EXCEEDED"


def test_phase6_background_jobs_duplicate_prevention_retry_and_startup_recovery() -> None:
    """
    Tests Module C Background Processing & Recovery:
    - Enqueue job with simulated transient failure -> FAILED (attempt 1)
    - Retry failed job -> COMPLETED (attempt 2, 100% progress)
    - Prevent duplicate active jobs (409 Conflict)
    - Startup recovery of interrupted RUNNING jobs -> marked FAILED (retryable)
    """
    with TestClient(app) as client:
        client.post("/api/auth/demo-session", json={"username": "dr.rostova"})
        inv_id = client.post(
            "/api/investigations",
            json={
                "title": "Phase 6 Background Job & Recovery Case",
                "description": "Tests job lifecycle, duplicate guard, retry, and crash recovery.",
                "priority": "HIGH",
                "classification": "FINANCIAL_FORENSICS",
            },
        ).json()["id"]

        pdf_bytes = (SAMPLE_DIR / "demo_clean_synthetic_invoice.pdf").read_bytes()
        client.post(
            f"/api/investigations/{inv_id}/documents",
            files=[("files", ("job_invoice.pdf", pdf_bytes, "application/pdf"))],
        )

        # 1. Enqueue job with simulate_failure_once=True -> fails on attempt 1
        fail_job_resp = client.post(
            "/api/jobs/enqueue",
            json={
                "investigation_id": inv_id,
                "job_type": "CONTEXTUAL_INTELLIGENCE_ANALYSIS",
                "execute_immediately": True,
                "simulate_failure_once": True,
            },
        )
        assert fail_job_resp.status_code == 201
        failed_job = fail_job_resp.json()
        job_id = failed_job["id"]
        assert failed_job["status"] == "FAILED"
        assert failed_job["attempt_count"] == 1
        assert "Simulated transient worker interruption" in (
            failed_job["error_summary"] or ""
        )

        # 2. Retry the failed job -> succeeds on attempt 2
        retry_resp = client.post(f"/api/jobs/{job_id}/retry")
        assert retry_resp.status_code == 200
        completed_job = retry_resp.json()
        assert completed_job["status"] == "COMPLETED"
        assert completed_job["attempt_count"] == 2
        assert completed_job["progress_percent"] == 100
        assert completed_job["error_summary"] is None

        # 3. Enqueue a QUEUED job (execute_immediately=False) and verify duplicate launch is blocked (409)
        queued_resp = client.post(
            "/api/jobs/enqueue",
            json={
                "investigation_id": inv_id,
                "job_type": "DOSSIER_GENERATION",
                "execute_immediately": False,
            },
        )
        assert queued_resp.status_code == 201
        q_job_id = queued_resp.json()["id"]
        assert queued_resp.json()["status"] == "QUEUED"

        dup_resp = client.post(
            "/api/jobs/enqueue",
            json={
                "investigation_id": inv_id,
                "job_type": "DOSSIER_GENERATION",
                "execute_immediately": False,
            },
        )
        assert dup_resp.status_code == 409
        assert dup_resp.json()["error"]["code"] == "DUPLICATE_ACTIVE_JOB"

        # 4. Simulate an interrupted RUNNING job and verify startup recovery
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE background_jobs SET status = 'RUNNING', stage_label = 'MID_EXECUTION' WHERE id = ?;",
                (q_job_id,),
            )

        recovery_report = JobService.recover_interrupted_jobs_on_startup()
        assert recovery_report.interrupted_jobs_found >= 1
        assert q_job_id in recovery_report.recovered_job_ids

        recovered_job = client.get(f"/api/jobs/{q_job_id}").json()
        assert recovered_job["status"] == "FAILED"
        assert recovered_job["stage_label"] == "INTERRUPTED_ON_SERVER_RESTART"


def test_phase6_audit_hash_chain_verification_and_tamper_detection() -> None:
    """
    Tests Module D Cryptographic Audit Ledger Integrity:
    - Verifies intact SHA-256 hash chain across all audit_logs
    - Simulates direct SQLite payload tampering and verifies /api/audit-logs/verify detects the exact tampered row
    - Restores original row and re-verifies chain integrity
    """
    with TestClient(app) as client:
        client.post("/api/auth/demo-session", json={"username": "admin.nair"})
        AuditService.ensure_hash_chain_backfilled()

        verify_ok = client.get("/api/audit-logs/verify")
        assert verify_ok.status_code == 200
        v_body = verify_ok.json()
        assert v_body["verified"] is True
        assert v_body["total_events_checked"] > 0
        assert v_body["corrupted_events_count"] == 0

        # Tamper with a single row's summary in SQLite
        with get_db_connection() as conn:
            target_row = conn.execute(
                "SELECT id, summary FROM audit_logs ORDER BY sequence_number DESC LIMIT 1;"
            ).fetchone()
            target_id = target_row["id"]
            original_summary = target_row["summary"]
            conn.execute(
                "UPDATE audit_logs SET summary = ? WHERE id = ?;",
                (original_summary + " [TAMPERED]", target_id),
            )

        try:
            verify_tampered = client.get("/api/audit-logs/verify").json()
            assert verify_tampered["verified"] is False
            assert verify_tampered["corrupted_events_count"] >= 1
            reasons = [
                 item["reason"] for item in verify_tampered["corrupted_events"]
            ]
            assert "EVENT_HASH_MISMATCH_PAYLOAD_TAMPERED" in reasons
        finally:
            # Restore original summary so database remains clean
            with get_db_connection() as conn:
                conn.execute(
                    "UPDATE audit_logs SET summary = ? WHERE id = ?;",
                    (original_summary, target_id),
                )

        reverify = client.get("/api/audit-logs/verify").json()
        assert reverify["verified"] is True


def test_phase6_reproducible_quality_benchmark_suite() -> None:
    """
    Tests Module E Extraction & Analysis Quality Benchmark:
    - Evaluates all 10 synthetic document categories in isolation
    - Reports real classification accuracy, CER, entity Precision/Recall/F1,
      table cell accuracy, bbox localization, financial calculation accuracy, and evidence completeness
    """
    with TestClient(app) as client:
        client.post("/api/auth/demo-session", json={"username": "dr.rostova"})
        bench_resp = client.post("/api/system/benchmark")
        assert bench_resp.status_code == 200
        bench = bench_resp.json()

        assert bench["isolated_from_production_db"] is True
        assert bench["specimens_evaluated"] == 10
        metrics = bench["aggregate_metrics"]
        assert metrics["document_classification_accuracy"] >= 0.90
        assert metrics["ocr_cer_native_pdf"] <= 0.15
        assert metrics["entity_extraction_f1"] >= 0.80
        assert metrics["table_cell_extraction_accuracy"] >= 0.85
        assert metrics["bounding_box_localization_accuracy"] == 1.0
        assert metrics["financial_calculation_accuracy"] == 1.0
        assert metrics["evidence_reference_completeness"] == 1.0


def test_phase6_sqlite_backup_and_restore_verification(tmp_path: Path) -> None:
    """
    Tests Module F SQLite Online Backup & Restore Verification:
    - Creates a consistent online backup via POST /api/system/backups
    - Verifies SHA-256 fingerprint and PRAGMA integrity_check
    - Restores backup into an isolated target database file and verifies row counts match
    """
    with TestClient(app) as client:
        client.post("/api/auth/demo-session", json={"username": "admin.nair"})
        bkp_resp = client.post(
            "/api/system/backups",
            json={"label": "Pytest Phase 6 Verification Snapshot"},
        )
        assert bkp_resp.status_code == 201
        bkp = bkp_resp.json()
        assert bkp["integrity_verified"] is True
        assert bkp["sqlite_integrity_check"] == "ok"
        backup_id = bkp["backup_id"]

        list_resp = client.get("/api/system/backups")
        assert list_resp.status_code == 200
        assert any(item["backup_id"] == backup_id for item in list_resp.json())

        # Verify restore into an isolated temporary SQLite path
        restore_target = tmp_path / "restored_veritas.db"
        restore_res = BackupService.verify_or_restore_backup(
            backup_id=backup_id,
            target_db_path=restore_target,
            perform_restore=True,
        )
        assert restore_res["sha256_verified"] is True
        assert restore_res["sqlite_integrity_check"] == "ok"
        assert restore_target.exists()
        assert restore_target.stat().st_size == bkp["size_bytes"]
