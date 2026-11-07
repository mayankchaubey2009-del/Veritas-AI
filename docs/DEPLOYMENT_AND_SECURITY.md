# VERITAS AI — Deployment Architecture & Security Hardening Guide (Phase 6)

This document provides the complete operational, security, and deployment reference for **VERITAS AI** (`v2.0.0-phase6`). It covers local development setup, production deployment topology, environment configuration, isolated storage layout, SQLite online backup/restore procedures, security controls, and known operational limitations.

---

## 1. Local Development Setup

### Prerequisites
- **Python**: `3.11+` (with `venv`)
- **Node.js**: `20+` LTS (`npm 10+`)
- **System Libraries**: OpenCV runtime dependencies, PyMuPDF (`fitz`), Pillow, ReportLab

### Step 1 — Backend Setup
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Start the FastAPI backend server:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

On startup, `lifespan` in `backend/app/main.py` automatically:
1. Validates startup configuration (`settings.validate_startup_environment()`).
2. Initializes and migrates the SQLite schema (`init_db()`).
3. Seeds initial investigations, Phase 2A–5 artifacts, and Phase 6 RBAC accounts (`seed_initial_data()`).
4. Backfills and verifies the append-only SHA-256 hash chain across `audit_logs` (`AuditService.backfill_hash_chain()`).
5. Recovers any interrupted `RUNNING` background jobs from a prior process crash (`JobService.recover_interrupted_jobs_on_startup()`).

### Step 2 — Frontend Setup
```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000` in your browser. In development mode (`ENABLE_DEMO_PERSONA_SWITCHING=true`), the platform automatically establishes an authenticated session for **Dr. Elena Rostova (`INVESTIGATOR`)** and exposes the **Guided Demo Walkthrough** and **Persona Switcher** in the top navigation bar.

---

## 2. Production Deployment Architecture

```
                         ┌──────────────────────────────────────────┐
                         │       TLS Termination / Reverse Proxy    │
                         │     (Cloudflare / AWS ALB / Nginx 1.26)  │
                         │   - HTTPS (TLS 1.3), HSTS, WAF, RateLim  │
                         └───────────────────┬──────────────────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
     ┌───────────────────────────────────┐       ┌───────────────────────────────────┐
     │     Next.js 14 Frontend Tier      │       │      FastAPI Backend Service      │
     │   (Port 3000, Node LTS Runtime)   │       │   (Port 8000, Gunicorn/Uvicorn)   │
     │ - Zero server secrets in bundle   │       │ - Session Cookie + Bearer Auth    │
     │ - RBAC-aware UI & Audit Verifier  │       │ - Strict RBAC & Case Isolation    │
     └───────────────────────────────────┘       └─────────────────┬─────────────────┘
                                                                   │
                       ┌───────────────────────────────────────────┼───────────────────────────────────────────┐
                       ▼                                           ▼                                           ▼
     ┌───────────────────────────────────┐       ┌───────────────────────────────────┐       ┌───────────────────────────────────┐
     │     Primary Database Storage      │       │   Isolated Forensic File Vault    │       │   Online Backup & WORM Ledger     │
     │  (SQLite WAL / PostgreSQL Ready)  │       │   (backend/storage/documents/)    │       │      (backend/data/backups/)      │
     │ - Users, Sessions, Investigations │       │ - Outside frontend/public         │       │ - Atomic sqlite3.backup snapshots │
     │ - Hash-Chained Audit Ledger       │       │ - UUID4 internal storage names    │       │ - SHA-256 manifest verification   │
     │ - Background Job Queue            │       │ - Path containment enforcement    │       │ - Off-host S3 Object Lock target  │
     └───────────────────────────────────┘       └───────────────────────────────────┘       └───────────────────────────────────┘
```

### Key Production Topology Principles
1. **Strict Secret Isolation**: `GEMINI_API_KEY`, session tokens, and filesystem paths exist exclusively on the backend tier. Only `NEXT_PUBLIC_API_BASE_URL` is exposed to the Next.js client bundle.
2. **Production Mode Enforcement**: Setting `ENVIRONMENT="production"` automatically:
   - Forces `AUTH_ENFORCED=True` (cannot be disabled via env override).
   - Forces `ENABLE_DEMO_PERSONA_SWITCHING=False` (disables `/api/auth/demo-switch` with `403 Forbidden`).
   - Forces `SESSION_COOKIE_SECURE=True` so session cookies are only transmitted over HTTPS.
