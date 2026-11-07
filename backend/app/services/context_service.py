import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.core.database import get_db_connection
from app.core.exceptions import InvalidDocumentException, ResourceNotFoundException
from app.models.entities import (
    ContextualEvaluationStatus,
    ForensicFindingSeverity,
    ForensicReviewStatus,
)
from app.schemas.auth import AuthenticatedUser
from app.schemas.context import (
    ContextualAnalysisBundleResponse,
    ContextualAnalysisRequest,
    ContextualFindingResponse,
    ContextualReviewRecordSchema,
    ContextualReviewRequest,
    DocumentReferenceItemSchema,
    EntityMatchClusterResponse,
    EvidenceValueItemSchema,
    FinancialValidationResultResponse,
    GraphEdgeSchema,
    GraphNodeSchema,
    InvestigationEntityGraphResponse,
    TimelineEventSchema,
)
from app.services.audit_service import AuditService
from app.services.contextual_intelligence_engine import ContextualIntelligenceEngine
from app.services.document_service import DocumentService, _parse_bbox


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_loads(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _row_to_contextual_finding(
    row: Any, reviews: Optional[List[ContextualReviewRecordSchema]] = None
) -> ContextualFindingResponse:
    doc_refs_raw = _safe_json_loads(row["document_references_json"], [])
    ev_vals_raw = _safe_json_loads(row["evidence_values_json"], [])

    doc_refs = [DocumentReferenceItemSchema(**dr) for dr in doc_refs_raw]
    ev_vals = [EvidenceValueItemSchema(**ev) for ev in ev_vals_raw]

    return ContextualFindingResponse(
        finding_id=row["id"],
        analysis_id=row["analysis_id"],
        investigation_id=row["investigation_id"],
        finding_type=row["finding_type"],
        severity=row["severity"],
        status=row["status"],
        title=row["title"],
        description=row["description"],
        document_references=doc_refs,
        evidence_values=ev_vals,
        comparison_method=row["comparison_method"],
        matching_rationale=row["matching_rationale"],
        confidence_score=round(float(row["confidence_score"] or 0.0), 4),
        confidence_interpretation=row["confidence_interpretation"] or "",
        possible_explanations=_safe_json_loads(row["possible_explanations_json"], []),
        recommended_human_action=row["recommended_human_action"],
        review_status=row["review_status"],
        reviewer=row["reviewer"],
        review_notes=row["review_notes"],
        reviewed_at=row["reviewed_at"],
        review_history=reviews or [],
        created_at=row["created_at"],
    )


class ContextService:
    @staticmethod
    def run_investigation_context_analysis(
        investigation_id: str,
        payload: Optional[ContextualAnalysisRequest] = None,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> ContextualAnalysisBundleResponse:
        req = payload or ContextualAnalysisRequest()

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, case_code, title, lead_investigator FROM investigations WHERE id = ?;",
                (investigation_id,),
            )
            inv_row = cursor.fetchone()
            if not inv_row:
                raise ResourceNotFoundException("Investigation", investigation_id)

            case_code = inv_row["case_code"]
            inv_title = inv_row["title"]
            actor = (
                f"{current_user.full_name} ({current_user.title})"
                if current_user
                else (
                    req.actor.strip()
                    if req.actor and req.actor.strip()
                    else (inv_row["lead_investigator"] or "Lead Forensic Analyst")
                )
            )

            cursor.execute(
                """
                SELECT id, file_type, storage_path FROM documents
                WHERE investigation_id = ? AND processing_status = 'COMPLETED'
                ORDER BY uploaded_at ASC;
                """,
                (investigation_id,),
            )
            doc_rows_for_ctx = cursor.fetchall()
            doc_ids = [r["id"] for r in doc_rows_for_ctx]

            forensic_meta_by_doc: Dict[str, Dict[str, Any]] = {}
            cursor.execute(
                """
                SELECT document_id, pdf_metadata_json
                FROM forensic_analyses
                WHERE investigation_id = ?
                ORDER BY created_at ASC;
                """,
                (investigation_id,),
            )
            for fa_r in cursor.fetchall():
                forensic_meta_by_doc[fa_r["document_id"]] = _safe_json_loads(
                    fa_r["pdf_metadata_json"], {}
                )

            # Fallback: extract PDF creationDate/modDate directly if Phase 3 analysis was not yet run on a PDF
            for dr in doc_rows_for_ctx:
                d_id = dr["id"]
                if d_id not in forensic_meta_by_doc and dr["file_type"] == "PDF":
                    try:
                        import fitz

                        with fitz.open(dr["storage_path"]) as pdf_doc:
                            meta = pdf_doc.metadata or {}
                            forensic_meta_by_doc[d_id] = {
                                "creation_date_raw": str(meta.get("creationDate") or ""),
                                "modification_date_raw": str(meta.get("modDate") or ""),
                            }
                    except Exception:
                        pass

        documents_bundle: List[Dict[str, Any]] = []
        for d_id in doc_ids:
            detail = DocumentService.get_document_detail(d_id)
            documents_bundle.append(detail.model_dump())

        analysis_id = str(uuid.uuid4())
        started_at = _utc_now_iso()

        with get_db_connection() as conn:
            cursor = conn.cursor()
            AuditService.append_event_with_cursor(
                cursor,
                investigation_id=investigation_id,
                action="CONTEXTUAL_ANALYSIS_STARTED",
                entity_type="CONTEXTUAL_ANALYSIS",
                entity_id=analysis_id,
                actor=actor,
                summary=f"Started Phase 4 Cross-Document Contextual Intelligence analysis for case {case_code} ({len(documents_bundle)} documents)",
                metadata={
                    "case_code": case_code,
                    "investigation_id": investigation_id,
                    "analysis_id": analysis_id,
                    "document_count": len(documents_bundle),
                },
                actor_user_id=current_user.id if current_user else None,
                actor_role=current_user.role if current_user else None,
                event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                created_at=started_at,
            )

        run_out = ContextualIntelligenceEngine.analyze_investigation_context(
            investigation_id=investigation_id,
            documents_bundle=documents_bundle,
            forensic_analyses_by_doc=forensic_meta_by_doc,
        )
        completed_at = _utc_now_iso()

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Replace prior contextual analysis for this investigation so findings don't duplicate
            cursor.execute(
                "DELETE FROM contextual_analyses WHERE investigation_id = ?;",
                (investigation_id,),
            )
            cursor.execute(
                "DELETE FROM findings WHERE investigation_id = ? AND finding_type LIKE 'CONTEXT_%';",
                (investigation_id,),
            )

            summary_meta = {
                "graph_nodes": run_out.graph_nodes,
            }

            cursor.execute(
                """
                INSERT INTO contextual_analyses (
                    id, investigation_id, status, documents_analyzed_count,
                    entities_resolved_count, relationships_discovered_count,
                    consistent_matches_count, potential_contradictions_count,
                    confirmed_mismatches_count, missing_information_count,
                    inconclusive_count, financial_checks_count,
                    timeline_events_json, summary_metrics_json,
                    processing_duration_ms, started_at, completed_at, created_at
                ) VALUES (?, ?, 'COMPLETED', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    analysis_id,
                    investigation_id,
                    run_out.documents_analyzed_count,
                    run_out.entities_resolved_count,
                    run_out.relationships_discovered_count,
                    run_out.consistent_matches_count,
                    run_out.potential_contradictions_count,
                    run_out.confirmed_mismatches_count,
                    run_out.missing_information_count,
                    run_out.inconclusive_count,
                    run_out.financial_checks_count,
                    json.dumps(run_out.timeline_events),
                    json.dumps(summary_meta),
                    run_out.processing_duration_ms,
                    started_at,
                    completed_at,
                    completed_at,
                ),
            )

            for em in run_out.entity_matches:
                cursor.execute(
                    """
                    INSERT INTO entity_matches (
                        id, analysis_id, investigation_id, entity_type,
                        canonical_value, match_status, confidence_score,
                        matching_rationale, member_entities_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        em["match_id"],
                        analysis_id,
                        investigation_id,
                        em["entity_type"],
                        em["canonical_value"],
                        em["match_status"],
                        em["confidence_score"],
                        em["matching_rationale"],
                        json.dumps(em["member_entities"]),
                        completed_at,
                    ),
                )

            for edge in run_out.graph_edges:
                cursor.execute(
                    """
                    INSERT INTO entity_relationships (
                        id, analysis_id, investigation_id, source_node_id,
                        source_node_type, source_label, target_node_id,
                        target_node_type, target_label, edge_type,
                        confidence_score, matching_rationale,
                        source_evidence_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        edge["relationship_id"],
                        analysis_id,
                        investigation_id,
                        edge["source_node_id"],
                        edge["source_node_type"],
                        edge["source_label"],
                        edge["target_node_id"],
                        edge["target_node_type"],
                        edge["target_label"],
                        edge["edge_type"],
                        edge["confidence_score"],
                        edge["matching_rationale"],
                        json.dumps(edge["source_evidence"]),
                        completed_at,
                    ),
                )

            for fv in run_out.financial_validations:
                cursor.execute(
                    """
                    INSERT INTO financial_validation_results (
                        id, analysis_id, investigation_id, document_id,
                        filename, document_type, check_type, status,
                        expected_value, observed_value, discrepancy_amount,
                        currency, formula_used, details_json, page_number,
                        bounding_box_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        fv["validation_id"],
                        analysis_id,
                        investigation_id,
                        fv["document_id"],
                        fv["filename"],
                        fv["document_type"],
                        fv["check_type"],
                        fv["status"],
                        fv["expected_value"],
                        fv["observed_value"],
                        fv["discrepancy_amount"],
                        fv["currency"],
                        fv["formula_used"],
                        json.dumps(fv["details"]),
                        fv.get("page_number", 1),
                        json.dumps(fv["bounding_box"])
                        if fv.get("bounding_box")
                        else None,
                        completed_at,
                    ),
                )

            for fnd in run_out.findings:
                initial_rev = (
                    ForensicReviewStatus.REVIEWED.value
                    if fnd["status"] == ContextualEvaluationStatus.CONSISTENT_EVIDENCE.value
                    else ForensicReviewStatus.REQUIRES_REVIEW.value
                )
                cursor.execute(
                    """
                    INSERT INTO contextual_findings (
                        id, analysis_id, investigation_id, finding_type,
                        severity, status, title, description,
                        document_references_json, evidence_values_json,
                        comparison_method, matching_rationale,
                        confidence_score, confidence_interpretation,
                        possible_explanations_json, recommended_human_action,
                        review_status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        fnd["finding_id"],
                        analysis_id,
                        investigation_id,
                        fnd["finding_type"],
                        fnd["severity"],
                        fnd["status"],
                        fnd["title"],
                        fnd["description"],
                        json.dumps(fnd["document_references"]),
                        json.dumps(fnd["evidence_values"]),
                        fnd["comparison_method"],
                        fnd["matching_rationale"],
                        fnd["confidence_score"],
                        fnd["confidence_interpretation"],
                        json.dumps(fnd["possible_explanations"]),
                        fnd["recommended_human_action"],
                        initial_rev,
                        completed_at,
                    ),
                )

                if fnd["severity"] != ForensicFindingSeverity.INFORMATIONAL.value:
                    first_doc_id = (
                        fnd["document_references"][0]["document_id"]
                        if fnd["document_references"]
                        else None
                    )
                    cursor.execute(
                        """
                        INSERT INTO findings (
                            id, investigation_id, document_id, finding_type,
                            severity, review_status, title, description,
                            confidence_score, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            fnd["finding_id"],
                            investigation_id,
                            first_doc_id,
                            f"CONTEXT_{fnd['finding_type']}",
                            fnd["severity"],
                            initial_rev,
                            fnd["title"],
                            fnd["description"],
                            fnd["confidence_score"],
                            completed_at,
                        ),
                    )
                    AuditService.append_event_with_cursor(
                        cursor,
                        investigation_id=investigation_id,
                        action="CONTEXTUAL_FINDING_CREATED",
                        entity_type="CONTEXTUAL_FINDING",
                        entity_id=fnd["finding_id"],
                        actor=actor,
                        summary=f"[{fnd['severity']}] {fnd['title']}",
                        metadata={
                            "case_code": case_code,
                            "analysis_id": analysis_id,
                            "finding_id": fnd["finding_id"],
                            "finding_type": fnd["finding_type"],
                            "status": fnd["status"],
                            "severity": fnd["severity"],
                        },
                        actor_user_id=current_user.id if current_user else None,
                        actor_role=current_user.role if current_user else None,
                        event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                        created_at=completed_at,
                    )

            cursor.execute(
                "UPDATE investigations SET updated_at = ? WHERE id = ?;",
                (completed_at, investigation_id),
            )
            AuditService.append_event_with_cursor(
                cursor,
                investigation_id=investigation_id,
                action="CONTEXTUAL_ANALYSIS_COMPLETED",
                entity_type="CONTEXTUAL_ANALYSIS",
                entity_id=analysis_id,
                actor=actor,
                summary=(
                    f"Completed Phase 4 Cross-Document Contextual Intelligence for {case_code} "
                    f"in {run_out.processing_duration_ms}ms: {len(run_out.findings)} findings, "
                    f"{run_out.entities_resolved_count} resolved entity clusters, "
                    f"{run_out.relationships_discovered_count} graph edges"
                ),
                metadata={
                    "case_code": case_code,
                    "analysis_id": analysis_id,
                    "documents_analyzed": run_out.documents_analyzed_count,
                    "entities_resolved": run_out.entities_resolved_count,
                    "relationships_discovered": run_out.relationships_discovered_count,
                    "confirmed_mismatches": run_out.confirmed_mismatches_count,
                    "potential_contradictions": run_out.potential_contradictions_count,
                    "consistent_matches": run_out.consistent_matches_count,
                },
                actor_user_id=current_user.id if current_user else None,
                actor_role=current_user.role if current_user else None,
                event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                created_at=completed_at,
            )

        return ContextService.get_investigation_context(investigation_id)

    @staticmethod
    def get_investigation_context(
        investigation_id: str,
    ) -> ContextualAnalysisBundleResponse:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, case_code, title FROM investigations WHERE id = ?;",
                (investigation_id,),
            )
            inv_row = cursor.fetchone()
            if not inv_row:
                raise ResourceNotFoundException("Investigation", investigation_id)

            cursor.execute(
                """
                SELECT * FROM contextual_analyses
                WHERE investigation_id = ?
                ORDER BY created_at DESC
                LIMIT 1;
                """,
                (investigation_id,),
            )
            ca_row = cursor.fetchone()

        if not ca_row:
            return ContextService.run_investigation_context_analysis(investigation_id)

        analysis_id = ca_row["id"]

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM entity_matches
                WHERE analysis_id = ?
                ORDER BY entity_type ASC, canonical_value ASC;
                """,
                (analysis_id,),
            )
            em_list: List[EntityMatchClusterResponse] = []
            for r in cursor.fetchall():
                members_raw = _safe_json_loads(r["member_entities_json"], [])
                doc_ids = {m.get("document_id") for m in members_raw}
                em_list.append(
                    EntityMatchClusterResponse(
                        match_id=r["id"],
                        analysis_id=r["analysis_id"],
                        investigation_id=r["investigation_id"],
                        entity_type=r["entity_type"],
                        canonical_value=r["canonical_value"],
                        match_status=r["match_status"],
                        confidence_score=round(float(r["confidence_score"] or 0.0), 4),
                        matching_rationale=r["matching_rationale"],
                        document_count=len(doc_ids),
                        member_entities=[
                            EvidenceValueItemSchema(**m) for m in members_raw
                        ],
                        created_at=r["created_at"],
                    )
                )

            cursor.execute(
                """
                SELECT * FROM entity_relationships
                WHERE analysis_id = ?
                ORDER BY created_at ASC;
                """,
                (analysis_id,),
            )
            edges: List[GraphEdgeSchema] = []
            for er in cursor.fetchall():
                edges.append(
                    GraphEdgeSchema(
                        relationship_id=er["id"],
                        source_node_id=er["source_node_id"],
                        source_node_type=er["source_node_type"],
                        source_label=er["source_label"],
                        target_node_id=er["target_node_id"],
                        target_node_type=er["target_node_type"],
                        target_label=er["target_label"],
                        edge_type=er["edge_type"],
                        confidence_score=round(float(er["confidence_score"] or 0.0), 4),
                        matching_rationale=er["matching_rationale"],
                        source_evidence=_safe_json_loads(
                            er["source_evidence_json"], {}
                        ),
                    )
                )

            summary_meta = _safe_json_loads(ca_row["summary_metrics_json"], {})
            raw_nodes = summary_meta.get("graph_nodes", [])
            nodes = [GraphNodeSchema(**n) for n in raw_nodes]

            contradiction_edges = sum(
                1 for e in edges if e.edge_type == "CONTRADICTS"
            )
            supporting_edges = sum(1 for e in edges if e.edge_type == "SUPPORTS")

            graph_resp = InvestigationEntityGraphResponse(
                investigation_id=investigation_id,
                analysis_id=analysis_id,
                node_count=len(nodes),
                edge_count=len(edges),
                contradiction_edge_count=contradiction_edges,
                supporting_edge_count=supporting_edges,
                nodes=nodes,
                edges=edges,
            )

            cursor.execute(
                """
                SELECT * FROM financial_validation_results
                WHERE analysis_id = ?
                ORDER BY created_at ASC;
                """,
                (analysis_id,),
            )
            fin_list: List[FinancialValidationResultResponse] = []
            for fvr in cursor.fetchall():
                fin_list.append(
                    FinancialValidationResultResponse(
                        validation_id=fvr["id"],
                        analysis_id=fvr["analysis_id"],
                        investigation_id=fvr["investigation_id"],
                        document_id=fvr["document_id"],
                        filename=fvr["filename"],
                        document_type=fvr["document_type"],
                        check_type=fvr["check_type"],
                        status=fvr["status"],
                        expected_value=fvr["expected_value"],
                        observed_value=fvr["observed_value"],
                        discrepancy_amount=fvr["discrepancy_amount"],
                        currency=fvr["currency"],
                        formula_used=fvr["formula_used"],
                        details=_safe_json_loads(fvr["details_json"], {}),
                        page_number=int(fvr["page_number"] or 1),
                        bounding_box=(
                            _parse_bbox(fvr["bounding_box_json"])
                            if fvr["bounding_box_json"]
                            else None
                        ),
                        created_at=fvr["created_at"],
                    )
                )

            cursor.execute(
                """
                SELECT * FROM contextual_review_history
                WHERE analysis_id = ?
                ORDER BY created_at DESC;
                """,
                (analysis_id,),
            )
            revs_by_finding: Dict[str, List[ContextualReviewRecordSchema]] = {}
            for rr in cursor.fetchall():
                revs_by_finding.setdefault(rr["finding_id"], []).append(
                    ContextualReviewRecordSchema(
                        review_id=rr["id"],
                        finding_id=rr["finding_id"],
                        analysis_id=rr["analysis_id"],
                        investigation_id=rr["investigation_id"],
                        previous_status=rr["previous_status"],
                        new_status=rr["new_status"],
                        reviewer=rr["reviewer"],
                        notes=rr["notes"] or "",
                        created_at=rr["created_at"],
                    )
                )

            cursor.execute(
                """
                SELECT * FROM contextual_findings
                WHERE analysis_id = ?
                ORDER BY
                    CASE severity
                        WHEN 'HIGH' THEN 1
                        WHEN 'MEDIUM' THEN 2
                        WHEN 'LOW' THEN 3
                        ELSE 4
                    END ASC,
                    created_at ASC;
                """,
                (analysis_id,),
            )
            findings = [
                _row_to_contextual_finding(r, revs_by_finding.get(r["id"], []))
                for r in cursor.fetchall()
            ]

            pending_cnt = sum(
                1
                for f in findings
                if f.review_status == ForensicReviewStatus.REQUIRES_REVIEW.value
            )
            reviewed_cnt = len(findings) - pending_cnt

            raw_timeline = _safe_json_loads(ca_row["timeline_events_json"], [])
            timeline_events = [TimelineEventSchema(**te) for te in raw_timeline]

            return ContextualAnalysisBundleResponse(
                analysis_id=analysis_id,
                investigation_id=investigation_id,
                case_code=inv_row["case_code"],
                investigation_title=inv_row["title"],
                status=ca_row["status"],
                documents_analyzed_count=int(ca_row["documents_analyzed_count"] or 0),
                entities_resolved_count=int(ca_row["entities_resolved_count"] or 0),
                relationships_discovered_count=int(
                    ca_row["relationships_discovered_count"] or 0
                ),
                consistent_matches_count=int(ca_row["consistent_matches_count"] or 0),
                potential_contradictions_count=int(
                    ca_row["potential_contradictions_count"] or 0
                ),
                confirmed_mismatches_count=int(
                    ca_row["confirmed_mismatches_count"] or 0
                ),
                missing_information_count=int(
                    ca_row["missing_information_count"] or 0
                ),
                inconclusive_count=int(ca_row["inconclusive_count"] or 0),
                financial_checks_count=int(ca_row["financial_checks_count"] or 0),
                pending_review_count=pending_cnt,
                reviewed_count=reviewed_cnt,
                processing_duration_ms=round(
                    float(ca_row["processing_duration_ms"] or 0.0), 2
                ),
                started_at=ca_row["started_at"],
                completed_at=ca_row["completed_at"],
                created_at=ca_row["created_at"],
                entity_matches=em_list,
                graph=graph_resp,
                financial_validations=fin_list,
                timeline_events=timeline_events,
                findings=findings,
            )

    @staticmethod
    def list_investigation_contextual_findings(
        investigation_id: str,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        review_status: Optional[str] = None,
    ) -> List[ContextualFindingResponse]:
        bundle = ContextService.get_investigation_context(investigation_id)
        items = bundle.findings
        if severity:
            items = [f for f in items if f.severity.upper() == severity.upper()]
        if status:
            items = [f for f in items if f.status.upper() == status.upper()]
        if review_status:
            items = [
                f for f in items if f.review_status.upper() == review_status.upper()
            ]
        return items

    @staticmethod
    def get_investigation_graph(
        investigation_id: str,
    ) -> InvestigationEntityGraphResponse:
        bundle = ContextService.get_investigation_context(investigation_id)
        return bundle.graph

    @staticmethod
    def get_investigation_financial_validations(
        investigation_id: str,
    ) -> List[FinancialValidationResultResponse]:
        bundle = ContextService.get_investigation_context(investigation_id)
        return bundle.financial_validations

    @staticmethod
    def get_contextual_finding_by_id(finding_id: str) -> ContextualFindingResponse:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM contextual_findings WHERE id = ?;", (finding_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise ResourceNotFoundException("ContextualFinding", finding_id)

            cursor.execute(
                """
                SELECT * FROM contextual_review_history
                WHERE finding_id = ?
                ORDER BY created_at DESC;
                """,
                (finding_id,),
            )
            revs = [
                ContextualReviewRecordSchema(
                    review_id=r["id"],
                    finding_id=r["finding_id"],
                    analysis_id=r["analysis_id"],
                    investigation_id=r["investigation_id"],
                    previous_status=r["previous_status"],
                    new_status=r["new_status"],
                    reviewer=r["reviewer"],
                    notes=r["notes"] or "",
                    created_at=r["created_at"],
                )
                for r in cursor.fetchall()
            ]
            return _row_to_contextual_finding(row, revs)

    @staticmethod
    def review_contextual_finding(
        finding_id: str,
        payload: ContextualReviewRequest,
        current_user: Optional[AuthenticatedUser] = None,
    ) -> ContextualFindingResponse:
        valid_statuses = {s.value for s in ForensicReviewStatus}
        norm_status = payload.review_status.strip().upper()
        if norm_status not in valid_statuses:
            raise InvalidDocumentException(
                message=(
                    f"Invalid review_status '{payload.review_status}'. "
                    f"Allowed values: {sorted(valid_statuses)}."
                ),
                code="INVALID_REVIEW_STATUS",
            )

        now = _utc_now_iso()
        review_id = str(uuid.uuid4())
        reviewer_clean = (
            f"{current_user.full_name} ({current_user.title})"
            if current_user
            else (payload.reviewer.strip() or "Lead Forensic Analyst")
        )
        reviewer_user_id = current_user.id if current_user else None
        notes_clean = payload.notes.strip()

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM contextual_findings WHERE id = ?;", (finding_id,)
            )
            f_row = cursor.fetchone()
            if not f_row:
                raise ResourceNotFoundException("ContextualFinding", finding_id)

            prev_status = f_row["review_status"]
            inv_id = f_row["investigation_id"]
            analysis_id = f_row["analysis_id"]

            cursor.execute(
                "SELECT case_code FROM investigations WHERE id = ?;", (inv_id,)
            )
            inv_row = cursor.fetchone()
            case_code = inv_row["case_code"] if inv_row else "UNKNOWN"

            cursor.execute(
                """
                UPDATE contextual_findings
                SET review_status = ?,
                    reviewer = ?,
                    reviewer_user_id = ?,
                    review_notes = ?,
                    reviewed_at = ?
                WHERE id = ?;
                """,
                (
                    norm_status,
                    reviewer_clean,
                    reviewer_user_id,
                    notes_clean,
                    now,
                    finding_id,
                ),
            )

            mapped_case_status = (
                "REQUIRES_REVIEW"
                if norm_status == "REQUIRES_REVIEW"
                else ("CONFIRMED" if norm_status == "CONFIRMED" else "DISMISSED")
            )
            cursor.execute(
                "UPDATE findings SET review_status = ? WHERE id = ?;",
                (mapped_case_status, finding_id),
            )

            cursor.execute(
                """
                INSERT INTO contextual_review_history (
                    id, finding_id, analysis_id, investigation_id,
                    previous_status, new_status, reviewer, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    review_id,
                    finding_id,
                    analysis_id,
                    inv_id,
                    prev_status,
                    norm_status,
                    reviewer_clean,
                    notes_clean,
                    now,
                ),
            )

            cursor.execute(
                "UPDATE investigations SET updated_at = ? WHERE id = ?;",
                (now, inv_id),
            )

            AuditService.append_event_with_cursor(
                cursor,
                investigation_id=inv_id,
                action="CONTEXTUAL_FINDING_REVIEWED",
                entity_type="CONTEXTUAL_FINDING",
                entity_id=finding_id,
                actor=reviewer_clean,
                summary=(
                    f"Human review recorded on contextual finding '{f_row['title']}': "
                    f"{prev_status} -> {norm_status}"
                    + (f" ({notes_clean[:80]})" if notes_clean else "")
                ),
                metadata={
                    "case_code": case_code,
                    "finding_id": finding_id,
                    "analysis_id": analysis_id,
                    "previous_status": prev_status,
                    "new_status": norm_status,
                    "reviewer": reviewer_clean,
                    "reviewer_user_id": reviewer_user_id,
                    "notes": notes_clean,
                },
                actor_user_id=reviewer_user_id,
                actor_role=current_user.role if current_user else None,
                event_origin="AUTHENTICATED_HUMAN" if current_user else "SYSTEM",
                created_at=now,
            )

        return ContextService.get_contextual_finding_by_id(finding_id)

    @staticmethod
    def backfill_phase4_context_for_existing_investigations() -> None:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT i.id
                FROM investigations i
                JOIN documents d ON d.investigation_id = i.id
                WHERE d.processing_status = 'COMPLETED';
                """
            )
            inv_ids = [r["id"] for r in cursor.fetchall()]

        for inv_id in inv_ids:
            try:
                with get_db_connection() as conn:
                    has_ca = conn.execute(
                        "SELECT 1 FROM contextual_analyses WHERE investigation_id = ? LIMIT 1;",
                        (inv_id,),
                    ).fetchone()
                if not has_ca:
                    ContextService.run_investigation_context_analysis(inv_id)
            except Exception:
                pass
