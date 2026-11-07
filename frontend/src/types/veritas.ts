export type NavigationSectionId =
  | "command-centre"
  | "investigations"
  | "document-intelligence"
  | "visual-forensics"
  | "contextual-intelligence"
  | "cross-document-analysis"
  | "evidence-explorer"
  | "investigation-dossiers"
  | "audit-history"
  | "settings";

export type InvestigationStatus =
  | "OPEN"
  | "IN_PROGRESS"
  | "UNDER_REVIEW"
  | "COMPLETED"
  | "ARCHIVED";

export type InvestigationPriority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type InvestigationClassification =
  | "FINANCIAL_FORENSICS"
  | "CONTRACT_INTEGRITY"
  | "IDENTITY_VERIFICATION"
  | "REGULATORY_COMPLIANCE"
  | "SUPPLY_CHAIN_AUDIT"
  | "GENERAL_FORENSICS";

export interface Investigation {
  id: string;
  case_code: string;
  title: string;
  description: string;
  status: InvestigationStatus;
  priority: InvestigationPriority;
  classification: InvestigationClassification;
  lead_investigator: string;
  document_count: number;
  findings_count: number;
  pending_review_count: number;
  created_at: string;
  updated_at: string;
}

export interface AuditLogEntry {
  id: string;
  sequence_number?: number | null;
  investigation_id?: string | null;
  case_code?: string | null;
  investigation_title?: string | null;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  actor: string;
  actor_user_id?: string | null;
  actor_role?: string | null;
  event_origin?:
    | "AUTHENTICATED_HUMAN"
    | "SYSTEM"
    | "BACKGROUND_WORKER"
    | "HISTORICAL_SEED_SIMULATION"
    | string;
  summary: string;
  metadata: Record<string, unknown>;
  prev_hash?: string;
  event_hash?: string;
  created_at: string;
}

export interface BoundingBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  page_width: number;
  page_height: number;
}

export interface FontMetadataItem {
  font_name: string;
  font_size: number;
  span_count: number;
}

export interface ClassificationCandidate {
  document_type: string;
  display_label: string;
  confidence: number;
  matched_signals: string[];
}

export interface DocumentClassification {
  document_type: string;
  display_label: string;
  confidence: number;
  is_certain: boolean;
  status_label: string;
  signals: string[];
  candidates: ClassificationCandidate[];
}

export interface LayoutRegion {
  id: string;
  document_id: string;
  page_number: number;
  region_type:
    | "DOCUMENT_TITLE"
    | "HEADER"
    | "SECTION_HEADING"
    | "PARAGRAPH"
    | "TABLE"
    | "KEY_VALUE_REGION"
    | "SIGNATURE_REGION"
    | "STAMP_REGION"
    | "FOOTER"
    | string;
  reading_order: number;
  parent_region_id?: string | null;
  label: string;
  text_content: string;
  bounding_box: BoundingBox;
  extraction_method: string;
  confidence: number;
  created_at: string;
}

export interface TableCell {
  id: string;
  table_id: string;
  document_id: string;
  page_number: number;
  row_index: number;
  col_index: number;
  cell_text: string;
  is_header: boolean;
  bounding_box: BoundingBox;
  confidence: number;
}

export interface ExtractedTable {
  id: string;
  table_identifier: string;
  document_id: string;
  page_number: number;
  row_count: number;
  column_count: number;
  headers: string[];
  bounding_box: BoundingBox;
  extraction_method: string;
  confidence: number;
  cells: TableCell[];
  created_at: string;
}

export interface ExtractedEntity {
  id: string;
  document_id: string;
  investigation_id: string;
  page_number: number;
  entity_type:
    | "PERSON_NAME"
    | "COMPANY_NAME"
    | "INVOICE_NUMBER"
    | "TAX_IDENTIFIER"
    | "DATE"
    | "MONETARY_AMOUNT"
    | "ACCOUNT_REFERENCE"
    | "ADDRESS"
    | string;
  raw_value: string;
  normalized_value: string;
  bounding_box: BoundingBox;
  extraction_method: string;
  confidence: number;
  source_reference: string;
  created_at: string;
}