3. **Private Evidence Storage**: Document binaries, page renders, visual forensics heatmaps, and exported PDF/JSON dossiers are stored inside `backend/storage/documents/`, completely outside `frontend/public/`, and served exclusively through authenticated, path-validated FastAPI endpoints with `X-Content-Type-Options: nosniff`.

---

## 3. Required Environment Variables

### Backend (`backend/.env`)

| Variable | Default (Dev) | Production Requirement | Purpose |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | `development` | `production` | Controls strict production security guards |
| `DEBUG` | `true` | `false` | Disables debug reload and verbose logging |
| `HOST` | `127.0.0.1` | `0.0.0.0` (behind reverse proxy) | Bind address for Uvicorn/Gunicorn |
| `PORT` | `8000` | `8000` | Backend HTTP port |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Explicit HTTPS origin(s) | Allowed origins for credentialed requests |
| `DATABASE_PATH` | `./data/veritas_forensics.db` | Persistent volume path | SQLite database file location |
| `BACKUP_DIR` | `./data/backups` | Separate persistent volume | Destination for online SQLite backups |
| `STORAGE_DIR` | `./storage/documents` | Encrypted persistent volume | Isolated vault for uploaded evidence & artifacts |
| `MAX_UPLOAD_SIZE_MB` | `25` | `25` | Maximum size per uploaded file |
| `MAX_TOTAL_UPLOAD_SIZE_MB` | `100` | `100` | Maximum aggregate size per batch upload |
| `MAX_FILES_PER_UPLOAD` | `10` | `10` | Maximum files per upload request |
| `MAX_PDF_PAGES` | `200` | `200` | Decompression/page-bomb limit for PDFs |
| `MAX_IMAGE_PIXELS` | `50000000` | `50000000` | Pixel flood / decompression bomb limit (50 MP) |
| `AUTH_ENFORCED` | `true` | Forced `true` | Requires authentication on all protected routes |
| `ENABLE_DEMO_PERSONA_SWITCHING` | `true` | Forced `false` | Enables/disables one-click hackathon persona switch |
| `SESSION_COOKIE_NAME` | `veritas_session` | `veritas_session` | Name of HttpOnly session cookie |
| `SESSION_TTL_HOURS` | `12` | `8` or `12` | Session token lifetime before expiration |
| `SESSION_COOKIE_SECURE` | `false` | Forced `true` | Restricts cookie transmission to HTTPS |
| `SESSION_COOKIE_SAMESITE` | `lax` | `lax` or `strict` | CSRF mitigation policy for session cookies |
| `LOGIN_RATE_LIMIT_MAX_ATTEMPTS` | `8` | `5` | Max failed logins per IP/username window |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `300` | `300` | Sliding window duration for login rate limiter |
| `INITIAL_ADMIN_USERNAME` | `p.nair` | Custom admin handle | Bootstrap administrator username |
| `INITIAL_ADMIN_PASSWORD` | `""` | Strong secret (min 16 chars) | Bootstrap password when creating fresh DB |
| `GEMINI_API_KEY` | `""` | Server-side API key | Optional Google Gemini synthesis key |

### Frontend (`frontend/.env.local`)

| Variable | Default (Dev) | Purpose |
| :--- | :--- | :--- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://127.0.0.1:8000` | Public URL of the FastAPI backend |

---

## 4. Storage Directory Layout

```
backend/
├── data/
│   ├── veritas_forensics.db          # Primary SQLite database (WAL mode, FK enforced)
│   └── backups/                      # Online SQLite backups + JSON SHA-256 manifests
│       ├── veritas_backup_<ts>_<id>.db
│       └── veritas_backup_<ts>_<id>.json
└── storage/
    └── documents/                    # Isolated Evidence Vault (outside frontend/public)
        ├── <investigation_id>/
        │   ├── <uuid4>.pdf           # Randomized internal filename (original name in DB only)
        │   ├── previews/             # Rendered page PNGs for bounding-box inspection
        │   └── forensics/            # Phase 3 visual forensics heatmaps & ELA overlays
        └── dossiers/
            └── <investigation_id>/   # Immutable PDF & JSON dossiers with SHA-256 hashes
```

Every file read or write inside `storage/documents/` passes through `DocumentService._assert_within_storage_root(candidate_path)`, which resolves symlinks and raises a `PermissionError` if the resolved path escapes `settings.resolved_storage_dir`.

