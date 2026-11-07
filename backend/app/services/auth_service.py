import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
from Crypto.Protocol.KDF import scrypt as crypto_scrypt
from fastapi import Depends, Request
from app.core.config import settings
from app.core.database import get_db_connection
from app.core.exceptions import (
    AuthenticationException,
    AuthorizationException,
    InvalidDocumentException,
    RateLimitException,
    ResourceNotFoundException,
)
from app.models.entities import AuditEventOrigin, UserRole
from app.schemas.auth import (
    AdminBootstrapRequest,
    AuthenticatedUser,
    AuthSessionResponse,
    AuthStatusResponse,
    DemoPersonaItem,
    LoginRequest,
    UserCreateRequest,
)
from app.services.audit_service import AuditService

PBKDF2_ITERATIONS = 310000

DEV_DEMO_PERSONAS_SPEC: List[Dict[str, str]] = [
    {
        "username": "dr.rostova",
        "email": "elena.rostova@veritas-forensics.synthetic.local",
        "full_name": "Dr. Elena Rostova",
        "title": "Principal Forensic Analyst",
        "role": UserRole.INVESTIGATOR.value,
        "badge_description": "INVESTIGATOR — Creates cases, uploads documents, runs forensic & dossier engines.",
    },
    {
        "username": "m.vance",
        "email": "marcus.vance@veritas-forensics.synthetic.local",
        "full_name": "Marcus Vance",
        "title": "Senior Forensic Compliance Reviewer",
        "role": UserRole.REVIEWER.value,
        "badge_description": "REVIEWER — Independently reviews findings and approves/rejects investigation dossiers.",
    },
    {
        "username": "admin.nair",
        "email": "priya.nair@veritas-forensics.synthetic.local",
        "full_name": "Director Priya Nair",
        "title": "Forensic Platform Administrator",
        "role": UserRole.ADMIN.value,
        "badge_description": "ADMIN — Manages users, access permissions, benchmarks, backups, and system configuration.",
    },
    {
        "username": "a.chen",
        "email": "audrey.chen@veritas-forensics.synthetic.local",
        "full_name": "Audrey Chen",
        "title": "External Audit Observer",
        "role": UserRole.VIEWER.value,
        "badge_description": "VIEWER — Strictly read-only inspection access; cannot mutate cases or approve dossiers.",
    },
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def hash_password_pbkdf2(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Hashes a password using salted PBKDF2-HMAC-SHA256 (310,000 iterations, OWASP 2023+)."""
    salt = secrets.token_bytes(16)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=32,
    )
    hash_b64 = base64.urlsafe_b64encode(derived).decode("ascii")
    return f"$pbkdf2-sha256${iterations}${salt_b64}${hash_b64}"


def hash_password_scrypt(password: str) -> str:
    """Hashes a password using memory-hard scrypt (N=16384, r=8, p=1)."""
    salt = secrets.token_bytes(16)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    derived = crypto_scrypt(
        password.encode("utf-8"), salt, key_len=32, N=16384, r=8, p=1
    )
    hash_b64 = base64.urlsafe_b64encode(derived).decode("ascii")
    return f"$scrypt$16384$8$1${salt_b64}${hash_b64}"


def hash_password(password: str, method: str = "pbkdf2") -> str:
    if method == "scrypt":
        return hash_password_scrypt(password)
    return hash_password_pbkdf2(password)


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time verification of PBKDF2-HMAC-SHA256 or scrypt password hashes."""
    try:
        parts = stored_hash.split("$")
        if len(parts) < 5:
            return False
        alg = parts[1]
        if alg == "pbkdf2-sha256":
            iterations = int(parts[2])
            salt = base64.urlsafe_b64decode(parts[3].encode("ascii"))
            expected = base64.urlsafe_b64decode(parts[4].encode("ascii"))
            candidate = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                iterations,
                dklen=len(expected),
            )
            return hmac.compare_digest(candidate, expected)
        if alg == "scrypt":
            n_val = int(parts[2])
            r_val = int(parts[3])
            p_val = int(parts[4])
            salt = base64.urlsafe_b64decode(parts[5].encode("ascii"))
            expected = base64.urlsafe_b64decode(parts[6].encode("ascii"))
            candidate = crypto_scrypt(
                password.encode("utf-8"),
                salt,
                key_len=len(expected),
                N=n_val,
                r=r_val,
                p=p_val,
            )
            return hmac.compare_digest(candidate, expected)
        return False
    except Exception:
        return False


def _hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def extract_raw_token(
    authorization: Optional[str] = None, session_cookie: Optional[str] = None
) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    if session_cookie and session_cookie.strip():
        return session_cookie.strip()
    return None


def _row_to_user_profile(
    row: Any,
    session_id: Optional[str] = None,
    session_expires_at: Optional[str] = None,
) -> AuthenticatedUser:
    keys = set(row.keys())
    return AuthenticatedUser(
        id=row["id"],
        username=row["username"],
        email=row["email"] if "email" in keys and row["email"] else "",
        full_name=row["full_name"],
        role=row["role"],
        title=row["title"] if "title" in keys and row["title"] else "",
        is_active=bool(row["is_active"]),
        is_demo_account=bool(row["is_demo_account"]),
        created_at=row["created_at"] if "created_at" in keys else "",
        last_login_at=row["last_login_at"] if "last_login_at" in keys else None,
        session_id=session_id,
        session_expires_at=session_expires_at,
    )


class AuthService:
    @staticmethod
    def ensure_demo_personas() -> None:
        """
        In non-production environments when demo mode is enabled, provisions the 4 synthetic
        demonstration personas with cryptographically random runtime passwords (never hardcoded).
        """
        if settings.is_production or not settings.enable_demo_mode:
            return

        now = _utc_now_iso()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for spec in DEV_DEMO_PERSONAS_SPEC:
                cursor.execute(
                    "SELECT id FROM users WHERE username = ?;",
                    (spec["username"],),
                )
                existing = cursor.fetchone()
                if not existing:
                    user_id = str(uuid.uuid4())
                    random_runtime_pw = secrets.token_urlsafe(32)
                    pw_hash = hash_password_pbkdf2(random_runtime_pw)
                    cursor.execute(
                        """
                        INSERT INTO users (
                            id, username, email, full_name, role, title,
                            password_hash, is_active, is_demo_account,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?);
                        """,
                        (
                            user_id,
                            spec["username"],
                            spec["email"],
                            spec["full_name"],
                            spec["role"],
                            spec["title"],
                            pw_hash,
                            now,
                            now,
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE users
                        SET full_name = ?, role = ?, title = ?
                        WHERE id = ?;
                        """,
                        (
                            spec["full_name"],
                            spec["role"],
                            spec["title"],
                            existing["id"],
                        ),
                    )

            # Assign ownership of pre-seeded demo cases to dr.rostova if owner_user_id is NULL
            cursor.execute("SELECT id FROM users WHERE username = 'dr.rostova';")
            elena_row = cursor.fetchone()
            if elena_row:
                cursor.execute(
                    """
                    UPDATE investigations
                    SET owner_user_id = COALESCE(owner_user_id, ?),
                        is_shared_org = 1
                    WHERE case_code IN ('VRT-2026-0001', 'VRT-2026-0002', 'VRT-2026-0003');
                    """,
                    (elena_row["id"],),
                )

    ensure_dev_demo_personas = ensure_demo_personas

    @staticmethod
    def _check_login_rate_limit(cursor: Any, identifier: str) -> None:
        window_start = (
            _utc_now() - timedelta(seconds=settings.login_rate_limit_window_seconds)
        ).isoformat()
        cursor.execute(
            """
            SELECT COUNT(*) AS failed_cnt
            FROM login_rate_limits
            WHERE identifier = ?
              AND succeeded = 0
              AND attempted_at >= ?;
            """,
            (identifier.lower(), window_start),
        )
        failed_cnt = int(cursor.fetchone()["failed_cnt"] or 0)
        if failed_cnt >= settings.login_rate_limit_attempts:
            raise RateLimitException(
                message=(
                    f"Too many failed login attempts for '{identifier}'. "
                    f"Account login temporarily rate-limited for {settings.login_rate_limit_window_seconds} seconds."
                ),
                code="RATE_LIMIT_EXCEEDED",
                details={
                    "max_attempts": settings.login_rate_limit_attempts,
                    "window_seconds": settings.login_rate_limit_window_seconds,
                },
            )

    @staticmethod
    def _record_login_attempt(cursor: Any, identifier: str, succeeded: bool) -> None:
        cursor.execute(
            """
            INSERT INTO login_rate_limits (id, identifier, attempted_at, succeeded)
            VALUES (?, ?, ?, ?);
            """,
            (
                str(uuid.uuid4()),
                identifier.lower(),
                _utc_now_iso(),
                1 if succeeded else 0,
            ),
        )

    @staticmethod
    def _create_session_for_user(
        cursor: Any,
        user_row: Any,
        ip_address: str = "",
        user_agent: str = "",
        login_method: str = "PASSWORD_LOGIN",
    ) -> AuthSessionResponse:
        now = _utc_now()
        now_iso = now.isoformat()
        expires_iso = (
            now + timedelta(seconds=settings.session_ttl_seconds)
        ).isoformat()

        raw_token = secrets.token_urlsafe(36)
        token_hash = _hash_session_token(raw_token)
        csrf_token = secrets.token_hex(24)
        session_id = str(uuid.uuid4())

        cursor.execute(
            """
            INSERT INTO user_sessions (
                id, user_id, token_hash, csrf_token, ip_address,
                user_agent, created_at, expires_at, is_revoked
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0);
            """,
            (
                session_id,
                user_row["id"],
                token_hash,
                csrf_token,
                ip_address[:120],
                user_agent[:240],
                now_iso,
                expires_iso,
            ),
        )
        cursor.execute(
            "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?;",
            (now_iso, now_iso, user_row["id"]),
        )

        AuditService.append_event_with_cursor(
            cursor=cursor,
            action="USER_SESSION_AUTHENTICATED",
            entity_type="USER_SESSION",
            entity_id=session_id,
            actor=f"{user_row['full_name']} ({user_row['username']})",
            actor_user_id=user_row["id"],
            actor_role=user_row["role"],
            event_origin=AuditEventOrigin.AUTHENTICATED_HUMAN.value,
            summary=(
                f"Authenticated session established for {user_row['username']} "
                f"[Role: {user_row['role']}] via {login_method}"
            ),
            metadata={
                "username": user_row["username"],
                "role": user_row["role"],
                "login_method": login_method,
                "session_id": session_id,
                "expires_at": expires_iso,
            },
            created_at=now_iso,
        )

        cursor.execute("SELECT * FROM users WHERE id = ?;", (user_row["id"],))
        updated_user = cursor.fetchone()
        user_prof = _row_to_user_profile(
            updated_user,
            session_id=session_id,
            session_expires_at=expires_iso,
        )
        return AuthSessionResponse(
            authenticated=True,
            access_token=raw_token,
            token_type="Bearer",
            session_token=raw_token,
            user=user_prof,
            session_id=session_id,
            expires_at=expires_iso,
            csrf_token=csrf_token,
        )

    @staticmethod
    def authenticate(
        payload: LoginRequest, ip_address: str = "", user_agent: str = ""
    ) -> AuthSessionResponse:
        username = payload.username.strip()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            AuthService._check_login_rate_limit(cursor, username)
            if ip_address:
                AuthService._check_login_rate_limit(cursor, f"ip:{ip_address}")

            cursor.execute(
                "SELECT * FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?);",
                (username, username),
            )
            user_row = cursor.fetchone()

        if not user_row or not bool(user_row["is_active"]):
            with get_db_connection() as conn:
                cursor = conn.cursor()
                AuthService._record_login_attempt(cursor, username, False)
                if ip_address:
                    AuthService._record_login_attempt(cursor, f"ip:{ip_address}", False)
            raise AuthenticationException(
                message="Invalid username or password.",
                code="INVALID_CREDENTIALS",
            )

        if not verify_password(payload.password, user_row["password_hash"]):
            with get_db_connection() as conn:
                cursor = conn.cursor()
                AuthService._record_login_attempt(cursor, username, False)
                if ip_address:
                    AuthService._record_login_attempt(cursor, f"ip:{ip_address}", False)
                AuditService.append_event_with_cursor(
                    cursor=cursor,
                    action="USER_LOGIN_FAILED",
                    entity_type="USER",
                    entity_id=user_row["id"],
                    actor=username,
                    actor_user_id=user_row["id"],
                    actor_role=user_row["role"],
                    event_origin=AuditEventOrigin.AUTHENTICATED_HUMAN.value,
                    summary=f"Failed password authentication attempt for account '{user_row['username']}'.",
                    metadata={"username": user_row["username"], "ip_address": ip_address},
                )
            raise AuthenticationException(
                message="Invalid username or password.",
                code="INVALID_CREDENTIALS",
            )

        with get_db_connection() as conn:
            cursor = conn.cursor()
            AuthService._record_login_attempt(cursor, username, True)
            return AuthService._create_session_for_user(
                cursor=cursor,
                user_row=user_row,
                ip_address=ip_address,
                user_agent=user_agent,
                login_method="PASSWORD_LOGIN",
            )

    login = authenticate

    @staticmethod
    def bootstrap_initial_admin(
        payload: AdminBootstrapRequest, ip_address: str = "", user_agent: str = ""
    ) -> AuthSessionResponse:
        expected_token = settings.get_bootstrap_token()
        if settings.is_production and not expected_token:
            raise AuthorizationException(
                message="Initial admin bootstrap requires VERITAS_BOOTSTRAP_TOKEN in production.",
                code="BOOTSTRAP_DISABLED_IN_PRODUCTION",
            )
        if expected_token:
            provided = (payload.bootstrap_token or "").strip()
            if not hmac.compare_digest(provided, expected_token):
                raise AuthorizationException(
                    message="Invalid bootstrap token provided.",
                    code="INVALID_BOOTSTRAP_TOKEN",
                )

        now = _utc_now_iso()
        username = payload.username.strip()
        email = (
            payload.email.strip().lower()
            if payload.email
            else f"{username.lower()}@veritas.local"
        )
        full_name = payload.full_name.strip()
        title = (payload.title or "Forensic Platform Administrator").strip()

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) AS real_users FROM users WHERE is_demo_account = 0;"
            )
            if int(cursor.fetchone()["real_users"] or 0) > 0:
                raise AuthorizationException(
                    message="Bootstrap is disabled because a primary user account already exists.",
                    code="BOOTSTRAP_ALREADY_COMPLETED",
                )

            cursor.execute(
                "SELECT 1 FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?);",
                (username, email),
            )
            if cursor.fetchone():
                raise InvalidDocumentException(
                    message=f"Username '{username}' or email '{email}' is already registered.",
                    code="USER_ALREADY_EXISTS",
                )

            user_id = str(uuid.uuid4())
            pw_hash = hash_password_pbkdf2(payload.password)
            cursor.execute(
                """
                INSERT INTO users (
                    id, username, email, full_name, role, title,
                    password_hash, is_active, is_demo_account,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?);
                """,
                (
                    user_id,
                    username,
                    email,
                    full_name,
                    UserRole.ADMIN.value,
                    title,
                    pw_hash,
                    now,
                    now,
                ),
            )
            cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
            user_row = cursor.fetchone()
            return AuthService._create_session_for_user(
                cursor=cursor,
                user_row=user_row,
                ip_address=ip_address,
                user_agent=user_agent,
                login_method="ADMIN_BOOTSTRAP",
            )

    bootstrap_first_admin = bootstrap_initial_admin

    @staticmethod
    def switch_demo_persona(
        username: str, ip_address: str = "", user_agent: str = ""
    ) -> AuthSessionResponse:
        if settings.is_production or not settings.enable_demo_mode:
            raise AuthorizationException(
                message="Guided demo persona switching is disabled in production.",
                code="DEMO_MODE_DISABLED",
            )

        AuthService.ensure_demo_personas()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE LOWER(username) = LOWER(?) AND is_demo_account = 1;",
                (username.strip(),),
            )
            user_row = cursor.fetchone()
            if not user_row:
                raise ResourceNotFoundException("DemoPersona", username)

            return AuthService._create_session_for_user(
                cursor=cursor,
                user_row=user_row,
                ip_address=ip_address,
                user_agent=user_agent,
                login_method="DEV_GUIDED_DEMO_SWITCH",
            )

    @staticmethod
    def create_user(
        payload: UserCreateRequest,
        actor_user: Optional[AuthenticatedUser] = None,
    ) -> AuthenticatedUser:
        if actor_user and actor_user.role != UserRole.ADMIN.value:
            raise AuthorizationException(
                message="Only ADMIN users may create or manage user accounts.",
                code="ADMIN_ROLE_REQUIRED",
            )

        now = _utc_now_iso()
        username = payload.username.strip()
        email = (
            payload.email.strip().lower()
            if payload.email
            else f"{username.lower()}@veritas.local"
        )
        full_name = payload.full_name.strip()
        title = (payload.title or "Forensic Investigator").strip()
        role_val = (
            payload.role.value
            if isinstance(payload.role, UserRole)
            else str(payload.role).strip().upper()
        )
        valid_roles = {r.value for r in UserRole}
        if role_val not in valid_roles:
            raise InvalidDocumentException(
                message=f"Invalid role '{role_val}'. Allowed: {sorted(valid_roles)}.",
                code="INVALID_USER_ROLE",
            )

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?);",
                (username, email),
            )
            if cursor.fetchone():
                raise InvalidDocumentException(
                    message=f"User with username '{username}' or email '{email}' already exists.",
                    code="USER_ALREADY_EXISTS",
                )

            user_id = str(uuid.uuid4())
            pw_hash = hash_password_pbkdf2(payload.password)
            cursor.execute(
                """
                INSERT INTO users (
                    id, username, email, full_name, role, title,
                    password_hash, is_active, is_demo_account,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?);
                """,
                (
                    user_id,
                    username,
                    email,
                    full_name,
                    role_val,
                    title,
                    pw_hash,
                    now,
                    now,
                ),
            )
            actor_label = (
                f"{actor_user.full_name} ({actor_user.username})"
                if actor_user
                else "System Admin"
            )
            AuditService.append_event_with_cursor(
                cursor=cursor,
                action="USER_ACCOUNT_CREATED",
                entity_type="USER",
                entity_id=user_id,
                actor=actor_label,
                actor_user_id=actor_user.id if actor_user else None,
                actor_role=actor_user.role if actor_user else UserRole.ADMIN.value,
                event_origin=AuditEventOrigin.AUTHENTICATED_HUMAN.value,
                summary=f"Created user account '{username}' with role {role_val}.",
                metadata={
                    "created_user_id": user_id,
                    "created_username": username,
                    "assigned_role": role_val,
                    "title": title,
                },
                created_at=now,
            )
            cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
            return _row_to_user_profile(cursor.fetchone())

    @staticmethod
    def list_users(
        _current_user: Optional[AuthenticatedUser] = None,
    ) -> List[AuthenticatedUser]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY created_at ASC;")
            return [_row_to_user_profile(r) for r in cursor.fetchall()]

    @staticmethod
    def logout(
        raw_token: Optional[str],
        user: Optional[AuthenticatedUser] = None,
    ) -> Dict[str, Any]:
        if not raw_token:
            return {"logged_out": True}
        token_hash = _hash_session_token(raw_token)
        now = _utc_now_iso()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT s.id, s.user_id, u.username, u.full_name, u.role
                FROM user_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.is_revoked = 0;
                """,
                (token_hash,),
            )
            s_row = cursor.fetchone()
            if s_row:
                cursor.execute(
                    """
                    UPDATE user_sessions
                    SET is_revoked = 1, revoked_at = ?
                    WHERE id = ?;
                    """,
                    (now, s_row["id"]),
                )
                AuditService.append_event_with_cursor(
                    cursor=cursor,
                    action="USER_SESSION_LOGOUT",
                    entity_type="USER_SESSION",
                    entity_id=s_row["id"],
                    actor=f"{s_row['full_name']} ({s_row['username']})",
                    actor_user_id=s_row["user_id"],
                    actor_role=s_row["role"],
                    event_origin=AuditEventOrigin.AUTHENTICATED_HUMAN.value,
                    summary=f"Session logged out and invalidated for {s_row['username']}.",
                    metadata={"session_id": s_row["id"]},
                    created_at=now,
                )
        return {"logged_out": True}

    logout_session = logout

    @staticmethod
    def resolve_session_from_request(
        request: Request,
    ) -> Optional[Tuple[AuthenticatedUser, str]]:
        """
        Extracts session token from `Authorization: Bearer <token>` or HttpOnly cookie (`veritas_session`),
        verifies expiration and revocation status, and returns (AuthenticatedUser, expires_at).
        """
        auth_header = request.headers.get("Authorization")
        session_cookie = request.cookies.get(settings.session_cookie_name)
        raw_token = extract_raw_token(auth_header, session_cookie)
        if not raw_token and request.method == "GET":
            q_tok = request.query_params.get("token")
            if q_tok and q_tok.strip():
                raw_token = q_tok.strip()
        if not raw_token:
            return None

        token_hash = _hash_session_token(raw_token)
        now_iso = _utc_now_iso()

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT s.id AS session_id, s.expires_at, s.is_revoked, u.*
                FROM user_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ?;
                """,
                (token_hash,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            if bool(row["is_revoked"]) or not bool(row["is_active"]):
                return None
            if str(row["expires_at"]) <= now_iso:
                return None
            expires_at = str(row["expires_at"])
            return (
                _row_to_user_profile(
                    row,
                    session_id=str(row["session_id"]),
                    session_expires_at=expires_at,
                ),
                expires_at,
            )

    @staticmethod
    def get_auth_status(
        current_user_or_request: Optional[Union[AuthenticatedUser, Request]] = None,
    ) -> AuthStatusResponse:
        if not settings.is_production and settings.enable_demo_mode:
            AuthService.ensure_demo_personas()

        user_prof: Optional[AuthenticatedUser] = None
        expires_at: Optional[str] = None
        if isinstance(current_user_or_request, Request):
            resolved = AuthService.resolve_session_from_request(current_user_or_request)
            if resolved:
                user_prof, expires_at = resolved
        elif isinstance(current_user_or_request, AuthenticatedUser):
            user_prof = current_user_or_request
            expires_at = current_user_or_request.session_expires_at

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM users WHERE is_demo_account = 0;"
            )
            real_users_cnt = int(cursor.fetchone()["cnt"] or 0)

        demo_personas: List[DemoPersonaItem] = []
        if not settings.is_production and settings.enable_demo_mode:
            demo_personas = [
                DemoPersonaItem(
                    username=p["username"],
                    full_name=p["full_name"],
                    role=p["role"],
                    title=p["title"],
                    badge_description=p["badge_description"],
                )
                for p in DEV_DEMO_PERSONAS_SPEC
            ]

        return AuthStatusResponse(
            authenticated=user_prof is not None,
            user=user_prof,
            session_expires_at=expires_at,
            demo_mode_enabled=not settings.is_production and settings.enable_demo_mode,
            bootstrap_available=(real_users_cnt == 0),
            demo_personas=demo_personas,
        )

    @staticmethod
    def check_investigation_access(
        first_arg: Union[str, AuthenticatedUser],
        second_arg: Union[AuthenticatedUser, str],
        require_write: bool = False,
        require_review: bool = False,
    ) -> Dict[str, Any]:
        """
        Enforces investigation-level authorization and role checks.
        Accepts either (investigation_id, user) or (user, investigation_id).
        """
        if isinstance(first_arg, AuthenticatedUser):
            user = first_arg
            investigation_id = str(second_arg)
        else:
            investigation_id = str(first_arg)
            user = second_arg  # type: ignore[assignment]

        if require_write and user.role == UserRole.VIEWER.value:
            raise AuthorizationException(
                message="VIEWER role has read-only access and cannot create, modify, or execute analyses.",
                code="VIEWER_READ_ONLY_RESTRICTION",
            )

        if require_review and user.role not in (
            UserRole.REVIEWER.value,
            UserRole.ADMIN.value,
        ):
            raise AuthorizationException(
                message=f"Role '{user.role}' is not authorized to record formal review dispositions. REVIEWER or ADMIN role required.",
                code="REVIEWER_ROLE_REQUIRED",
            )

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM investigations WHERE id = ?;",
                (investigation_id,),
            )
            inv_row = cursor.fetchone()
            if not inv_row:
                raise ResourceNotFoundException("Investigation", investigation_id)

            inv_dict = dict(inv_row)
            if user.role == UserRole.ADMIN.value:
                return inv_dict

            owner_id = inv_dict.get("owner_user_id")
            is_shared = bool(inv_dict.get("is_shared_org"))

            if owner_id is None or owner_id == user.id or is_shared:
                return inv_dict

            cursor.execute(
                """
                SELECT access_level
                FROM investigation_members
                WHERE investigation_id = ? AND user_id = ?;
                """,
                (investigation_id, user.id),
            )
            member_row = cursor.fetchone()
            if not member_row:
                raise AuthorizationException(
                    message=(
                        f"User '{user.username}' does not have permission to access "
                        f"investigation '{inv_dict.get('case_code') or investigation_id}'."
                    ),
                    code="CROSS_INVESTIGATION_ACCESS_DENIED",
                    details={
                        "investigation_id": investigation_id,
                        "user_id": user.id,
                    },
                )

            if require_write and member_row["access_level"] in ("VIEWER", "READ"):
                raise AuthorizationException(
                    message="User has read-only membership on this investigation.",
                    code="INVESTIGATION_WRITE_ACCESS_DENIED",
                )

            return inv_dict

    @staticmethod
    def check_document_access(
        first_arg: Union[str, AuthenticatedUser],
        second_arg: Union[AuthenticatedUser, str],
        require_write: bool = False,
        require_review: bool = False,
    ) -> Dict[str, Any]:
        if isinstance(first_arg, AuthenticatedUser):
            user = first_arg
            document_id = str(second_arg)
        else:
            document_id = str(first_arg)
            user = second_arg  # type: ignore[assignment]

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM documents WHERE id = ?;",
                (document_id,),
            )
            doc_row = cursor.fetchone()
            if not doc_row:
                raise ResourceNotFoundException("Document", document_id)
            doc_dict = dict(doc_row)

        AuthService.check_investigation_access(
            doc_dict["investigation_id"],
            user,
            require_write=require_write,
            require_review=require_review,
        )
        return doc_dict

    @staticmethod
    def grant_investigation_member(
        investigation_id: str,
        target_user_id: str,
        access_level: str = "MEMBER",
        actor_user: Optional[AuthenticatedUser] = None,
        acting_user: Optional[AuthenticatedUser] = None,
    ) -> Dict[str, Any]:
        user = actor_user or acting_user
        if not user:
            raise AuthenticationException(message="Authentication required.")

        inv_dict = AuthService.check_investigation_access(
            investigation_id,
            user,
            require_write=True,
        )
        if (
            user.role != UserRole.ADMIN.value
            and inv_dict.get("owner_user_id") != user.id
        ):
            raise AuthorizationException(
                message="Only the investigation owner or an ADMIN can grant investigation access.",
                code="OWNER_OR_ADMIN_REQUIRED",
            )

        norm_level = access_level.strip().upper()
        if norm_level not in ("OWNER", "MEMBER", "WRITE", "REVIEWER", "VIEWER", "READ"):
            raise InvalidDocumentException(
                message=f"Invalid access_level '{access_level}'.",
                code="INVALID_ACCESS_LEVEL",
            )

        now = _utc_now_iso()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username, full_name, role FROM users WHERE id = ?;",
                (target_user_id,),
            )
            target_u = cursor.fetchone()
            if not target_u:
                raise ResourceNotFoundException("User", target_user_id)

            cursor.execute(
                """
                INSERT INTO investigation_members (
                    id, investigation_id, user_id, access_level, granted_by_user_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id, user_id) DO UPDATE SET
                    access_level = excluded.access_level,
                    granted_by_user_id = excluded.granted_by_user_id;
                """,
                (
                    str(uuid.uuid4()),
                    investigation_id,
                    target_user_id,
                    norm_level,
                    user.id,
                    now,
                ),
            )
            AuditService.append_event_with_cursor(
                cursor=cursor,
                investigation_id=investigation_id,
                action="INVESTIGATION_ACCESS_GRANTED",
                entity_type="INVESTIGATION_MEMBER",
                entity_id=target_user_id,
                actor=f"{user.full_name} ({user.username})",
                actor_user_id=user.id,
                actor_role=user.role,
                event_origin=AuditEventOrigin.AUTHENTICATED_HUMAN.value,
                summary=(
                    f"Granted {norm_level} access on {inv_dict['case_code']} to "
                    f"{target_u['full_name']} ({target_u['username']})."
                ),
                metadata={
                    "target_user_id": target_user_id,
                    "target_username": target_u["username"],
                    "access_level": norm_level,
                },
                created_at=now,
            )
        return {
            "investigation_id": investigation_id,
            "user_id": target_user_id,
            "access_level": norm_level,
            "granted_at": now,
        }


def get_optional_user(request: Request) -> Optional[AuthenticatedUser]:
    resolved = AuthService.resolve_session_from_request(request)
    if not resolved:
        return None
    return resolved[0]


def require_authenticated_user(request: Request) -> AuthenticatedUser:
    """FastAPI dependency that strictly requires a valid, unrevoked, non-expired session."""
    resolved = AuthService.resolve_session_from_request(request)
    if not resolved:
        raise AuthenticationException(
            message="Authentication required. Please sign in to access VERITAS AI.",
            code="AUTHENTICATION_REQUIRED",
        )
    return resolved[0]


def require_roles(
    *roles: Union[str, UserRole, Sequence[Union[str, UserRole]]],
) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """FastAPI dependency factory enforcing that the authenticated user holds one of `roles`."""
    allowed_values = set()
    for item in roles:
        if isinstance(item, (list, tuple, set)):
            for sub in item:
                allowed_values.add(sub.value if isinstance(sub, UserRole) else str(sub))
        else:
            allowed_values.add(item.value if isinstance(item, UserRole) else str(item))

    def _checker(
        user: AuthenticatedUser = Depends(require_authenticated_user),
    ) -> AuthenticatedUser:
        if user.role not in allowed_values:
            raise AuthorizationException(
                message=(
                    f"Role '{user.role}' is not permitted to perform this action. "
                    f"Required roles: {sorted(allowed_values)}."
                ),
                code="INSUFFICIENT_ROLE_PERMISSIONS",
                details={
                    "user_role": user.role,
                    "required_roles": sorted(allowed_values),
                },
            )
        return user

    return _checker
