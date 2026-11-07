from typing import List, Optional
from fastapi import APIRouter, Cookie, Depends, Header, Request, Response, status
from app.core.config import settings
from app.models.entities import UserRole
from app.schemas.auth import (
    AdminBootstrapRequest,
    AuthenticatedUser,
    AuthSessionResponse,
    AuthStatusResponse,
    DemoPersonaSwitchRequest,
    LoginRequest,
    UserCreateRequest,
)
from app.services.auth_service import (
    AuthService,
    extract_raw_token,
    get_optional_user,
    require_authenticated_user,
    require_roles,
)

router = APIRouter(prefix="/auth", tags=["Authentication & Access Control"])


def _set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
    )


@router.get("/me", response_model=AuthStatusResponse)
def get_auth_status(
    current_user: Optional[AuthenticatedUser] = Depends(get_optional_user),
) -> AuthStatusResponse:
    return AuthService.get_auth_status(current_user)


@router.post("/login", response_model=AuthSessionResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> AuthSessionResponse:
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "")
    session_resp = AuthService.authenticate(
        payload=payload,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    _set_session_cookie(response, session_resp.access_token)
    return session_resp


@router.post("/logout")
def logout(
    response: Response,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(
        default=None, alias=settings.session_cookie_name
    ),
    current_user: Optional[AuthenticatedUser] = Depends(get_optional_user),
):
    raw_token = extract_raw_token(authorization, session_cookie)
    AuthService.logout(raw_token=raw_token, user=current_user)
    _clear_session_cookie(response)
    return {"logged_out": True}


@router.post(
    "/bootstrap",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def bootstrap_initial_admin(
    payload: AdminBootstrapRequest,
    request: Request,
    response: Response,
) -> AuthSessionResponse:
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "")
    session_resp = AuthService.bootstrap_initial_admin(
        payload=payload,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    _set_session_cookie(response, session_resp.access_token)
    return session_resp


@router.post("/demo-session", response_model=AuthSessionResponse)
def switch_demo_persona(
    payload: DemoPersonaSwitchRequest,
    request: Request,
    response: Response,
) -> AuthSessionResponse:
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "")
    session_resp = AuthService.switch_demo_persona(
        username=payload.username,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    _set_session_cookie(response, session_resp.access_token)
    return session_resp


@router.get("/users", response_model=List[AuthenticatedUser])
def list_users(
    _admin: AuthenticatedUser = Depends(require_roles(UserRole.ADMIN.value)),
) -> List[AuthenticatedUser]:
    return AuthService.list_users()


@router.post(
    "/users",
    response_model=AuthenticatedUser,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: UserCreateRequest,
    admin_user: AuthenticatedUser = Depends(require_roles(UserRole.ADMIN.value)),
) -> AuthenticatedUser:
    return AuthService.create_user(payload=payload, actor_user=admin_user)
