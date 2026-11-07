import json
import re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from app.core.config import settings
from app.models.entities import ReasoningClaimType
from app.schemas.dossier import (
    EvidenceGroundedClaimSchema,
    EvidenceManifestItemSchema,
    EvidencePageRefSchema,
    InvestigationQuestionSchema,
    ReasoningSectionSchema,
    RejectedClaimLogSchema,
    SourceDocumentHashItemSchema,
    VerificationStepSchema,
)

REASONING_ENGINE_VERSION = "1.7.0-phase5-grounded"
PROMPT_VERSION = "veritas-phase5-strict-grounding-v1.0"

PROHIBITED_ACCUSATORY_PATTERNS = [
    re.compile(r"\bis\s+fraudulent\b", re.IGNORECASE),
    re.compile(r"\bcommitted\s+fraud\b", re.IGNORECASE),
    re.compile(r"\bguilty\s+of\s+(?:fraud|forgery)\b", re.IGNORECASE),
    re.compile(r"\bcriminal\s+forgery\b", re.IGNORECASE),
    re.compile(r"\bdefinitively\s+forged\b", re.IGNORECASE),
]


@dataclass
class ReasoningRunOutput:
    reasoning_engine_version: str
    ai_provider: str
    ai_model: str
    prompt_version: str
    ai_assisted: bool
    fallback_used: bool
    fallback_reason: Optional[str]
    source_analysis_ids: Dict[str, Any]
    source_document_hashes: List[SourceDocumentHashItemSchema]
    evidence_manifest: Dict[str, EvidenceManifestItemSchema]
    sections: List[ReasoningSectionSchema]
    claims: List[EvidenceGroundedClaimSchema]
    rejected_claims_count: int
    rejected_claims_log: List[RejectedClaimLogSchema]
    questions: List[InvestigationQuestionSchema]
    verification_steps: List[VerificationStepSchema]
    processing_duration_ms: float