export interface ExtractionRecord {
  id: string;
  document_id: string;
  page_number: number;
  block_index: number;
  extracted_text: string;
  field_name?: string | null;
  field_value?: string | null;
  bounding_box: BoundingBox;
  extraction_method: "NATIVE_PDF" | "VISUAL_OCR" | string;
  confidence: number;
  source_reference: string;
  font_name?: string | null;
  font_size?: number | null;
  created_at: string;
}

export interface DocumentPage {
  id: string;
  document_id: string;
  page_number: number;
  width: number;
  height: number;
  extraction_method: "NATIVE_PDF" | "VISUAL_OCR" | string;
  is_scanned_page: boolean;
  raw_text: string;
  char_count: number;
  block_count: number;
  average_confidence: number;
  fonts: FontMetadataItem[];
  extractions: ExtractionRecord[];
  layout_regions: LayoutRegion[];
  tables: ExtractedTable[];
  entities: ExtractedEntity[];
  created_at: string;
}

export interface DocumentSummary {
  id: string;
  investigation_id: string;
  filename: string;
  file_type: string;
  mime_type: string;
  file_size_bytes: number;
  sha256_hash: string;
  page_count: number;
  extraction_method_summary: "NATIVE_PDF" | "VISUAL_OCR" | "HYBRID_PDF_OCR" | string;
  is_scanned: boolean;
  average_confidence: number;
  extracted_char_count: number;
  document_type: string;
  document_type_label: string;
  classification_confidence: number;
  classification_is_certain: boolean;
  classification_signals: string[];
  layout_region_count: number;
  table_count: number;
  entity_count: number;
  forensic_status?: string;
  latest_analysis_id?: string | null;
  forensic_findings_count?: number;
  forensic_analyzed_at?: string | null;
  processing_status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED" | string;
  error_message?: string | null;
  uploaded_at: string;
  processed_at?: string | null;
}

export interface ForensicReviewRecord {
  review_id: string;
  finding_id: string;
  analysis_id: string;
  investigation_id: string;
  document_id: string;
  previous_status: string;
  new_status: string;
  reviewer: string;
  notes: string;
  created_at: string;
}

export interface ForensicArtifact {
  artifact_id: string;
  analysis_id: string;
  investigation_id: string;
  document_id: string;
  page_number: number;
  artifact_type:
    | "ELA_DERIVED_IMAGE"
    | "LOCAL_VARIANCE_HEATMAP"
    | "SIGNATURE_CROP"
    | "STAMP_CROP"
    | "PAGE_RENDER"
    | string;
  module_name: string;
  title: string;
  description: string;
  mime_type: string;
  file_size_bytes: number;
  sha256_hash: string;
  source_document_sha256: string;
  is_derived_from_pdf_render: boolean;
  parameters: Record<string, unknown>;
  stats: Record<string, unknown>;
  created_at: string;
}

export interface ForensicFinding {
  finding_id: string;
  investigation_id: string;
  document_id: string;
  document_sha256: string;
  analysis_id: string;
  module_name:
    | "MODULE_A_IMAGE_CONSISTENCY"
    | "MODULE_B_ELA"
    | "MODULE_C_TYPOGRAPHY"
    | "MODULE_D_ALIGNMENT"
    | "MODULE_E_PDF_METADATA"
    | "MODULE_F_SIGNATURE_STAMP"
    | "MODULE_G_TEXT_VISUAL"
    | string;
  finding_category: string;
  severity: "INFORMATIONAL" | "LOW" | "MEDIUM" | "HIGH" | string;
  title: string;
  observation: string;
  technical_explanation: string;
  possible_benign_explanations: string[];
  confidence_score: number;
  confidence_interpretation: string;
  limitations: string;
  page_number: number;
  bounding_box?: BoundingBox | null;
  evidence_reference: string;
  artifact_id?: string | null;
  analysis_parameters: Record<string, unknown>;
  evidence_metrics: Record<string, unknown>;
  recommended_human_action: string;
  review_status:
    | "REQUIRES_REVIEW"
    | "REVIEWED"
    | "INCONCLUSIVE"
    | "CONFIRMED"
    | "DISMISSED"
    | string;
  reviewer?: string | null;
  review_notes?: string | null;
  reviewed_at?: string | null;
  review_history: ForensicReviewRecord[];
  created_at: string;
}

