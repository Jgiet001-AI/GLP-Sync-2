"""
Integration tests for JWT authentication.

Tests the security of the JWT authentication system.
"""

import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest

from src.glp.agent.api.auth import (
    AuthenticationError,
    JWTConfig,
    TokenPayload,
    _extract_token,
    _validate_token,
    get_user_context_jwt,
)
from src.glp.agent.domain.entities import UserContext


# Test fixtures
@pytest.fixture
def jwt_secret():
    """Test JWT secret."""
    return "test-secret-key-for-testing-only"


@pytest.fixture
def valid_payload():
    """Valid JWT payload."""
    return {
        "sub": "user123",
        "tenant_id": "tenant456",
        "session_id": "session789",
        "iss": "test-issuer",
        "aud": "test-audience",
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "nbf": int(datetime.now(timezone.utc).timestamp()),
    }


@pytest.fixture
def valid_token(jwt_secret, valid_payload):
    """Generate a valid JWT token."""
    return jwt.encode(valid_payload, jwt_secret, algorithm="HS256")


@pytest.fixture
def expired_token(jwt_secret, valid_payload):
    """Generate an expired JWT token."""
    payload = valid_payload.copy()
    payload["exp"] = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


@pytest.fixture
def token_missing_tenant(jwt_secret, valid_payload):
    """Generate a token missing tenant_id."""
    payload = valid_payload.copy()
    del payload["tenant_id"]
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


@pytest.fixture
def token_missing_user(jwt_secret, valid_payload):
    """Generate a token missing sub (user_id)."""
    payload = valid_payload.copy()
    del payload["sub"]
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


class TestExtractToken:
    """Tests for token extraction from Authorization header."""

    def test_extract_valid_bearer_token(self):
        """Valid Bearer token is extracted correctly."""
        result = _extract_token("Bearer abc123token")
        assert result == "abc123token"

    def test_extract_bearer_case_insensitive(self):
        """Bearer keyword is case insensitive."""
        result = _extract_token("bearer abc123token")
        assert result == "abc123token"

    def test_extract_missing_bearer_prefix(self):
        """Missing Bearer prefix raises error."""
        with pytest.raises(AuthenticationError) as exc_info:
            _extract_token("abc123token")
        assert "Invalid authorization header format" in str(exc_info.value.detail)

    def test_extract_wrong_auth_type(self):
        """Wrong auth type raises error."""
        with pytest.raises(AuthenticationError) as exc_info:
            _extract_token("Basic abc123token")
        assert "Invalid authorization header format" in str(exc_info.value.detail)

    def test_extract_empty_token(self):
        """Empty authorization raises error."""
        with pytest.raises(AuthenticationError) as exc_info:
            _extract_token("")
        assert "Authorization header required" in str(exc_info.value.detail)


class TestValidateToken:
    """Tests for JWT validation."""

    def test_validate_valid_token(self, jwt_secret, valid_token):
        """Valid token is validated successfully."""
        with patch.object(JWTConfig, "SECRET", jwt_secret), \
             patch.object(JWTConfig, "ISSUER", "test-issuer"), \
             patch.object(JWTConfig, "AUDIENCE", "test-audience"):
            result = _validate_token(valid_token)

        assert isinstance(result, TokenPayload)
        assert result.user_id == "user123"
        assert result.tenant_id == "tenant456"
        assert result.session_id == "session789"

    def test_validate_expired_token(self, jwt_secret, expired_token):
        """Expired token raises authentication error."""
        with patch.object(JWTConfig, "SECRET", jwt_secret), \
             patch.object(JWTConfig, "ISSUER", "test-issuer"), \
             patch.object(JWTConfig, "AUDIENCE", "test-audience"):
            with pytest.raises(AuthenticationError) as exc_info:
                _validate_token(expired_token)
        assert "expired" in str(exc_info.value.detail).lower()

    def test_validate_invalid_signature(self, jwt_secret, valid_token):
        """Token with wrong secret raises error."""
        with patch.object(JWTConfig, "SECRET", "wrong-secret"), \
             patch.object(JWTConfig, "ISSUER", "test-issuer"), \
             patch.object(JWTConfig, "AUDIENCE", "test-audience"):
            with pytest.raises(AuthenticationError) as exc_info:
                _validate_token(valid_token)
        assert "Invalid token" in str(exc_info.value.detail)

    def test_validate_missing_tenant_id(self, jwt_secret, token_missing_tenant):
        """Token missing tenant_id raises error."""
        with patch.object(JWTConfig, "SECRET", jwt_secret), \
             patch.object(JWTConfig, "ISSUER", "test-issuer"), \
             patch.object(JWTConfig, "AUDIENCE", "test-audience"):
            with pytest.raises(AuthenticationError) as exc_info:
                _validate_token(token_missing_tenant)
        assert "tenant_id" in str(exc_info.value.detail)

    def test_validate_missing_user_id(self, jwt_secret, token_missing_user):
        """Token missing sub (user_id) raises error."""
        with patch.object(JWTConfig, "SECRET", jwt_secret), \
             patch.object(JWTConfig, "ISSUER", "test-issuer"), \
             patch.object(JWTConfig, "AUDIENCE", "test-audience"):
            with pytest.raises(AuthenticationError) as exc_info:
                _validate_token(token_missing_user)
        assert "sub" in str(exc_info.value.detail)

    def test_validate_malformed_token(self, jwt_secret):
        """Malformed token raises error."""
        with patch.object(JWTConfig, "SECRET", jwt_secret):
            with pytest.raises(AuthenticationError):
                _validate_token("not.a.valid.jwt")