class InvestigationReasoningEngine:
    """
    VERITAS AI Phase 5 — Evidence-Grounded Investigation Reasoning Engine.
    Synthesizes outputs from Phases 1–4 into 14 structured reasoning sections (A–N),
    strictly validates every claim against the Evidence Reference Manifest, rejects
    unsupported or accusatory statements, and supports an optional provider-independent
    Gemini API integration with deterministic fallback.
    """

    @staticmethod
    def build_evidence_manifest(
        documents_bundle: List[Dict[str, Any]],
        forensic_analyses: List[Dict[str, Any]],
        forensic_findings: List[Dict[str, Any]],
        contextual_bundle: Optional[Dict[str, Any]],
    ) -> Tuple[
        Dict[str, EvidenceManifestItemSchema],
        Dict[str, str],
        Dict[str, SourceDocumentHashItemSchema],
    ]:
        """
        Builds a deterministic, verifiable Evidence Reference Manifest mapping
        canonical Evidence IDs (EVID-*) to persisted database records across Phases 2A–4.
        Also returns a lookup table `record_id_to_evid_id` and `doc_hash_map`.
        """
        manifest: Dict[str, EvidenceManifestItemSchema] = {}
        record_to_evid: Dict[str, str] = {}
        doc_hash_map: Dict[str, SourceDocumentHashItemSchema] = {}

        # 1. Documents (Phase 2A & 2B)
        for idx, doc in enumerate(documents_bundle, start=1):
            evid_id = f"EVID-DOC-{idx:03d}"
            doc_id = str(doc["id"])
            fname = str(doc["filename"])
            sha = str(doc.get("sha256_hash") or "")
            dtype = str(doc.get("document_type") or "OTHER_UNKNOWN")
            p_cnt = int(doc.get("page_count") or 1)
            conf = float(doc.get("classification_confidence") or 0.0)

            doc_hash_map[doc_id] = SourceDocumentHashItemSchema(
                document_id=doc_id,
                filename=fname,
                document_type=dtype,
                sha256_hash=sha,
                page_count=p_cnt,
            )
            manifest[evid_id] = EvidenceManifestItemSchema(
                evidence_id=evid_id,
                source_type="DOCUMENT",
                source_record_id=doc_id,
                document_id=doc_id,
                filename=fname,
                document_sha256=sha,
                page_number=1,
                summary=(
                    f"Document '{fname}' classified as {dtype} "
                    f"({conf * 100:.1f}% confidence, {p_cnt} page(s), "
                    f"extraction: {doc.get('extraction_method_summary', 'NATIVE_PDF')}, "
                    f"SHA-256: {sha[:16]}...)"
                ),
                raw_value=fname,
                normalized_value=dtype,
                confidence_score=conf,
                review_status="REVIEWED",
            )
            record_to_evid[doc_id] = evid_id

        # 2. Extracted Tables (Phase 2B)
        tbl_counter = 0
        for doc in documents_bundle:
            doc_id = str(doc["id"])
            fname = str(doc["filename"])
            sha = str(doc.get("sha256_hash") or "")
            for tbl in doc.get("tables", []):
                tbl_counter += 1
                evid_id = f"EVID-TBL-{tbl_counter:03d}"
                t_id = str(tbl.get("id") or tbl.get("table_identifier") or evid_id)
                p_num = int(tbl.get("page_number") or 1)
                headers = ", ".join(str(h) for h in tbl.get("headers", []))
                manifest[evid_id] = EvidenceManifestItemSchema(
                    evidence_id=evid_id,
                    source_type="TABLE",
                    source_record_id=t_id,
                    document_id=doc_id,
                    filename=fname,
                    document_sha256=sha,
                    page_number=p_num,
                    summary=(
                        f"Table {tbl.get('table_identifier', '')} in '{fname}' (p.{p_num}): "
                        f"{tbl.get('row_count', 0)}x{tbl.get('column_count', 0)} grid [{headers}]"
                    ),
                    raw_value=headers,
                    normalized_value=f"{tbl.get('row_count', 0)}x{tbl.get('column_count', 0)}",
                    confidence_score=float(tbl.get("confidence") or 0.95),
                    review_status="REVIEWED",
                )
                record_to_evid[t_id] = evid_id

        # 3. Visual Forensic Findings (Phase 3)
        for idx, ff in enumerate(forensic_findings, start=1):
            evid_id = f"EVID-FOR-{idx:03d}"
            f_id = str(ff["finding_id"])
            doc_id = str(ff["document_id"])
            doc_info = doc_hash_map.get(doc_id)
            fname = doc_info.filename if doc_info else str(ff.get("filename") or "")
            sha = str(ff.get("document_sha256") or (doc_info.sha256_hash if doc_info else ""))
            p_num = int(ff.get("page_number") or 1)
            rev_status = str(ff.get("review_status") or "REQUIRES_REVIEW")
            manifest[evid_id] = EvidenceManifestItemSchema(
                evidence_id=evid_id,
                source_type="VISUAL_FORENSIC_FINDING",
                source_record_id=f_id,
                document_id=doc_id,
                filename=fname,
                document_sha256=sha,
                page_number=p_num,
                summary=(
                    f"[{ff.get('module_name')}] {ff.get('title')} on '{fname}' (p.{p_num}) — "
                    f"Severity: {ff.get('severity')}, Review: {rev_status}"
                ),
                raw_value=str(ff.get("observation") or ""),
                normalized_value=str(ff.get("finding_category") or ""),
                confidence_score=float(ff.get("confidence_score") or 0.85),
                review_status=rev_status,
            )
            record_to_evid[f_id] = evid_id

        # 4. Contextual Intelligence Artifacts (Phase 4)
        if contextual_bundle:
            # 4a. Financial Validation Results (Decimal)
            for idx, fv in enumerate(
                contextual_bundle.get("financial_validations", []), start=1
            ):
                evid_id = f"EVID-FIN-{idx:03d}"
                v_id = str(fv["validation_id"])
                doc_id = str(fv["document_id"])
                fname = str(fv["filename"])
                doc_info = doc_hash_map.get(doc_id)
                sha = doc_info.sha256_hash if doc_info else ""
                p_num = int(fv.get("page_number") or 1)
                manifest[evid_id] = EvidenceManifestItemSchema(
                    evidence_id=evid_id,
                    source_type="FINANCIAL_VALIDATION",
                    source_record_id=v_id,
                    document_id=doc_id,
                    filename=fname,
                    document_sha256=sha,
                    page_number=p_num,
                    summary=(
                        f"Decimal Check [{fv.get('check_type')}] on '{fname}' (p.{p_num}): "
                        f"Expected={fv.get('expected_value')}, Observed={fv.get('observed_value')}, "
                        f"Discrepancy={fv.get('discrepancy_amount')} ({fv.get('status')})"
                    ),
                    raw_value=str(fv.get("observed_value") or ""),
                    normalized_value=str(fv.get("expected_value") or ""),
                    confidence_score=1.0,
                    review_status="REVIEWED",
                )
                record_to_evid[v_id] = evid_id

            # 4b. Contextual Contradiction & Corroboration Findings
            for idx, cf in enumerate(contextual_bundle.get("findings", []), start=1):
                evid_id = f"EVID-CTX-{idx:03d}"
                cf_id = str(cf["finding_id"])
                doc_refs = cf.get("document_references", [])
                primary_doc_id = doc_refs[0]["document_id"] if doc_refs else None
                primary_fname = (
                    ", ".join(dr["filename"] for dr in doc_refs)
                    if doc_refs
                    else "Investigation Scope"
                )
                primary_sha = doc_refs[0]["document_sha256"] if doc_refs else ""
                primary_page = (
                    doc_refs[0]["page_numbers"][0]
                    if doc_refs and doc_refs[0].get("page_numbers")
                    else 1
                )
                rev_status = str(cf.get("review_status") or "REQUIRES_REVIEW")
                manifest[evid_id] = EvidenceManifestItemSchema(
                    evidence_id=evid_id,
                    source_type="CONTEXTUAL_FINDING",
                    source_record_id=cf_id,
                    document_id=primary_doc_id,
                    filename=primary_fname,
                    document_sha256=primary_sha,
                    page_number=int(primary_page),
                    summary=(
                        f"[{cf.get('status')}] {cf.get('title')} "
                        f"(Method: {cf.get('comparison_method')}, Review: {rev_status})"
                    ),
                    raw_value=str(cf.get("description") or ""),
                    normalized_value=str(cf.get("finding_type") or ""),
                    confidence_score=float(cf.get("confidence_score") or 0.9),
                    review_status=rev_status,
                )
                record_to_evid[cf_id] = evid_id

            # 4c. Entity Resolution Clusters
            for idx, em in enumerate(
                contextual_bundle.get("entity_matches", []), start=1
            ):
                evid_id = f"EVID-RES-{idx:03d}"
                m_id = str(em["match_id"])
                members = em.get("member_entities", [])
                primary_doc_id = members[0]["document_id"] if members else None
                fnames = sorted({m["filename"] for m in members})
                primary_sha = members[0]["document_sha256"] if members else ""
                raw_vals = sorted({m["raw_value"] for m in members})
                manifest[evid_id] = EvidenceManifestItemSchema(
                    evidence_id=evid_id,
                    source_type="ENTITY_RESOLUTION",
                    source_record_id=m_id,
                    document_id=primary_doc_id,
                    filename=", ".join(fnames),
                    document_sha256=primary_sha,
                    page_number=int(members[0]["page_number"]) if members else 1,
                    summary=(
                        f"Resolved {em.get('entity_type')} '{em.get('canonical_value')}' "
                        f"[{em.get('match_status')}] across {em.get('document_count', 1)} document(s): "
                        f"raw values {raw_vals}"
                    ),
                    raw_value="; ".join(raw_vals),
                    normalized_value=str(em.get("canonical_value") or ""),
                    confidence_score=float(em.get("confidence_score") or 0.9),
                    review_status="REVIEWED",
                )
                record_to_evid[m_id] = evid_id

        return manifest, record_to_evid, doc_hash_map

    @staticmethod
    def validate_and_filter_claims(
        candidate_claims: List[Dict[str, Any]],
        evidence_manifest: Dict[str, EvidenceManifestItemSchema],
        valid_document_ids: Set[str],
    ) -> Tuple[List[EvidenceGroundedClaimSchema], List[RejectedClaimLogSchema]]:
        """
        STRICT EVIDENCE GROUNDING VALIDATOR (Section 4):
        1. Rejects any claim with zero valid evidence references in `evidence_manifest`.
        2. Rejects any claim referencing fabricated/unknown document IDs.
        3. Rejects any claim asserting `HUMAN_CONFIRMED_CONCLUSION` unless at least one
           supporting evidence record has `review_status == 'CONFIRMED'`.
        4. Rejects any claim using prohibited accusatory language ("is fraudulent", "committed fraud", etc.).
        """
        validated: List[EvidenceGroundedClaimSchema] = []
        rejected_log: List[RejectedClaimLogSchema] = []
        allowed_claim_types = {ct.value for ct in ReasoningClaimType}

        for idx, raw_c in enumerate(candidate_claims, start=1):
            c_text = str(raw_c.get("claim_text") or "").strip()
            c_type = str(
                raw_c.get("claim_type")
                or ReasoningClaimType.AUTOMATED_TECHNICAL_OBSERVATION.value
            ).strip()

            if not c_text:
                rejected_log.append(
                    RejectedClaimLogSchema(
                        attempted_claim_text="<EMPTY_CLAIM>",
                        attempted_claim_type=c_type,
                        rejection_reason="EMPTY_CLAIM_TEXT",
                    )
                )
                continue

            if c_type not in allowed_claim_types:
                rejected_log.append(
                    RejectedClaimLogSchema(
                        attempted_claim_text=c_text,
                        attempted_claim_type=c_type,
                        rejection_reason=f"INVALID_CLAIM_TYPE:{c_type}",
                    )
                )
                continue

            # Check for prohibited accusatory fraud/guilt language
            if any(pat.search(c_text) for pat in PROHIBITED_ACCUSATORY_PATTERNS):
                rejected_log.append(
                    RejectedClaimLogSchema(
                        attempted_claim_text=c_text,
                        attempted_claim_type=c_type,
                        rejection_reason="PROHIBITED_ACCUSATORY_CLAIM: Must never automatically label a person or document fraudulent.",
                    )
                )
                continue

            raw_supp = [str(x) for x in raw_c.get("supporting_evidence_ids", []) if x]
            raw_contra = [
                str(x) for x in raw_c.get("contradicting_evidence_ids", []) if x
            ]

            # Check if any referenced evidence ID is fabricated (not in manifest)
            invalid_evids = [
                eid
                for eid in (raw_supp + raw_contra)
                if eid not in evidence_manifest
            ]
            if invalid_evids:
                rejected_log.append(
                    RejectedClaimLogSchema(
                        attempted_claim_text=c_text,
                        attempted_claim_type=c_type,
                        rejection_reason=f"UNSUPPORTED_FABRICATED_EVIDENCE_IDS:{','.join(invalid_evids)}",
                    )
                )
                continue

            valid_supp = [eid for eid in raw_supp if eid in evidence_manifest]
            valid_contra = [eid for eid in raw_contra if eid in evidence_manifest]

            if not valid_supp:
                rejected_log.append(
                    RejectedClaimLogSchema(
                        attempted_claim_text=c_text,
                        attempted_claim_type=c_type,
                        rejection_reason="UNSUPPORTED_CLAIM_NO_SUPPORTING_EVIDENCE_REFERENCES: All claims must have at least one valid supporting evidence ID.",
                    )
                )
                continue

            # Check document_ids validity
            raw_doc_ids = [str(d) for d in raw_c.get("document_ids", []) if d]
            if any(d not in valid_document_ids for d in raw_doc_ids):
                rejected_log.append(
                    RejectedClaimLogSchema(
                        attempted_claim_text=c_text,
                        attempted_claim_type=c_type,
                        rejection_reason="INVALID_DOCUMENT_ID_NOT_IN_INVESTIGATION",
                    )
                )
                continue

            # If document_ids were not explicitly listed, derive from referenced manifest items
            if not raw_doc_ids:
                derived_docs: List[str] = []
                for eid in valid_supp + valid_contra:
                    d_id = evidence_manifest[eid].document_id
                    if d_id and d_id in valid_document_ids and d_id not in derived_docs:
                        derived_docs.append(d_id)
                raw_doc_ids = derived_docs

            # Check HUMAN_CONFIRMED_CONCLUSION rule: must never convert an unconfirmed automated finding into a human-confirmed conclusion
            has_confirmed_human_review = any(
                evidence_manifest[eid].review_status == "CONFIRMED"
                for eid in (valid_supp + valid_contra)
            )
            if (
                c_type == ReasoningClaimType.HUMAN_CONFIRMED_CONCLUSION.value
                and not has_confirmed_human_review
            ):
                rejected_log.append(
                    RejectedClaimLogSchema(
                        attempted_claim_text=c_text,
                        attempted_claim_type=c_type,
                        rejection_reason="UNCONFIRMED_HUMAN_CONCLUSION_VIOLATION: Automated findings cannot be claimed as HUMAN_CONFIRMED_CONCLUSION without human review_status='CONFIRMED'.",
                    )
                )
                continue

            # Build page_references
            raw_pages = raw_c.get("page_references", [])
            page_refs: List[EvidencePageRefSchema] = []
            if raw_pages:
                for pr in raw_pages:
                    if isinstance(pr, dict) and pr.get("document_id") in valid_document_ids:
                        page_refs.append(
                            EvidencePageRefSchema(
                                document_id=str(pr["document_id"]),
                                filename=str(pr.get("filename") or ""),
                                page_number=int(pr.get("page_number") or 1),
                            )
                        )
            if not page_refs:
                seen_dp: Set[Tuple[str, int]] = set()
                for eid in valid_supp + valid_contra:
                    item = evidence_manifest[eid]
                    if item.document_id and item.document_id in valid_document_ids:
                        key = (item.document_id, item.page_number)
                        if key not in seen_dp:
                            seen_dp.add(key)
                            page_refs.append(
                                EvidencePageRefSchema(
                                    document_id=item.document_id,
                                    filename=item.filename.split(",")[0].strip(),
                                    page_number=item.page_number,
                                )
                            )

            claim_id = str(raw_c.get("claim_id") or f"CLM-{len(validated) + 1:03d}")
            validated.append(
                EvidenceGroundedClaimSchema(
                    claim_id=claim_id,
                    section_key=str(raw_c.get("section_key") or "D_KEY_OBSERVATIONS"),
                    claim_text=c_text,
                    claim_type=c_type,
                    supporting_evidence_ids=valid_supp,
                    contradicting_evidence_ids=valid_contra,
                    document_ids=raw_doc_ids,
                    page_references=page_refs,
                    reasoning_method=str(
                        raw_c.get("reasoning_method")
                        or "Deterministic Evidence Manifest Synthesis"
                    ),
                    confidence_score=round(
                        float(raw_c.get("confidence_score") or 0.9), 4
                    ),
                    confidence_interpretation=str(
                        raw_c.get("confidence_interpretation")
                        or "Grounded in persisted Phase 2A–4 evidence records."
                    ),
                    is_human_confirmed=has_confirmed_human_review,
                )
            )

        return validated, rejected_log

    @staticmethod
    def generate_investigation_reasoning(
        investigation_row: Dict[str, Any],
        documents_bundle: List[Dict[str, Any]],
        forensic_analyses: List[Dict[str, Any]],
        forensic_findings: List[Dict[str, Any]],
        contextual_bundle: Optional[Dict[str, Any]],
        audit_logs_count: int = 0,
        use_ai_provider_if_available: bool = True,
        custom_ai_callable: Optional[
            Callable[[Dict[str, EvidenceManifestItemSchema]], Dict[str, Any]]
        ] = None,
    ) -> ReasoningRunOutput:
        """
        Synthesizes all persisted Phase 1–4 records into 14 structured reasoning sections (A–N),
        validated evidence-grounded claims, non-accusatory investigation questions, and
        recommended human verification steps.
        """
        t_start = time.perf_counter()

        manifest, record_to_evid, doc_hash_map = (
            InvestigationReasoningEngine.build_evidence_manifest(
                documents_bundle=documents_bundle,
                forensic_analyses=forensic_analyses,
                forensic_findings=forensic_findings,
                contextual_bundle=contextual_bundle,
            )
        )
        valid_doc_ids = set(doc_hash_map.keys())
        all_doc_evids = [
            eid for eid, m in manifest.items() if m.source_type == "DOCUMENT"
        ]

        # Build candidate deterministic claims from actual persisted evidence
        candidate_claims: List[Dict[str, Any]] = []

        # 1. Document Scope & Inventory Claims (Sections B & C)
        for doc in documents_bundle:
            d_id = str(doc["id"])
            evid_id = record_to_evid.get(d_id)
            if not evid_id:
                continue
            fname = str(doc["filename"])
            dtype = str(doc.get("document_type_label") or doc.get("document_type"))
            conf = float(doc.get("classification_confidence") or 0.0)
            sha = str(doc.get("sha256_hash") or "")
            ext_method = str(doc.get("extraction_method_summary") or "NATIVE_PDF")

            candidate_claims.append(
                {
                    "section_key": "C_DOCUMENTS_EXAMINED",
                    "claim_text": (
                        f"Examined document '{fname}' (SHA-256: {sha[:16]}...), classified as "
                        f"{dtype} ({conf * 100:.1f}% confidence) via {ext_method} extraction "
                        f"with {doc.get('layout_region_count', 0)} layout regions, "
                        f"{doc.get('table_count', 0)} table(s), and {doc.get('entity_count', 0)} extracted entities."
                    ),
                    "claim_type": ReasoningClaimType.DIRECTLY_OBSERVED_FACT.value,
                    "supporting_evidence_ids": [evid_id],
                    "contradicting_evidence_ids": [],
                    "document_ids": [d_id],
                    "page_references": [
                        {"document_id": d_id, "filename": fname, "page_number": 1}
                    ],
                    "reasoning_method": "Phase 2A/2B Document Ingestion & Classification Inventory",
                    "confidence_score": conf,
                    "confidence_interpretation": (
                        "Directly observed file hash and automated structural classification."
                    ),
                }
            )

        # 2. Financial Validation Claims (Section H)
        fin_evids: List[str] = []
        if contextual_bundle:
            for fv in contextual_bundle.get("financial_validations", []):
                v_id = str(fv["validation_id"])
                evid_id = record_to_evid.get(v_id)
                if not evid_id:
                    continue
                fin_evids.append(evid_id)
                d_id = str(fv["document_id"])
                fname = str(fv["filename"])
                is_consistent = fv.get("status") == "CONSISTENT_EVIDENCE"

                candidate_claims.append(
                    {
                        "section_key": "H_FINANCIAL_VALIDATION_RESULTS",
                        "claim_text": (
                            f"Deterministic Decimal validation [{fv.get('check_type')}] on '{fname}' "
                            f"evaluated formula ({fv.get('formula_used')}): Expected = {fv.get('expected_value')}, "
                            f"Observed = {fv.get('observed_value')}, Discrepancy = {fv.get('discrepancy_amount')} {fv.get('currency')} "
                            f"({fv.get('status')})."
                        ),
                        "claim_type": ReasoningClaimType.DETERMINISTIC_CALCULATION_RESULT.value,
                        "supporting_evidence_ids": [evid_id],
                        "contradicting_evidence_ids": (
                            [doc_evid for doc_id, doc_evid in record_to_evid.items() if doc_id in valid_doc_ids and doc_id != d_id and doc_evid.startswith("EVID-DOC-")]
                            if not is_consistent and fv.get("check_type") == "CROSS_DOC_SETTLEMENT_RECONCILIATION"
                            else []
                        ),
                        "document_ids": [d_id] if d_id in valid_doc_ids else [],
                        "page_references": [
                            {
                                "document_id": d_id,
                                "filename": fname,
                                "page_number": int(fv.get("page_number") or 1),
                            }
                        ],
                        "reasoning_method": "Exact Python decimal.Decimal(ROUND_HALF_UP) Arithmetic Verification",
                        "confidence_score": 1.0,
                        "confidence_interpretation": "Exact deterministic Decimal calculation with zero floating-point rounding drift.",
                    }
                )

        # 3. Contextual Findings Claims (Sections D, E, F, J, K)
        consistent_evids: List[str] = []
        contradiction_evids: List[str] = []
        missing_evids: List[str] = []
        timeline_evids: List[str] = []

        if contextual_bundle:
            for cf in contextual_bundle.get("findings", []):
                cf_id = str(cf["finding_id"])
                evid_id = record_to_evid.get(cf_id)
                if not evid_id:
                    continue
                status = str(cf.get("status") or "")
                f_type = str(cf.get("finding_type") or "")
                rev_status = str(cf.get("review_status") or "REQUIRES_REVIEW")
                doc_refs = cf.get("document_references", [])
                d_ids = [
                    str(dr["document_id"])
                    for dr in doc_refs
                    if str(dr["document_id"]) in valid_doc_ids
                ]
                p_refs = [
                    {
                        "document_id": str(dr["document_id"]),
                        "filename": str(dr["filename"]),
                        "page_number": int(
                            dr["page_numbers"][0] if dr.get("page_numbers") else 1
                        ),
                    }
                    for dr in doc_refs
                    if str(dr["document_id"]) in valid_doc_ids
                ]

                if status == "CONSISTENT_EVIDENCE":
                    sec_key = "E_CONSISTENT_EVIDENCE"
                    consistent_evids.append(evid_id)
                elif status == "MISSING_INFORMATION":
                    sec_key = "K_MISSING_INFORMATION"
                    missing_evids.append(evid_id)
                elif "TIMELINE" in f_type:
                    sec_key = "J_INVESTIGATION_TIMELINE"
                    timeline_evids.append(evid_id)
                    contradiction_evids.append(evid_id)
                else:
                    sec_key = "F_POTENTIAL_CONTRADICTIONS"
                    contradiction_evids.append(evid_id)

                claim_t = (
                    ReasoningClaimType.HUMAN_CONFIRMED_CONCLUSION.value
                    if rev_status == "CONFIRMED"
                    else (
                        ReasoningClaimType.UNKNOWN_OR_MISSING_INFORMATION.value
                        if status == "MISSING_INFORMATION"
                        else ReasoningClaimType.AUTOMATED_TECHNICAL_OBSERVATION.value
                    )
                )

                candidate_claims.append(
                    {
                        "section_key": sec_key,
                        "claim_text": f"{cf.get('title')}: {cf.get('description')}",
                        "claim_type": claim_t,
                        "supporting_evidence_ids": [evid_id],
                        "contradicting_evidence_ids": (
                            [record_to_evid.get(d) for d in d_ids[1:] if record_to_evid.get(d)]
                            if status in ("CONFIRMED_DATA_MISMATCH", "POTENTIAL_INCONSISTENCY") and len(d_ids) > 1
                            else []
                        ),
                        "document_ids": d_ids,
                        "page_references": p_refs,
                        "reasoning_method": str(
                            cf.get("comparison_method")
                            or "Cross-Document Contextual Correlation"
                        ),
                        "confidence_score": float(cf.get("confidence_score") or 0.9),
                        "confidence_interpretation": str(
                            cf.get("confidence_interpretation")
                            or "Cross-document evidence comparison."
                        ),
                    }
                )

        # 4. Visual Forensic Findings Claims (Section G)
        forensic_evids: List[str] = []
        for ff in forensic_findings:
            f_id = str(ff["finding_id"])
            evid_id = record_to_evid.get(f_id)
            if not evid_id:
                continue
            forensic_evids.append(evid_id)
            d_id = str(ff["document_id"])
            doc_info = doc_hash_map.get(d_id)
            fname = doc_info.filename if doc_info else "Document"
            rev_status = str(ff.get("review_status") or "REQUIRES_REVIEW")
            sev = str(ff.get("severity") or "LOW")

            claim_t = (
                ReasoningClaimType.HUMAN_CONFIRMED_CONCLUSION.value
                if rev_status == "CONFIRMED"
                else ReasoningClaimType.AUTOMATED_TECHNICAL_OBSERVATION.value
            )

            candidate_claims.append(
                {
                    "section_key": "G_VISUAL_FORENSIC_OBSERVATIONS",
                    "claim_text": (
                        f"Visual Forensics [{ff.get('module_name')}] on '{fname}' (Page {ff.get('page_number', 1)}): "
                        f"{ff.get('title')} — {ff.get('observation')} "
                        f"(Possible benign explanation: {(ff.get('possible_benign_explanations') or ['Standard document variance'])[0]})"
                    ),
                    "claim_type": claim_t,
                    "supporting_evidence_ids": [evid_id],
                    "contradicting_evidence_ids": [],
                    "document_ids": [d_id] if d_id in valid_doc_ids else [],
                    "page_references": [
                        {
                            "document_id": d_id,
                            "filename": fname,
                            "page_number": int(ff.get("page_number") or 1),
                        }
                    ],
                    "reasoning_method": f"Phase 3 Visual Forensics ({ff.get('module_name')})",
                    "confidence_score": float(ff.get("confidence_score") or 0.85),
                    "confidence_interpretation": str(
                        ff.get("confidence_interpretation")
                        or "Signal-level visual forensic observation."
                    ),
                }
            )

        # 5. Entity Resolution Claims (Section I)
        res_evids: List[str] = []
        if contextual_bundle:
            for em in contextual_bundle.get("entity_matches", []):
                if int(em.get("document_count") or 0) < 2 and em.get("match_status") == "SINGLETON_UNCORROBORATED":
                    continue
                m_id = str(em["match_id"])
                evid_id = record_to_evid.get(m_id)
                if not evid_id:
                    continue
                res_evids.append(evid_id)
                members = em.get("member_entities", [])
                d_ids = sorted(
                    {
                        str(m["document_id"])
                        for m in members
                        if str(m["document_id"]) in valid_doc_ids
                    }
                )
                candidate_claims.append(
                    {
                        "section_key": "I_ENTITY_AND_RELATIONSHIP_ANALYSIS",
                        "claim_text": (
                            f"Entity Resolution linked {em.get('entity_type')} '{em.get('canonical_value')}' "
                            f"across {em.get('document_count')} document(s) with status {em.get('match_status')}: "
                            f"{em.get('matching_rationale')}"
                        ),
                        "claim_type": (
                            ReasoningClaimType.DIRECTLY_OBSERVED_FACT.value
                            if em.get("match_status") == "EXACT_MATCH"
                            else ReasoningClaimType.POTENTIAL_INTERPRETATION.value
                        ),
                        "supporting_evidence_ids": [evid_id],
                        "contradicting_evidence_ids": [],
                        "document_ids": d_ids,
                        "page_references": [],
                        "reasoning_method": "Phase 4 Cross-Document Entity Resolution",
                        "confidence_score": float(em.get("confidence_score") or 0.9),
                        "confidence_interpretation": str(
                            em.get("matching_rationale") or "Entity normalization match."
                        ),
                    }
                )

        # 6. Optional AI Provider Integration Layer (Section 5)
        ai_provider = "VERITAS_DETERMINISTIC_SYNTHESIZER"
        ai_model = "veritas-grounded-reasoning-v1.7"
        fallback_used = False
        fallback_reason: Optional[str] = None
        ai_executive_narrative: Optional[str] = None

        if custom_ai_callable is not None:
            try:
                ai_resp = custom_ai_callable(manifest)
                ai_provider = str(ai_resp.get("provider") or "CUSTOM_AI_PROVIDER")
                ai_model = str(ai_resp.get("model") or "custom-model")
                if ai_resp.get("executive_summary"):
                    ai_executive_narrative = str(ai_resp["executive_summary"])
                for extra_claim in ai_resp.get("claims", []):
                    candidate_claims.append(extra_claim)
            except Exception as exc:
                fallback_used = True
                fallback_reason = f"AI provider error handled gracefully via deterministic fallback: {exc}"
                ai_provider = "VERITAS_DETERMINISTIC_SYNTHESIZER"
                ai_model = "veritas-grounded-reasoning-v1.7"
        elif use_ai_provider_if_available and settings.enable_gemini_reasoning:
            api_key = settings.get_server_gemini_api_key()
            if not api_key:
                fallback_used = True
                fallback_reason = (
                    "ENABLE_GEMINI_REASONING is true but GEMINI_API_KEY is not configured; "
                    "executed deterministic evidence-grounded synthesizer."
                )
            else:
                try:
                    ai_out = InvestigationReasoningEngine._invoke_gemini_synthesis(
                        api_key=api_key,
                        model_name=settings.gemini_model,
                        case_code=str(investigation_row.get("case_code") or ""),
                        manifest=manifest,
                    )
                    ai_provider = "GOOGLE_GEMINI_API"
                    ai_model = settings.gemini_model
                    if ai_out.get("executive_summary"):
                        ai_executive_narrative = str(ai_out["executive_summary"])
                    for extra_claim in ai_out.get("claims", []):
                        candidate_claims.append(extra_claim)
                except Exception as exc:
                    fallback_used = True
                    fallback_reason = (
                        f"Gemini API synthesis unavailable ({type(exc).__name__}); "
                        "fell back to deterministic evidence-grounded synthesizer."
                    )
                    ai_provider = "VERITAS_DETERMINISTIC_SYNTHESIZER"
                    ai_model = "veritas-grounded-reasoning-v1.7"

        # 7. Strictly Validate All Candidate Claims Against the Evidence Manifest
        validated_claims, rejected_claims_log = (
            InvestigationReasoningEngine.validate_and_filter_claims(
                candidate_claims=candidate_claims,
                evidence_manifest=manifest,
                valid_document_ids=valid_doc_ids,
            )
        )

        # 8. Generate Non-Accusatory Investigation Questions (Section 8)
        questions = InvestigationReasoningEngine._generate_investigation_questions(
            documents_bundle=documents_bundle,
            contextual_bundle=contextual_bundle,
            forensic_findings=forensic_findings,
            record_to_evid=record_to_evid,
            all_doc_evids=all_doc_evids,
        )

        # 9. Generate Recommended Human Verification Steps (Section 3.M)
        verification_steps = (
            InvestigationReasoningEngine._generate_verification_steps(
                documents_bundle=documents_bundle,
                contextual_bundle=contextual_bundle,
                forensic_findings=forensic_findings,
                record_to_evid=record_to_evid,
                all_doc_evids=all_doc_evids,
            )
        )

        # 10. Assemble the 14 Structured Reasoning Sections (A through N)
        sections = InvestigationReasoningEngine._build_structured_sections(
            investigation_row=investigation_row,
            documents_bundle=documents_bundle,
            forensic_analyses=forensic_analyses,
            forensic_findings=forensic_findings,
            contextual_bundle=contextual_bundle,
            validated_claims=validated_claims,
            questions=questions,
            verification_steps=verification_steps,
            all_doc_evids=all_doc_evids,
            consistent_evids=consistent_evids,
            contradiction_evids=contradiction_evids,
            forensic_evids=forensic_evids,
            fin_evids=fin_evids,
            res_evids=res_evids,
            timeline_evids=timeline_evids,
            missing_evids=missing_evids,
            audit_logs_count=audit_logs_count,
            ai_executive_narrative=ai_executive_narrative,
        )

        source_analysis_ids = {
            "forensic_analysis_ids": [
                str(fa.get("analysis_id"))
                for fa in forensic_analyses
                if fa.get("analysis_id")
            ],
            "contextual_analysis_id": (
                str(contextual_bundle.get("analysis_id"))
                if contextual_bundle and contextual_bundle.get("analysis_id")
                else None
            ),
        }

        dur_ms = round((time.perf_counter() - t_start) * 1000, 2)
        return ReasoningRunOutput(
            reasoning_engine_version=REASONING_ENGINE_VERSION,
            ai_provider=ai_provider,
            ai_model=ai_model,
            prompt_version=PROMPT_VERSION,
            ai_assisted=True,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            source_analysis_ids=source_analysis_ids,
            source_document_hashes=list(doc_hash_map.values()),
            evidence_manifest=manifest,
            sections=sections,
            claims=validated_claims,
            rejected_claims_count=len(rejected_claims_log),
            rejected_claims_log=rejected_claims_log,
            questions=questions,
            verification_steps=verification_steps,
            processing_duration_ms=dur_ms,
        )

    @staticmethod
    def _generate_investigation_questions(
        documents_bundle: List[Dict[str, Any]],
        contextual_bundle: Optional[Dict[str, Any]],
        forensic_findings: List[Dict[str, Any]],
        record_to_evid: Dict[str, str],
        all_doc_evids: List[str],
    ) -> List[InvestigationQuestionSchema]:
        questions: List[InvestigationQuestionSchema] = []
        q_idx = 0

        if contextual_bundle:
            for cf in contextual_bundle.get("findings", []):
                cf_id = str(cf["finding_id"])
                evid_id = record_to_evid.get(cf_id)
                f_type = str(cf.get("finding_type") or "")
                doc_refs = cf.get("document_references", [])
                d_ids = [str(dr["document_id"]) for dr in doc_refs]
                p_refs = [
                    EvidencePageRefSchema(
                        document_id=str(dr["document_id"]),
                        filename=str(dr["filename"]),
                        page_number=int(
                            dr["page_numbers"][0] if dr.get("page_numbers") else 1
                        ),
                    )
                    for dr in doc_refs
                ]

                if f_type in (
                    "CONTRADICTORY_MONETARY_AMOUNT",
                    "INTERNAL_TOTAL_CONTRADICTION",
                    "INVOICE_ARITHMETIC_DISCREPANCY",
                ):
                    q_idx += 1
                    questions.append(
                        InvestigationQuestionSchema(
                            question_id=f"Q-{q_idx:03d}",
                            question_text=(
                                "Which executed contract, purchase order, or billing amendment explains "
                                f"the difference between the declared monetary amounts in ({cf.get('title')})?"
                            ),
                            rationale=(
                                "Multiple monetary values or arithmetic totals were observed across the submitted "
                                "records; human procurement and treasury verification is required to establish the authorized figure."
                            ),
                            priority="HIGH",
                            related_evidence_ids=[evid_id] if evid_id else all_doc_evids[:1],
                            document_ids=d_ids,
                            page_references=p_refs,
                        )
                    )
                elif f_type == "CONFLICTING_ACCOUNT_IBAN":
                    q_idx += 1
                    questions.append(
                        InvestigationQuestionSchema(
                            question_id=f"Q-{q_idx:03d}",
                            question_text=(
                                "Is there an independent bank mandate or treasury confirmation letter "
                                "verifying the authorized beneficiary IBAN account for this vendor?"
                            ),
                            rationale=(
                                "Conflicting beneficiary account references were extracted across documents referencing "
                                "the same transaction."
                            ),
                            priority="HIGH",
                            related_evidence_ids=[evid_id] if evid_id else all_doc_evids[:1],
                            document_ids=d_ids,
                            page_references=p_refs,
                        )
                    )
                elif f_type == "TIMELINE_CHRONOLOGY_INCONSISTENCY":
                    q_idx += 1
                    questions.append(
                        InvestigationQuestionSchema(
                            question_id=f"Q-{q_idx:03d}",
                            question_text=(
                                "Does the observed post-settlement PDF modification timestamp have a documented "
                                "archival, DMS export, or workflow explanation?"
                            ),
                            rationale=(
                                "The PDF container modification timestamp occurs after the recorded settlement date on "
                                "the bank statement and escrow receipt."
                            ),
                            priority="MEDIUM",
                            related_evidence_ids=[evid_id] if evid_id else all_doc_evids[:1],
                            document_ids=d_ids,
                            page_references=p_refs,
                        )
                    )
                elif f_type == "MISSING_SUPPORTING_EVIDENCE":
                    q_idx += 1
                    questions.append(
                        InvestigationQuestionSchema(
                            question_id=f"Q-{q_idx:03d}",
                            question_text=(
                                "Are there missing supporting documents (such as the referenced Purchase Order "
                                "or Tax Certificate) available in the procurement archive?"
                            ),
                            rationale=str(cf.get("description") or ""),
                            priority="MEDIUM",
                            related_evidence_ids=[evid_id] if evid_id else all_doc_evids[:1],
                            document_ids=d_ids,
                            page_references=p_refs,
                        )
                    )

        # Add visual forensics question if high/medium visual findings exist
        high_for = [
            ff
            for ff in forensic_findings
            if ff.get("severity") in ("HIGH", "MEDIUM")
        ]
        if high_for:
            ff0 = high_for[0]
            evid_id = record_to_evid.get(str(ff0["finding_id"]))
            d_id = str(ff0["document_id"])
            q_idx += 1
            questions.append(
                InvestigationQuestionSchema(
                    question_id=f"Q-{q_idx:03d}",
                    question_text=(
                        "Can the document issuer provide the original native ERP export or custody chain "
                        "to clarify the localized typography, patch, and incremental-save signals?"
                    ),
                    rationale=(
                        f"{len(high_for)} HIGH/MEDIUM visual forensic signal(s) were detected across the submitted files."
                    ),
                    priority="HIGH",
                    related_evidence_ids=[evid_id] if evid_id else all_doc_evids[:1],
                    document_ids=[d_id],
                    page_references=[
                        EvidencePageRefSchema(
                            document_id=d_id,
                            filename=str(ff0.get("filename") or "Document"),
                            page_number=int(ff0.get("page_number") or 1),
                        )
                    ],
                )
            )

        if not questions and documents_bundle:
            d0 = documents_bundle[0]
            questions.append(
                InvestigationQuestionSchema(
                    question_id="Q-001",
                    question_text="Are all supporting schedules and counterparty confirmations uploaded for this investigation?",
                    rationale="Standard completeness review for uploaded investigation records.",
                    priority="LOW",
                    related_evidence_ids=all_doc_evids[:1],
                    document_ids=[str(d0["id"])],
                    page_references=[
                        EvidencePageRefSchema(
                            document_id=str(d0["id"]),
                            filename=str(d0["filename"]),
                            page_number=1,
                        )
                    ],
                )
            )

        return questions

    @staticmethod
    def _generate_verification_steps(
        documents_bundle: List[Dict[str, Any]],
        contextual_bundle: Optional[Dict[str, Any]],
        forensic_findings: List[Dict[str, Any]],
        record_to_evid: Dict[str, str],
        all_doc_evids: List[str],
    ) -> List[VerificationStepSchema]:
        steps: List[VerificationStepSchema] = []
        s_num = 0

        if contextual_bundle:
            for cf in contextual_bundle.get("findings", []):
                if cf.get("status") == "CONSISTENT_EVIDENCE":
                    continue
                cf_id = str(cf["finding_id"])
                evid_id = record_to_evid.get(cf_id)
                doc_refs = cf.get("document_references", [])
                d_ids = [str(dr["document_id"]) for dr in doc_refs]
                s_num += 1
                steps.append(
                    VerificationStepSchema(
                        step_id=f"STEP-{s_num:03d}",
                        step_number=s_num,
                        title=f"Verify {cf.get('finding_type', '').replace('_', ' ').title()}",
                        action_description=str(
                            cf.get("recommended_human_action")
                            or "Perform manual cross-document verification."
                        ),
                        target_evidence_ids=[evid_id] if evid_id else all_doc_evids[:1],
                        document_ids=d_ids,
                        priority=str(cf.get("severity") or "MEDIUM"),
                    )
                )

        for ff in forensic_findings:
            if ff.get("severity") != "HIGH":
                continue
            evid_id = record_to_evid.get(str(ff["finding_id"]))
            s_num += 1
            steps.append(
                VerificationStepSchema(
                    step_id=f"STEP-{s_num:03d}",
                    step_number=s_num,
                    title=f"Inspect Visual Signal: {ff.get('title')}",
                    action_description=str(
                        ff.get("recommended_human_action")
                        or "Inspect the highlighted region in the Visual Forensics workspace."
                    ),
                    target_evidence_ids=[evid_id] if evid_id else all_doc_evids[:1],
                    document_ids=[str(ff["document_id"])],
                    priority="HIGH",
                )
            )

        if not steps:
            steps.append(
                VerificationStepSchema(
                    step_id="STEP-001",
                    step_number=1,
                    title="Complete Human Supervisory Sign-Off",
                    action_description="Review extracted entities, tables, and audit logs before approving the investigation dossier.",
                    target_evidence_ids=all_doc_evids[:1],
                    document_ids=[str(d["id"]) for d in documents_bundle[:1]],
                    priority="MEDIUM",
                )
            )

        return steps

    @staticmethod
    def _build_structured_sections(
        investigation_row: Dict[str, Any],
        documents_bundle: List[Dict[str, Any]],
        forensic_analyses: List[Dict[str, Any]],
        forensic_findings: List[Dict[str, Any]],
        contextual_bundle: Optional[Dict[str, Any]],
        validated_claims: List[EvidenceGroundedClaimSchema],
        questions: List[InvestigationQuestionSchema],
        verification_steps: List[VerificationStepSchema],
        all_doc_evids: List[str],
        consistent_evids: List[str],
        contradiction_evids: List[str],
        forensic_evids: List[str],
        fin_evids: List[str],
        res_evids: List[str],
        timeline_evids: List[str],
        missing_evids: List[str],
        audit_logs_count: int,
        ai_executive_narrative: Optional[str] = None,
    ) -> List[ReasoningSectionSchema]:
        case_code = str(investigation_row.get("case_code") or "UNKNOWN")
        inv_title = str(investigation_row.get("title") or "Investigation")
        lead_inv = str(
            investigation_row.get("lead_investigator") or "Lead Forensic Analyst"
        )
        doc_count = len(documents_bundle)
        ctx_findings = (
            contextual_bundle.get("findings", []) if contextual_bundle else []
        )
        confirmed_mismatches = (
            int(contextual_bundle.get("confirmed_mismatches_count") or 0)
            if contextual_bundle
            else 0
        )
        consistent_cnt = (
            int(contextual_bundle.get("consistent_matches_count") or 0)
            if contextual_bundle
            else 0
        )
        missing_cnt = (
            int(contextual_bundle.get("missing_information_count") or 0)
            if contextual_bundle
            else 0
        )

        def claims_for(sec_key: str) -> List[str]:
            return [c.claim_id for c in validated_claims if c.section_key == sec_key]

        exec_narrative = ai_executive_narrative or (
            f"[SYNTHETIC DEMONSTRATION MATERIAL — AI-ASSISTED EVIDENCE SYNTHESIS] "
            f"Investigation {case_code} ('{inv_title}') examined {doc_count} uploaded document(s) "
            f"across Native PDF and Visual OCR extraction pipelines, 7-module Visual Forensics inspection, "
            f"and deterministic Decimal cross-document correlation. "
            f"The analysis established {consistent_cnt} corroborated evidence match(es), "
            f"{confirmed_mismatches} confirmed cross-document data mismatch(es), "
            f"{len(forensic_findings)} visual forensic signal observation(s), and "
            f"{missing_cnt} missing supporting document reference(s). "
            f"All observations in this dossier are strictly grounded in persisted evidence IDs and "
            f"remain subject to human investigator review and verification."
        )

        sections: List[ReasoningSectionSchema] = [
            ReasoningSectionSchema(
                section_key="A_EXECUTIVE_SUMMARY",
                section_code="A",
                title="A. Executive Summary",
                narrative=exec_narrative,
                claim_ids=[c.claim_id for c in validated_claims[:6]],
                evidence_ids=(
                    contradiction_evids[:3] + consistent_evids[:2] + all_doc_evids[:2]
                ),
            ),
            ReasoningSectionSchema(
                section_key="B_INVESTIGATION_SCOPE",
                section_code="B",
                title="B. Investigation Scope",
                narrative=(
                    f"Case {case_code} is assigned to {lead_inv} under classification "
                    f"'{investigation_row.get('classification', 'FINANCIAL_FORENSICS')}' "
                    f"(Priority: {investigation_row.get('priority', 'CRITICAL')}, Status: {investigation_row.get('status', 'OPEN')}). "
                    f"The scope encompasses multi-document ingestion with SHA-256 integrity fingerprinting, "
                    f"structure & layout extraction, visual authenticity signal analysis, deterministic Decimal "
                    f"financial validation, and cross-document entity resolution ({audit_logs_count} audit events logged)."
                ),
                claim_ids=claims_for("C_DOCUMENTS_EXAMINED"),
                evidence_ids=all_doc_evids,
            ),
            ReasoningSectionSchema(
                section_key="C_DOCUMENTS_EXAMINED",
                section_code="C",
                title="C. Documents Examined",
                narrative=(
                    f"A total of {doc_count} document(s) were ingested into private forensic storage, "
                    f"fingerprinted via SHA-256, and processed through Phase 2A/2B extraction: "
                    + "; ".join(
                        f"{d['filename']} ({d.get('document_type')}, {d.get('extraction_method_summary')}, SHA-256: {str(d.get('sha256_hash', ''))[:12]}...)"
                        for d in documents_bundle
                    )
                    if documents_bundle
                    else "No documents have been uploaded to this investigation yet."
                ),
                claim_ids=claims_for("C_DOCUMENTS_EXAMINED"),
                evidence_ids=all_doc_evids,
            ),
            ReasoningSectionSchema(
                section_key="D_KEY_OBSERVATIONS",
                section_code="D",
                title="D. Key Observations",
                narrative=(
                    f"Across {doc_count} document(s), the platform generated {len(validated_claims)} "
                    f"evidence-grounded claim(s): {len(contradiction_evids)} cross-document contradiction/inconsistency "
                    f"record(s), {len(consistent_evids)} corroborated settlement record(s), "
                    f"{len(fin_evids)} deterministic Decimal arithmetic check(s), and "
                    f"{len(forensic_evids)} visual forensic signal(s)."
                ),
                claim_ids=(
                    claims_for("F_POTENTIAL_CONTRADICTIONS")
                    + claims_for("E_CONSISTENT_EVIDENCE")
                ),
                evidence_ids=(contradiction_evids + consistent_evids)[:8],
            ),
            ReasoningSectionSchema(
                section_key="E_CONSISTENT_EVIDENCE",
                section_code="E",
                title="E. Consistent Evidence",
                narrative=(
                    "Cross-document correlation identified corroborated evidence across independent document channels: "
                    + " | ".join(
                        f"{cf.get('title')}"
                        for cf in ctx_findings
                        if cf.get("status") == "CONSISTENT_EVIDENCE"
                    )
                    if consistent_evids
                    else "No multi-document corroboration clusters were established in the current document set."
                ),
                claim_ids=claims_for("E_CONSISTENT_EVIDENCE"),
                evidence_ids=consistent_evids or all_doc_evids[:1],
            ),
            ReasoningSectionSchema(
                section_key="F_POTENTIAL_CONTRADICTIONS",
                section_code="F",
                title="F. Potential Contradictions",
                narrative=(
                    "Cross-document comparison surfaced the following data mismatches and potential inconsistencies "
                    "(presented with source coordinates and non-accusatory alternative explanations): "
                    + " | ".join(
                        f"[{cf.get('status')}] {cf.get('title')}"
                        for cf in ctx_findings
                        if cf.get("status")
                        in ("CONFIRMED_DATA_MISMATCH", "POTENTIAL_INCONSISTENCY")
                    )
                    if contradiction_evids
                    else "No cross-document contradictions were detected across the current documents."
                ),
                claim_ids=claims_for("F_POTENTIAL_CONTRADICTIONS"),
                evidence_ids=contradiction_evids or all_doc_evids[:1],
            ),
            ReasoningSectionSchema(
                section_key="G_VISUAL_FORENSIC_OBSERVATIONS",
                section_code="G",
                title="G. Visual Forensic Observations",
                narrative=(
                    f"Seven-module Visual Forensics executed across {len(forensic_analyses)} document analysis run(s), "
                    f"recording {len(forensic_findings)} explainable finding(s) across Image Consistency, Error Level Analysis (ELA), "
                    f"Typography & Font Consistency, Alignment & Geometry, PDF Metadata/Incremental Saves, Signature/Stamp Inspection, "
                    f"and Text-vs-Visual Comparison."
                ),
                claim_ids=claims_for("G_VISUAL_FORENSIC_OBSERVATIONS"),
                evidence_ids=forensic_evids or all_doc_evids[:1],
            ),
            ReasoningSectionSchema(
                section_key="H_FINANCIAL_VALIDATION_RESULTS",
                section_code="H",
                title="H. Financial Validation Results",
                narrative=(
                    f"Executed {len(fin_evids)} deterministic Python Decimal(ROUND_HALF_UP) financial checks "
                    f"verifying invoice line-item sums against declared totals, bank statement opening/debit/closing "
                    f"balance reconciliation, and cross-document wire settlement parity."
                ),
                claim_ids=claims_for("H_FINANCIAL_VALIDATION_RESULTS"),
                evidence_ids=fin_evids or all_doc_evids[:1],
            ),
            ReasoningSectionSchema(
                section_key="I_ENTITY_AND_RELATIONSHIP_ANALYSIS",
                section_code="I",
                title="I. Entity and Relationship Analysis",
                narrative=(
                    f"Resolved {contextual_bundle.get('entities_resolved_count', 0) if contextual_bundle else 0} entity cluster(s) "
                    f"and mapped {contextual_bundle.get('relationships_discovered_count', 0) if contextual_bundle else 0} relationship edge(s) "
                    f"across DOCUMENT, COMPANY, PERSON, INVOICE, BANK_ACCOUNT, and AMOUNT nodes while preserving raw OCR strings "
                    f"alongside normalized values."
                ),
                claim_ids=claims_for("I_ENTITY_AND_RELATIONSHIP_ANALYSIS"),
                evidence_ids=res_evids or all_doc_evids[:1],
            ),
            ReasoningSectionSchema(
                section_key="J_INVESTIGATION_TIMELINE",
                section_code="J",
                title="J. Investigation Timeline",
                narrative=(
                    f"Chronological ordering of {len(contextual_bundle.get('timeline_events', [])) if contextual_bundle else 0} "
                    f"extracted document dates, bank ledger posting dates, and PDF container modification timestamps: "
                    + " -> ".join(
                        f"{te.get('date_iso')}: {te.get('title')} [{te.get('status')}]"
                        for te in (
                            contextual_bundle.get("timeline_events", [])
                            if contextual_bundle
                            else []
                        )
                    )
                ),
                claim_ids=claims_for("J_INVESTIGATION_TIMELINE"),
                evidence_ids=timeline_evids or all_doc_evids[:1],
            ),
            ReasoningSectionSchema(
                section_key="K_MISSING_INFORMATION",
                section_code="K",
                title="K. Missing Information",
                narrative=(
                    "External document references and evidentiary completeness check: "
                    + " | ".join(
                        f"{cf.get('title')}: {cf.get('description')}"
                        for cf in ctx_findings
                        if cf.get("status") == "MISSING_INFORMATION"
                    )
                    if missing_evids
                    else "All referenced supporting document types appear present in the current investigation."
                ),
                claim_ids=claims_for("K_MISSING_INFORMATION"),
                evidence_ids=missing_evids or all_doc_evids[:1],
            ),
            ReasoningSectionSchema(
                section_key="L_UNRESOLVED_QUESTIONS",
                section_code="L",
                title="L. Unresolved Questions",
                narrative=(
                    f"Generated {len(questions)} non-accusatory, evidence-backed question(s) for human investigator follow-up: "
                    + " | ".join(
                        f"({q.question_id}) {q.question_text}" for q in questions
                    )
                ),
                claim_ids=[],
                evidence_ids=[
                    eid for q in questions for eid in q.related_evidence_ids
                ]
                or all_doc_evids[:1],
            ),
            ReasoningSectionSchema(
                section_key="M_RECOMMENDED_HUMAN_VERIFICATION_STEPS",
                section_code="M",
                title="M. Recommended Human Verification Steps",
                narrative=(
                    f"Structured {len(verification_steps)} human verification step(s) prioritized by evidentiary impact: "
                    + " | ".join(
                        f"Step {s.step_number} [{s.priority}]: {s.title} — {s.action_description}"
                        for s in verification_steps
                    )
                ),
                claim_ids=[],
                evidence_ids=[
                    eid
                    for s in verification_steps
                    for eid in s.target_evidence_ids
                ]
                or all_doc_evids[:1],
            ),
            ReasoningSectionSchema(
                section_key="N_LIMITATIONS_AND_CONFIDENCE_INTERPRETATION",
                section_code="N",
                title="N. Limitations and Confidence Interpretation",
                narrative=(
                    "FORENSIC & AI LIMITATIONS STATEMENT: VERITAS AI is an evidence-intelligence platform. "
                    "Automated extraction (PyMuPDF / PaddleOCR), visual signal inspection (OpenCV / ELA / Typography), "
                    "and cross-document correlation surface technical observations and mathematical discrepancies, "
                    "not legal determinations of fraud or culpability. OCR confidence depends on scan resolution; "
                    "ELA on PDF-rendered pages reflects rendering contrast rather than original JPEG quantization; "
                    "and cross-document discrepancies may arise from unrecorded contract amendments or clerical revisions. "
                    "All AI-assisted reasoning and automated findings remain unapproved until reviewed by a qualified human investigator."
                ),
                claim_ids=[],
                evidence_ids=all_doc_evids,
            ),
        ]
        return sections

    @staticmethod
    def _invoke_gemini_synthesis(
        api_key: str,
        model_name: str,
        case_code: str,
        manifest: Dict[str, EvidenceManifestItemSchema],
    ) -> Dict[str, Any]:
        """
        Optional server-side Gemini REST API call that synthesizes an executive summary
        from the Evidence Reference Manifest without exposing credentials or inventing facts.
        """
        manifest_summary_lines = [
            f"- {eid} ({item.source_type}, doc={item.filename}, p.{item.page_number}, review={item.review_status}): {item.summary}"
            for eid, item in list(manifest.items())[:40]
        ]
        prompt = (
            f"You are the VERITAS AI Evidence-Grounded Reasoning Synthesizer (Prompt Version: {PROMPT_VERSION}).\n"
            f"Synthesize a concise, non-accusatory executive summary for Investigation {case_code} "
            "strictly using the following Evidence Reference Manifest. Never invent facts, never claim fraud, "
            "and cite evidence IDs (e.g., EVID-CTX-001) inline.\n\n"
            "EVIDENCE MANIFEST:\n"
            + "\n".join(manifest_summary_lines)
            + '\n\nRespond strictly in JSON format: {"executive_summary": "..."}'
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        req_body = json.dumps(
            {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json",
                },
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=req_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            raw_resp = json.loads(resp.read().decode("utf-8"))
            text_part = (
                raw_resp["candidates"][0]["content"]["parts"][0]["text"]
            )
            parsed = json.loads(text_part)
            return {
                "executive_summary": str(parsed.get("executive_summary") or ""),
                "claims": parsed.get("claims", []),
            }