export interface ModuleExecutionSummary {
  module_name: string;
  display_name: string;
  status: string;
  findings_count: number;
  duration_ms: number;
  methodology_summary: string;
  limitations_note: string;
}

export interface PdfEmbeddedImageInfo {
  page_number: number;
  xref: number;
  width: number;
  height: number;
  bits_per_component: number;
  colorspace: string;
  compression_filter: string;
  name: string;
}

export interface PdfFontResourceInfo {
  page_number: number;
  xref: number;
  font_name: string;
  font_type: string;
  encoding: string;
  is_subset: boolean;
}

export interface PdfAnnotationInfo {
  page_number: number;
  annot_type: string;
  rect: number[];
  content: string;
  author: string;
}

export interface DocumentMetadataInspection {
  source_format: string;
  is_pdf: boolean;
  creator: string;
  producer: string;
  creation_date_raw: string;
  modification_date_raw: string;
  title: string;
  author: string;
  subject: string;
  keywords: string;
  pdf_version: string;
  is_encrypted: boolean;
  incremental_Save_eof_count: number;
  xref_object_count: number;
  page_dimensions: Array<Record<string, unknown>>;
  embedded_images: PdfEmbeddedImageInfo[];
  font_resources: PdfFontResourceInfo[];
  annotations: PdfAnnotationInfo[];
  raster_header_info: Record<string, unknown>;
}

export interface ForensicAnalysisDetail {
  analysis_id: string;
  investigation_id: string;
  document_id: string;
  filename: string;
  file_type: string;
  document_sha256: string;
  original_file_intact: boolean;
  status: string;
  modules_executed: string[];
  module_summaries: ModuleExecutionSummary[];
  parameters: Record<string, unknown>;
  metadata_inspection: DocumentMetadataInspection;
  findings_count: number;
  high_severity_count: number;
  medium_severity_count: number;
  low_severity_count: number;
  informational_count: number;
  pending_review_count: number;
  reviewed_count: number;
  processing_duration_ms: number;
  started_at: string;
  completed_at?: string | null;
  error_message?: string | null;
  created_at: string;
  artifacts: ForensicArtifact[];
  findings: ForensicFinding[];
}

export interface EvidenceValueItem {
  document_id: string;
  filename: string;
  document_type: string;
  document_sha256: string;
  page_number: number;
  entity_id?: string | null;
  field_label: string;
  raw_value: string;
  normalized_value: string;
  bounding_box?: BoundingBox | null;
  extraction_method: string;
  confidence: number;
}

export interface DocumentReferenceItem {
  document_id: string;
  filename: string;
  document_type: string;
  document_sha256: string;
  page_numbers: number[];
}

export interface ContextualReviewRecord {
  review_id: string;
  finding_id: string;
  analysis_id: string;
  investigation_id: string;
  previous_status: string;
  new_status: string;
  reviewer: string;
  notes: string;
  created_at: string;
}

export interface ContextualFinding {
  finding_id: string;
  analysis_id: string;
  investigation_id: string;
  finding_type: string;
  severity: "HIGH" | "MEDIUM" | "LOW" | "INFORMATIONAL" | string;
  status:
    | "CONFIRMED_DATA_MISMATCH"
    | "POTENTIAL_INCONSISTENCY"
    | "MISSING_INFORMATION"
    | "CONSISTENT_EVIDENCE"
    | "INCONCLUSIVE_RESULT"
    | string;
  title: string;
  description: string;
  document_references: DocumentReferenceItem[];
  evidence_values: EvidenceValueItem[];
  comparison_method: string;
  matching_rationale: string;
  confidence_score: number;
  confidence_interpretation: string;
  possible_explanations: string[];
  recommended_human_action: string;
  review_status:
    | "REQUIRES_REVIEW"
    | "REVIEWED"
    | "INCONCLUSIVE"
    | "CONFIRMED"
    | "DISMISSED"
    | string;
  reviewer?: string | null;
  review_notes?: string | null;
  reviewed_at?: string | null;
  review_history: ContextualReviewRecord[];
  created_at: string;
}

