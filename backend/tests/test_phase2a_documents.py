import hashlib
from pathlib import Path
from fastapi.testclient import TestClient
from app.core.database import init_db
from app.main import app
from app.services.auth_service import AuthService

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "sample-data"

init_db()
AuthService.ensure_demo_personas()
client = TestClient(app)
client.post("/api/auth/demo-session", json={"username": "dr.rostova"})


def test_health_and_phase1_preservation() -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["database"]["connected"] is True
    assert body["database"]["schema_version"] == "2.0.0-phase6"


def test_multi_document_upload_dual_path_extraction_and_persistence() -> None:
    inv_resp = client.post(
        "/api/investigations",
        json={
            "title": "Phase 2A Dual-Path Extraction Verification Case",
            "description": "Automated pytest verification of Native PDF (Path A) and Visual OCR (Path B) ingestion.",
            "priority": "CRITICAL",
            "classification": "FINANCIAL_FORENSICS",
            "lead_investigator": "Automated Verification Suite",
        },
    )
    assert inv_resp.status_code == 201
    inv_id = inv_resp.json()["id"]

    try:
        native_pdf_path = SAMPLE_DIR / "sovereign_vendor_invoice_native.pdf"
        scanned_png_path = SAMPLE_DIR / "scanned_escrow_receipt.png"

        pdf_bytes = native_pdf_path.read_bytes()
        png_bytes = scanned_png_path.read_bytes()

        expected_pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        expected_png_sha256 = hashlib.sha256(png_bytes).hexdigest()

        upload_resp = client.post(
            f"/api/investigations/{inv_id}/documents",
            files=[
                (
                    "files",
                    (
                        "sovereign_vendor_invoice_native.pdf",
                        pdf_bytes,
                        "application/pdf",
                    ),
                ),
                (
                    "files",
                    ("scanned_escrow_receipt.png", png_bytes, "image/png"),
                ),
            ],
            data={"actor": "Pytest Forensic Runner"},
        )
        assert upload_resp.status_code == 201, upload_resp.text
        upload_data = upload_resp.json()
        assert upload_data["uploaded_count"] == 2
        docs = upload_data["documents"]
        assert len(docs) == 2

        pdf_doc = next(d for d in docs if d["file_type"] == "PDF")
        png_doc = next(d for d in docs if d["file_type"] == "PNG")

        # Verify SHA-256 fingerprints
        assert pdf_doc["sha256_hash"] == expected_pdf_sha256
        assert png_doc["sha256_hash"] == expected_png_sha256

        # Verify Path A (Native PDF) vs Path B (Visual OCR)
        assert pdf_doc["processing_status"] == "COMPLETED"
        assert pdf_doc["extraction_method_summary"] == "NATIVE_PDF"
        assert pdf_doc["is_scanned"] is False
        assert pdf_doc["page_count"] == 2
        assert pdf_doc["average_confidence"] == 1.0

        assert png_doc["processing_status"] == "COMPLETED"
        assert png_doc["extraction_method_summary"] == "VISUAL_OCR"
        assert png_doc["is_scanned"] is True
        assert png_doc["page_count"] == 1
        assert 0.80 <= png_doc["average_confidence"] <= 1.0

        # Verify GET /api/investigations/{id}/documents
        list_resp = client.get(f"/api/investigations/{inv_id}/documents")
        assert list_resp.status_code == 200
        listed_ids = {d["id"] for d in list_resp.json()}
        assert pdf_doc["id"] in listed_ids
        assert png_doc["id"] in listed_ids

        # Verify GET /api/documents/{id} for Native PDF
        pdf_detail_resp = client.get(f"/api/documents/{pdf_doc['id']}")
        assert pdf_detail_resp.status_code == 200
        pdf_detail = pdf_detail_resp.json()
        assert len(pdf_detail["pages"]) == 2
        assert len(pdf_detail["pages"][0]["fonts"]) > 0
        assert any(
            f["field_name"] == "INVOICE_NUMBER"
            and f["field_value"] == "INV-2026-9941"
            for f in pdf_detail["structured_fields"]
        )

        # Verify GET /api/documents/{id}/extraction for Scanned PNG (OCR)
        png_ext_resp = client.get(f"/api/documents/{png_doc['id']}/extraction")
        assert png_ext_resp.status_code == 200
        png_ext = png_ext_resp.json()
        assert png_ext["extraction_method_summary"] == "VISUAL_OCR"
        assert png_ext["total_blocks"] >= 5
        assert "INV-2026-9941" in png_ext["full_text"]
        for block in png_ext["extractions"]:
            assert block["extraction_method"] == "VISUAL_OCR"
            assert block["bounding_box"]["x1"] > block["bounding_box"]["x0"]
            assert block["bounding_box"]["y1"] > block["bounding_box"]["y0"]
            assert block["source_reference"].startswith(
                f"doc:{png_doc['id']}#page:1@bbox:"
            )

        # Verify GET /api/documents/{id}/pages/{page_number}
        page2_resp = client.get(f"/api/documents/{pdf_doc['id']}/pages/2")
        assert page2_resp.status_code == 200
        page2_data = page2_resp.json()
        assert page2_data["page_number"] == 2
        assert page2_data["extraction_method"] == "NATIVE_PDF"
        assert "PO-2026-4410" in page2_data["raw_text"]
    finally:
        client.delete(f"/api/investigations/{inv_id}")


def test_rejects_spoofed_magic_signature() -> None:
    inv_resp = client.post(
        "/api/investigations",
        json={
            "title": "Signature Validation Test Case",
            "description": "Verify spoofed files are rejected.",
            "priority": "LOW",
            "classification": "GENERAL_FORENSICS",
            "lead_investigator": "Security Validator",
        },
    )
    inv_id = inv_resp.json()["id"]
    try:
        spoofed_bytes = b"NOT_A_REAL_PDF_HEADER_1234567890"
        bad_resp = client.post(
            f"/api/investigations/{inv_id}/documents",
            files=[
                ("files", ("fake_document.pdf", spoofed_bytes, "application/pdf"))
            ],
        )
        assert bad_resp.status_code == 400
        err = bad_resp.json()
        assert err["error"]["code"] == "INVALID_FILE_SIGNATURE"
    finally:
        client.delete(f"/api/investigations/{inv_id}")


def test_scanned_pdf_automatic_ocr_routing() -> None:
    inv_resp = client.post(
        "/api/investigations",
        json={
            "title": "Scanned PDF Auto-Routing Verification Case",
            "description": "Verify PDF with zero vector text is routed to Path B Visual OCR.",
            "priority": "MEDIUM",
            "classification": "CONTRACT_INTEGRITY",
            "lead_investigator": "Automated Verification Suite",
        },
    )
    inv_id = inv_resp.json()["id"]
    try:
        scanned_pdf_bytes = (
            SAMPLE_DIR / "scanned_contract_addendum.pdf"
        ).read_bytes()
        up_resp = client.post(
            f"/api/investigations/{inv_id}/documents",
            files=[
                (
                    "files",
                    (
                        "scanned_contract_addendum.pdf",
                        scanned_pdf_bytes,
                        "application/pdf",
                    ),
                )
            ],
        )
        assert up_resp.status_code == 201
        doc_item = up_resp.json()["documents"][0]
        assert doc_item["file_type"] == "PDF"
        assert doc_item["is_scanned"] is True
        assert doc_item["extraction_method_summary"] == "VISUAL_OCR"
        assert doc_item["extracted_char_count"] > 100
    finally:
        client.delete(f"/api/investigations/{inv_id}")
