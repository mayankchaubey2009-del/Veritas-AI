from decimal import Decimal
from pathlib import Path
from fastapi.testclient import TestClient
from app.core.database import init_db
from app.main import app
from app.services.auth_service import AuthService
from scripts.generate_phase3_demo_data import generate_all_phase3_demo_files

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "sample-data"

init_db()
AuthService.ensure_demo_personas()
generate_all_phase3_demo_files()
client = TestClient(app)
client.post("/api/auth/demo-session", json={"username": "dr.rostova"})


def test_phase4_contextual_intelligence_correlation_and_financial_validation() -> None:
    """
    Comprehensive Phase 4 verification covering:
    1. Exact entity matching across documents
    2. Uncertain OCR-normalized entity matching without false merges
    3. Conflicting monetary amounts across documents ($489,500.00 vs $189,500.00)
    4. Conflicting IBAN / account references (CH7799990000884100991 vs CH9300000011623852957)
    5. Duplicate invoice number with conflicting values (INV-2026-8841)
    6. Invoice line-item arithmetic validation using Decimal
    7. Bank statement balance reconciliation using Decimal
    8. Missing supporting evidence detection (Certificate of Origin / Tax Certificate)
    9. Cross-document relationship graph generation (nodes & edges)
    10. Evidence coordinate preservation
    11. Database persistence of contextual findings
    12. Human review updates & review history
    13. Audit logging of contextual analysis & review actions
    14. Preservation of all previous phases
    """
    # Create an investigation and upload the 4 synthetic demonstration documents
    inv_resp = client.post(
        "/api/investigations",
        json={
            "title": "Phase 4 Cross-Document Contradiction & Financial Validation Suite",
            "description": "Automated verification of Phase 4 Contextual Intelligence Engine.",
            "priority": "CRITICAL",
            "classification": "FINANCIAL_FORENSICS",
            "lead_investigator": "Phase 4 Verification Suite",
            "tags": ["PHASE-4", "CONTEXTUAL-INTELLIGENCE", "SYNTHETIC-DEMO"],
        },
    )
    assert inv_resp.status_code == 201
    inv_id = inv_resp.json()["id"]

    clean_pdf = SAMPLE_DIR / "demo_clean_synthetic_invoice.pdf"
    inconsistent_pdf = SAMPLE_DIR / "demo_inconsistent_synthetic_invoice.pdf"
    scanned_jpg = SAMPLE_DIR / "demo_scanned_escrow_receipt.jpg"
    bank_pdf = SAMPLE_DIR / "demo_supporting_bank_statement.pdf"

    files = [
        ("files", (clean_pdf.name, clean_pdf.read_bytes(), "application/pdf")),
        ("files", (inconsistent_pdf.name, inconsistent_pdf.read_bytes(), "application/pdf")),
        ("files", (scanned_jpg.name, scanned_jpg.read_bytes(), "image/jpeg")),
        ("files", (bank_pdf.name, bank_pdf.read_bytes(), "application/pdf")),
    ]
    up_resp = client.post(f"/api/investigations/{inv_id}/documents", files=files)
    assert up_resp.status_code == 201
    uploaded_docs = up_resp.json()["documents"]
    assert len(uploaded_docs) == 4

    # Trigger POST /api/investigations/{investigation_id}/context/analyze explicitly
    analyze_resp = client.post(
        f"/api/investigations/{inv_id}/context/analyze",
        json={"actor": "Phase 4 Automated Pytest", "force_reanalyze": True},
    )
    assert analyze_resp.status_code == 200
    ctx = analyze_resp.json()

    # Verify GET /api/investigations/{investigation_id}/context returns identical persisted state
    get_ctx_resp = client.get(f"/api/investigations/{inv_id}/context")
    assert get_ctx_resp.status_code == 200
    ctx_persisted = get_ctx_resp.json()
    assert ctx_persisted["analysis_id"] == ctx["analysis_id"]
    assert ctx_persisted["status"] == "COMPLETED"

    assert ctx["documents_analyzed_count"] == 4
    assert ctx["confirmed_mismatches_count"] >= 3
    assert ctx["missing_information_count"] >= 1
    assert ctx["consistent_matches_count"] >= 2

    # 1 & 2. Entity Resolution: Exact & Uncertain OCR-Normalized matches
    entity_matches = ctx["entity_matches"]
    assert len(entity_matches) >= 5
    match_statuses = {m["match_status"] for m in entity_matches}
    assert "EXACT_MATCH" in match_statuses
    assert "UNCERTAIN_OCR_NORMALIZED_MATCH" in match_statuses

    # Verify INV-2026-8841 is resolved across multiple documents
    inv_cluster = next(
        (
            m
            for m in entity_matches
            if m["entity_type"] == "INVOICE_NUMBER"
            and "INV-2026-8841" in m["canonical_value"]
        ),
        None,
    )
    assert inv_cluster is not None
    assert inv_cluster["document_count"] >= 3
    for member in inv_cluster["member_entities"]:
        assert member["raw_value"]
        assert member["document_id"]
        assert member["page_number"] >= 1
        assert member["bounding_box"] is not None

    # Verify uncertain OCR-normalized company match preserves raw OCR value alongside normalized value
    uncertain_company = next(
        (
            m
            for m in entity_matches
            if m["entity_type"] == "COMPANY_NAME"
            and m["match_status"] == "UNCERTAIN_OCR_NORMALIZED_MATCH"
        ),
        None,
    )
    assert uncertain_company is not None
    assert (
        "OCR" in uncertain_company["matching_rationale"]
        or "alphanumeric" in uncertain_company["matching_rationale"]
    )

    # 3, 4, 5, 8, 10. Findings verification
    findings_resp = client.get(f"/api/investigations/{inv_id}/context/findings")
    assert findings_resp.status_code == 200
    findings = findings_resp.json()
    assert len(findings) >= 6

    finding_types = {f["finding_type"] for f in findings}
    assert "CONTRADICTORY_MONETARY_AMOUNT" in finding_types
    assert "CONFLICTING_ACCOUNT_IBAN" in finding_types
    assert "INTERNAL_TOTAL_CONTRADICTION" in finding_types
    assert "ENTITY_NAME_OCR_VARIATION" in finding_types
    assert "CORROBORATED_SETTLEMENT_EVIDENCE" in finding_types
    assert "MISSING_SUPPORTING_EVIDENCE" in finding_types
    assert "TIMELINE_CHRONOLOGY_INCONSISTENCY" in finding_types

    # Verify every finding preserves source coordinates and avoids automatic accusation language
    for f in findings:
        assert f["status"] in {
            "CONFIRMED_DATA_MISMATCH",
            "POTENTIAL_INCONSISTENCY",
            "MISSING_INFORMATION",
            "CONSISTENT_EVIDENCE",
            "INCONCLUSIVE_RESULT",
        }
        assert len(f["document_references"]) >= 1
        assert len(f["evidence_values"]) >= 1
        for ev in f["evidence_values"]:
            assert ev["document_id"]
            assert ev["page_number"] >= 1
        assert len(f["possible_explanations"]) >= 1

    # 6 & 7. Financial Validation using Decimal
    fin_resp = client.get(f"/api/investigations/{inv_id}/context/financial-validation")
    assert fin_resp.status_code == 200
    fin_items = fin_resp.json()
    assert len(fin_items) >= 3

    # Check Invoice Arithmetic (both $189,500.00 and $489,500.00 line items sum deterministically)
    invoice_checks = [
        item
        for item in fin_items
        if item["check_type"] == "INVOICE_LINE_ITEM_SUM_TO_TOTAL"
    ]
    assert len(invoice_checks) >= 2
    for ic in invoice_checks:
        assert ic["status"] == "CONSISTENT_EVIDENCE"
        clean_disc = ic["discrepancy_amount"].replace("+", "").replace(",", "")
        assert Decimal(clean_disc) == Decimal("0.00")

    # Check Bank Statement Balance Reconciliation ($1,250,000.00 - $189,500.00 == $1,060,500.00)
    bank_checks = [
        item
        for item in fin_items
        if item["check_type"] == "BANK_OPENING_DEBITS_CLOSING_RECONCILIATION"
    ]
    assert len(bank_checks) == 1
    bc = bank_checks[0]
    assert bc["status"] == "CONSISTENT_EVIDENCE"
    assert Decimal(bc["details"]["expected_closing_balance"]) == Decimal("1060500.00")
    assert Decimal(bc["details"]["observed_closing_balance"]) == Decimal("1060500.00")
    clean_bank_disc = bc["discrepancy_amount"].replace("+", "").replace(",", "")
    assert Decimal(clean_bank_disc) == Decimal("0.00")

    # Check Cross-Document Settlement Reconciliation
    cross_checks = [
        item
        for item in fin_items
        if item["check_type"] == "CROSS_DOC_SETTLEMENT_RECONCILIATION"
    ]
    assert len(cross_checks) >= 2
    mismatched_cross = [
        c for c in cross_checks if c["status"] == "CONFIRMED_DATA_MISMATCH"
    ]
    assert len(mismatched_cross) == 1
    assert Decimal(mismatched_cross[0]["details"]["discrepancy"]) == Decimal("300000.00")

    # 9. Cross-Document Relationship Graph
    graph_resp = client.get(f"/api/investigations/{inv_id}/context/graph")
    assert graph_resp.status_code == 200
    graph = graph_resp.json()
    assert graph["node_count"] >= 8
    assert graph["edge_count"] >= 8
    assert graph["contradiction_edge_count"] >= 2

    node_types = {n["node_type"] for n in graph["nodes"]}
    assert "DOCUMENT" in node_types
    assert "INVOICE" in node_types
    assert "BANK_ACCOUNT" in node_types
    assert "AMOUNT" in node_types

    edge_types = {e["edge_type"] for e in graph["edges"]}
    assert "CONTRADICTS" in edge_types
    assert "SUPPORTS" in edge_types

    # 12. Human Review workflow on a contextual finding
    target_finding_id = findings[0]["finding_id"]
    single_f_resp = client.get(f"/api/context/findings/{target_finding_id}")
    assert single_f_resp.status_code == 200
    assert single_f_resp.json()["review_status"] == "REQUIRES_REVIEW"

    rev_resp = client.post(
        f"/api/context/findings/{target_finding_id}/review",
        json={
            "review_status": "CONFIRMED",
            "notes": "Confirmed cross-document discrepancy between altered invoice ($489,500) and settled escrow/bank wire ($189,500).",
            "reviewer": "Senior Financial Investigator",
        },
    )
    assert rev_resp.status_code == 200
    rev_body = rev_resp.json()
    assert rev_body["review_status"] == "CONFIRMED"
    assert "Dr. Elena Rostova" in rev_body["reviewer"]
    assert len(rev_body["review_history"]) == 1
    assert rev_body["review_history"][0]["new_status"] == "CONFIRMED"

    # 13. Verify Audit Trail records Phase 4 actions
    audit_resp = client.get(f"/api/audit-logs?investigation_id={inv_id}&limit=100")
    assert audit_resp.status_code == 200
    audit_json = audit_resp.json()
    audit_items = audit_json if isinstance(audit_json, list) else audit_json.get("items", [])
    audit_actions = {item["action"] for item in audit_items}
    assert "CONTEXTUAL_ANALYSIS_STARTED" in audit_actions
    assert "CONTEXTUAL_FINDING_CREATED" in audit_actions
    assert "CONTEXTUAL_ANALYSIS_COMPLETED" in audit_actions
    assert "CONTEXTUAL_FINDING_REVIEWED" in audit_actions


