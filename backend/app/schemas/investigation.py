from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models.entities import (
    InvestigationClassification,
    InvestigationPriority,
    InvestigationStatus,
)


class InvestigationCreate(BaseModel):
    title: str = Field(
        ...,
        min_length=3,
        max_length=160,
        description="Official title of the forensic investigation.",
    )
    description: str = Field(
        default="",
        max_length=2000,
        description="Investigation hypothesis, scope, and initial briefing.",
    )
    priority: InvestigationPriority = Field(
        default=InvestigationPriority.HIGH,
        description="Operational urgency level.",
    )
    classification: InvestigationClassification = Field(
        default=InvestigationClassification.FINANCIAL_FORENSICS,
        description="Forensic domain classification.",
    )
    lead_investigator: str = Field(
        default="Lead Forensic Analyst",
        min_length=2,
        max_length=100,
        description="Assigned lead investigator or analyst.",
    )


class InvestigationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    status: Optional[InvestigationStatus] = None
    priority: Optional[InvestigationPriority] = None
    classification: Optional[InvestigationClassification] = None
    lead_investigator: Optional[str] = Field(default=None, min_length=2, max_length=100)


class CaseNoteCreate(BaseModel):
    actor: str = Field(default="Lead Forensic Analyst", min_length=2, max_length=100)
    note: str = Field(..., min_length=2, max_length=1000)


class AuditLogResponse(BaseModel):
    id: str
    investigation_id: Optional[str] = None
    case_code: Optional[str] = None
    investigation_title: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    actor: str
    actor_user_id: Optional[str] = None
    actor_role: Optional[str] = None
    event_origin: str = "AUTHENTICATED_HUMAN"
    sequence_number: Optional[int] = None
    prev_hash: Optional[str] = None
    event_hash: Optional[str] = None
    summary: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class InvestigationResponse(BaseModel):
    id: str
    case_code: str
    title: str
    description: str
    status: InvestigationStatus
    priority: InvestigationPriority
    classification: InvestigationClassification
    lead_investigator: str
    owner_user_id: Optional[str] = None
    document_count: int = 0
    findings_count: int = 0
    pending_review_count: int = 0
    created_at: str
    updated_at: str


class InvestigationDetailResponse(InvestigationResponse):
    audit_trail: List[AuditLogResponse] = Field(default_factory=list)
    documents: List[Dict[str, Any]] = Field(default_factory=list)
    findings: List[Dict[str, Any]] = Field(default_factory=list)
