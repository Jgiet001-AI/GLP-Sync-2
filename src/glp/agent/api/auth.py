"""
JWT Authentication for Agent API.

Provides secure JWT validation for all agent endpoints.
Supports both HS256 (symmetric) and RS256 (asymmetric) algorithms.

Security Features:
- Full claim validation (iss, aud, exp, nbf)
- Clock skew tolerance
- Tenant/user extraction with validation
- Dev mode toggle (REQUIRE_AUTH=false)
- Comprehensive logging of auth failures

Environment Variables:
- JWT_SECRET: Secret key for HS256 (required if using HS256)
- JWT_ALGORITHM: Algorithm to use (default: HS256)
- JWT_ISSUER: Expected issuer claim (optional)
- JWT_AUDIENCE: Expected audience claim (optional)
- REQUIRE_AUTH: Enable/disable auth (default: true)
- JWT_CLOCK_SKEW_SECONDS: Clock skew tolerance (default: 30)
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Union

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel

from ..domain.entities import UserContext

logger = logging.getLogger(__name__)


class JWTConfig:
    """JWT configuration from environment variables."""

    SECRET: Optional[str] = os.getenv("JWT_SECRET")
    ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ISSUER: Optional[str] = os.getenv("JWT_ISSUER")
    AUDIENCE: Optional[str] = os.getenv("JWT_AUDIENCE")
    REQUIRE_AUTH: bool = os.getenv("REQUIRE_AUTH", "true").lower() == "true"
    CLOCK_SKEW_SECONDS: int = int(os.getenv("JWT_CLOCK_SKEW_SECONDS", "30"))

    # Required claims in the token
    TENANT_ID_CLAIM: str = os.getenv("JWT_TENANT_ID_CLAIM", "tenant_id")
    USER_ID_CLAIM: str = os.getenv("JWT_USER_ID_CLAIM", "sub")
    SESSION_ID_CLAIM: str = os.getenv("JWT_SESSION_ID_CLAIM", "session_id")


class TokenPayload(BaseModel):
    """Validated JWT payload."""

    tenant_id: str
    user_id: str
    session_id: Optional[str] = None

    # Standard claims
    iss: Optional[str] = None
    aud: Optional[Union[str, list[str]]] = None  # Can be string or list
    exp: Optional[int] = None
    iat: Optional[int] = None
    nbf: Optional[int] = None


class AuthenticationError(HTTPException):
    """Authentication failure exception."""

    def __init__(self, detail: str, headers: Optional[dict] = None):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers=headers or {"WWW-Authenticate": "Bearer"},
        )


class AuthorizationError(HTTPException):
    """Authorization failure exception."""

    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


def _check_config() -> None:
    """Verify JWT configuration is valid.

    Raises:
        HTTPException: If configuration is invalid in production mode
    """
    if not JWTConfig.REQUIRE_AUTH:
        logger.warning(
            "REQUIRE_AUTH=false - authentication disabled. "
            "This should NEVER be used in production!"
        )
        return

    if not JWTConfig.SECRET:
        logger.error("JWT_SECRET not configured but REQUIRE_AUTH=true")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server authentication not configured",
        )


def _extract_token(authorization: str) -> str:
    """Extract bearer token from Authorization header.

    Args:
        authorization: Authorization header value

    Returns:
        The token string

    Raises:
        AuthenticationError: If header format is invalid
    """
    if not authorization:
        raise AuthenticationError("Authorization header required")

    parts = authorization.split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthenticationError(
            "Invalid authorization header format. Expected: Bearer <token>"
        )

    return parts[1]


def _validate_token(token: str) -> TokenPayload:
    """Validate JWT and extract payload.

    Args:
        token: JWT string

    Returns:
        Validated token payload

    Raises:
        AuthenticationError: If token is invalid
    """
    options = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_nbf": True,
        "verify_iat": True,
        "require_exp": True,
        "leeway": JWTConfig.CLOCK_SKEW_SECONDS,
    }

    # Add issuer/audience verification if configured
    if JWTConfig.ISSUER:
        options["verify_iss"] = True
    if JWTConfig.AUDIENCE:
        options["verify_aud"] = True

    try:
        payload = jwt.decode(
            token,
            JWTConfig.SECRET,
            algorithms=[JWTConfig.ALGORITHM],
            options=options,
            issuer=JWTConfig.ISSUER,
            audience=JWTConfig.AUDIENCE,
        )
    except jwt.ExpiredSignatureError:
        logger.warning("JWT expired")
        raise AuthenticationError("Token has expired")
    except jwt.JWTClaimsError as e:
        logger.warning(f"JWT claims error: {e}")
        raise AuthenticationError(f"Invalid token claims: {e}")
    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise AuthenticationError("Invalid token")

    # Extract required claims
    tenant_id = payload.get(JWTConfig.TENANT_ID_CLAIM)
    user_id = payload.get(JWTConfig.USER_ID_CLAIM)

    if not tenant_id:
        logger.warning(f"Missing {JWTConfig.TENANT_ID_CLAIM} claim in token")
        raise AuthenticationError(f"Token missing required claim: {JWTConfig.TENANT_ID_CLAIM}")

    if not user_id:
        logger.warning(f"Missing {JWTConfig.USER_ID_CLAIM} claim in token")
        raise AuthenticationError(f"Token missing required claim: {JWTConfig.USER_ID_CLAIM}")

    return TokenPayload(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=payload.get(JWTConfig.SESSION_ID_CLAIM),
        iss=payload.get("iss"),
        aud=payload.get("aud"),
        exp=payload.get("exp"),
        iat=payload.get("iat"),
        nbf=payload.get("nbf"),
    )


async def validate_jwt_token(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> TokenPayload:
    """FastAPI dependency for JWT validation.

    Args:
        authorization: Authorization header with Bearer token (optional in dev mode)

    Returns:
        Validated token payload

    Raises:
        AuthenticationError: If authentication fails
    """
    _check_config()

    # Dev mode bypass - works even without Authorization header
    if not JWTConfig.REQUIRE_AUTH:
        logger.debug("Auth disabled - returning dev context")
        return TokenPayload(
            tenant_id="dev-tenant",
            user_id="dev-user",
            session_id="dev-session",
        )

    # In production mode, header is required
    if not authorization:
        raise AuthenticationError("Authorization header required")

    token = _extract_token(authorization)
    return _validate_token(token)


def get_user_context_jwt(
    token_payload: TokenPayload = Depends(validate_jwt_token),
) -> UserContext:
    """Extract user context from validated JWT.

    This is the secure replacement for the header-based get_user_context.

    Args:
        token_payload: Validated JWT payload

    Returns:
        UserContext with tenant/user from JWT
    """
    return UserContext(
        tenant_id=token_payload.tenant_id,
        user_id=token_payload.user_id,
        session_id=token_payload.session_id,
    )


# Alias for backward compatibility during migration
get_user_context = get_user_context_jwt
