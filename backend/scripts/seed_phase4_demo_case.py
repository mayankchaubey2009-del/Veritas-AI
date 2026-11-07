from pathlib import Path
from app.core.database import get_db_connection, init_db
from app.schemas.dossier import DossierGenerateRequest, DossierReviewRequest
from app.services.context_service import ContextService
from app.services.document_service import DocumentService
from app.services.dossier_service import DossierService
from app.services.forensics_service import ForensicsService
from scripts.generate_phase3_demo_data import generate_all_phase3_demo_files

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "sample-data"


def seed_phase4_demo() -> None:
    init_db()
    generate_all_phase3_demo_files()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Clean up ephemeral pytest-created investigations so the workspace stays clean
        cursor.execute(
            """
            DELETE FROM investigations
            WHERE case_code NOT IN ('VRT-2026-0001', 'VRT-2026-0002', 'VRT-2026-0003');
            """
        )

        cursor.execute(
            "SELECT id FROM investigations WHERE case_code = 'VRT-2026-0003';"
        )
        inv3 = cursor.fetchone()
        if inv3:
            inv3_id = inv3["id"]
            # Refresh VRT-2026-0003 documents with the latest Phase 2B/3/4 extraction & forensics
            cursor.execute(
                "DELETE FROM documents WHERE investigation_id = ?;", (inv3_id,)
            )
            cursor.execute(
                "DELETE FROM findings WHERE investigation_id = ?;", (inv3_id,)
            )
            cursor.execute(
                "DELETE FROM contextual_analyses WHERE investigation_id = ?;",
                (inv3_id,),
            )

    if inv3:
        demo_files = [
            (
                "demo_inconsistent_synthetic_invoice.pdf",
                "application/pdf",
                (SAMPLE_DIR / "demo_inconsistent_synthetic_invoice.pdf").read_bytes(),
            ),
            (
                "demo_clean_synthetic_invoice.pdf",
                "application/pdf",
                (SAMPLE_DIR / "demo_clean_synthetic_invoice.pdf").read_bytes(),
            ),
            (
                "demo_scanned_escrow_receipt.jpg",
                "image/jpeg",
                (SAMPLE_DIR / "demo_scanned_escrow_receipt.jpg").read_bytes(),
            ),
            (
                "demo_supporting_bank_statement.pdf",
                "application/pdf",
                (SAMPLE_DIR / "demo_supporting_bank_statement.pdf").read_bytes(),
            ),
        ]
        docs = DocumentService.ingest_and_extract_documents(
            investigation_id=inv3_id,
            files_payload=demo_files,
            actor="Dr. Elena Rostova (Principal Forensic Analyst)",
        )
        for d in docs:
            ForensicsService.run_document_forensic_analysis(d.id)

    # Ensure Phase 2B, Phase 3, and Phase 4 are populated for all active investigations
    DocumentService.backfill_phase2b_structure_for_existing_documents()
    ForensicsService.backfill_phase3_forensics_for_existing_documents()

    with get_db_connection() as conn:
        inv_rows = conn.execute(
            "SELECT id, case_code FROM investigations ORDER BY case_code ASC;"
        ).fetchall()

    for r in inv_rows:
        bundle = ContextService.run_investigation_context_analysis(r["id"])
        print(
            f"Seeded Phase 4 Context for {r['case_code']}: "
            f"{bundle.documents_analyzed_count} docs, "
            f"{bundle.entities_resolved_count} entities resolved, "
            f"{bundle.relationships_discovered_count} graph edges, "
            f"{len(bundle.findings)} findings"
        )
        dossier = DossierService.generate_investigation_dossier(
            investigation_id=r["id"],
            payload=DossierGenerateRequest(
                actor="Dr. Elena Rostova (Lead Forensic Investigator)"
            ),
        )
        print(
            f"Compiled Phase 5 Dossier for {r['case_code']}: "
            f"v{dossier.version_number} ({dossier.dossier_id[:8]}), "
            f"PDF: {dossier.pdf_size_bytes}B, "
            f"JSON: {dossier.json_size_bytes}B, "
            f"Claims: {len(dossier.reasoning.claims)}, "
            f"Evidence Items: {len(dossier.reasoning.evidence_manifest)}"
        )


if __name__ == "__main__":
    seed_phase4_demo()