---

## 5. Backup and Restore Procedures

### Creating an Online Backup
VERITAS AI uses SQLite's native online backup API (`sqlite3.Connection.backup()`) in `BackupService.create_backup()` so snapshots are transactionally consistent even while the application is serving requests.

- **Via API (Admin Role Required)**:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/system/backups \
    -H "Authorization: Bearer <admin_token>" \
    -H "Content-Type: application/json" \
    -d '{"label": "pre-release-snapshot"}'
  ```
- **Via UI**: Navigate to **Platform Settings → SQLite Online Backup & Integrity Verification** as `ADMIN` and click **Create Online Backup**.

### Verifying a Backup
```bash
curl -X POST http://127.0.0.1:8000/api/system/backups/<backup_id>/verify \
  -H "Authorization: Bearer <admin_token>"
```
This recomputes the SHA-256 digest of the `.db` snapshot file, compares it against the signed manifest, and runs `PRAGMA integrity_check` inside a read-only SQLite connection.

### Restoring from a Backup
1. Stop or drain traffic to the FastAPI process.
2. Verify the target backup via `BackupService.verify_backup(backup_id)` to confirm `sha256_matches=True` and `sqlite_integrity_ok=True`.
3. Execute `BackupService.restore_backup(backup_id)` (or copy the verified `.db` file over `backend/data/veritas_forensics.db` after removing stale `-wal` and `-shm` files).
4. Restart the FastAPI service and verify `/api/health` and `/api/audit-logs/verify`.

---

## 6. Security Hardening Checklist

- [x] **Salted Password Hashing**: PBKDF2-HMAC-SHA256 (`310,000` iterations) and `scrypt` (`N=16384, r=8, p=1`) with constant-time `hmac.compare_digest` verification.
- [x] **Session Token Security**: 256-bit cryptographically random tokens (`secrets.token_urlsafe(32)`), only the SHA-256 hash (`token_sha256`) is stored in SQLite.
- [x] **Cookie Hardening**: `HttpOnly`, `SameSite=Lax`, configurable `Secure` flag (forced `True` in production).
- [x] **Brute-Force Protection**: Sliding-window rate limiting on `/api/auth/login` (`429 Too Many Requests`).
- [x] **Role-Based Access Control (RBAC)**: Enforced at route dependencies for `ADMIN`, `INVESTIGATOR`, `REVIEWER`, and `VIEWER`.
- [x] **Cross-Investigation Isolation**: Non-admin users with explicit investigation assignments (`assigned_investigations_json`) are restricted from reading or mutating unassigned cases (`403 CROSS_INVESTIGATION_ACCESS_DENIED`).
- [x] **Separation of Duties**: Dossier creators cannot approve their own compiled dossiers (`403 SELF_DOSSIER_APPROVAL_PROHIBITED`), and `INVESTIGATOR`/`VIEWER` roles cannot transition a dossier to `APPROVED`.
- [x] **Multi-Layer Upload Validation**: Extension allowlist + MIME allowlist + magic-byte signature inspection (`%PDF-`, `\x89PNG\r\n\x1a\n`, `\xff\xd8\xff`) + page count and pixel flood limits.
- [x] **Sanitized Global Exception Handling**: Unexpected server exceptions log full stack traces internally while returning sanitized JSON with a correlation `error_id` (`ERR-*`) and zero internal path or traceback leakage.
- [x] **Response Security Headers**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`.

---

## 7. Known Limitations

1. **Local SQLite Tamper Evident vs. Tamper Proof**: The SHA-256 hash chain in `audit_logs` detects any single-row modification, insertion, or deletion (`GET /api/audit-logs/verify`). However, an attacker with root/filesystem write access to `veritas_forensics.db` could theoretically rewrite a historical row and recompute all subsequent hashes in the chain. True tamper-proofing requires streaming each `event_hash` to an external WORM (Write-Once-Read-Many) log sink or RFC 3161 timestamp authority.
2. **In-Memory Rate Limiter Scope**: Login rate limiting is tracked in process memory per worker. In a multi-worker Gunicorn/Kubernetes deployment, rate limiting should be backed by Redis or enforced at the ingress reverse proxy / WAF.
3. **Single-Writer SQLite Concurrency**: While SQLite WAL mode supports concurrent readers and serialized writers suitable for hackathon and departmental deployments, high-throughput multi-node deployments should migrate the storage layer to PostgreSQL.
