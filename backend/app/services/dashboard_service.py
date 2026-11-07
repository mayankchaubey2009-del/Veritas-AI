from datetime import datetime, timezone
from typing import Dict
from app.core.database import get_db_connection
from app.schemas.dashboard import CommandCentreSummaryResponse, DashboardMetrics
from app.services.investigation_service import InvestigationService


class DashboardService:
    @staticmethod
    def get_metrics() -> DashboardMetrics:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) AS cnt FROM investigations;")
            total_investigations = int(cursor.fetchone()["cnt"])

            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM investigations WHERE status IN ('OPEN', 'IN_PROGRESS', 'UNDER_REVIEW');"
            )
            active_investigations = int(cursor.fetchone()["cnt"])

            cursor.execute("SELECT COUNT(*) AS cnt FROM documents;")
            documents_processed = int(cursor.fetchone()["cnt"])

            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM findings WHERE review_status = 'REQUIRES_REVIEW';"
            )
            findings_requiring_review = int(cursor.fetchone()["cnt"])

            cursor.execute("SELECT COUNT(*) AS cnt FROM findings;")
            total_findings = int(cursor.fetchone()["cnt"])

            cursor.execute("SELECT COUNT(*) AS cnt FROM audit_logs;")
            processing_events_count = int(cursor.fetchone()["cnt"])

            cursor.execute(
                "SELECT status, COUNT(*) AS cnt FROM investigations GROUP BY status;"
            )
            status_breakdown: Dict[str, int] = {
                row["status"]: int(row["cnt"]) for row in cursor.fetchall()
            }

            cursor.execute(
                "SELECT priority, COUNT(*) AS cnt FROM investigations GROUP BY priority;"
            )
            priority_breakdown: Dict[str, int] = {
                row["priority"]: int(row["cnt"]) for row in cursor.fetchall()
            }

            return DashboardMetrics(
                total_investigations=total_investigations,
                active_investigations=active_investigations,
                documents_processed=documents_processed,
                findings_requiring_review=findings_requiring_review,
                total_findings=total_findings,
                processing_events_count=processing_events_count,
                status_breakdown=status_breakdown,
                priority_breakdown=priority_breakdown,
            )

    @staticmethod
    def get_command_centre_summary() -> CommandCentreSummaryResponse:
        metrics = DashboardService.get_metrics()
        recent_investigations = InvestigationService.list_investigations(limit=12)
        processing_activity = InvestigationService.list_audit_logs(limit=25)
        return CommandCentreSummaryResponse(
            metrics=metrics,
            recent_investigations=recent_investigations,
            processing_activity=processing_activity,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
