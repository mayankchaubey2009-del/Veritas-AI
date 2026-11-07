from typing import List, Optional
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=80)
    password: str = Field(..., min_length=6, max_length=200)


class AdminBootstrapRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=60)
    full_name: str = Field(..., min_length=3, max_length=120)
    password: str = Field(..., min_length=8, max_length=200)
    email: Optional[str] = Field(default=None, max_length=120)
    title: str = Field(default="Forensic Platform Administrator", max_length=120)
    bootstrap_token: Optional[str] = Field(
        default=None,
        description="Optional server bootstrap secret if VERITAS_BOOTSTRAP_TOKEN is set.",
    )


BootstrapAdminRequest = AdminBootstrapRequest


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=60)
    full_name: str = Field(..., min_length=3, max_length=120)
    role: str = Field(default="INVESTIGATOR")
    title: str = Field(default="Forensic Investigator", max_length=120)
    email: Optional[str] = Field(default=None, max_length=120)
    password: str = Field(..., min_length=8, max_length=200)


class DemoPersonaSwitchRequest(BaseModel):
    username: str = Field(
        ...,
        description="Synthetic demo username (e.g. dr.rostova, m.vance, admin.nair, a.chen) in development mode.",
    )


class InvestigationMemberGrantRequest(BaseModel):
    user_id: str = Field(..., min_length=3)
    access_level: str = Field(
        default="MEMBER",
        description="Access level: OWNER, MEMBER, WRITE, REVIEWER, READ, or VIEWER.",
    )


class AuthenticatedUser(BaseModel):
    id: str
    username: str
    email: str = ""
    full_name: str
    role: str
    title: str = ""
    is_active: bool = True
    is_demo_account: bool = False
    created_at: str = ""
    last_login_at: Optional[str] = None
    session_id: Optional[str] = None
    session_expires_at: Optional[str] = None


UserProfileResponse = AuthenticatedUser


class AuthSessionResponse(BaseModel):
    authenticated: bool = True
    access_token: str
    token_type: str = "Bearer"
    session_token: Optional[str] = None
    user: AuthenticatedUser
    session_id: str
    expires_at: str
    csrf_token: str = ""


class DemoPersonaItem(BaseModel):
    username: str
    full_name: str
    role: str
    title: str = ""
    badge_description: str


class AuthStatusResponse(BaseModel):
    authenticated: bool
    user: Optional[AuthenticatedUser] = None
    session_expires_at: Optional[str] = None
    demo_mode_enabled: bool
    bootstrap_available: bool
    demo_personas: List[DemoPersonaItem] = Field(default_factory=list)
