# VERITAS AI

**Enterprise AI-Powered Document Forensics & Contextual Intelligence Platform**

VERITAS AI is designed to investigate multi-document evidentiary corpora, identify visual tampering anomalies, detect contextual inconsistencies, correlate entities across documents, and compile evidence-backed investigation dossiers.

---

## Phase 1 — Foundation & Architecture

Phase 1 establishes the full-stack foundation:
- **Frontend**: Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, and Lucide icons styled in a deep midnight navy & electric cyan forensic aesthetic.
- **Backend**: Python FastAPI with Pydantic v2 validation, structured exception handling, environment configuration, and restricted CORS.
- **Database**: SQLite in Write-Ahead Logging (`WAL`) mode with relational tables (`investigations`, `documents`, `findings`, `audit_logs`).
- **Genuine Data Policy**: Zero fake AI functionality, zero hardcoded dashboard numbers, and zero simulated scan results. Every metric, investigation record, status change, case note, and health telemetry readout is backed by live SQLite queries.

---

## Project Structure

```text
VERITAS-AI/
│
├── frontend/
│   ├── src/
│   │   ├── app/                # Next.js App Router layout, styles, and main page
│   │   ├── components/         # Sidebar, TopHeader, Modal, Workspace, and 10 Views
│   │   ├── lib/                # Strongly-typed REST API client
│   │   └── types/              # TypeScript interfaces & domain enums
│   ├── public/
│   └── package.json
│
├── backend/
│   ├── app/
│   │   ├── api/                # FastAPI routers (health, dashboard, investigations, audit)
│   │   ├── core/               # Settings, SQLite WAL engine, structured exceptions
│   │   ├── models/             # Domain enumerations
│   │   ├── schemas/            # Pydantic v2 request/response models
│   │   ├── services/           # SQLite business logic & aggregation services
│   │   └── main.py             # FastAPI application factory & CORS setup
│   ├── .env.example
│   └── requirements.txt
│
├── docs/
│   └── ARCHITECTURE.md
├── sample-data/
│   └── README.md
├── README.md
└── .gitignore
```

---

## Setup & Execution Commands

### 1. Backend Setup (FastAPI + SQLite)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy environment template if .env does not exist
cp -n .env.example .env

# Start FastAPI server on http://127.0.0.1:8000
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend Setup (Next.js + Tailwind CSS)

```bash
cd frontend
npm install

# Start Next.js development server on http://localhost:3000
npm run dev
```

---

## Core API Endpoints (Phase 1)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Live API & SQLite health probe, latency, record counts, and subsystem status |
| `GET` | `/api/system/config` | Sanitized server configuration & security diagnostics |
| `GET` | `/api/dashboard/summary` | Real-time Command Centre metrics, recent investigations, and processing activity |
| `GET` | `/api/investigations` | List and filter investigations (`status`, `priority`, `search`) |
| `POST` | `/api/investigations` | Create a new SQLite investigation record & log audit event |
| `GET` | `/api/investigations/{id}` | Retrieve full investigation details, linked documents/findings, and audit trail |
| `PATCH` | `/api/investigations/{id}` | Update investigation status or parameters & log audit event |
| `POST` | `/api/investigations/{id}/notes` | Append an investigator case note to the SQLite audit ledger |
| `DELETE` | `/api/investigations/{id}` | Delete an investigation and record removal in the audit ledger |
| `GET` | `/api/audit-logs` | Retrieve chronological forensic audit trail entries |
