#!/usr/bin/env python3
"""Unit tests for OAuth2 Token Management.

Tests cover:
    - Token fetching and caching
    - Token expiration detection
    - Retry logic on failures
    - Thread-safety of concurrent token requests
"""

# Import the classes we're testing
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(__file__).rsplit("/tests", 1)[0])
from src.glp.api.auth import CachedToken, TokenManager
from src.glp.api.exceptions import ConfigurationError

# ============================================
# CachedToken Tests
# ============================================

class TestCachedToken:
    """Test the CachedToken dataclass."""

    def test_not_expired_when_new(self):
        """Fresh token should not be expired."""
        token = CachedToken(
            access_token="test_token_123",
            expires_at=time.time() + 3600,  # 1 hour from now
        )
        assert not token.is_expired
        assert token.time_remaining > 3500  # Should have ~1 hour

    def test_expired_when_past(self):
        """Token with past expiration should be expired."""
        token = CachedToken(
            access_token="test_token_123",
            expires_at=time.time() - 100,  # Already expired
        )
        assert token.is_expired
        assert token.time_remaining == 0

    def test_expired_within_buffer(self):
        """Token expiring within dynamic buffer should be considered expired.

        Dynamic buffer is 10% of TTL, capped between 30s and 300s, plus jitter.
        Default expires_in=7200 gives buffer of 300s (max cap).
        """
        token = CachedToken(
            access_token="test_token_123",
            expires_at=time.time() + 200,  # 200 seconds from now (< 300 max buffer)
            expires_in=7200,  # Default TTL, 10% = 720s but capped at 300s
        )
        assert token.is_expired  # Should be considered expired due to buffer

    def test_dynamic_buffer_short_ttl(self):
        """Short TTL should use 10% buffer (not fixed 5 minutes)."""
        # 600s TTL gives 60s base buffer (10%), plus ±10% jitter (54-66s)
        token = CachedToken(
            access_token="test_token_123",
            expires_at=time.time() + 50,  # 50 seconds from now (< min jitter of 54s)
            expires_in=600,  # 10 minute TTL → 60s buffer (± jitter)
        )
        # With 50s remaining and 54-66s buffer, token should be expired
        assert token.is_expired

    def test_token_id_is_sha256_hash(self):
        """token_id should be SHA-256 hash prefix for safe logging."""
        import hashlib
        token = CachedToken(
            access_token="my_secret_token_value",
            expires_at=time.time() + 3600,
        )
        expected_hash = hashlib.sha256(b"my_secret_token_value").hexdigest()[:8]
        assert token.token_id == expected_hash
        assert "my_secret" not in token.token_id

    def test_default_token_type(self):
        """Token type should default to Bearer."""
        token = CachedToken(access_token="test", expires_at=time.time() + 3600)
        assert token.token_type == "Bearer"


# ============================================
# TokenManager Tests
# ============================================

class TestTokenManager:
    """Test the TokenManager class."""

    @pytest.fixture
    def env_vars(self, monkeypatch):
        """Set required environment variables."""
        monkeypatch.setenv("GLP_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("GLP_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("GLP_TOKEN_URL", "https://auth.example.com/token")

    def test_missing_env_vars_raises(self, monkeypatch):
        """Should raise ConfigurationError when env vars are missing."""
        monkeypatch.delenv("GLP_CLIENT_ID", raising=False)
        monkeypatch.delenv("GLP_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("GLP_TOKEN_URL", raising=False)

        with pytest.raises(ConfigurationError) as exc:
            TokenManager()

        assert "GLP_CLIENT_ID" in str(exc.value)

    def test_explicit_credentials(self, monkeypatch):
        """Should accept explicit credentials over env vars."""
        monkeypatch.delenv("GLP_CLIENT_ID", raising=False)

        manager = TokenManager(
            client_id="explicit_id",
            client_secret="explicit_secret",
            token_url="https://explicit.example.com/token",
        )

        assert manager.client_id == "explicit_id"
        assert manager.client_secret == "explicit_secret"

    @pytest.mark.asyncio
    async def test_get_token_fetches_new(self, env_vars):
        """First call to get_token should fetch a new token."""
        manager = TokenManager()

        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "access_token": "new_access_token_abc123",
            "expires_in": 3600,
            "token_type": "Bearer",
        })

        # Create proper async context manager mocks
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            token = await manager.get_token()

        assert token == "new_access_token_abc123"

    @pytest.mark.asyncio
    async def test_get_token_returns_cached(self, env_vars):
        """Second call should return cached token without HTTP call."""
        manager = TokenManager()

        # Pre-populate the cache
        manager._cached_token = CachedToken(
            access_token="cached_token_xyz",
            expires_at=time.time() + 3600,
        )

        # This should NOT make an HTTP call
        with patch("aiohttp.ClientSession") as mock_session_cls:
            token = await manager.get_token()
            mock_session_cls.assert_not_called()

        assert token == "cached_token_xyz"

    @pytest.mark.asyncio
    async def test_invalidate_clears_cache(self, env_vars):
        """invalidate() should clear the cached token."""
        manager = TokenManager()
        manager._cached_token = CachedToken(
            access_token="cached_token",
            expires_at=time.time() + 3600,
        )

        manager.invalidate()

        assert manager._cached_token is None

    def test_token_info_returns_debug_data(self, env_vars):
        """token_info should return safe debug information with SHA-256 hash."""
        import hashlib
        manager = TokenManager()
        test_token = "a_very_long_token_that_should_be_hashed"
        manager._cached_token = CachedToken(
            access_token=test_token,
            expires_at=time.time() + 3600,
        )

        info = manager.token_info

        assert not info["is_expired"]
        assert info["time_remaining_seconds"] > 3500
        # Should use SHA-256 hash prefix instead of truncated token
        expected_hash = hashlib.sha256(test_token.encode()).hexdigest()[:8]
        assert info["token_id"] == expected_hash
        # Verify actual token is not exposed
        assert "a_very_long" not in str(info)
        assert "token_preview" not in info  # Old field should not exist


# ============================================
# Run tests
# ============================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
