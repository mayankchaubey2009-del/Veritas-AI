from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ReasoningGenerateRequest(BaseModel):
    actor: str = Field(
        default="Dr. Elena Rostova (Principal Forensic Analyst)",
        min_length=2,
        max_length=120,
    )
    use_ai_provider_if_available: bool = Field(
        default=True,
        description="Whether to attempt optional Gemini synthesis before deterministic fallback.",
    )


class DossierGenerateRequest(BaseModel):
    actor: str = Field(
        default="Dr. Elena Rostova (Principal Forensic Analyst)",
        min_length=2,
        max_length=120,
    )
    title: Optional[str] = Field(
        default=None,
        max_length=240,
        description="Optional custom title for the generated dossier version.",
    )
    regenerate_reasoning: bool = Field(
        default=True,
        description="Whether to run a fresh evidence-grounded reasoning pass prior to dossier compilation.",
    )


class DossierReviewRequest(BaseModel):
    review_status: str = Field(
        ...,
        description="Human review status: APPROVED, UNDER_REVIEW, REQUIRES_REVISION, UNAPPROVED_AI_ASSISTED, or ARCHIVED.",
    )
    reviewer: str = Field(
        default="",
        max_length=120,
        description="Optional fallback reviewer label when invoked outside HTTP session; in HTTP requests, authenticated session identity takes precedence.",
    )
    notes: str = Field(
        default="",
        max_length=3000,
        description="Human review notes documenting the sign-off rationale or required revisions.",
    )


class EvidencePageRefSchema(BaseModel):
    document_id: str
    filename: str
    page_number: int


class EvidenceManifestItemSchema(BaseModel):
    evidence_id: str
    source_type: str
    source_record_id: str
    document_id: Optional[str] = None
    filename: str = ""
    document_sha256: str = ""
    page_number: int = 1
    summary: str
    raw_value: str = ""
    normalized_value: str = ""
    confidence_score: float = 1.0
    review_status: str = "REQUIRES_REVIEW"


class EvidenceGroundedClaimSchema(BaseModel):
    claim_id: str
    section_key: str
    claim_text: str
    claim_type: str
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    contradicting_evidence_ids: List[str] = Field(default_factory=list)
    document_ids: List[str] = Field(default_factory=list)
    page_references: List[EvidencePageRefSchema] = Field(default_factory=list)
    reasoning_method: str
    confidence_score: float = 1.0
    confidence_interpretation: str
    is_human_confirmed: bool = False


class RejectedClaimLogSchema(BaseModel):
    attempted_claim_text: str
    attempted_claim_type: str
    rejection_reason: str


class ReasoningSectionSchema(BaseModel):
    section_key: str
    section_code: str
    title: str
    narrative: str
    claim_ids: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)


class InvestigationQuestionSchema(BaseModel):
    question_id: str
    question_text: str
    rationale: str
    priority: str
    related_evidence_ids: List[str] = Field(default_factory=list)
    document_ids: List[str] = Field(default_factory=list)
    page_references: List[EvidencePageRefSchema] = Field(default_factory=list)


class VerificationStepSchema(BaseModel):
    step_id: str
    step_number: int
    title: str
    action_description: str
    target_evidence_ids: List[str] = Field(default_factory=list)
    document_ids: List[str] = Field(default_factory=list)
    priority: str = "HIGH"


class SourceDocumentHashItemSchema(BaseModel):
    document_id: str
    filename: str
    document_type: str
    sha256_hash: str
    page_count: int


class InvestigationReasoningResponse(BaseModel):
    reasoning_run_id: str
    investigation_id: str
    case_code: str
    investigation_title: str
    reasoning_engine_version: str
    ai_provider: str
    ai_model: str
    prompt_version: str
    ai_assisted: bool
    fallback_used: bool
    fallback_reason: Optional[str] = None
    source_analysis_ids: Dict[str, Any] = Field(default_factory=dict)
    source_document_hashes: List[SourceDocumentHashItemSchema] = Field(
        default_factory=list
    )
    evidence_manifest: Dict[str, EvidenceManifestItemSchema] = Field(
        default_factory=dict
    )
    sections: List[ReasoningSectionSchema] = Field(default_factory=list)
    claims: List[EvidenceGroundedClaimSchema] = Field(default_factory=list)
    rejected_claims_count: int = 0
    rejected_claims_log: List[RejectedClaimLogSchema] = Field(default_factory=list)
    questions: List[InvestigationQuestionSchema] = Field(default_factory=list)
    verification_steps: List[VerificationStepSchema] = Field(default_factory=list)
    processing_duration_ms: float
    created_at: str


class DossierReviewRecordSchema(BaseModel):
    review_id: str
    dossier_id: str
    investigation_id: str
    previous_status: str
    new_status: str
    reviewer: str
    reviewer_user_id: Optional[str] = None
    notes: str
    created_at: str


class DossierSummaryResponse(BaseModel):
    dossier_id: str
    investigation_id: str
    case_code: str
    reasoning_run_id: str
    version_number: int
    title: str
    status: str
    reasoning_engine_version: str
    ai_provider: str
    ai_model: str
    prompt_version: str
    pdf_size_bytes: int
    pdf_sha256_hash: str
    json_size_bytes: int
    json_sha256_hash: str
    dossier_sha256_hash: str
    review_status: str
    reviewed_by: Optional[str] = None
    reviewed_by_user_id: Optional[str] = None
    review_notes: Optional[str] = None
    reviewed_at: Optional[str] = None
    generated_by: str
    generated_by_user_id: Optional[str] = None
    created_at: str


class DossierDetailResponse(DossierSummaryResponse):
    source_analysis_ids: Dict[str, Any] = Field(default_factory=dict)
    source_document_hashes: List[SourceDocumentHashItemSchema] = Field(
        default_factory=list
    )
    reasoning: InvestigationReasoningResponse
    review_history: List[DossierReviewRecordSchema] = Field(default_factory=list)
