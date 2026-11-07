from typing import List, Optional
from pydantic import BaseModel, Field


class BoundingBoxSchema(BaseModel):
    x0: float = Field(..., description="Left X coordinate")
    y0: float = Field(..., description="Top Y coordinate")
    x1: float = Field(..., description="Right X coordinate")
    y1: float = Field(..., description="Bottom Y coordinate")
    page_width: float = Field(default=0.0, description="Source page/image width")
    page_height: float = Field(default=0.0, description="Source page/image height")


class FontMetadataItem(BaseModel):
    font_name: str
    font_size: float
    span_count: int = 1


class ClassificationCandidateSchema(BaseModel):
    document_type: str
    display_label: str
    confidence: float
    matched_signals: List[str] = Field(default_factory=list)


class DocumentClassificationSchema(BaseModel):
    document_type: str
    display_label: str
    confidence: float
    is_certain: bool
    status_label: str
    signals: List[str] = Field(default_factory=list)
    candidates: List[ClassificationCandidateSchema] = Field(default_factory=list)


class LayoutRegionResponse(BaseModel):
    id: str
    document_id: str
    page_number: int
    region_type: str
    reading_order: int = 0
    parent_region_id: Optional[str] = None
    label: str
    text_content: str
    bounding_box: BoundingBoxSchema
    extraction_method: str
    confidence: float
    created_at: str


class TableCellResponse(BaseModel):
    id: str
    table_id: str
    document_id: str
    page_number: int
    row_index: int
    col_index: int
    cell_text: str
    is_header: bool = False
    bounding_box: BoundingBoxSchema
    confidence: float


class ExtractedTableResponse(BaseModel):
    id: str
    table_identifier: str
    document_id: str
    page_number: int
    row_count: int
    column_count: int
    headers: List[str] = Field(default_factory=list)
    bounding_box: BoundingBoxSchema
    extraction_method: str
    confidence: float
    cells: List[TableCellResponse] = Field(default_factory=list)
    created_at: str


class ExtractedEntityResponse(BaseModel):
    id: str
    document_id: str
    investigation_id: str
    page_number: int
    entity_type: str
    raw_value: str
    normalized_value: str
    bounding_box: BoundingBoxSchema
    extraction_method: str
    confidence: float
    source_reference: str
    created_at: str


class ExtractionRecordResponse(BaseModel):
    id: str
    document_id: str
    page_number: int
    block_index: int = 0
    extracted_text: str
    field_name: Optional[str] = None
    field_value: Optional[str] = None
    bounding_box: BoundingBoxSchema
    extraction_method: str
    confidence: float
    source_reference: str
    font_name: Optional[str] = None
    font_size: Optional[float] = None
    created_at: str


class DocumentPageResponse(BaseModel):
    id: str
    document_id: str
    page_number: int
    width: float
    height: float
    extraction_method: str
    is_scanned_page: bool
    raw_text: str
    char_count: int
    block_count: int
    average_confidence: float
    fonts: List[FontMetadataItem] = Field(default_factory=list)
    extractions: List[ExtractionRecordResponse] = Field(default_factory=list)
    layout_regions: List[LayoutRegionResponse] = Field(default_factory=list)
    tables: List[ExtractedTableResponse] = Field(default_factory=list)
    entities: List[ExtractedEntityResponse] = Field(default_factory=list)
    created_at: str


class DocumentSummaryResponse(BaseModel):
    id: str
    investigation_id: str
    filename: str
    file_type: str
    mime_type: str
    file_size_bytes: int
    sha256_hash: str
    page_count: int
    extraction_method_summary: str
    is_scanned: bool
    average_confidence: float
    extracted_char_count: int
    document_type: str = "OTHER_UNKNOWN"
    document_type_label: str = "Other / Unknown"
    classification_confidence: float = 0.0
    classification_is_certain: bool = False
    classification_signals: List[str] = Field(default_factory=list)
    layout_region_count: int = 0
    table_count: int = 0
    entity_count: int = 0
    forensic_status: str = "NOT_ANALYZED"
    latest_analysis_id: Optional[str] = None
    forensic_findings_count: int = 0
    forensic_analyzed_at: Optional[str] = None
    processing_status: str
    error_message: Optional[str] = None
    uploaded_at: str
    processed_at: Optional[str] = None


class DocumentDetailResponse(DocumentSummaryResponse):
    classification: DocumentClassificationSchema
    pages: List[DocumentPageResponse] = Field(default_factory=list)
    structured_fields: List[ExtractionRecordResponse] = Field(default_factory=list)
    layout_regions: List[LayoutRegionResponse] = Field(default_factory=list)
    tables: List[ExtractedTableResponse] = Field(default_factory=list)
    entities: List[ExtractedEntityResponse] = Field(default_factory=list)


class DocumentExtractionBundleResponse(BaseModel):
    document_id: str
    investigation_id: str
    filename: str
    sha256_hash: str
    page_count: int
    extraction_method_summary: str
    is_scanned: bool
    average_confidence: float
    document_type: str
    document_type_label: str
    classification_confidence: float
    classification_is_certain: bool
    total_blocks: int
    structured_field_count: int
    layout_region_count: int = 0
    table_count: int = 0
    entity_count: int = 0
    full_text: str
    structured_fields: List[ExtractionRecordResponse] = Field(default_factory=list)
    extractions: List[ExtractionRecordResponse] = Field(default_factory=list)
    layout_regions: List[LayoutRegionResponse] = Field(default_factory=list)
    tables: List[ExtractedTableResponse] = Field(default_factory=list)
    entities: List[ExtractedEntityResponse] = Field(default_factory=list)


class MultiDocumentUploadResponse(BaseModel):
    investigation_id: str
    uploaded_count: int
    documents: List[DocumentSummaryResponse]