export interface EntityMatchCluster {
  match_id: string;
  analysis_id: string;
  investigation_id: string;
  entity_type: string;
  canonical_value: string;
  match_status:
    | "EXACT_MATCH"
    | "UNCERTAIN_OCR_NORMALIZED_MATCH"
    | "SINGLETON_UNCORROBORATED"
    | string;
  confidence_score: number;
  matching_rationale: string;
  document_count: number;
  member_entities: EvidenceValueItem[];
  created_at: string;
}

export interface GraphNode {
  node_id: string;
  node_type:
    | "DOCUMENT"
    | "COMPANY"
    | "PERSON"
    | "INVOICE"
    | "BANK_ACCOUNT"
    | "TRANSACTION"
    | "AMOUNT"
    | "DATE"
    | string;
  label: string;
  subtitle: string;
  status: "CONTRADICTION" | "CONSISTENT" | "NEUTRAL" | string;
  document_id?: string | null;
  page_number?: number | null;
  bounding_box?: BoundingBox | null;
  metadata: Record<string, unknown>;
}

export interface GraphEdge {
  relationship_id: string;
  source_node_id: string;
  source_node_type: string;
  source_label: string;
  target_node_id: string;
  target_node_type: string;
  target_label: string;
  edge_type:
    | "MENTIONS"
    | "ISSUED_BY"
    | "PAID_TO"
    | "REFERENCES"
    | "SUPPORTS"
    | "CONTRADICTS"
    | "MATCHES"
    | "RELATED_TO"
    | string;
  confidence_score: number;
  matching_rationale: string;
  source_evidence: Record<string, unknown>;
}

