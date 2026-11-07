import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Tuple
from app.core.config import settings
from app.core.exceptions import DatabaseOperationException

SCHEMA_VERSION = "2.0.0-phase6"

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS investigations (
        id TEXT PRIMARY KEY,
        case_code TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'OPEN',
        priority TEXT NOT NULL DEFAULT 'HIGH',
        classification TEXT NOT NULL DEFAULT 'GENERAL_FORENSICS',
        lead_investigator TEXT NOT NULL DEFAULT 'Lead Forensic Analyst',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        investigation_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        file_type TEXT NOT NULL,
        mime_type TEXT DEFAULT 'application/octet-stream',
        file_size_bytes INTEGER NOT NULL DEFAULT 0,
        sha256_hash TEXT,
        storage_path TEXT DEFAULT '',
        page_count INTEGER NOT NULL DEFAULT 1,
        extraction_method_summary TEXT NOT NULL DEFAULT 'PENDING',
        is_scanned INTEGER NOT NULL DEFAULT 0,
        average_confidence REAL NOT NULL DEFAULT 0.0,
        extracted_char_count INTEGER NOT NULL DEFAULT 0,
        document_type TEXT NOT NULL DEFAULT 'OTHER_UNKNOWN',
        classification_confidence REAL NOT NULL DEFAULT 0.0,
        classification_is_certain INTEGER NOT NULL DEFAULT 0,
        classification_signals_json TEXT NOT NULL DEFAULT '[]',
        classification_candidates_json TEXT NOT NULL DEFAULT '[]',
        layout_region_count INTEGER NOT NULL DEFAULT 0,
        table_count INTEGER NOT NULL DEFAULT 0,
        entity_count INTEGER NOT NULL DEFAULT 0,
        forensic_status TEXT NOT NULL DEFAULT 'NOT_ANALYZED',
        latest_analysis_id TEXT DEFAULT NULL,
        forensic_findings_count INTEGER NOT NULL DEFAULT 0,
        forensic_analyzed_at TEXT DEFAULT NULL,
        processing_status TEXT NOT NULL DEFAULT 'PENDING',
        error_message TEXT DEFAULT NULL,
        uploaded_at TEXT NOT NULL,
        processed_at TEXT DEFAULT NULL,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS document_pages (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        width REAL NOT NULL DEFAULT 0.0,
        height REAL NOT NULL DEFAULT 0.0,
        extraction_method TEXT NOT NULL,
        is_scanned_page INTEGER NOT NULL DEFAULT 0,
        raw_text TEXT NOT NULL DEFAULT '',
        char_count INTEGER NOT NULL DEFAULT 0,
        block_count INTEGER NOT NULL DEFAULT 0,
        average_confidence REAL NOT NULL DEFAULT 1.0,
        font_summary_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
        UNIQUE(document_id, page_number)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS document_extractions (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        investigation_id TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        block_index INTEGER NOT NULL DEFAULT 0,
        extracted_text TEXT NOT NULL,
        field_name TEXT,
        field_value TEXT,
        bounding_box_json TEXT NOT NULL,
        extraction_method TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 1.0,
        source_reference TEXT NOT NULL,
        font_name TEXT,
        font_size REAL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS document_layout_regions (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        region_type TEXT NOT NULL,
        reading_order INTEGER NOT NULL DEFAULT 0,
        parent_region_id TEXT DEFAULT NULL,
        label TEXT NOT NULL,
        text_content TEXT NOT NULL DEFAULT '',
        bounding_box_json TEXT NOT NULL,
        extraction_method TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 1.0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS document_tables (
        id TEXT PRIMARY KEY,
        table_identifier TEXT NOT NULL,
        document_id TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        row_count INTEGER NOT NULL DEFAULT 0,
        column_count INTEGER NOT NULL DEFAULT 0,
        headers_json TEXT NOT NULL DEFAULT '[]',
        bounding_box_json TEXT NOT NULL,
        extraction_method TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 1.0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS document_table_cells (
        id TEXT PRIMARY KEY,
        table_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        row_index INTEGER NOT NULL,
        col_index INTEGER NOT NULL,
        cell_text TEXT NOT NULL DEFAULT '',
        is_header INTEGER NOT NULL DEFAULT 0,
        bounding_box_json TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 1.0,
        FOREIGN KEY (table_id) REFERENCES document_tables(id) ON DELETE CASCADE,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS document_entities (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        investigation_id TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        entity_type TEXT NOT NULL,
        raw_value TEXT NOT NULL,
        normalized_value TEXT NOT NULL,
        bounding_box_json TEXT NOT NULL,
        extraction_method TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 1.0,
        source_reference TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS findings (
        id TEXT PRIMARY KEY,
        investigation_id TEXT NOT NULL,
        document_id TEXT,
        finding_type TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'MEDIUM',
        review_status TEXT NOT NULL DEFAULT 'REQUIRES_REVIEW',
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        confidence_score REAL DEFAULT 0.0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS forensic_analyses (
        id TEXT PRIMARY KEY,
        investigation_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        document_sha256 TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'COMPLETED',
        modules_executed_json TEXT NOT NULL DEFAULT '[]',
        module_summaries_json TEXT NOT NULL DEFAULT '[]',
        parameters_json TEXT NOT NULL DEFAULT '{}',
        pdf_metadata_json TEXT NOT NULL DEFAULT '{}',
        findings_count INTEGER NOT NULL DEFAULT 0,
        high_severity_count INTEGER NOT NULL DEFAULT 0,
        medium_severity_count INTEGER NOT NULL DEFAULT 0,
        low_severity_count INTEGER NOT NULL DEFAULT 0,
        informational_count INTEGER NOT NULL DEFAULT 0,
        processing_duration_ms REAL NOT NULL DEFAULT 0.0,
        started_at TEXT NOT NULL,
        completed_at TEXT DEFAULT NULL,
        error_message TEXT DEFAULT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS forensic_artifacts (
        id TEXT PRIMARY KEY,
        analysis_id TEXT NOT NULL,
        investigation_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        page_number INTEGER NOT NULL DEFAULT 1,
        artifact_type TEXT NOT NULL,
        module_name TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        mime_type TEXT NOT NULL DEFAULT 'image/png',
        storage_path TEXT NOT NULL,
        file_size_bytes INTEGER NOT NULL DEFAULT 0,
        sha256_hash TEXT NOT NULL,
        source_document_sha256 TEXT NOT NULL,
        is_derived_from_pdf_render INTEGER NOT NULL DEFAULT 0,
        parameters_json TEXT NOT NULL DEFAULT '{}',
        stats_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        FOREIGN KEY (analysis_id) REFERENCES forensic_analyses(id) ON DELETE CASCADE,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS forensic_findings (
        id TEXT PRIMARY KEY,
        investigation_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        document_sha256 TEXT NOT NULL,
        analysis_id TEXT NOT NULL,
        module_name TEXT NOT NULL,
        finding_category TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'LOW',
        title TEXT NOT NULL,
        observation TEXT NOT NULL,
        technical_explanation TEXT NOT NULL,
        possible_benign_explanations_json TEXT NOT NULL DEFAULT '[]',
        confidence_score REAL NOT NULL DEFAULT 0.0,
        confidence_interpretation TEXT NOT NULL,
        limitations TEXT NOT NULL DEFAULT '',
        page_number INTEGER NOT NULL DEFAULT 1,
        bounding_box_json TEXT DEFAULT NULL,
        evidence_reference TEXT NOT NULL,
        artifact_id TEXT DEFAULT NULL,
        analysis_parameters_json TEXT NOT NULL DEFAULT '{}',
        evidence_metrics_json TEXT NOT NULL DEFAULT '{}',
        recommended_human_action TEXT NOT NULL,
        review_status TEXT NOT NULL DEFAULT 'REQUIRES_REVIEW',
        reviewer TEXT DEFAULT NULL,
        review_notes TEXT DEFAULT NULL,
        reviewed_at TEXT DEFAULT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
        FOREIGN KEY (analysis_id) REFERENCES forensic_analyses(id) ON DELETE CASCADE,
        FOREIGN KEY (artifact_id) REFERENCES forensic_artifacts(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS forensic_reviews (
        id TEXT PRIMARY KEY,
        finding_id TEXT NOT NULL,
        analysis_id TEXT NOT NULL,
        investigation_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        previous_status TEXT NOT NULL,
        new_status TEXT NOT NULL,
        reviewer TEXT NOT NULL,
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY (finding_id) REFERENCES forensic_findings(id) ON DELETE CASCADE,
        FOREIGN KEY (analysis_id) REFERENCES forensic_analyses(id) ON DELETE CASCADE,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS contextual_analyses (
        id TEXT PRIMARY KEY,
        investigation_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'COMPLETED',
        documents_analyzed_count INTEGER NOT NULL DEFAULT 0,
        entities_resolved_count INTEGER NOT NULL DEFAULT 0,
        relationships_discovered_count INTEGER NOT NULL DEFAULT 0,
        consistent_matches_count INTEGER NOT NULL DEFAULT 0,
        potential_contradictions_count INTEGER NOT NULL DEFAULT 0,
        confirmed_mismatches_count INTEGER NOT NULL DEFAULT 0,
        missing_information_count INTEGER NOT NULL DEFAULT 0,
        inconclusive_count INTEGER NOT NULL DEFAULT 0,
        financial_checks_count INTEGER NOT NULL DEFAULT 0,
        timeline_events_json TEXT NOT NULL DEFAULT '[]',
        summary_metrics_json TEXT NOT NULL DEFAULT '{}',
        processing_duration_ms REAL NOT NULL DEFAULT 0.0,
        started_at TEXT NOT NULL,
        completed_at TEXT DEFAULT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS entity_matches (
        id TEXT PRIMARY KEY,
        analysis_id TEXT NOT NULL,
        investigation_id TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        canonical_value TEXT NOT NULL,
        match_status TEXT NOT NULL,
        confidence_score REAL NOT NULL DEFAULT 1.0,
        matching_rationale TEXT NOT NULL,
        member_entities_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        FOREIGN KEY (analysis_id) REFERENCES contextual_analyses(id) ON DELETE CASCADE,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS entity_relationships (
        id TEXT PRIMARY KEY,
        analysis_id TEXT NOT NULL,
        investigation_id TEXT NOT NULL,
        source_node_id TEXT NOT NULL,
        source_node_type TEXT NOT NULL,
        source_label TEXT NOT NULL,
        target_node_id TEXT NOT NULL,
        target_node_type TEXT NOT NULL,
        target_label TEXT NOT NULL,
        edge_type TEXT NOT NULL,
        confidence_score REAL NOT NULL DEFAULT 1.0,
        matching_rationale TEXT NOT NULL,
        source_evidence_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        FOREIGN KEY (analysis_id) REFERENCES contextual_analyses(id) ON DELETE CASCADE,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS financial_validation_results (
        id TEXT PRIMARY KEY,
        analysis_id TEXT NOT NULL,
        investigation_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        document_type TEXT NOT NULL,
        check_type TEXT NOT NULL,
        status TEXT NOT NULL,
        expected_value TEXT NOT NULL,
        observed_value TEXT NOT NULL,
        discrepancy_amount TEXT NOT NULL DEFAULT '0.00',
        currency TEXT NOT NULL DEFAULT 'USD',
        formula_used TEXT NOT NULL,
        details_json TEXT NOT NULL DEFAULT '{}',
        page_number INTEGER NOT NULL DEFAULT 1,
        bounding_box_json TEXT DEFAULT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (analysis_id) REFERENCES contextual_analyses(id) ON DELETE CASCADE,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS contextual_findings (
        id TEXT PRIMARY KEY,
        analysis_id TEXT NOT NULL,
        investigation_id TEXT NOT NULL,
        finding_type TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'MEDIUM',
        status TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        document_references_json TEXT NOT NULL DEFAULT '[]',
        evidence_values_json TEXT NOT NULL DEFAULT '[]',
        comparison_method TEXT NOT NULL,
        matching_rationale TEXT NOT NULL,
        confidence_score REAL NOT NULL DEFAULT 1.0,
        confidence_interpretation TEXT NOT NULL,
        possible_explanations_json TEXT NOT NULL DEFAULT '[]',
        recommended_human_action TEXT NOT NULL,
        review_status TEXT NOT NULL DEFAULT 'REQUIRES_REVIEW',
        reviewer TEXT DEFAULT NULL,
        review_notes TEXT DEFAULT NULL,
        reviewed_at TEXT DEFAULT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (analysis_id) REFERENCES contextual_analyses(id) ON DELETE CASCADE,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS contextual_review_history (
        id TEXT PRIMARY KEY,
        finding_id TEXT NOT NULL,
        analysis_id TEXT NOT NULL,
        investigation_id TEXT NOT NULL,
        previous_status TEXT NOT NULL,
        new_status TEXT NOT NULL,
        reviewer TEXT NOT NULL,
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY (finding_id) REFERENCES contextual_findings(id) ON DELETE CASCADE,
        FOREIGN KEY (analysis_id) REFERENCES contextual_analyses(id) ON DELETE CASCADE,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS investigation_reasoning_runs (
        id TEXT PRIMARY KEY,
        investigation_id TEXT NOT NULL,
        case_code TEXT NOT NULL,
        reasoning_engine_version TEXT NOT NULL,
        ai_provider TEXT NOT NULL,
        ai_model TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        ai_assisted INTEGER NOT NULL DEFAULT 1,
        fallback_used INTEGER NOT NULL DEFAULT 0,
        fallback_reason TEXT DEFAULT NULL,
        source_analysis_ids_json TEXT NOT NULL DEFAULT '{}',
        source_document_hashes_json TEXT NOT NULL DEFAULT '[]',
        evidence_manifest_json TEXT NOT NULL DEFAULT '{}',
        sections_json TEXT NOT NULL DEFAULT '[]',
        claims_json TEXT NOT NULL DEFAULT '[]',
        rejected_claims_count INTEGER NOT NULL DEFAULT 0,
        rejected_claims_log_json TEXT NOT NULL DEFAULT '[]',
        questions_json TEXT NOT NULL DEFAULT '[]',
        verification_steps_json TEXT NOT NULL DEFAULT '[]',
        processing_duration_ms REAL NOT NULL DEFAULT 0.0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS investigation_dossiers (
        id TEXT PRIMARY KEY,
        investigation_id TEXT NOT NULL,
        reasoning_run_id TEXT NOT NULL,
        version_number INTEGER NOT NULL DEFAULT 1,
        title TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'UNAPPROVED_AI_ASSISTED',
        reasoning_engine_version TEXT NOT NULL,
        ai_provider TEXT NOT NULL,
        ai_model TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        source_analysis_ids_json TEXT NOT NULL DEFAULT '{}',
        source_document_hashes_json TEXT NOT NULL DEFAULT '[]',
        evidence_manifest_json TEXT NOT NULL DEFAULT '{}',
        pdf_storage_path TEXT NOT NULL,
        pdf_size_bytes INTEGER NOT NULL DEFAULT 0,
        pdf_sha256_hash TEXT NOT NULL,
        json_storage_path TEXT NOT NULL,
        json_size_bytes INTEGER NOT NULL DEFAULT 0,
        json_sha256_hash TEXT NOT NULL,
        dossier_sha256_hash TEXT NOT NULL,
        review_status TEXT NOT NULL DEFAULT 'UNAPPROVED_AI_ASSISTED',
        reviewed_by TEXT DEFAULT NULL,
        review_notes TEXT DEFAULT NULL,
        reviewed_at TEXT DEFAULT NULL,
        generated_by TEXT NOT NULL DEFAULT 'Lead Forensic Analyst',
        created_at TEXT NOT NULL,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE,
        FOREIGN KEY (reasoning_run_id) REFERENCES investigation_reasoning_runs(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS dossier_review_history (
        id TEXT PRIMARY KEY,
        dossier_id TEXT NOT NULL,
        investigation_id TEXT NOT NULL,
        previous_status TEXT NOT NULL,
        new_status TEXT NOT NULL,
        reviewer TEXT NOT NULL,
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY (dossier_id) REFERENCES investigation_dossiers(id) ON DELETE CASCADE,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id TEXT PRIMARY KEY,
        sequence_number INTEGER DEFAULT NULL,
        investigation_id TEXT,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT,
        actor TEXT NOT NULL DEFAULT 'System',
        actor_user_id TEXT DEFAULT NULL,
        actor_role TEXT DEFAULT NULL,
        event_origin TEXT NOT NULL DEFAULT 'AUTHENTICATED_HUMAN',
        summary TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        prev_hash TEXT NOT NULL DEFAULT 'GENESIS',
        event_hash TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'INVESTIGATOR',
        title TEXT NOT NULL DEFAULT '',
        password_hash TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        is_demo_account INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_login_at TEXT DEFAULT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS user_sessions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        token_hash TEXT UNIQUE NOT NULL,
        csrf_token TEXT NOT NULL DEFAULT '',
        ip_address TEXT DEFAULT '',
        user_agent TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        revoked_at TEXT DEFAULT NULL,
        is_revoked INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS login_rate_limits (
        id TEXT PRIMARY KEY,
        identifier TEXT NOT NULL,
        attempted_at TEXT NOT NULL,
        succeeded INTEGER NOT NULL DEFAULT 0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS investigation_members (
        id TEXT PRIMARY KEY,
        investigation_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        access_level TEXT NOT NULL DEFAULT 'MEMBER',
        granted_by_user_id TEXT DEFAULT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE(investigation_id, user_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS background_jobs (
        id TEXT PRIMARY KEY,
        investigation_id TEXT NOT NULL,
        document_id TEXT DEFAULT NULL,
        job_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'QUEUED',
        stage_label TEXT NOT NULL DEFAULT 'QUEUED',
        progress_percent INTEGER NOT NULL DEFAULT 0,
        current_stage TEXT NOT NULL DEFAULT 'Queued for processing',
        error_summary TEXT DEFAULT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL DEFAULT 3,
        retry_count INTEGER NOT NULL DEFAULT 0,
        max_retries INTEGER NOT NULL DEFAULT 3,
        idempotency_key TEXT DEFAULT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        result_summary_json TEXT NOT NULL DEFAULT '{}',
        created_by_user_id TEXT DEFAULT NULL,
        created_by_actor TEXT NOT NULL DEFAULT 'System',
        queued_at TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT '',
        started_at TEXT DEFAULT NULL,
        completed_at TEXT DEFAULT NULL,
        failed_at TEXT DEFAULT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_investigations_created_at ON investigations(created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_investigations_status ON investigations(status);",
    "CREATE INDEX IF NOT EXISTS idx_documents_investigation ON documents(investigation_id);",
    "CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256_hash);",
    "CREATE INDEX IF NOT EXISTS idx_doc_pages_document ON document_pages(document_id, page_number);",
    "CREATE INDEX IF NOT EXISTS idx_doc_extractions_doc_page ON document_extractions(document_id, page_number, block_index);",
    "CREATE INDEX IF NOT EXISTS idx_doc_extractions_inv ON document_extractions(investigation_id);",
    "CREATE INDEX IF NOT EXISTS idx_doc_layout_doc_page ON document_layout_regions(document_id, page_number, reading_order);",
    "CREATE INDEX IF NOT EXISTS idx_doc_tables_doc_page ON document_tables(document_id, page_number);",
    "CREATE INDEX IF NOT EXISTS idx_doc_table_cells_table ON document_table_cells(table_id, row_index, col_index);",
    "CREATE INDEX IF NOT EXISTS idx_doc_entities_doc_page ON document_entities(document_id, page_number);",
    "CREATE INDEX IF NOT EXISTS idx_doc_entities_inv_type ON document_entities(investigation_id, entity_type);",
    "CREATE INDEX IF NOT EXISTS idx_findings_investigation ON findings(investigation_id);",
    "CREATE INDEX IF NOT EXISTS idx_findings_review_status ON findings(review_status);",
    "CREATE INDEX IF NOT EXISTS idx_forensic_analyses_doc ON forensic_analyses(document_id, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_forensic_analyses_inv ON forensic_analyses(investigation_id, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_forensic_artifacts_analysis ON forensic_artifacts(analysis_id, page_number);",
    "CREATE INDEX IF NOT EXISTS idx_forensic_artifacts_doc ON forensic_artifacts(document_id, page_number);",
    "CREATE INDEX IF NOT EXISTS idx_forensic_findings_doc ON forensic_findings(document_id, page_number, severity);",
    "CREATE INDEX IF NOT EXISTS idx_forensic_findings_analysis ON forensic_findings(analysis_id);",
    "CREATE INDEX IF NOT EXISTS idx_forensic_findings_inv_status ON forensic_findings(investigation_id, review_status);",
    "CREATE INDEX IF NOT EXISTS idx_forensic_reviews_finding ON forensic_reviews(finding_id, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_ctx_analyses_inv ON contextual_analyses(investigation_id, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_entity_matches_inv ON entity_matches(investigation_id, entity_type);",
    "CREATE INDEX IF NOT EXISTS idx_entity_rels_inv ON entity_relationships(investigation_id, edge_type);",
    "CREATE INDEX IF NOT EXISTS idx_fin_val_inv ON financial_validation_results(investigation_id, document_id);",
    "CREATE INDEX IF NOT EXISTS idx_ctx_findings_inv ON contextual_findings(investigation_id, severity, status);",
    "CREATE INDEX IF NOT EXISTS idx_ctx_reviews_finding ON contextual_review_history(finding_id, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_reasoning_runs_inv ON investigation_reasoning_runs(investigation_id, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_dossiers_inv ON investigation_dossiers(investigation_id, version_number DESC);",
    "CREATE INDEX IF NOT EXISTS idx_dossier_reviews ON dossier_review_history(dossier_id, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_seq ON audit_logs(sequence_number ASC);",
    "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(token_hash);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_rate_limits_ident ON login_rate_limits(identifier, attempted_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_inv_members_inv_user ON investigation_members(investigation_id, user_id);",
    "CREATE INDEX IF NOT EXISTS idx_bg_jobs_inv ON background_jobs(investigation_id, updated_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_bg_jobs_status ON background_jobs(status, updated_at ASC);",
]

USER_MIGRATION_COLUMNS: List[Tuple[str, str]] = [
    ("title", "TEXT NOT NULL DEFAULT ''"),
]

BACKGROUND_JOB_MIGRATION_COLUMNS: List[Tuple[str, str]] = [
    ("stage_label", "TEXT NOT NULL DEFAULT 'QUEUED'"),
    ("attempt_count", "INTEGER NOT NULL DEFAULT 0"),
    ("max_attempts", "INTEGER NOT NULL DEFAULT 3"),
    ("queued_at", "TEXT NOT NULL DEFAULT ''"),
]

DOCUMENT_MIGRATION_COLUMNS: List[Tuple[str, str]] = [
    ("mime_type", "TEXT DEFAULT 'application/octet-stream'"),
    ("storage_path", "TEXT DEFAULT ''"),
    ("page_count", "INTEGER NOT NULL DEFAULT 1"),
    ("extraction_method_summary", "TEXT NOT NULL DEFAULT 'PENDING'"),
    ("is_scanned", "INTEGER NOT NULL DEFAULT 0"),
    ("average_confidence", "REAL NOT NULL DEFAULT 0.0"),
    ("extracted_char_count", "INTEGER NOT NULL DEFAULT 0"),
    ("document_type", "TEXT NOT NULL DEFAULT 'OTHER_UNKNOWN'"),
    ("classification_confidence", "REAL NOT NULL DEFAULT 0.0"),
    ("classification_is_certain", "INTEGER NOT NULL DEFAULT 0"),
    ("classification_signals_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("classification_candidates_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("layout_region_count", "INTEGER NOT NULL DEFAULT 0"),
    ("table_count", "INTEGER NOT NULL DEFAULT 0"),
    ("entity_count", "INTEGER NOT NULL DEFAULT 0"),
    ("forensic_status", "TEXT NOT NULL DEFAULT 'NOT_ANALYZED'"),
    ("latest_analysis_id", "TEXT DEFAULT NULL"),
    ("forensic_findings_count", "INTEGER NOT NULL DEFAULT 0"),
    ("forensic_analyzed_at", "TEXT DEFAULT NULL"),
    ("error_message", "TEXT DEFAULT NULL"),
    ("processed_at", "TEXT DEFAULT NULL"),
]

INVESTIGATION_MIGRATION_COLUMNS: List[Tuple[str, str]] = [
    ("owner_user_id", "TEXT DEFAULT NULL"),
    ("is_shared_org", "INTEGER NOT NULL DEFAULT 0"),
]

DOSSIER_MIGRATION_COLUMNS: List[Tuple[str, str]] = [
    ("generated_by_user_id", "TEXT DEFAULT NULL"),
    ("reviewed_by_user_id", "TEXT DEFAULT NULL"),
]

DOSSIER_REVIEW_MIGRATION_COLUMNS: List[Tuple[str, str]] = [
    ("reviewer_user_id", "TEXT DEFAULT NULL"),
    ("reviewer_role", "TEXT DEFAULT NULL"),
    ("is_simulated_demo", "INTEGER NOT NULL DEFAULT 0"),
]

FORENSIC_FINDING_MIGRATION_COLUMNS: List[Tuple[str, str]] = [
    ("reviewer_user_id", "TEXT DEFAULT NULL"),
]

CONTEXTUAL_FINDING_MIGRATION_COLUMNS: List[Tuple[str, str]] = [
    ("reviewer_user_id", "TEXT DEFAULT NULL"),
]

AUDIT_LOG_MIGRATION_COLUMNS: List[Tuple[str, str]] = [
    ("sequence_number", "INTEGER DEFAULT NULL"),
    ("actor_user_id", "TEXT DEFAULT NULL"),
    ("actor_role", "TEXT DEFAULT NULL"),
    ("event_origin", "TEXT NOT NULL DEFAULT 'AUTHENTICATED_HUMAN'"),
    ("prev_hash", "TEXT NOT NULL DEFAULT 'GENESIS'"),
    ("event_hash", "TEXT NOT NULL DEFAULT ''"),
]


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Yields a configured SQLite connection with Row factory and foreign keys enabled."""
    db_path = settings.resolved_db_path
    conn = None
    try:
        conn = sqlite3.connect(str(db_path), timeout=20.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        if conn is not None:
            conn.rollback()
        raise DatabaseOperationException(
            message="SQLite database operation failed.",
            details={"sqlite_error": str(exc)},
        ) from exc
    finally:
        if conn is not None:
            conn.close()


def _migrate_table_columns(
    conn: sqlite3.Connection, table_name: str, columns: List[Tuple[str, str]]
) -> None:
    """Safely adds columns to an existing SQLite table without data loss."""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name});")
    existing_cols = {row["name"] for row in cursor.fetchall()}

    for col_name, col_def in columns:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def};")


def init_db() -> None:
    """Initializes and safely migrates SQLite tables and indexes on application startup."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for statement in DDL_STATEMENTS:
            if not statement.strip().upper().startswith("CREATE INDEX"):
                cursor.execute(statement)
        _migrate_table_columns(conn, "documents", DOCUMENT_MIGRATION_COLUMNS)
        _migrate_table_columns(conn, "investigations", INVESTIGATION_MIGRATION_COLUMNS)
        _migrate_table_columns(
            conn, "investigation_dossiers", DOSSIER_MIGRATION_COLUMNS
        )
        _migrate_table_columns(
            conn, "dossier_review_history", DOSSIER_REVIEW_MIGRATION_COLUMNS
        )
        _migrate_table_columns(
            conn, "forensic_findings", FORENSIC_FINDING_MIGRATION_COLUMNS
        )
        _migrate_table_columns(
            conn, "contextual_findings", CONTEXTUAL_FINDING_MIGRATION_COLUMNS
        )
        _migrate_table_columns(conn, "audit_logs", AUDIT_LOG_MIGRATION_COLUMNS)
        _migrate_table_columns(conn, "users", USER_MIGRATION_COLUMNS)
        _migrate_table_columns(
            conn, "background_jobs", BACKGROUND_JOB_MIGRATION_COLUMNS
        )
        for statement in DDL_STATEMENTS:
            if statement.strip().upper().startswith("CREATE INDEX"):
                cursor.execute(statement)

        # Ensure pre-Phase-6 seeded demo cases remain visible to authenticated org members
        cursor.execute(
            """
            UPDATE investigations
            SET is_shared_org = 1
            WHERE case_code IN ('VRT-2026-0001', 'VRT-2026-0002', 'VRT-2026-0003');
            """
        )

        # Label historical pre-Phase-6 simulated demo approvals transparently without deleting them
        cursor.execute(
            """
            UPDATE dossier_review_history
            SET is_simulated_demo = 1,
                reviewer_role = COALESCE(reviewer_role, 'HISTORICAL_SIMULATED_DEMO')
            WHERE reviewer_user_id IS NULL;
            """
        )


def check_db_health() -> Dict[str, Any]:
    """Performs a live SQLite probe and returns genuine telemetry metrics."""
    start = time.perf_counter()
    db_path = settings.resolved_db_path
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 AS alive;")
            row = cursor.fetchone()
            is_alive = bool(row and row["alive"] == 1)

            cursor.execute("SELECT sqlite_version() AS version;")
            sqlite_version = cursor.fetchone()["version"]

            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            )
            table_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM investigations;")
            investigations_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM documents;")
            documents_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM document_extractions;")
            extractions_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM document_layout_regions;")
            layout_regions_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM document_tables;")
            tables_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM document_entities;")
            entities_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM findings;")
            legacy_findings_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM forensic_analyses;")
            forensic_analyses_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM forensic_findings;")
            forensic_findings_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM forensic_artifacts;")
            forensic_artifacts_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM forensic_reviews;")
            forensic_reviews_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM contextual_analyses;")
            contextual_analyses_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM contextual_findings;")
            contextual_findings_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM entity_relationships;")
            entity_relationships_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM financial_validation_results;")
            financial_validations_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM investigation_reasoning_runs;")
            reasoning_runs_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM investigation_dossiers;")
            dossiers_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM audit_logs;")
            audit_logs_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM users;")
            users_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) AS cnt FROM background_jobs;")
            jobs_count = cursor.fetchone()["cnt"]

        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        file_size_bytes = db_path.stat().st_size if db_path.exists() else 0

        return {
            "connected": is_alive,
            "engine": "SQLite",
            "sqlite_version": sqlite_version,
            "schema_version": SCHEMA_VERSION,
            "database_file": db_path.name,
            "file_size_bytes": file_size_bytes,
            "latency_ms": latency_ms,
            "tables_initialized": table_count,
            "record_counts": {
                "investigations": investigations_count,
                "documents": documents_count,
                "extractions": extractions_count,
                "layout_regions": layout_regions_count,
                "tables": tables_count,
                "entities": entities_count,
                "forensic_analyses": forensic_analyses_count,
                "forensic_findings": forensic_findings_count,
                "forensic_artifacts": forensic_artifacts_count,
                "forensic_reviews": forensic_reviews_count,
                "contextual_analyses": contextual_analyses_count,
                "contextual_findings": contextual_findings_count,
                "entity_relationships": entity_relationships_count,
                "financial_validations": financial_validations_count,
                "reasoning_runs": reasoning_runs_count,
                "dossiers": dossiers_count,
                "findings": legacy_findings_count + forensic_findings_count,
                "audit_logs": audit_logs_count,
                "users": users_count,
                "background_jobs": jobs_count,
            },
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "connected": False,
            "engine": "SQLite",
            "schema_version": SCHEMA_VERSION,
            "latency_ms": latency_ms,
            "error": str(exc),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
