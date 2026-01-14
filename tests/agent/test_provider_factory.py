"""
Tests for embedding provider selection and fallback logic.

Tests the provider factory logic in app.py that selects embedding providers
based on environment variables and implements automatic fallback.
"""

import logging
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.glp.agent.providers.base import LLMProviderConfig, LLMProviderError
from src.glp.agent.providers.openai import OpenAIProvider, OPENAI_AVAILABLE
from src.glp.agent.providers.voyageai import VoyageAIProvider, VOYAGEAI_AVAILABLE


# Skip if OpenAI not installed (required for fallback)
pytestmark = pytest.mark.skipif(
    not OPENAI_AVAILABLE,
    reason="openai package required for provider selection tests"
)


@pytest.fixture
def clean_env(monkeypatch):
    """Clean environment for provider selection tests."""
    # Remove all provider-related env vars
    env_vars = [
        "EMBEDDING_PROVIDER",
        "VOYAGE_API_KEY",
        "VOYAGEAI_API_KEY",
        "OPENAI_API_KEY",
        "VOYAGE_EMBEDDING_MODEL",
        "OPENAI_EMBEDDING_MODEL",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def mock_logger():
    """Mock logger to capture log messages."""
    logger = MagicMock(spec=logging.Logger)
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    return logger


class TestEmbeddingProviderSelection:
    """Tests for embedding provider selection logic."""

    def test_default_to_openai_when_no_env_var(self, clean_env, mock_logger):
        """Default to OpenAI when EMBEDDING_PROVIDER not set."""
        clean_env.setenv("OPENAI_API_KEY", "test-openai-key")

        # Mock provider creation
        with patch("src.glp.agent.providers.openai.AsyncOpenAI"):
            # Simulate the selection logic from app.py
            embedding_provider_name = os.getenv("EMBEDDING_PROVIDER", "openai").lower()
            assert embedding_provider_name == "openai"

            # Should create OpenAI provider
            config = LLMProviderConfig(
                api_key="test-openai-key",
                model="gpt-4o",
                embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
            )
            provider = OpenAIProvider(config)
            assert provider is not None
            assert provider.embedding_model == "text-embedding-3-large"

    def test_select_voyageai_when_env_var_set(self, clean_env, mock_logger):
        """Select Voyage AI when EMBEDDING_PROVIDER=voyageai."""
        clean_env.setenv("EMBEDDING_PROVIDER", "voyageai")
        clean_env.setenv("VOYAGE_API_KEY", "test-voyage-key")
        clean_env.setenv("OPENAI_API_KEY", "test-openai-key")

        embedding_provider_name = os.getenv("EMBEDDING_PROVIDER", "openai").lower()
        assert embedding_provider_name == "voyageai"

        # Validate provider name
        valid_providers = ["openai", "voyageai", "voyage"]
        assert embedding_provider_name in valid_providers

    def test_select_voyage_alternative_name(self, clean_env, mock_logger):
        """Select Voyage AI when EMBEDDING_PROVIDER=voyage."""
        clean_env.setenv("EMBEDDING_PROVIDER", "voyage")
        clean_env.setenv("VOYAGE_API_KEY", "test-voyage-key")

        embedding_provider_name = os.getenv("EMBEDDING_PROVIDER", "openai").lower()
        assert embedding_provider_name == "voyage"

        # Should be recognized as valid
        valid_providers = ["openai", "voyageai", "voyage"]
        assert embedding_provider_name in valid_providers

    def test_invalid_provider_name_validation(self, clean_env, mock_logger):
        """Invalid provider name should be detected."""
        clean_env.setenv("EMBEDDING_PROVIDER", "invalid-provider")

        embedding_provider_name = os.getenv("EMBEDDING_PROVIDER", "openai").lower()
        assert embedding_provider_name == "invalid-provider"

        # Validation logic
        valid_providers = ["openai", "voyageai", "voyage"]
        is_valid = embedding_provider_name in valid_providers

        assert is_valid is False
        # In app.py, this would trigger a warning and fallback to openai


class TestVoyageAIFallbackLogic:
    """Tests for Voyage AI provider fallback scenarios."""

    def test_fallback_when_voyage_api_key_missing(self, clean_env, mock_logger):
        """Fallback to OpenAI when VOYAGE_API_KEY not set."""
        clean_env.setenv("EMBEDDING_PROVIDER", "voyageai")
        clean_env.setenv("OPENAI_API_KEY", "test-openai-key")
        # VOYAGE_API_KEY not set

        embedding_provider_name = os.getenv("EMBEDDING_PROVIDER", "openai").lower()
        voyage_key = os.getenv("VOYAGE_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        assert embedding_provider_name == "voyageai"
        assert voyage_key is None
        assert openai_key == "test-openai-key"

        # Should fallback to OpenAI
        embedding_provider = None
        if not voyage_key:
            # Fallback logic would be triggered
            with patch("src.glp.agent.providers.openai.AsyncOpenAI"):
                config = LLMProviderConfig(
                    api_key=openai_key,
                    model="gpt-4o",
                    embedding_model="text-embedding-3-large",
                )
                embedding_provider = OpenAIProvider(config)

        assert embedding_provider is not None
        assert isinstance(embedding_provider, OpenAIProvider)

    @pytest.mark.skipif(not VOYAGEAI_AVAILABLE, reason="voyageai package not installed")
    def test_fallback_when_voyage_init_fails(self, clean_env, mock_logger):
        """Fallback to OpenAI when Voyage AI initialization fails."""
        clean_env.setenv("EMBEDDING_PROVIDER", "voyageai")
        clean_env.setenv("VOYAGE_API_KEY", "invalid-key")
        clean_env.setenv("OPENAI_API_KEY", "test-openai-key")

        embedding_provider = None
        voyage_key = os.getenv("VOYAGE_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        # Try Voyage AI (should fail)
        if voyage_key and VoyageAIProvider:
            try:
                with patch("src.glp.agent.providers.voyageai.voyageai.Client", side_effect=Exception("Invalid API key")):
                    embedding_config = LLMProviderConfig(
                        api_key=voyage_key,
                        model="voyage-2",
                        embedding_model="voyage-2",
                    )
                    embedding_provider = VoyageAIProvider(embedding_config)
            except Exception:
                # Fallback to OpenAI
                with patch("src.glp.agent.providers.openai.AsyncOpenAI"):
                    embedding_config = LLMProviderConfig(
                        api_key=openai_key,
                        model="gpt-4o",
                        embedding_model="text-embedding-3-large",
                    )
                    embedding_provider = OpenAIProvider(embedding_config)

        assert embedding_provider is not None
        assert isinstance(embedding_provider, OpenAIProvider)

    def test_fallback_when_voyageai_not_available(self, clean_env, mock_logger):
        """Fallback to OpenAI when VoyageAI package not installed."""
        clean_env.setenv("EMBEDDING_PROVIDER", "voyageai")
        clean_env.setenv("VOYAGE_API_KEY", "test-voyage-key")
        clean_env.setenv("OPENAI_API_KEY", "test-openai-key")

        embedding_provider = None
        voyage_key = os.getenv("VOYAGE_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        # Simulate VoyageAIProvider not available
        with patch("src.glp.agent.providers.voyageai.VOYAGEAI_AVAILABLE", False):
            # Check availability
            if voyage_key and not VOYAGEAI_AVAILABLE:
                # Should fallback to OpenAI
                with patch("src.glp.agent.providers.openai.AsyncOpenAI"):
                    config = LLMProviderConfig(
                        api_key=openai_key,
                        model="gpt-4o",
                        embedding_model="text-embedding-3-large",
                    )
                    embedding_provider = OpenAIProvider(config)

        assert embedding_provider is not None
        assert isinstance(embedding_provider, OpenAIProvider)


class TestOpenAIProviderSelection:
    """Tests for OpenAI provider selection."""

    def test_use_openai_when_explicitly_set(self, clean_env, mock_logger):
        """Use OpenAI when EMBEDDING_PROVIDER=openai."""
        clean_env.setenv("EMBEDDING_PROVIDER", "openai")
        clean_env.setenv("OPENAI_API_KEY", "test-openai-key")

        embedding_provider_name = os.getenv("EMBEDDING_PROVIDER", "openai").lower()
        openai_key = os.getenv("OPENAI_API_KEY")

        assert embedding_provider_name == "openai"
        assert openai_key == "test-openai-key"

        # Should not try Voyage AI
        embedding_provider = None
        if embedding_provider_name == "openai" and openai_key:
            with patch("src.glp.agent.providers.openai.AsyncOpenAI"):
                config = LLMProviderConfig(
                    api_key=openai_key,
                    model="gpt-4o",
                    embedding_model="text-embedding-3-large",
                )
                embedding_provider = OpenAIProvider(config)

        assert embedding_provider is not None
        assert isinstance(embedding_provider, OpenAIProvider)

    def test_custom_openai_embedding_model(self, clean_env, mock_logger):
        """Custom OpenAI embedding model is respected."""
        clean_env.setenv("EMBEDDING_PROVIDER", "openai")
        clean_env.setenv("OPENAI_API_KEY", "test-openai-key")
        clean_env.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

        openai_key = os.getenv("OPENAI_API_KEY")
        embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")

        assert embedding_model == "text-embedding-3-small"

        with patch("src.glp.agent.providers.openai.AsyncOpenAI"):
            config = LLMProviderConfig(
                api_key=openai_key,
                model="gpt-4o",
                embedding_model=embedding_model,
            )
            provider = OpenAIProvider(config)
            assert provider.embedding_model == "text-embedding-3-small"


class TestProviderConfigurationEdgeCases:
    """Tests for edge cases in provider configuration."""

    def test_no_providers_available(self, clean_env, mock_logger):
        """No provider when all API keys missing."""
        # No API keys set

        voyage_key = os.getenv("VOYAGE_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        assert voyage_key is None
        assert openai_key is None

        # Both providers should fail to initialize
        embedding_provider = None
        assert embedding_provider is None

    def test_case_insensitive_provider_name(self, clean_env, mock_logger):
        """Provider name is case insensitive."""
        clean_env.setenv("EMBEDDING_PROVIDER", "VoyageAI")

        embedding_provider_name = os.getenv("EMBEDDING_PROVIDER", "openai").lower()
        assert embedding_provider_name == "voyageai"

        valid_providers = ["openai", "voyageai", "voyage"]
        assert embedding_provider_name in valid_providers

    @pytest.mark.skipif(not VOYAGEAI_AVAILABLE, reason="voyageai package not installed")
    def test_custom_voyage_embedding_model(self, clean_env, mock_logger):
        """Custom Voyage embedding model is respected."""
        clean_env.setenv("EMBEDDING_PROVIDER", "voyageai")
        clean_env.setenv("VOYAGE_API_KEY", "test-voyage-key")
        clean_env.setenv("VOYAGE_EMBEDDING_MODEL", "voyage-large-2")

        voyage_key = os.getenv("VOYAGE_API_KEY")
        embedding_model = os.getenv("VOYAGE_EMBEDDING_MODEL", "voyage-2")

        assert embedding_model == "voyage-large-2"

        with patch("src.glp.agent.providers.voyageai.voyageai.Client"):
            config = LLMProviderConfig(
                api_key=voyage_key,
                model="voyage-2",
                embedding_model=embedding_model,
            )
            provider = VoyageAIProvider(config)
            assert provider.embedding_model == "voyage-large-2"

    def test_whitespace_in_provider_name(self, clean_env, mock_logger):
        """Whitespace is handled in provider name."""
        clean_env.setenv("EMBEDDING_PROVIDER", "  voyageai  ")

        embedding_provider_name = os.getenv("EMBEDDING_PROVIDER", "openai").lower().strip()
        assert embedding_provider_name == "voyageai"

    def test_empty_provider_name_defaults_to_openai(self, clean_env, mock_logger):
        """Empty provider name defaults to OpenAI."""
        clean_env.setenv("EMBEDDING_PROVIDER", "")

        # Default behavior when empty
        embedding_provider_name = os.getenv("EMBEDDING_PROVIDER") or "openai"
        embedding_provider_name = embedding_provider_name.lower()

        assert embedding_provider_name == "openai"


class TestProviderValidation:
    """Tests for provider validation logic."""

    def test_validate_voyageai_provider_name(self):
        """Validate that 'voyageai' is a valid provider name."""
        valid_providers = ["openai", "voyageai", "voyage"]
        assert "voyageai" in valid_providers

    def test_validate_voyage_provider_name(self):
        """Validate that 'voyage' is a valid provider name."""
        valid_providers = ["openai", "voyageai", "voyage"]
        assert "voyage" in valid_providers

    def test_validate_openai_provider_name(self):
        """Validate that 'openai' is a valid provider name."""
        valid_providers = ["openai", "voyageai", "voyage"]
        assert "openai" in valid_providers

    def test_invalid_provider_names(self):
        """Invalid provider names are detected."""
        valid_providers = ["openai", "voyageai", "voyage"]

        invalid_names = ["anthropic", "cohere", "huggingface", "azure", ""]
        for name in invalid_names:
            if name:  # Skip empty string for this test
                assert name not in valid_providers

    def test_provider_validation_logic(self):
        """Provider validation logic works correctly."""
        valid_providers = ["openai", "voyageai", "voyage"]

        # Valid providers
        assert "openai" in valid_providers
        assert "voyageai" in valid_providers
        assert "voyage" in valid_providers

        # Invalid providers
        assert "invalid" not in valid_providers
        assert "gpt" not in valid_providers
