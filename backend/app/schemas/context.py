from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.schemas.document import BoundingBoxSchema


class ContextualAnalysisRequest(BaseModel):
    actor: str = Field(
        default="Dr. Elena Rostova (Principal Forensic Analyst)",
        min_length=2,
        max_length=120,
    )
    force_reanalyze: bool = Field(
        default=True,
        description="Whether to run a fresh cross-document contextual intelligence analysis.",
    )


class ContextualReviewRequest(BaseModel):
    review_status: str = Field(
        ...,
        description="Human review disposition: REVIEWED, INCONCLUSIVE, CONFIRMED, DISMISSED, or REQUIRES_REVIEW.",
    )
    reviewer: str = Field(
        default="Dr. Elena Rostova (Principal Forensic Analyst)",
        min_length=2,
        max_length=120,
    )
    notes: str = Field(
        default="",
        max_length=2000,
    )


class EvidenceValueItemSchema(BaseModel):
    document_id: str
    filename: str
    document_type: str
    document_sha256: str
    page_number: int
    entity_id: Optional[str] = None
    field_label: str = ""
    raw_value: str
    normalized_value: str
    bounding_box: Optional[BoundingBoxSchema] = None
    extraction_method: str = "NATIVE_PDF"
    confidence: float = 1.0


class DocumentReferenceItemSchema(BaseModel):
    document_id: str
    filename: str
    document_type: str
    document_sha256: str
    page_numbers: List[int] = Field(default_factory=list)


class ContextualReviewRecordSchema(BaseModel):
    review_id: str
    finding_id: str
    analysis_id: str
    investigation_id: str
    previous_status: str
    new_status: str
    reviewer: str
    notes: str
    created_at: str


class ContextualFindingResponse(BaseModel):
    finding_id: str
    analysis_id: str
    investigation_id: str
    finding_type: str
    severity: str
    status: str
    title: str
    description: str
    document_references: List[DocumentReferenceItemSchema] = Field(default_factory=list)
    evidence_values: List[EvidenceValueItemSchema] = Field(default_factory=list)
    comparison_method: str
    matching_rationale: str
    confidence_score: float
    confidence_interpretation: str
    possible_explanations: List[str] = Field(default_factory=list)
    recommended_human_action: str
    review_status: str
    reviewer: Optional[str] = None
    review_notes: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_history: List[ContextualReviewRecordSchema] = Field(default_factory=list)
    created_at: str


class EntityMatchClusterResponse(BaseModel):
    match_id: str
    analysis_id: str
    investigation_id: str
    entity_type: str
    canonical_value: str
    match_status: str
    confidence_score: float
    matching_rationale: str
    document_count: int
    member_entities: List[EvidenceValueItemSchema] = Field(default_factory=list)
    created_at: str


class GraphNodeSchema(BaseModel):
    node_id: str
    node_type: str
    label: str
    subtitle: str = ""
    status: str = "NEUTRAL"
    document_id: Optional[str] = None
    page_number: Optional[int] = None
    bounding_box: Optional[BoundingBoxSchema] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphEdgeSchema(BaseModel):
    relationship_id: str
    source_node_id: str
    source_node_type: str
    source_label: str
    target_node_id: str
    target_node_type: str
    target_label: str
    edge_type: str
    confidence_score: float
    matching_rationale: str
    source_evidence: Dict[str, Any] = Field(default_factory=dict)


class InvestigationEntityGraphResponse(BaseModel):
    investigation_id: str
    analysis_id: str
    node_count: int
    edge_count: int
    contradiction_edge_count: int
    supporting_edge_count: int
    nodes: List[GraphNodeSchema] = Field(default_factory=list)
    edges: List[GraphEdgeSchema] = Field(default_factory=list)


class FinancialValidationResultResponse(BaseModel):
    validation_id: str
    analysis_id: str
    investigation_id: str
    document_id: str
    filename: str
    document_type: str
    check_type: str
    status: str
    expected_value: str
    observed_value: str
    discrepancy_amount: str
    currency: str
    formula_used: str
    details: Dict[str, Any] = Field(default_factory=dict)
    page_number: int = 1
    bounding_box: Optional[BoundingBoxSchema] = None
    created_at: str


class TimelineEventSchema(BaseModel):
    event_id: str
    date_iso: str
    event_type: str
    title: str
    description: str
    status: str
    document_id: str
    filename: str
    document_sha256: str
    page_number: int
    raw_date_value: str
    bounding_box: Optional[BoundingBoxSchema] = None


class ContextualAnalysisBundleResponse(BaseModel):
    analysis_id: str
    investigation_id: str
    case_code: str
    investigation_title: str
    status: str
    documents_analyzed_count: int
    entities_resolved_count: int
    relationships_discovered_count: int
    consistent_matches_count: int
    potential_contradictions_count: int
    confirmed_mismatches_count: int
    missing_information_count: int
    inconclusive_count: int
    financial_checks_count: int
    pending_review_count: int
    reviewed_count: int
    processing_duration_ms: float
    started_at: str
    completed_at: Optional[str] = None
    created_at: str
    entity_matches: List[EntityMatchClusterResponse] = Field(default_factory=list)
    graph: InvestigationEntityGraphResponse
    financial_validations: List[FinancialValidationResultResponse] = Field(
        default_factory=list
    )
    timeline_events: List[TimelineEventSchema] = Field(default_factory=list)
    findings: List[ContextualFindingResponse] = Field(default_factory=list)
