import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

JWT_ALGORITHM = "HS256"
DEFAULT_JWT_EXPIRES_MINUTES = 480

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
http_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def _jwt_secret() -> str:
    return os.getenv("JWT_SECRET", "dev-change-this-jwt-secret")


def _jwt_expires_minutes() -> int:
    raw_value = os.getenv("JWT_EXPIRES_MINUTES")
    if not raw_value:
        return DEFAULT_JWT_EXPIRES_MINUTES

    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_JWT_EXPIRES_MINUTES

    if value <= 0:
        return DEFAULT_JWT_EXPIRES_MINUTES

    return value


def create_access_token(user_id: int) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=_jwt_expires_minutes())

    payload = {
        "sub": str(user_id),
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    token = jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)
    expires_in = int((expires_at - now).total_seconds())
    return token, expires_in


def cleanup_expired_revoked_tokens(request: Request) -> None:
    now_ts = int(datetime.now(timezone.utc).timestamp())
    request.app.state.db.cleanup_expired_revoked_tokens(now_ts)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
        )

    token = credentials.credentials

    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired.",
        ) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
        ) from exc

    user_id_raw = payload.get("sub")
    token_jti = payload.get("jti")
    token_exp = payload.get("exp")

    if not user_id_raw or not token_jti or not token_exp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
        )

    try:
        user_id = int(user_id_raw)
        token_exp_int = int(token_exp)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
        ) from exc

    cleanup_expired_revoked_tokens(request)
    if request.app.state.db.is_token_revoked(token_jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revoked.",
        )

    user = request.app.state.db.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    return {
        "id": user["id"],
        "name": user["name"],
        "groups": request.app.state.db.get_user_groups(user["id"]),
        "token_jti": token_jti,
        "token_exp": token_exp_int,
    }
