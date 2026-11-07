from fastapi import APIRouter, Depends
from app.schemas.auth import AuthenticatedUser
from app.schemas.dashboard import CommandCentreSummaryResponse, DashboardMetrics
from app.services.auth_service import require_authenticated_user
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Command Centre Dashboard"])


@router.get("/summary", response_model=CommandCentreSummaryResponse)
def get_command_centre_summary(
    _current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> CommandCentreSummaryResponse:
    return DashboardService.get_command_centre_summary()


@router.get("/metrics", response_model=DashboardMetrics)
def get_dashboard_metrics(
    _current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> DashboardMetrics:
    return DashboardService.get_metrics()