class TestDevModeBypass:
    """Tests for development mode authentication bypass."""

    @pytest.mark.asyncio
    async def test_dev_mode_bypasses_auth(self):
        """When REQUIRE_AUTH=false, auth is bypassed."""
        with patch.object(JWTConfig, "REQUIRE_AUTH", False), \
             patch.object(JWTConfig, "SECRET", "test-secret"):
            # Should not raise even with invalid auth
            from src.glp.agent.api.auth import validate_jwt_token
            result = await validate_jwt_token("Bearer invalid")

        assert result.tenant_id == "dev-tenant"
        assert result.user_id == "dev-user"

    @pytest.mark.asyncio
    async def test_prod_mode_requires_valid_jwt(self, jwt_secret):
        """When REQUIRE_AUTH=true, valid JWT is required."""
        with patch.object(JWTConfig, "REQUIRE_AUTH", True), \
             patch.object(JWTConfig, "SECRET", jwt_secret):
            from src.glp.agent.api.auth import validate_jwt_token
            with pytest.raises(AuthenticationError):
                await validate_jwt_token("Bearer invalid")


class TestUserContextExtraction:
    """Tests for UserContext extraction from JWT."""

    @pytest.mark.asyncio
    async def test_user_context_from_valid_jwt(self, jwt_secret, valid_token):
        """UserContext is correctly extracted from valid JWT."""
        with patch.object(JWTConfig, "SECRET", jwt_secret), \
             patch.object(JWTConfig, "REQUIRE_AUTH", True), \
             patch.object(JWTConfig, "ISSUER", "test-issuer"), \
             patch.object(JWTConfig, "AUDIENCE", "test-audience"):
            from src.glp.agent.api.auth import validate_jwt_token
            result = await validate_jwt_token(f"Bearer {valid_token}")

        assert isinstance(result, TokenPayload)
        assert result.tenant_id == "tenant456"
        assert result.user_id == "user123"
        assert result.session_id == "session789"


class TestClockSkewTolerance:
    """Tests for clock skew tolerance."""

    def test_slightly_future_nbf_accepted(self, jwt_secret, valid_payload):
        """Token with nbf slightly in the future is accepted (clock skew)."""
        payload = valid_payload.copy()
        # Set nbf 20 seconds in the future (within default 30s tolerance)
        payload["nbf"] = int((datetime.now(timezone.utc) + timedelta(seconds=20)).timestamp())
        token = jwt.encode(payload, jwt_secret, algorithm="HS256")

        with patch.object(JWTConfig, "SECRET", jwt_secret), \
             patch.object(JWTConfig, "CLOCK_SKEW_SECONDS", 30), \
             patch.object(JWTConfig, "ISSUER", "test-issuer"), \
             patch.object(JWTConfig, "AUDIENCE", "test-audience"):
            result = _validate_token(token)

        assert result.user_id == "user123"

    def test_far_future_nbf_rejected(self, jwt_secret, valid_payload):
        """Token with nbf far in the future is rejected."""
        payload = valid_payload.copy()
        # Set nbf 2 minutes in the future (beyond tolerance)
        payload["nbf"] = int((datetime.now(timezone.utc) + timedelta(minutes=2)).timestamp())
        token = jwt.encode(payload, jwt_secret, algorithm="HS256")

        with patch.object(JWTConfig, "SECRET", jwt_secret), \
             patch.object(JWTConfig, "CLOCK_SKEW_SECONDS", 30), \
             patch.object(JWTConfig, "ISSUER", "test-issuer"), \
             patch.object(JWTConfig, "AUDIENCE", "test-audience"):
            with pytest.raises(AuthenticationError):
                _validate_token(token)
