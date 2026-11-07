from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.schemas.document import BoundingBoxSchema


class ForensicAnalysisRequest(BaseModel):
    actor: str = Field(
        default="Lead Forensic Analyst",
        min_length=2,
        max_length=120,
        description="Identity of the analyst or automated pipeline triggering the analysis.",
    )
    ela_jpeg_quality: int = Field(
        default=90,
        ge=60,
        le=98,
        description="JPEG recompression quality level (Q) used for Error Level Analysis.",
    )
    ela_amplification_scale: float = Field(
        default=18.0,
        ge=5.0,
        le=40.0,
        description="Pixel-difference amplification factor for ELA diagnostic visualization.",
    )
    force_reanalyze: bool = Field(
        default=True,
        description="Whether to run a fresh analysis even if a prior analysis exists.",
    )


class ForensicReviewRequest(BaseModel):
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
        description="Analyst review notes, verification steps performed, or benign justification.",
    )


class ForensicReviewRecordResponse(BaseModel):
    review_id: str
    finding_id: str
    analysis_id: str
    investigation_id: str
    document_id: str
    previous_status: str
    new_status: str
    reviewer: str
    notes: str
    created_at: str


class ForensicArtifactResponse(BaseModel):
    artifact_id: str
    analysis_id: str
    investigation_id: str
    document_id: str
    page_number: int
    artifact_type: str
    module_name: str
    title: str
    description: str
    mime_type: str
    file_size_bytes: int
    sha256_hash: str
    source_document_sha256: str
    is_derived_from_pdf_render: bool
    parameters: Dict[str, Any] = Field(default_factory=dict)
    stats: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ForensicFindingResponse(BaseModel):
    finding_id: str
    investigation_id: str
    document_id: str
    document_sha256: str
    analysis_id: str
    module_name: str
    finding_category: str
    severity: str
    title: str
    observation: str
    technical_explanation: str
    possible_benign_explanations: List[str] = Field(default_factory=list)
    confidence_score: float
    confidence_interpretation: str
    limitations: str = ""
    page_number: int
    bounding_box: Optional[BoundingBoxSchema] = None
    evidence_reference: str
    artifact_id: Optional[str] = None
    analysis_parameters: Dict[str, Any] = Field(default_factory=dict)
    evidence_metrics: Dict[str, Any] = Field(default_factory=dict)
    recommended_human_action: str
    review_status: str
    reviewer: Optional[str] = None
    review_notes: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_history: List[ForensicReviewRecordResponse] = Field(default_factory=list)
    created_at: str


class ModuleExecutionSummarySchema(BaseModel):
    module_name: str
    display_name: str
    status: str  # "COMPLETED" | "NOT_APPLICABLE" | "SKIPPED" | "FAILED"
    findings_count: int = 0
    duration_ms: float = 0.0
    methodology_summary: str = ""
    limitations_note: str = ""


class PdfEmbeddedImageInfoSchema(BaseModel):
    page_number: int
    xref: int
    width: int
    height: int
    bits_per_component: int
    colorspace: str
    compression_filter: str
    name: str


class PdfFontResourceInfoSchema(BaseModel):
    page_number: int
    xref: int
    font_name: str
    font_type: str
    encoding: str
    is_subset: bool


class PdfAnnotationInfoSchema(BaseModel):
    page_number: int
    annot_type: str
    rect: List[float]
    content: str
    author: str


class DocumentMetadataInspectionSchema(BaseModel):
    source_format: str  # "PDF" | "JPG" | "JPEG" | "PNG"
    is_pdf: bool
    creator: str = ""
    producer: str = ""
    creation_date_raw: str = ""
    modification_date_raw: str = ""
    title: str = ""
    author: str = ""
    subject: str = ""
    keywords: str = ""
    pdf_version: str = ""
    is_encrypted: bool = False
    incremental_Save_eof_count: int = 1
    xref_object_count: int = 0
    page_dimensions: List[Dict[str, Any]] = Field(default_factory=list)
    embedded_images: List[PdfEmbeddedImageInfoSchema] = Field(default_factory=list)
    font_resources: List[PdfFontResourceInfoSchema] = Field(default_factory=list)
    annotations: List[PdfAnnotationInfoSchema] = Field(default_factory=list)
    raster_header_info: Dict[str, Any] = Field(default_factory=dict)


class ForensicAnalysisDetailResponse(BaseModel):
    analysis_id: str
    investigation_id: str
    document_id: str
    filename: str
    file_type: str
    document_sha256: str
    original_file_intact: bool
    status: str
    modules_executed: List[str] = Field(default_factory=list)
    module_summaries: List[ModuleExecutionSummarySchema] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    metadata_inspection: DocumentMetadataInspectionSchema
    findings_count: int = 0
    high_severity_count: int = 0
    medium_severity_count: int = 0
    low_severity_count: int = 0
    informational_count: int = 0
    pending_review_count: int = 0
    reviewed_count: int = 0
    processing_duration_ms: float = 0.0
    started_at: str
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    artifacts: List[ForensicArtifactResponse] = Field(default_factory=list)
    findings: List[ForensicFindingResponse] = Field(default_factory=list)
