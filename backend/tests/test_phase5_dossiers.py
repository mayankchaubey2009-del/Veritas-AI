import hashlib
import json
from pathlib import Path
import fitz
from fastapi.testclient import TestClient
from app.core.database import init_db
from app.main import app
from app.models.entities import ReasoningClaimType
from app.schemas.dossier import (
    DossierReviewRequest,
    EvidenceManifestItemSchema,
    ReasoningGenerateRequest,
)
from app.services.auth_service import AuthService
from app.services.dossier_service import DossierService
from app.services.investigation_reasoning_engine import InvestigationReasoningEngine
from scripts.generate_phase3_demo_data import generate_all_phase3_demo_files

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "sample-data"

init_db()
AuthService.ensure_demo_personas()
generate_all_phase3_demo_files()
client = TestClient(app)
client.post("/api/auth/demo-session", json={"username": "dr.rostova"})


def test_phase5_strict_claim_validation_and_unsupported_rejection() -> None:
    """
    Tests Section 4 & Section 12:
    - Evidence-reference validation
    - Unsupported AI claim rejection (no evidence IDs, fabricated evidence IDs, invalid document IDs)
    - Prohibition on converting unconfirmed automated findings into HUMAN_CONFIRMED_CONCLUSION
    - Prohibition on accusatory fraud/guilt claims
    """
    manifest = {
        "EVID-DOC-001": EvidenceManifestItemSchema(
            evidence_id="EVID-DOC-001",
            source_type="DOCUMENT",
            source_record_id="doc-1",
            document_id="doc-1",
            filename="demo_clean_synthetic_invoice.pdf",
            document_sha256="abc1234567890",
            page_number=1,
            summary="Clean invoice",
            review_status="REVIEWED",
        ),
        "EVID-CTX-001": EvidenceManifestItemSchema(
            evidence_id="EVID-CTX-001",
            source_type="CONTEXTUAL_FINDING",
            source_record_id="ctx-1",
            document_id="doc-1",
            filename="demo_clean_synthetic_invoice.pdf",
            document_sha256="abc1234567890",
            page_number=1,
            summary="Unreviewed contradiction finding",
            review_status="REQUIRES_REVIEW",
        ),
        "EVID-CTX-002": EvidenceManifestItemSchema(
            evidence_id="EVID-CTX-002",
            source_type="CONTEXTUAL_FINDING",
            source_record_id="ctx-2",
            document_id="doc-1",
            filename="demo_clean_synthetic_invoice.pdf",
            document_sha256="abc1234567890",
            page_number=1,
            summary="Human-confirmed contradiction finding",
            review_status="CONFIRMED",
        ),
    }
    valid_doc_ids = {"doc-1"}

    candidates = [
        # 1. Valid claim grounded in EVID-DOC-001
        {
            "section_key": "C_DOCUMENTS_EXAMINED",
            "claim_text": "Document demo_clean_synthetic_invoice.pdf was examined on page 1.",
            "claim_type": ReasoningClaimType.DIRECTLY_OBSERVED_FACT.value,
            "supporting_evidence_ids": ["EVID-DOC-001"],
            "contradicting_evidence_ids": [],
            "document_ids": ["doc-1"],
        },
        # 2. Valid HUMAN_CONFIRMED_CONCLUSION grounded in EVID-CTX-002 (which has review_status=='CONFIRMED')
        {
            "section_key": "F_POTENTIAL_CONTRADICTIONS",
            "claim_text": "Human review confirmed the cross-document discrepancy in EVID-CTX-002.",
            "claim_type": ReasoningClaimType.HUMAN_CONFIRMED_CONCLUSION.value,
            "supporting_evidence_ids": ["EVID-CTX-002"],
            "contradicting_evidence_ids": [],
            "document_ids": ["doc-1"],
        },
        # 3. REJECT: No evidence references at all
        {
            "section_key": "D_KEY_OBSERVATIONS",
            "claim_text": "Unsupported AI hallucination without any evidence IDs.",
            "claim_type": ReasoningClaimType.POTENTIAL_INTERPRETATION.value,
            "supporting_evidence_ids": [],
            "contradicting_evidence_ids": [],
        },
        # 4. REJECT: Fabricated evidence ID not in manifest
        {
            "section_key": "D_KEY_OBSERVATIONS",
            "claim_text": "Claim citing a non-existent evidence ID EVID-FAKE-999.",
            "claim_type": ReasoningClaimType.AUTOMATED_TECHNICAL_OBSERVATION.value,
            "supporting_evidence_ids": ["EVID-FAKE-999"],
            "contradicting_evidence_ids": [],
        },
        # 5. REJECT: Unconfirmed automated finding promoted to HUMAN_CONFIRMED_CONCLUSION
        {
            "section_key": "F_POTENTIAL_CONTRADICTIONS",
            "claim_text": "Automated finding EVID-CTX-001 is a human-confirmed conclusion.",
            "claim_type": ReasoningClaimType.HUMAN_CONFIRMED_CONCLUSION.value,
            "supporting_evidence_ids": ["EVID-CTX-001"],
            "contradicting_evidence_ids": [],
        },
        # 6. REJECT: Prohibited accusatory fraud/guilt language
        {
            "section_key": "F_POTENTIAL_CONTRADICTIONS",
            "claim_text": "This document is fraudulent and the vendor committed fraud.",
            "claim_type": ReasoningClaimType.POTENTIAL_INTERPRETATION.value,
            "supporting_evidence_ids": ["EVID-DOC-001"],
            "contradicting_evidence_ids": [],
        },
        # 7. REJECT: Unknown document_id not belonging to investigation
        {
            "section_key": "C_DOCUMENTS_EXAMINED",
            "claim_text": "References foreign document doc-999.",
            "claim_type": ReasoningClaimType.DIRECTLY_OBSERVED_FACT.value,
            "supporting_evidence_ids": ["EVID-DOC-001"],
            "contradicting_evidence_ids": [],
            "document_ids": ["doc-999"],
        },
        # 8. REJECT: Claim with empty supporting_evidence_ids even if contradicting_evidence_ids is set
        {
            "section_key": "F_POTENTIAL_CONTRADICTIONS",
            "claim_text": "Unsupported contradiction claim with zero supporting evidence IDs.",
            "claim_type": ReasoningClaimType.AUTOMATED_TECHNICAL_OBSERVATION.value,
            "supporting_evidence_ids": [],
            "contradicting_evidence_ids": ["EVID-CTX-001"],
        },
    ]

    validated, rejected = InvestigationReasoningEngine.validate_and_filter_claims(
        candidate_claims=candidates,
        evidence_manifest=manifest,
        valid_document_ids=valid_doc_ids,
    )

    assert len(validated) == 2
    assert len(rejected) == 6

    rejection_reasons = " | ".join(r.rejection_reason for r in rejected)
    assert "UNSUPPORTED_CLAIM_NO_SUPPORTING_EVIDENCE_REFERENCES" in rejection_reasons
    assert "UNSUPPORTED_FABRICATED_EVIDENCE_IDS" in rejection_reasons
    assert "UNCONFIRMED_HUMAN_CONCLUSION_VIOLATION" in rejection_reasons
    assert "PROHIBITED_ACCUSATORY_CLAIM" in rejection_reasons
    assert "INVALID_DOCUMENT_ID_NOT_IN_INVESTIGATION" in rejection_reasons


