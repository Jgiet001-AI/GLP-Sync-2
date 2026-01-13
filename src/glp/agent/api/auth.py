"""
JWT Authentication for Agent API.

Provides secure JWT validation for all agent endpoints.
Supports both symmetric (HS256) and asymmetric (RS256, ES256) algorithms.

Security Features:
- Full claim validation (iss, aud, exp, nbf)
- Clock skew tolerance
- Tenant/user extraction with validation
- Dev mode toggle (REQUIRE_AUTH=false)
- Comprehensive logging of auth failures
- Public key support for RS/ES algorithms

Environment Variables:
- JWT_SECRET: Secret key for HS* algorithms (required if using HMAC)
- JWT_PUBLIC_KEY: Public key for RS*/ES*/PS* algorithms (PEM format or file path)
- JWT_ALGORITHM: Algorithm to use (default: HS256)
- JWT_ISSUER: Expected issuer claim (optional)
- JWT_AUDIENCE: Expected audience claim (optional)
- REQUIRE_AUTH: Enable/disable auth (default: true)
- JWT_CLOCK_SKEW_SECONDS: Clock skew tolerance (default: 30)

Key Configuration:
- HS256/HS384/HS512: Requires JWT_SECRET (shared secret)
- RS256/RS384/RS512: Requires JWT_PUBLIC_KEY (RSA public key)
- ES256/ES384/ES512: Requires JWT_PUBLIC_KEY (ECDSA public key)
- PS256/PS384/PS512: Requires JWT_PUBLIC_KEY (RSA-PSS public key)
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Union

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel

from ..domain.entities import UserContext

logger = logging.getLogger(__name__)


class JWTConfig:
    """JWT configuration from environment variables."""

    SECRET: Optional[str] = os.getenv("JWT_SECRET")
    PUBLIC_KEY: Optional[str] = os.getenv("JWT_PUBLIC_KEY")
    ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ISSUER: Optional[str] = os.getenv("JWT_ISSUER")
    AUDIENCE: Optional[str] = os.getenv("JWT_AUDIENCE")
    REQUIRE_AUTH: bool = os.getenv("REQUIRE_AUTH", "true").lower() == "true"
    CLOCK_SKEW_SECONDS: int = int(os.getenv("JWT_CLOCK_SKEW_SECONDS", "30"))

    # Required claims in the token
    TENANT_ID_CLAIM: str = os.getenv("JWT_TENANT_ID_CLAIM", "tenant_id")
    USER_ID_CLAIM: str = os.getenv("JWT_USER_ID_CLAIM", "sub")
    SESSION_ID_CLAIM: str = os.getenv("JWT_SESSION_ID_CLAIM", "session_id")

    # Security: Explicit allowlist of algorithms (prevents 'none' and unexpected algs)
    # Only algorithms with proper cryptographic guarantees are allowed
    ALLOWED_ALGORITHMS: frozenset[str] = frozenset({
        "HS256", "HS384", "HS512",  # HMAC with SHA-2
        "RS256", "RS384", "RS512",  # RSA with SHA-2
        "ES256", "ES384", "ES512",  # ECDSA with SHA-2
        "PS256", "PS384", "PS512",  # RSA-PSS with SHA-2
    })

    # Symmetric algorithms that use shared secret
    SYMMETRIC_ALGORITHMS: frozenset[str] = frozenset({
        "HS256", "HS384", "HS512",
    })

    # Asymmetric algorithms that use public/private keys
    ASYMMETRIC_ALGORITHMS: frozenset[str] = frozenset({
        "RS256", "RS384", "RS512",  # RSA
        "ES256", "ES384", "ES512",  # ECDSA
        "PS256", "PS384", "PS512",  # RSA-PSS
    })

    # Cache for loaded public key
    _public_key_cache: Optional[str] = None

    @classmethod
    def validate_algorithm(cls) -> str:
        """Validate that configured algorithm is in the allowlist.

        Returns:
            The validated algorithm

        Raises:
            ValueError: If algorithm is not allowed
        """
        alg = cls.ALGORITHM.upper()

        # Explicitly reject 'none' algorithm (CVE-2015-2951)
        if alg == "NONE":
            raise ValueError(
                "JWT algorithm 'none' is not allowed - this is a security vulnerability"
            )

        if alg not in cls.ALLOWED_ALGORITHMS:
            raise ValueError(
                f"JWT algorithm '{cls.ALGORITHM}' is not allowed. "
                f"Allowed algorithms: {sorted(cls.ALLOWED_ALGORITHMS)}"
            )

        return alg

    @classmethod
    def is_symmetric_algorithm(cls) -> bool:
        """Check if configured algorithm is symmetric (uses shared secret)."""
        return cls.ALGORITHM.upper() in cls.SYMMETRIC_ALGORITHMS

    @classmethod
    def is_asymmetric_algorithm(cls) -> bool:
        """Check if configured algorithm is asymmetric (uses public/private keys)."""
        return cls.ALGORITHM.upper() in cls.ASYMMETRIC_ALGORITHMS

    @classmethod
    def get_verification_key(cls) -> str:
        """Get the appropriate key for JWT verification.

        For symmetric algorithms (HS*): Returns the secret
        For asymmetric algorithms (RS*/ES*/PS*): Returns the public key

        Returns:
            The verification key

        Raises:
            ValueError: If required key is not configured
        """
        if cls.is_symmetric_algorithm():
            if not cls.SECRET:
                raise ValueError(
                    f"JWT_SECRET required for symmetric algorithm {cls.ALGORITHM}"
                )
            return cls.SECRET

        # Asymmetric algorithm - need public key
        if cls._public_key_cache:
            return cls._public_key_cache

        if not cls.PUBLIC_KEY:
            raise ValueError(
                f"JWT_PUBLIC_KEY required for asymmetric algorithm {cls.ALGORITHM}. "
                "Provide PEM-formatted key directly or path to key file."
            )

        # Check if PUBLIC_KEY is a file path
        public_key = cls.PUBLIC_KEY
        if os.path.isfile(public_key):
            logger.info(f"Loading JWT public key from file: {public_key}")
            with open(public_key, "r") as f:
                public_key = f.read()

        # Validate it looks like a PEM key
        if not public_key.strip().startswith("-----BEGIN"):
            raise ValueError(
                "JWT_PUBLIC_KEY must be PEM format (starting with '-----BEGIN')"
            )

        cls._public_key_cache = public_key
        return public_key


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

    # Validate algorithm is in allowlist (prevents 'none' attack)
    try:
        JWTConfig.validate_algorithm()
    except ValueError as e:
        logger.error(f"Invalid JWT algorithm configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server authentication misconfigured",
        )

    # Validate the appropriate key is configured for the algorithm
    try:
        JWTConfig.get_verification_key()
    except ValueError as e:
        logger.error(f"JWT key configuration error: {e}")
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
        "require": ["exp"],
    }

    # Add issuer/audience verification if configured
    if JWTConfig.ISSUER:
        options["verify_iss"] = True
    if JWTConfig.AUDIENCE:
        options["verify_aud"] = True

    # Use validated algorithm from allowlist
    validated_alg = JWTConfig.validate_algorithm()

    # Get the appropriate verification key (secret or public key)
    verification_key = JWTConfig.get_verification_key()

    try:
        payload = jwt.decode(
            token,
            verification_key,
            algorithms=[validated_alg],  # Only allow the single configured algorithm
            options=options,
            issuer=JWTConfig.ISSUER,
            audience=JWTConfig.AUDIENCE,
            leeway=JWTConfig.CLOCK_SKEW_SECONDS,
        )
    except jwt.ExpiredSignatureError:
        logger.warning("JWT expired")
        raise AuthenticationError("Token has expired")
    except jwt.ImmatureSignatureError as e:
        logger.warning(f"JWT not yet valid: {e}")
        raise AuthenticationError(f"Token not yet valid: {e}")
    except jwt.InvalidAudienceError as e:
        logger.warning(f"JWT audience error: {e}")
        raise AuthenticationError(f"Invalid token claims: {e}")
    except jwt.InvalidIssuerError as e:
        logger.warning(f"JWT issuer error: {e}")
        raise AuthenticationError(f"Invalid token claims: {e}")
    except InvalidTokenError as e:
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
