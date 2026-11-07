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


def test_phase2b_classification_layout_tables_entities_and_coordinates() -> None:
    inv_resp = client.post(
        "/api/investigations",
        json={
            "title": "Phase 2B Structure Intelligence Verification Case",
            "description": "Tests classification, layout tree, table cells, entity normalization, and coordinates.",
            "priority": "CRITICAL",
            "classification": "FINANCIAL_FORENSICS",
            "lead_investigator": "Phase 2B Pytest Suite",
        },
    )
    assert inv_resp.status_code == 201
    inv_id = inv_resp.json()["id"]

    try:
        invoice_bytes = (
            SAMPLE_DIR / "sovereign_vendor_invoice_native.pdf"
        ).read_bytes()
        bank_bytes = (SAMPLE_DIR / "meridian_bank_statement.pdf").read_bytes()
        receipt_bytes = (SAMPLE_DIR / "scanned_escrow_receipt.png").read_bytes()

        up_resp = client.post(
            f"/api/investigations/{inv_id}/documents",
            files=[
                (
                    "files",
                    (
                        "sovereign_vendor_invoice_native.pdf",
                        invoice_bytes,
                        "application/pdf",
                    ),
                ),
                (
                    "files",
                    (
                        "meridian_bank_statement.pdf",
                        bank_bytes,
                        "application/pdf",
                    ),
                ),
                (
                    "files",
                    (
                        "scanned_escrow_receipt.png",
                        receipt_bytes,
                        "image/png",
                    ),
                ),
            ],
        )
        assert up_resp.status_code == 201, up_resp.text
        docs = {d["filename"]: d for d in up_resp.json()["documents"]}

        # 1. Verify Commercial Invoice Classification, Layout, Table & Entities
        inv_doc = docs["sovereign_vendor_invoice_native.pdf"]
        assert inv_doc["document_type"] == "COMMERCIAL_INVOICE"
        assert inv_doc["classification_confidence"] >= 0.85
        assert inv_doc["classification_is_certain"] is True
        assert inv_doc["layout_region_count"] >= 10
        assert inv_doc["table_count"] >= 1
        assert inv_doc["entity_count"] >= 10

        inv_detail_resp = client.get(f"/api/documents/{inv_doc['id']}")
        assert inv_detail_resp.status_code == 200
        inv_detail = inv_detail_resp.json()

        # Verify Layout Regions preserve coordinates and expected types
        region_types = {r["region_type"] for r in inv_detail["layout_regions"]}
        assert "DOCUMENT_TITLE" in region_types
        assert "KEY_VALUE_REGION" in region_types
        assert "TABLE" in region_types
        assert "STAMP_REGION" in region_types
        assert "SECTION_HEADING" in region_types
        assert "SIGNATURE_REGION" in region_types
        assert "FOOTER" in region_types

        for reg in inv_detail["layout_regions"]:
            bb = reg["bounding_box"]
            assert bb["x1"] > bb["x0"]
            assert bb["y1"] > bb["y0"]
            assert bb["page_width"] > 0 and bb["page_height"] > 0

        # Verify Table Extraction & Cell Coordinates
        assert len(inv_detail["tables"]) >= 1
        tbl = inv_detail["tables"][0]
        assert tbl["table_identifier"] == "TBL-P1-01"
        assert tbl["row_count"] == 3
        assert tbl["column_count"] == 4
        assert tbl["headers"] == [
            "Item Code",
            "Line Item Description",
            "Qty",
            "Amount",
        ]
        assert len(tbl["cells"]) == 12
        for cell in tbl["cells"]:
            cbb = cell["bounding_box"]
            assert cbb["x1"] > cbb["x0"]
            assert cbb["y1"] > cbb["y0"]

        # Verify Entity Extraction (raw_value + normalized_value + coordinates)
        entities = inv_detail["entities"]
        entity_types = {e["entity_type"] for e in entities}
        assert "PERSON_NAME" in entity_types
        assert "COMPANY_NAME" in entity_types
        assert "INVOICE_NUMBER" in entity_types
        assert "TAX_IDENTIFIER" in entity_types
        assert "DATE" in entity_types
        assert "MONETARY_AMOUNT" in entity_types
        assert "ACCOUNT_REFERENCE" in entity_types
        assert "ADDRESS" in entity_types

        person_ent = next(
            e for e in entities if e["entity_type"] == "PERSON_NAME"
        )
        assert person_ent["raw_value"] == "Dr. Viktor Kestrel"
        assert person_ent["normalized_value"] == "VIKTOR KESTREL"
        assert person_ent["bounding_box"]["x1"] > person_ent["bounding_box"]["x0"]

        # 2. Verify Bank Statement Classification & Table
        bank_doc = docs["meridian_bank_statement.pdf"]
        assert bank_doc["document_type"] == "BANK_STATEMENT"
        assert bank_doc["classification_is_certain"] is True
        assert bank_doc["table_count"] == 1

        # 3. Verify Scanned Receipt (Path B OCR) Classification & Preview Endpoint
        rcpt_doc = docs["scanned_escrow_receipt.png"]
        assert rcpt_doc["document_type"] == "RECEIPT"
        assert rcpt_doc["extraction_method_summary"] == "VISUAL_OCR"

        preview_resp = client.get(
            f"/api/documents/{inv_doc['id']}/pages/1/preview"
        )
        assert preview_resp.status_code == 200
        assert preview_resp.headers["content-type"] == "image/png"
        assert preview_resp.content.startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        client.delete(f"/api/investigations/{inv_id}")


def test_phase2b_low_confidence_unclassified_handling() -> None:
    inv_resp = client.post(
        "/api/investigations",
        json={
            "title": "Low Confidence Classification Test Case",
            "description": "Verifies ambiguous documents do not claim certainty.",
            "priority": "LOW",
            "classification": "GENERAL_FORENSICS",
            "lead_investigator": "Phase 2B Pytest Suite",
        },
    )
    inv_id = inv_resp.json()["id"]

    try:
        ambig_bytes = (SAMPLE_DIR / "ambiguous_memo_note.pdf").read_bytes()
        up_resp = client.post(
            f"/api/investigations/{inv_id}/documents",
            files=[
                (
                    "files",
                    ("ambiguous_memo_note.pdf", ambig_bytes, "application/pdf"),
                )
            ],
        )
        assert up_resp.status_code == 201
        doc_summary = up_resp.json()["documents"][0]

        assert doc_summary["document_type"] == "OTHER_UNKNOWN"
        assert doc_summary["classification_is_certain"] is False
        assert doc_summary["classification_confidence"] < 0.50

        detail_resp = client.get(f"/api/documents/{doc_summary['id']}")
        assert detail_resp.status_code == 200
        cls_info = detail_resp.json()["classification"]
        assert cls_info["is_certain"] is False
        assert "Manual Analyst Review Required" in cls_info["status_label"]
    finally:
        client.delete(f"/api/investigations/{inv_id}")