def test_phase5_end_to_end_reasoning_dossiers_versioning_review_and_fallback() -> None:
    """
    Tests Sections 3–12 end-to-end:
    - Creates an investigation with the 4 synthetic documents
    - Generates Evidence-Grounded Reasoning (14 sections A–N, validated claims, questions, verification steps)
    - Tests AI provider failure handling & graceful deterministic fallback
    - Generates Dossier v1 (PDF + JSON), verifies SHA-256 hashes, PDF multi-page structure, and JSON schema
    - Generates Dossier v2 and verifies immutable version history (v1 and v2 both preserved)
    - Performs human review & approval on Dossier v2
    - Verifies Audit Trail entries
    """
    inv_resp = client.post(
        "/api/investigations",
        json={
            "title": "Phase 5 AI Investigation Reasoning & Dossier Verification Case",
            "description": "End-to-end verification of Phase 5 Evidence-Grounded Reasoning and Dossier Generation.",
            "priority": "CRITICAL",
            "classification": "FINANCIAL_FORENSICS",
            "lead_investigator": "Phase 5 Automated Pytest",
            "tags": ["PHASE-5", "DOSSIER", "SYNTHETIC-DEMO"],
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
    assert len(up_resp.json()["documents"]) == 4

    # 1. Test AI Provider Failure Fallback & Unsupported Claim Filtering via custom_ai_callable
    def failing_ai_provider(_manifest):
        raise RuntimeError("Simulated external AI provider network timeout")

    fallback_res = DossierService.generate_investigation_reasoning(
        investigation_id=inv_id,
        payload=ReasoningGenerateRequest(actor="Pytest Fallback Check"),
        custom_ai_callable=failing_ai_provider,
    )
    assert fallback_res.fallback_used is True
    assert "Simulated external AI provider network timeout" in (
        fallback_res.fallback_reason or ""
    )
    assert len(fallback_res.sections) == 14
    assert len(fallback_res.claims) >= 10

    # Test AI provider returning a mix of 1 valid grounded claim and 1 unsupported hallucinated claim
    def mixed_ai_provider(manifest):
        first_evid = next(iter(manifest.keys()))
        return {
            "provider": "TEST_AI_SYNTHESIZER",
            "model": "test-grounded-v1",
            "executive_summary": f"Synthesized summary referencing {first_evid}.",
            "claims": [
                {
                    "section_key": "D_KEY_OBSERVATIONS",
                    "claim_text": f"AI synthesized observation backed by {first_evid}.",
                    "claim_type": ReasoningClaimType.POTENTIAL_INTERPRETATION.value,
                    "supporting_evidence_ids": [first_evid],
                    "contradicting_evidence_ids": [],
                },
                {
                    "section_key": "D_KEY_OBSERVATIONS",
                    "claim_text": "Hallucinated AI claim with fabricated evidence ID EVID-BOGUS-999.",
                    "claim_type": ReasoningClaimType.DIRECTLY_OBSERVED_FACT.value,
                    "supporting_evidence_ids": ["EVID-BOGUS-999"],
                    "contradicting_evidence_ids": [],
                },
            ],
        }

    mixed_res = DossierService.generate_investigation_reasoning(
        investigation_id=inv_id,
        payload=ReasoningGenerateRequest(actor="Pytest Mixed AI Check"),
        custom_ai_callable=mixed_ai_provider,
    )
    assert mixed_res.ai_provider == "TEST_AI_SYNTHESIZER"
    assert mixed_res.rejected_claims_count == 1
    assert (
        "EVID-BOGUS-999" in mixed_res.rejected_claims_log[0].rejection_reason
    )

    # 2. Test REST Endpoint POST /api/investigations/{investigation_id}/reasoning/generate
    r_gen_resp = client.post(
        f"/api/investigations/{inv_id}/reasoning/generate",
        json={
            "actor": "Phase 5 Pytest Suite",
            "use_ai_provider_if_available": False,
        },
    )
    assert r_gen_resp.status_code == 200
    r_data = r_gen_resp.json()
    assert len(r_data["sections"]) == 14
    section_codes = [s["section_code"] for s in r_data["sections"]]
    assert section_codes == [
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "I",
        "J",
        "K",
        "L",
        "M",
        "N",
    ]
    assert len(r_data["questions"]) >= 4
    assert len(r_data["verification_steps"]) >= 3
    assert len(r_data["evidence_manifest"]) >= 15

    # Verify every claim references valid manifest IDs and document IDs
    manifest_keys = set(r_data["evidence_manifest"].keys())
    for clm in r_data["claims"]:
        assert clm["supporting_evidence_ids"] or clm["contradicting_evidence_ids"]
        for eid in clm["supporting_evidence_ids"] + clm["contradicting_evidence_ids"]:
            assert eid in manifest_keys

    # 3. Generate Dossier v1 via POST /api/investigations/{investigation_id}/dossiers/generate
    d1_resp = client.post(
        f"/api/investigations/{inv_id}/dossiers/generate",
        json={
            "actor": "Phase 5 Pytest Suite",
            "title": "Dossier Version 1 — Initial Synthesis",
            "regenerate_reasoning": True,
        },
    )
    assert d1_resp.status_code == 200
    d1 = d1_resp.json()
    assert d1["version_number"] == 1
    assert d1["review_status"] == "UNAPPROVED_AI_ASSISTED"
    d1_id = d1["dossier_id"]

    # Download and verify PDF Dossier v1
    pdf_resp = client.get(f"/api/dossiers/{d1_id}/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    pdf_bytes = pdf_resp.content
    assert pdf_bytes.startswith(b"%PDF-")
    assert hashlib.sha256(pdf_bytes).hexdigest() == d1["pdf_sha256_hash"]

    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf_doc:
        assert len(pdf_doc) >= 3
        full_pdf_text = "\n".join(page.get_text("text") for page in pdf_doc)
        assert "SYNTHETIC DEMONSTRATION MATERIAL" in full_pdf_text
        assert "EVIDENCE-BACKED INVESTIGATION DOSSIER" in full_pdf_text
        assert "COMPLETE EVIDENCE REFERENCE MANIFEST" in full_pdf_text
        assert "EVID-DOC-001" in full_pdf_text

    # Download and verify JSON Dossier v1
    json_resp = client.get(f"/api/dossiers/{d1_id}/json")
    assert json_resp.status_code == 200
    json_bytes = json_resp.content
    assert hashlib.sha256(json_bytes).hexdigest() == d1["json_sha256_hash"]
    parsed_json = json.loads(json_bytes.decode("utf-8"))
    assert parsed_json["dossier_metadata"]["dossier_id"] == d1_id
    assert parsed_json["dossier_metadata"]["version_number"] == 1
    assert len(parsed_json["reasoning_sections"]) == 14
    assert len(parsed_json["evidence_grounded_claims"]) >= 10

    # 4. Generate Dossier v2 and verify immutable versioning (v1 is preserved!)
    d2_resp = client.post(
        f"/api/investigations/{inv_id}/dossiers/generate",
        json={
            "actor": "Phase 5 Pytest Suite",
            "title": "Dossier Version 2 — Supervisory Review Edition",
            "regenerate_reasoning": False,
        },
    )
    assert d2_resp.status_code == 200
    d2 = d2_resp.json()
    assert d2["version_number"] == 2
    assert d2["dossier_id"] != d1_id

    list_resp = client.get(f"/api/investigations/{inv_id}/dossiers")
    assert list_resp.status_code == 200
    versions_list = list_resp.json()
    assert len(versions_list) == 2
    assert [v["version_number"] for v in versions_list] == [2, 1]

    # 5. Human Review and Approval on Dossier v2 (Switch to independent REVIEWER Marcus Vance)
    client.post("/api/auth/demo-session", json={"username": "m.vance"})
    rev_resp = client.post(
        f"/api/dossiers/{d2['dossier_id']}/review",
        json={
            "review_status": "APPROVED",
            "reviewer": "Marcus Vance",
            "notes": "Verified all evidence references, Decimal calculations, and visual forensic observations. Approved for release.",
        },
    )
    assert rev_resp.status_code == 200
    rev_d2 = rev_resp.json()
    assert rev_d2["review_status"] == "APPROVED"
    assert "Marcus Vance" in rev_d2["reviewed_by"]
    assert len(rev_d2["review_history"]) == 1
    assert rev_d2["review_history"][0]["previous_status"] == "UNAPPROVED_AI_ASSISTED"
    assert rev_d2["review_history"][0]["new_status"] == "APPROVED"

    # 6. Verify Audit Trail records all Phase 5 events
    audit_resp = client.get(f"/api/audit-logs?investigation_id={inv_id}&limit=100")
    assert audit_resp.status_code == 200
    audit_items = audit_resp.json()
    audit_actions = {item["action"] for item in audit_items}
    assert "INVESTIGATION_REASONING_GENERATED" in audit_actions
    assert "INVESTIGATION_DOSSIER_GENERATED" in audit_actions
    assert "INVESTIGATION_DOSSIER_REVIEWED" in audit_actions
    client.post("/api/auth/demo-session", json={"username": "dr.rostova"})


def test_phase5_human_approval_integrity_and_bot_rejection() -> None:
    """
    Regression test for Section A: Human Approval Integrity:
    - Newly generated dossiers MUST begin as UNAPPROVED_AI_ASSISTED.
    - Approval attempts without an explicit human reviewer (or reviewer < 3 chars) are rejected.
    - Approval attempts without review notes (< 5 chars) are rejected.
    - Approval attempts by automated bots or AI self-approval are rejected.
    - Self-approval by the investigator who generated the dossier is rejected (403).
    - Genuine human approval by an independent REVIEWER with explanatory notes succeeds.
    """
    import pytest
    from app.core.exceptions import InvalidDocumentException

    client.post("/api/auth/demo-session", json={"username": "dr.rostova"})
    inv_resp = client.post(
        "/api/investigations",
        json={
            "title": "Human Approval Integrity Test Case",
            "description": "Verifying strict human approval guardrails.",
            "priority": "HIGH",
            "classification": "FINANCIAL_FORENSICS",
            "lead_investigator": "Dr. Elena Rostova",
        },
    )
    assert inv_resp.status_code == 201
    inv_id = inv_resp.json()["id"]

    # Ingest 1 test PDF
    pdf_bytes = (SAMPLE_DIR / "demo_clean_synthetic_invoice.pdf").read_bytes()
    upload_resp = client.post(
        f"/api/investigations/{inv_id}/documents",
        files=[("files", ("invoice.pdf", pdf_bytes, "application/pdf"))],
    )
    assert upload_resp.status_code == 201

    # 1. Generate dossier: MUST begin as UNAPPROVED_AI_ASSISTED
    d_resp = client.post(f"/api/investigations/{inv_id}/dossiers/generate", json={})
    assert d_resp.status_code == 200
    dossier = d_resp.json()
    dossier_id = dossier["dossier_id"]
    assert dossier["review_status"] == "UNAPPROVED_AI_ASSISTED"
    assert dossier["reviewed_by"] is None
    assert dossier["reviewed_at"] is None

    # 2. Direct service call without reviewer or with bot reviewer is rejected
    with pytest.raises(InvalidDocumentException):
        DossierService.review_dossier(
            dossier_id=dossier_id,
            payload=DossierReviewRequest(
                review_status="APPROVED",
                reviewer="",
                notes="Approved without name.",
            ),
            current_user=None,
        )

    with pytest.raises(InvalidDocumentException) as bot_exc:
        DossierService.review_dossier(
            dossier_id=dossier_id,
            payload=DossierReviewRequest(
                review_status="APPROVED",
                reviewer="automated_agent_v1",
                notes="Automated system approval.",
            ),
            current_user=None,
        )
    assert "Automated or AI systems cannot approve dossiers" in bot_exc.value.message

    # 3. Investigator attempting to approve their own dossier via HTTP is rejected (403)
    self_approve_resp = client.post(
        f"/api/dossiers/{dossier_id}/review",
        json={
            "review_status": "APPROVED",
            "notes": "Attempting self approval.",
        },
    )
    assert self_approve_resp.status_code == 403

    # 4. Switch to independent REVIEWER (Marcus Vance); missing notes is rejected (400)
    client.post("/api/auth/demo-session", json={"username": "m.vance"})
    err2 = client.post(
        f"/api/dossiers/{dossier_id}/review",
        json={"review_status": "APPROVED", "notes": ""},
    )
    assert err2.status_code in (400, 422)

    # 5. Genuine human approval by independent REVIEWER with explanatory notes succeeds
    ok_resp = client.post(
        f"/api/dossiers/{dossier_id}/review",
        json={
            "review_status": "APPROVED",
            "notes": "Independently verified original SHA-256 fingerprint and calculations. Approved.",
        },
    )
    assert ok_resp.status_code == 200
    approved = ok_resp.json()
    assert approved["review_status"] == "APPROVED"
    assert "Marcus Vance" in approved["reviewed_by"]
    assert len(approved["review_history"]) == 1
    assert approved["review_history"][0]["previous_status"] == "UNAPPROVED_AI_ASSISTED"
    assert approved["review_history"][0]["new_status"] == "APPROVED"
