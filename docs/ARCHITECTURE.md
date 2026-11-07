# VERITAS AI — Phase 1 Architecture & Technical Specification

## 1. Architectural Overview

VERITAS AI is an enterprise document forensics and contextual intelligence platform engineered with a clean separation between presentation (`frontend/`) and forensic persistence/intelligence services (`backend/`).

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    VERITAS AI FRONTEND (Next.js 14)                     │
│  • Command Centre Dashboard         • Quick-Access Case Workspace       │
│  • 10 Forensic Navigation Views     • Strongly-Typed REST Client        │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ HTTP / JSON (CORS Restricted)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     VERITAS AI BACKEND (FastAPI)                        │
│  • /api/health & /api/system/config • /api/dashboard/summary            │
│  • /api/investigations (CRUD+Notes) • /api/audit-logs                   │
│  • Structured Exception Middleware  • Pydantic v2 Schema Validation     │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ SQLite3 (WAL Mode + Foreign Keys)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  SQLITE FORENSIC STORE (veritas_forensics.db)           │
│  • investigations   • documents   • findings   • audit_logs             │
└─────────────────────────────────────────────────────────────────────────┘
```

## 2. SQLite Relational Schema

- **`investigations`**: Stores forensic case metadata (`id`, `case_code`, `title`, `description`, `status`, `priority`, `classification`, `lead_investigator`, `created_at`, `updated_at`).
- **`documents`**: Prepared for Phase 2 ingestion (`id`, `investigation_id`, `filename`, `file_type`, `file_size_bytes`, `sha256_hash`, `processing_status`, `uploaded_at`).
- **`findings`**: Prepared for Phase 3–4 visual and contextual anomalies (`id`, `investigation_id`, `document_id`, `finding_type`, `severity`, `review_status`, `title`, `description`, `confidence_score`, `created_at`).
- **`audit_logs`**: Immutable operational ledger recording every investigation creation, status transition, and case note (`id`, `investigation_id`, `action`, `entity_type`, `entity_id`, `actor`, `summary`, `metadata_json`, `created_at`).

## 3. Security & Configuration Principles

1. **Zero Secret Exposure**: AI provider credentials (`GEMINI_API_KEY`) reside strictly in `backend/.env` and are never returned by API endpoints or bundled into `NEXT_PUBLIC_*` frontend variables.
2. **Restricted CORS**: Local development origins are explicitly whitelisted (`http://localhost:3000`, `http://127.0.0.1:3000`).
3. **Structured Error Handling**: All validation, HTTP, and database errors return a deterministic JSON envelope (`status`, `error.code`, `error.message`, `error.details`, `error.timestamp`).