export interface InvestigationEntityGraph {
  investigation_id: string;
  analysis_id: string;
  node_count: number;
  edge_count: number;
  contradiction_edge_count: number;
  supporting_edge_count: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface FinancialValidationResult {
  validation_id: string;
  analysis_id: string;
  investigation_id: string;
  document_id: string;
  filename: string;
  document_type: string;
  check_type:
    | "INVOICE_LINE_ITEM_SUM_TO_TOTAL"
    | "BANK_OPENING_DEBITS_CLOSING_RECONCILIATION"
    | "CROSS_DOC_SETTLEMENT_RECONCILIATION"
    | string;
  status:
    | "CONFIRMED_DATA_MISMATCH"
    | "POTENTIAL_INCONSISTENCY"
    | "MISSING_INFORMATION"
    | "CONSISTENT_EVIDENCE"
    | "INCONCLUSIVE_RESULT"
    | string;
  expected_value: string;
  observed_value: string;
  discrepancy_amount: string;
  currency: string;
  formula_used: string;
  details: Record<string, unknown>;
  page_number: number;
  bounding_box?: BoundingBox | null;
  created_at: string;
}

export interface TimelineEvent {
  event_id: string;
  date_iso: string;
  event_type: string;
  title: string;
  description: string;
  status: "CHRONOLOGICALLY_CONSISTENT" | "CHRONOLOGY_WARNING" | string;
  document_id: string;
  filename: string;
  document_sha256: string;
  page_number: number;
  raw_date_value: string;
  bounding_box?: BoundingBox | null;
}

export interface ContextualAnalysisBundle {
  analysis_id: string;
  investigation_id: string;
  case_code: string;
  investigation_title: string;
  status: string;
  documents_analyzed_count: number;
  entities_resolved_count: number;
  relationships_discovered_count: number;
  consistent_matches_count: number;
  potential_contradictions_count: number;
  confirmed_mismatches_count: number;
  missing_information_count: number;
  inconclusive_count: number;
  financial_checks_count: number;
  pending_review_count: number;
  reviewed_count: number;
  processing_duration_ms: number;
  started_at: string;
  completed_at?: string | null;
  created_at: string;
  entity_matches: EntityMatchCluster[];
  graph: InvestigationEntityGraph;
  financial_validations: FinancialValidationResult[];
  timeline_events: TimelineEvent[];
  findings: ContextualFinding[];
}

export interface EvidencePageRef {
  document_id: string;
  filename: string;
  page_number: number;
}

export interface EvidenceManifestItem {
  evidence_id: string;
  source_type:
    | "DOCUMENT"
    | "TABLE"
    | "VISUAL_FORENSIC_FINDING"
    | "FINANCIAL_VALIDATION"
    | "CONTEXTUAL_FINDING"
    | "ENTITY_RESOLUTION"
    | string;
  source_record_id: string;
  document_id?: string | null;
  filename: string;
  document_sha256: string;
  page_number: number;
  summary: string;
  raw_value: string;
  normalized_value: string;
  confidence_score: number;
  review_status: string;
}

export interface EvidenceGroundedClaim {
  claim_id: string;
  section_key: string;
  claim_text: string;
  claim_type:
    | "DIRECTLY_OBSERVED_FACT"
    | "DETERMINISTIC_CALCULATION_RESULT"
    | "AUTOMATED_TECHNICAL_OBSERVATION"
    | "POTENTIAL_INTERPRETATION"
    | "HUMAN_CONFIRMED_CONCLUSION"
    | "UNKNOWN_OR_MISSING_INFORMATION"
    | string;
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  document_ids: string[];
  page_references: EvidencePageRef[];
  reasoning_method: string;
  confidence_score: number;
  confidence_interpretation: string;
  is_human_confirmed: boolean;
}

export interface RejectedClaimLog {
  attempted_claim_text: string;
  attempted_claim_type: string;
  rejection_reason: string;
}

export interface ReasoningSection {
  section_key: string;
  section_code: string;
  title: string;
  narrative: string;
  claim_ids: string[];
  evidence_ids: string[];
}

export interface InvestigationQuestion {
  question_id: string;
  question_text: string;
  rationale: string;
  priority: "HIGH" | "MEDIUM" | "LOW" | string;
  related_evidence_ids: string[];
  document_ids: string[];
  page_references: EvidencePageRef[];
}

export interface VerificationStep {
  step_id: string;
  step_number: number;
  title: string;
  action_description: string;
  target_evidence_ids: string[];
  document_ids: string[];
  priority: "HIGH" | "MEDIUM" | "LOW" | string;
}

export interface SourceDocumentHashItem {
  document_id: string;
  filename: string;
  document_type: string;
  sha256_hash: string;
  page_count: number;
}

export interface InvestigationReasoning {
  reasoning_run_id: string;
  investigation_id: string;
  case_code: string;
  investigation_title: string;
  reasoning_engine_version: string;
  ai_provider: string;
  ai_model: string;
  prompt_version: string;
  ai_assisted: boolean;
  fallback_used: boolean;
  fallback_reason?: string | null;
  source_analysis_ids: Record<string, unknown>;
  source_document_hashes: SourceDocumentHashItem[];
  evidence_manifest: Record<string, EvidenceManifestItem>;
  sections: ReasoningSection[];
  claims: EvidenceGroundedClaim[];
  rejected_claims_count: number;
  rejected_claims_log: RejectedClaimLog[];
  questions: InvestigationQuestion[];
  verification_steps: VerificationStep[];
  processing_duration_ms: number;
  created_at: string;
}

export interface DossierReviewRecord {
  review_id: string;
  dossier_id: string;
  investigation_id: string;
  previous_status: string;
  new_status: string;
  reviewer: string;
  reviewer_user_id?: string | null;
  reviewer_role?: string | null;
  is_simulated_demo?: boolean;
  notes: string;
  created_at: string;
}

export interface DossierSummary {
  dossier_id: string;
  investigation_id: string;
  case_code: string;
  reasoning_run_id: string;
  version_number: number;
  title: string;
  status: string;
  reasoning_engine_version: string;
  ai_provider: string;
  ai_model: string;
  prompt_version: string;
  pdf_size_bytes: number;
  pdf_sha256_hash: string;
  json_size_bytes: number;
  json_sha256_hash: string;
  dossier_sha256_hash: string;
  review_status:
    | "UNAPPROVED_AI_ASSISTED"
    | "UNDER_REVIEW"
    | "APPROVED"
    | "REQUIRES_REVISION"
    | "ARCHIVED"
    | string;
  reviewed_by?: string | null;
  reviewed_by_user_id?: string | null;
  review_notes?: string | null;
  reviewed_at?: string | null;
  generated_by: string;
  generated_by_user_id?: string | null;
  created_at: string;
}

export interface DossierDetail extends DossierSummary {
  source_analysis_ids: Record<string, unknown>;
  source_document_hashes: SourceDocumentHashItem[];
  reasoning: InvestigationReasoning;
  review_history: DossierReviewRecord[];
}

export interface DocumentDetail extends DocumentSummary {
  classification: DocumentClassification;
  pages: DocumentPage[];
  structured_fields: ExtractionRecord[];
  layout_regions: LayoutRegion[];
  tables: ExtractedTable[];
  entities: ExtractedEntity[];
}

export interface DocumentExtractionBundle {
  document_id: string;
  investigation_id: string;
  filename: string;
  sha256_hash: string;
  page_count: number;
  extraction_method_summary: string;
  is_scanned: boolean;
  average_confidence: number;
  document_type: string;
  document_type_label: string;
  classification_confidence: number;
  classification_is_certain: boolean;
  total_blocks: number;
  structured_field_count: number;
  layout_region_count: number;
  table_count: number;
  entity_count: number;
  full_text: string;
  structured_fields: ExtractionRecord[];
  extractions: ExtractionRecord[];
  layout_regions: LayoutRegion[];
  tables: ExtractedTable[];
  entities: ExtractedEntity[];
}

export interface MultiDocumentUploadResponse {
  investigation_id: string;
  uploaded_count: number;
  documents: DocumentSummary[];
}

export interface InvestigationDetail extends Investigation {
  audit_trail: AuditLogEntry[];
  documents: DocumentSummary[];
  findings: Array<{
    id: string;
    investigation_id: string;
    document_id?: string | null;
    finding_type: string;
    severity: string;
    review_status: string;
    title: string;
    description: string;
    confidence_score: number;
    created_at: string;
  }>;
}

export interface InvestigationCreatePayload {
  title: string;
  description: string;
  priority: InvestigationPriority;
  classification: InvestigationClassification;
  lead_investigator: string;
}

export interface InvestigationUpdatePayload {
  title?: string;
  description?: string;
  status?: InvestigationStatus;
  priority?: InvestigationPriority;
  classification?: InvestigationClassification;
  lead_investigator?: string;
}

export interface DashboardMetrics {
  total_investigations: number;
  active_investigations: number;
  documents_processed: number;
  findings_requiring_review: number;
  total_findings: number;
  processing_events_count: number;
  status_breakdown: Record<string, number>;
  priority_breakdown: Record<string, number>;
}

export interface CommandCentreSummary {
  metrics: DashboardMetrics;
  recent_investigations: Investigation[];
  processing_activity: AuditLogEntry[];
  generated_at: string;
}

export interface SubsystemStatus {
  name: string;
  status: "OPERATIONAL" | "STANDBY" | "DEGRADED" | string;
  phase: string;
  description: string;
}

export interface HealthStatusResponse {
  status: "healthy" | "degraded" | string;
  service: string;
  version: string;
  environment: string;
  uptime_seconds: number;
  timestamp: string;
  database: {
    connected: boolean;
    engine: string;
    sqlite_version?: string;
    schema_version?: string;
    database_file?: string;
    file_size_bytes?: number;
    latency_ms: number;
    tables_initialized?: number;
    record_counts?: {
      investigations: number;
      documents: number;
      extractions?: number;
      layout_regions?: number;
      tables?: number;
      entities?: number;
      findings: number;
      audit_logs: number;
    };
    checked_at: string;
    error?: string;
  };
  subsystems: SubsystemStatus[];
}

export interface SanitizedSystemConfig {
  app_name: string;
  app_version: string;
  environment: string;
  cors_origins: string[];
  database: {
    engine: string;
    file_name?: string;
    sqlite_version?: string;
    schema_version?: string;
    connected: boolean;
    latency_ms: number;
  };
  security: {
    api_keys_exposed_to_client: boolean;
    gemini_key_configured_on_server: boolean;
    cors_restricted: boolean;
    authentication_enforced?: boolean;
    password_kdf?: string;
    allow_self_dossier_approval?: boolean;
    demo_mode_enabled?: boolean;
    max_upload_size_mb?: number;
    max_pdf_pages?: number;
    max_image_pixels?: number;
  };
  audit_integrity?: {
    verified: boolean;
    total_events_checked: number;
    latest_event_hash: string;
  };
  feature_flags: {
    ocr_pipeline_enabled: boolean;
    cv_forensics_enabled: boolean;
    gemini_reasoning_enabled: boolean;
  };
}

export type UserRole = "ADMIN" | "INVESTIGATOR" | "REVIEWER" | "VIEWER" | string;

export interface AuthenticatedUser {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: UserRole;
  title: string;
  is_active: boolean;
  is_demo_account: boolean;
  created_at: string;
  last_login_at?: string | null;
  session_id?: string | null;
  session_expires_at?: string | null;
}

export interface DemoPersonaItem {
  username: string;
  full_name: string;
  role: UserRole;
  title?: string;
  badge_description: string;
}

export interface AuthStatusResponse {
  authenticated: boolean;
  user?: AuthenticatedUser | null;
  session_expires_at?: string | null;
  demo_mode_enabled: boolean;
  bootstrap_available: boolean;
  demo_personas: DemoPersonaItem[];
}

export interface AuthSessionResponse {
  authenticated: boolean;
  access_token: string;
  token_type: string;
  session_token?: string | null;
  user: AuthenticatedUser;
  session_id: string;
  expires_at: string;
  csrf_token: string;
}

export interface AuditVerificationResult {
  verified: boolean;
  chain_valid: boolean;
  tamper_detected: boolean;
  total_events_checked: number;
  head_sequence_number: number;
  latest_event_hash: string;
  genesis_hash: string;
  origin_breakdown: Record<string, number>;
  corrupted_events_count: number;
  corrupted_events: Array<{
    event_id: string;
    sequence_number?: number;
    issue_type: string;
    reason?: string;
    description: string;
  }>;
  verified_at: string;
  architectural_limitations: string[];
}

export interface BackgroundJob {
  id: string;
  investigation_id: string;
  document_id?: string | null;
  job_type: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED" | string;
  stage_label: string;
  progress_percent: number;
  attempt_count: number;
  max_attempts: number;
  idempotency_key?: string | null;
  error_summary?: string | null;
  payload: Record<string, unknown>;
  result_summary: Record<string, unknown>;
  created_by_user_id?: string | null;
  created_by_actor: string;
  queued_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at: string;
}

export interface QualityBenchmarkReport {
  benchmark_version: string;
  evaluated_at: string;
  isolated_from_production_db: boolean;
  specimens_evaluated: number;
  duration_ms: number;
  aggregate_metrics: {
    document_classification_accuracy: number;
    ocr_cer_native_pdf: number;
    ocr_cer_scanned_images: number;
    ocr_cer_overall: number;
    entity_extraction_precision: number;
    entity_extraction_recall: number;
    entity_extraction_f1: number;
    table_cell_extraction_accuracy: number;
    bounding_box_localization_accuracy: number;
    financial_calculation_accuracy: number;
    evidence_reference_completeness: number;
    grounded_claims_verified: string;
  };
  specimen_results: Array<{
    specimen_id: string;
    category: string;
    filename: string;
    file_type: string;
    page_count: number;
    extraction_method: string;
    expected_doc_type: string;
    predicted_doc_type: string;
    classification_match: boolean;
    classification_confidence: number;
    classification_is_certain: boolean;
    cer: number;
    entity_tp: number;
    entity_fp: number;
    entity_fn: number;
    gt_table_cells: number;
    matched_table_cells: number;
    bboxes_valid: string;
    duration_ms: number;
  }>;
  methodology_notes: string[];
}

export interface DatabaseBackupManifest {
  backup_id: string;
  label: string;
  filename: string;
  size_bytes: number;
  sha256_hash: string;
  sqlite_integrity_check: string;
  investigations_count: number;
  documents_count: number;
  audit_logs_count: number;
  created_by: string;
  created_at: string;
  integrity_verified: boolean;
}
