import hashlib
from pathlib import Path
from fastapi.testclient import TestClient
from app.core.database import get_db_connection
from app.main import app

SAMPLE_DIR = Path("/Users/mayankchaubey/Desktop/VERITAS-AI/sample-data")


def test_phase3_full_forensics_pipeline_modules_and_immutability() -> None:
    """
    Tests Phase 3 Visual Forensics across:
    - Clean synthetic invoice (PDF)
    - Synthetic invoice with deliberate visual inconsistencies (PDF)
    - Scanned JPEG receipt (JPG — authentic ELA)
    - Lossless PNG receipt (PNG — graceful ELA limitation handling)
    Verifies Modules A, B, C, D, E, F, G, bounding boxes, SHA-256 linkage,
    original file immutability, derived artifacts, human review, and audit logging.
    """
    with TestClient(app) as client:
        client.post("/api/auth/demo-session", json={"username": "dr.rostova"})
        # 1. Create a synthetic demonstration investigation
        inv_resp = client.post(
            "/api/investigations",
            json={
                "title": "SYNTHETIC DEMO — Phase 3 Visual Forensics & Authenticity Evaluation",
                "description": "Synthetic demonstration case containing clean invoice, altered invoice, scanned JPEG receipt, and supporting bank statement.",
                "priority": "CRITICAL",
                "classification": "FINANCIAL_FORENSICS",
                "lead_investigator": "Dr. Elena Rostova (Principal Forensic Analyst)",
            },
        )
        assert inv_resp.status_code == 201
        inv_id = inv_resp.json()["id"]

        clean_pdf_bytes = (SAMPLE_DIR / "demo_clean_synthetic_invoice.pdf").read_bytes()
        inconsistent_pdf_bytes = (
            SAMPLE_DIR / "demo_inconsistent_synthetic_invoice.pdf"
        ).read_bytes()
        jpeg_receipt_bytes = (SAMPLE_DIR / "demo_scanned_escrow_receipt.jpg").read_bytes()
        png_receipt_bytes = (SAMPLE_DIR / "scanned_escrow_receipt.png").read_bytes()

        inconsistent_sha256 = hashlib.sha256(inconsistent_pdf_bytes).hexdigest()
        jpeg_sha256 = hashlib.sha256(jpeg_receipt_bytes).hexdigest()

        # 2. Upload all 4 documents
        upload_resp = client.post(
            f"/api/investigations/{inv_id}/documents",
            files=[
                (
                    "files",
                    ("demo_clean_synthetic_invoice.pdf", clean_pdf_bytes, "application/pdf"),
                ),
                (
                    "files",
                    (
                        "demo_inconsistent_synthetic_invoice.pdf",
                        inconsistent_pdf_bytes,
                        "application/pdf",
                    ),
                ),
                (
                    "files",
                    ("demo_scanned_escrow_receipt.jpg", jpeg_receipt_bytes, "image/jpeg"),
                ),
                (
                    "files",
                    ("scanned_escrow_receipt.png", png_receipt_bytes, "image/png"),
                ),
            ],
            data={"actor": "Dr. Elena Rostova"},
        )
        assert upload_resp.status_code == 201
        docs = {d["filename"]: d for d in upload_resp.json()["documents"]}

        clean_doc_id = docs["demo_clean_synthetic_invoice.pdf"]["id"]
        inc_doc_id = docs["demo_inconsistent_synthetic_invoice.pdf"]["id"]
        jpg_doc_id = docs["demo_scanned_escrow_receipt.jpg"]["id"]
        png_doc_id = docs["scanned_escrow_receipt.png"]["id"]

        # 3. Explicitly trigger POST /api/documents/{id}/forensics/analyze on the inconsistent invoice
        inc_an_resp = client.post(
            f"/api/documents/{inc_doc_id}/forensics/analyze",
            json={
                "actor": "Dr. Elena Rostova",
                "ela_jpeg_quality": 90,
                "ela_amplification_scale": 18.0,
                "force_reanalyze": True,
            },
        )
        assert inc_an_resp.status_code == 200
        inc_analysis = inc_an_resp.json()

        # Verify original document immutability and SHA-256 linkage
        assert inc_analysis["document_sha256"] == inconsistent_sha256
        assert inc_analysis["original_file_intact"] is True
        assert inc_analysis["status"] == "COMPLETED"
        assert len(inc_analysis["modules_executed"]) == 7

        # Verify Module E: PDF Metadata & Object Inspection
        meta = inc_analysis["metadata_inspection"]
        assert meta["is_pdf"] is True
        assert "Desktop PDF Compositor Pro" in meta["creator"]
        assert meta["creation_date_raw"] != meta["modification_date_raw"]
        assert meta["incremental_Save_eof_count"] >= 2
        assert len(meta["embedded_images"]) >= 1
        assert len(meta["font_resources"]) >= 2
        assert len(meta["annotations"]) >= 1

        # Verify findings across Modules A, B, C, D, E, F, G on the inconsistent invoice
        inc_findings = inc_analysis["findings"]
        modules_with_findings = {f["module_name"] for f in inc_findings}
        categories_found = {f["finding_category"] for f in inc_findings}

        assert "MODULE_A_IMAGE_CONSISTENCY" in modules_with_findings
        assert "MODULE_B_ELA" in modules_with_findings
        assert "MODULE_C_TYPOGRAPHY" in modules_with_findings
        assert "MODULE_D_ALIGNMENT" in modules_with_findings
        assert "MODULE_E_PDF_METADATA" in modules_with_findings
        assert "MODULE_F_SIGNATURE_STAMP" in modules_with_findings
        assert "MODULE_G_TEXT_VISUAL" in modules_with_findings

        assert "LOCAL_BACKGROUND_PATCH_DIFFERENCE" in categories_found
        assert "INTRA_LINE_FONT_FAMILY_MISMATCH" in categories_found
        assert "BASELINE_OR_FONTSIZE_DISCONTINUITY" in categories_found
        assert (
            "LEFT_MARGIN_RAIL_MISALIGNMENT" in categories_found
            or "TABLE_OR_COLUMN_CELL_MISALIGNMENT" in categories_found
        )
        assert "PDF_MODIFICATION_OR_INCREMENTAL_SAVE" in categories_found
        assert "PDF_ANNOTATION_LAYER_PRESENT" in categories_found
        assert "OCCLUDED_OR_ZERO_CONTRAST_NATIVE_TEXT" in categories_found

        # Verify every finding contains all required explainable fields and valid coordinates
        valid_severities = {"INFORMATIONAL", "LOW", "MEDIUM", "HIGH"}
        for fnd in inc_findings:
            assert fnd["finding_id"]
            assert fnd["investigation_id"] == inv_id
            assert fnd["document_id"] == inc_doc_id
            assert fnd["document_sha256"] == inconsistent_sha256
            assert fnd["analysis_id"] == inc_analysis["analysis_id"]
            assert fnd["severity"] in valid_severities
            assert len(fnd["observation"]) > 15
            assert len(fnd["technical_explanation"]) > 15
            assert len(fnd["possible_benign_explanations"]) >= 1
            assert 0.0 <= fnd["confidence_score"] <= 1.0
            assert len(fnd["confidence_interpretation"]) > 5
            assert fnd["page_number"] >= 1
            assert fnd["evidence_reference"].startswith(f"doc:{inc_doc_id}")
            assert len(fnd["recommended_human_action"]) > 10

            bb = fnd["bounding_box"]
            if bb is not None:
                assert 0.0 <= bb["x0"] < bb["x1"] <= bb["page_width"] + 1.0
                assert 0.0 <= bb["y0"] < bb["y1"] <= bb["page_height"] + 1.0

        # 4. Verify derived artifacts and GET /api/forensics/artifacts/{artifact_id}
        assert len(inc_analysis["artifacts"]) >= 2
        for art in inc_analysis["artifacts"]:
            art_resp = client.get(f"/api/forensics/artifacts/{art['artifact_id']}")
            assert art_resp.status_code == 200
            assert art_resp.headers["content-type"] == "image/png"
            assert art_resp.content.startswith(b"\x89PNG")

        # 5. Test ELA on supported JPEG input (demo_scanned_escrow_receipt.jpg)
        jpg_an_resp = client.get(f"/api/documents/{jpg_doc_id}/forensics")
        assert jpg_an_resp.status_code == 200
        jpg_analysis = jpg_an_resp.json()
        assert jpg_analysis["document_sha256"] == jpeg_sha256
        assert jpg_analysis["original_file_intact"] is True
        jpg_ela_findings = [
            f for f in jpg_analysis["findings"] if f["module_name"] == "MODULE_B_ELA"
        ]
        assert len(jpg_ela_findings) == 1
        assert (
            jpg_ela_findings[0]["analysis_parameters"]["source_format"]
            == "ORIGINAL_JPEG"
        )
        assert jpg_ela_findings[0]["artifact_id"] is not None

        # 6. Test graceful handling of unsupported ELA format (lossless PNG)
        png_an_resp = client.get(f"/api/documents/{png_doc_id}/forensics")
        assert png_an_resp.status_code == 200
        png_analysis = png_an_resp.json()
        png_ela_findings = [
            f for f in png_analysis["findings"] if f["module_name"] == "MODULE_B_ELA"
        ]
        assert len(png_ela_findings) == 1
        assert (
            png_ela_findings[0]["finding_category"]
            == "ELA_LOSSLESS_FORMAT_LIMITATION"
        )
        assert (
            png_ela_findings[0]["analysis_parameters"]["source_format"]
            == "LOSSLESS_PNG"
        )

        # 7. Compare clean invoice vs inconsistent invoice
        clean_an_resp = client.get(f"/api/documents/{clean_doc_id}/forensics")
        assert clean_an_resp.status_code == 200
        clean_analysis = clean_an_resp.json()
        assert clean_analysis["high_severity_count"] == 0
        assert inc_analysis["high_severity_count"] >= 2

        # 8. Test GET /api/forensics/analyses/{analysis_id} and GET /api/documents/{id}/forensics/findings
        by_id_resp = client.get(
            f"/api/forensics/analyses/{inc_analysis['analysis_id']}"
        )
        assert by_id_resp.status_code == 200
        assert by_id_resp.json()["analysis_id"] == inc_analysis["analysis_id"]

        high_findings_resp = client.get(
            f"/api/documents/{inc_doc_id}/forensics/findings?severity=HIGH"
        )
        assert high_findings_resp.status_code == 200
        assert len(high_findings_resp.json()) == inc_analysis["high_severity_count"]

        # 9. Test Human Review workflow and Audit Logging
        target_finding_id = high_findings_resp.json()[0]["finding_id"]

        # Review 1: Mark as INCONCLUSIVE
        rev1_resp = client.post(
            f"/api/forensics/findings/{target_finding_id}/review",
            json={
                "review_status": "INCONCLUSIVE",
                "reviewer": "Dr. Elena Rostova",
                "notes": "Pending original paper voucher inspection from escrow agent.",
            },
        )
        assert rev1_resp.status_code == 200
        rev1_data = rev1_resp.json()
        assert rev1_data["review_status"] == "INCONCLUSIVE"
        assert "Dr. Elena Rostova" in rev1_data["reviewer"]
        assert len(rev1_data["review_history"]) == 1

        # Review 2: Mark as REVIEWED
        rev2_resp = client.post(
            f"/api/forensics/findings/{target_finding_id}/review",
            json={
                "review_status": "REVIEWED",
                "reviewer": "Dr. Elena Rostova",
                "notes": "Verified typography mismatch against clean baseline invoice INV-2026-8841.",
            },
        )
        assert rev2_resp.status_code == 200
        rev2_data = rev2_resp.json()
        assert rev2_data["review_status"] == "REVIEWED"
        assert len(rev2_data["review_history"]) == 2

        # Verify audit log entries
        audit_resp = client.get(f"/api/audit-logs?investigation_id={inv_id}&limit=100")
        assert audit_resp.status_code == 200
        audit_actions = {entry["action"] for entry in audit_resp.json()}
        assert "FORENSIC_ANALYSIS_STARTED" in audit_actions
        assert "FORENSIC_FINDING_CREATED" in audit_actions
        assert "FORENSIC_ANALYSIS_COMPLETED" in audit_actions
        assert "FORENSIC_FINDING_REVIEWED" in audit_actions

        # Verify database persistence directly in SQLite
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT COUNT(*) AS cnt FROM forensic_analyses WHERE investigation_id = ?;",
                (inv_id,),
            )
            assert c.fetchone()["cnt"] == 4
            c.execute(
                "SELECT COUNT(*) AS cnt FROM forensic_reviews WHERE finding_id = ?;",
                (target_finding_id,),
            )
            assert c.fetchone()["cnt"] == 2


def test_phase3_api_error_handling() -> None:
    """Verifies structured error handling on non-existent IDs and invalid review dispositions."""
    with TestClient(app) as client:
        client.post("/api/auth/demo-session", json={"username": "dr.rostova"})
        r1 = client.get("/api/documents/non-existent-doc-id/forensics")
        assert r1.status_code == 404

        r2 = client.get("/api/forensics/analyses/non-existent-analysis-id")
        assert r2.status_code == 404

        r3 = client.get("/api/forensics/findings/non-existent-finding-id")
        assert r3.status_code == 404

        r4 = client.get("/api/forensics/artifacts/non-existent-artifact-id")
        assert r4.status_code == 404

        # Invalid review status returns 400
        with get_db_connection() as conn:
            row = conn.execute("SELECT id FROM forensic_findings LIMIT 1;").fetchone()
        if row:
            r5 = client.post(
                f"/api/forensics/findings/{row['id']}/review",
                json={
                    "review_status": "DECLARED_FRAUDULENT",
                    "reviewer": "Analyst",
                    "notes": "Invalid disposition test",
                },
            )
            assert r5.status_code == 400
