from typing import Any, Dict, List
from pydantic import BaseModel


class SubsystemStatus(BaseModel):
    name: str
    status: str
    phase: str
    description: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    uptime_seconds: float
    timestamp: str
    database: Dict[str, Any]
    subsystems: List[SubsystemStatus]
