from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BackgroundJobEnqueueRequest(BaseModel):
    investigation_id: str = Field(..., min_length=1)
    document_id: Optional[str] = None
    job_type: str = Field(
        default="FULL_INVESTIGATION_PIPELINE",
        description=(
            "Job type: DOCUMENT_INGESTION_AND_EXTRACTION, VISUAL_FORENSICS_ANALYSIS, "
            "CONTEXTUAL_INTELLIGENCE_ANALYSIS, DOSSIER_GENERATION, or FULL_INVESTIGATION_PIPELINE"
        ),
    )
    execute_immediately: bool = Field(
        default=True,
        description="Whether to execute the job synchronously/in-background immediately or leave QUEUED for worker.",
    )
    simulate_failure_once: bool = Field(
        default=False,
        description="Optional test flag to simulate a transient processing failure on attempt 1 so retry recovery can be verified.",
    )


class BackgroundJobResponse(BaseModel):
    id: str
    investigation_id: str
    document_id: Optional[str] = None
    job_type: str
    status: str
    stage_label: str
    progress_percent: int
    attempt_count: int
    max_attempts: int
    idempotency_key: Optional[str] = None
    error_summary: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    result_summary: Dict[str, Any] = Field(default_factory=dict)
    created_by_user_id: Optional[str] = None
    created_by_actor: str
    queued_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    updated_at: str


class StartupRecoveryReport(BaseModel):
    interrupted_jobs_found: int
    recovered_job_ids: List[str] = Field(default_factory=list)
    timestamp: str