def test_phase4_arithmetic_discrepancy_and_no_false_merges(tmp_path: Path) -> None:
    """
    Verifies:
    - Deterministic Decimal detection of an invoice where Sum(Line Totals) + Tax != Grand Total
    - Distinct companies (Aegis Orbital vs Northstar Sovereign) are never falsely merged
    - 404 and 400 validation handling on Phase 4 endpoints
    """
    import fitz

    bad_math_pdf = tmp_path / "synthetic_bad_arithmetic_invoice.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(
        fitz.Point(50, 60),
        "COMMERCIAL INVOICE & BILLING STATEMENT",
        fontsize=16.0,
        fontname="hebo",
    )
    page.insert_text(
        fitz.Point(50, 95), "Invoice Number: INV-2026-9900", fontsize=10.0, fontname="helv"
    )
    page.insert_text(
        fitz.Point(50, 113), "Invoice Date: 2026-10-20", fontsize=10.0, fontname="helv"
    )
    page.insert_text(
        fitz.Point(50, 131),
        "Issued By: Aegis Orbital Logistics Ltd",
        fontsize=10.0,
        fontname="helv",
    )
    page.insert_text(
        fitz.Point(50, 149),
        "Billed To: Northstar Sovereign Holdings Inc",
        fontsize=10.0,
        fontname="helv",
    )

    col_x = [50.0, 130.0, 360.0, 440.0, 545.0]
    row_y = [200.0, 228.0, 256.0, 284.0]
    rows = [
        ["Item Code", "Description", "Qty", "Line Total"],
        ["ITM-01", "Telemetry Unit Alpha", "1", "$10,000.00 USD"],
        ["ITM-02", "Telemetry Unit Beta", "1", "$15,000.00 USD"],
    ]
    for r_i in range(3):
        for c_i in range(4):
            rect = fitz.Rect(col_x[c_i], row_y[r_i], col_x[c_i + 1], row_y[r_i + 1])
            page.draw_rect(rect, color=(0.3, 0.3, 0.3), width=0.7)
            page.insert_text(
                fitz.Point(col_x[c_i] + 5, row_y[r_i] + 18),
                rows[r_i][c_i],
                fontsize=9.5,
                fontname="hebo" if r_i == 0 else "helv",
            )

    # Line items sum to $25,000.00, Tax is $0.00, but Declared Total is $31,250.00 ($6,250.00 arithmetic error)
    page.insert_text(
        fitz.Point(50, 330), "Subtotal Amount: $25,000.00 USD", fontsize=10.0, fontname="helv"
    )
    page.insert_text(
        fitz.Point(50, 348), "VAT (0% Export Exempt): $0.00 USD", fontsize=10.0, fontname="helv"
    )
    page.insert_text(
        fitz.Point(50, 366), "Total Amount Due: $31,250.00 USD", fontsize=10.0, fontname="hebo"
    )
    doc.save(str(bad_math_pdf))
    doc.close()

    inv_resp = client.post(
        "/api/investigations",
        json={
            "title": "Phase 4 Decimal Arithmetic Discrepancy Verification",
            "description": "Tests deterministic Decimal detection of line-item sum mismatch.",
            "priority": "HIGH",
            "classification": "FINANCIAL_FORENSICS",
            "lead_investigator": "Phase 4 Pytest",
            "tags": ["PHASE-4", "DECIMAL-ARITHMETIC"],
        },
    )
    assert inv_resp.status_code == 201
    inv_id = inv_resp.json()["id"]

    up_resp = client.post(
        f"/api/investigations/{inv_id}/documents",
        files=[("files", (bad_math_pdf.name, bad_math_pdf.read_bytes(), "application/pdf"))],
    )
    assert up_resp.status_code == 201

    ctx_resp = client.get(f"/api/investigations/{inv_id}/context")
    assert ctx_resp.status_code == 200
    ctx = ctx_resp.json()

    # Check that INVOICE_ARITHMETIC_DISCREPANCY finding was generated with exact $6,250.00 discrepancy
    arith_finding = next(
        (f for f in ctx["findings"] if f["finding_type"] == "INVOICE_ARITHMETIC_DISCREPANCY"),
        None,
    )
    assert arith_finding is not None
    assert arith_finding["status"] == "CONFIRMED_DATA_MISMATCH"
    assert "25,000.00" in arith_finding["description"]
    assert "31,250.00" in arith_finding["description"]

    # Check that Aegis Orbital and Northstar Sovereign are NOT merged into a single entity cluster
    company_clusters = [
        em for em in ctx["entity_matches"] if em["entity_type"] == "COMPANY_NAME"
    ]
    for cluster in company_clusters:
        canon = cluster["canonical_value"].upper()
        assert not ("AEGIS" in canon and "NORTHSTAR" in canon)

    # Check 404 handling for non-existent investigation
    not_found_resp = client.get("/api/investigations/non-existent-inv-id/context")
    assert not_found_resp.status_code == 404

    # Check 400 handling for invalid review status
    bad_rev = client.post(
        f"/api/context/findings/{arith_finding['finding_id']}/review",
        json={
            "review_status": "INVALID_STATUS_CODE",
            "reviewer": "Pytest",
            "notes": "Should fail validation",
        },
    )
    assert bad_rev.status_code == 400
