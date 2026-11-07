from typing import Dict, List
from pydantic import BaseModel, Field
from app.schemas.investigation import AuditLogResponse, InvestigationResponse


class DashboardMetrics(BaseModel):
    total_investigations: int = 0
    active_investigations: int = 0
    documents_processed: int = 0
    findings_requiring_review: int = 0
    total_findings: int = 0
    processing_events_count: int = 0
    status_breakdown: Dict[str, int] = Field(default_factory=dict)
    priority_breakdown: Dict[str, int] = Field(default_factory=dict)


class CommandCentreSummaryResponse(BaseModel):
    metrics: DashboardMetrics
    recent_investigations: List[InvestigationResponse]
    processing_activity: List[AuditLogResponse]
    generated_at: str
