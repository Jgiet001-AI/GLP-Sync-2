"""
Voyage AI Embedding Provider.

Implements the ILLMProvider interface for Voyage AI's embedding models.
This provider is specialized for embeddings only (no chat support).
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Optional

from ..domain.entities import (
    ChatEvent,
    ErrorType,
    Message,
    ToolDefinition,
)
from .base import BaseLLMProvider, LLMProviderConfig, LLMProviderError

logger = logging.getLogger(__name__)

# Lazy import to avoid requiring voyageai if not used
try:
    import voyageai

    VOYAGEAI_AVAILABLE = True
except ImportError:
    VOYAGEAI_AVAILABLE = False
    voyageai = None


class VoyageAIProvider(BaseLLMProvider):
    """Voyage AI embedding provider implementation.

    Supports:
    - voyage-2
    - voyage-large-2
    - voyage-code-2
    - voyage-lite-02-instruct
    - High-quality embeddings optimized for retrieval

    Note: This provider only supports embeddings, not chat.

    Usage:
        config = LLMProviderConfig(
            api_key="pa-...",
            model="voyage-2",  # Used for chat (if needed)
            embedding_model="voyage-2",
        )
        provider = VoyageAIProvider(config)

        embedding, model, dim = await provider.embed("Hello world")
    """

    # Default models
    DEFAULT_MODEL = "voyage-2"  # Not used for chat, but required by base
    DEFAULT_EMBEDDING_MODEL = "voyage-2"

    # Embedding dimensions by model
    EMBEDDING_DIMENSIONS = {
        "voyage-2": 1024,
        "voyage-large-2": 1536,
        "voyage-code-2": 1536,
        "voyage-lite-02-instruct": 1024,
    }

    def __init__(self, config: LLMProviderConfig):
        """Initialize the Voyage AI provider.

        Args:
            config: Provider configuration

        Raises:
            ImportError: If voyageai package is not installed
        """
        if not VOYAGEAI_AVAILABLE:
            raise ImportError(
                "voyageai package is required for VoyageAIProvider. "
                "Install with: pip install voyageai"
            )

        super().__init__(config)

        # Set embedding model
        self.embedding_model = (
            config.embedding_model or self.DEFAULT_EMBEDDING_MODEL
        )

        # Initialize client
        self.client = voyageai.Client(
            api_key=config.api_key,
        )

    @property
    def supports_tools(self) -> bool:
        """Voyage AI is embedding-only, no tool support."""
        return False

    @property
    def supports_streaming(self) -> bool:
        """Voyage AI is embedding-only, no streaming support."""
        return False

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[ChatEvent]:
        """Chat is not supported by Voyage AI.

        Args:
            messages: Ignored
            tools: Ignored
            system_prompt: Ignored
            stream: Ignored
            temperature: Ignored
            max_tokens: Ignored

        Yields:
            Error event indicating chat is not supported

        Raises:
            NotImplementedError: Always, as Voyage AI only supports embeddings
        """
        self._reset_sequence()
        yield self._create_error(
            "Voyage AI provider only supports embeddings, not chat. "
            "Use Anthropic or OpenAI for chat functionality.",
            ErrorType.FATAL,
        )
        yield self._create_done()

    async def embed(self, text: str) -> tuple[list[float], str, int]:
        """Generate an embedding for text.

        Args:
            text: Text to embed

        Returns:
            Tuple of (embedding_vector, model_name, dimension)

        Raises:
            LLMProviderError: On API errors
        """
        try:
            # Voyage AI client is synchronous, but we're in async context
            # We call the sync method directly - it's fast enough for single embeddings
            response = self.client.embed(
                texts=[text],
                model=self.embedding_model,
            )

            # Extract first embedding
            embedding = response.embeddings[0]
            dimension = len(embedding)

            return embedding, self.embedding_model, dimension

        except Exception as e:
            # Voyage AI doesn't have specific error types, catch all
            logger.error(f"Voyage AI embedding error: {e}")

            # Check for rate limiting in error message
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str:
                raise LLMProviderError(
                    f"Rate limited: {e}",
                    error_type=ErrorType.RATE_LIMIT,
                    original_error=e,
                )

            # Check for timeout
            if "timeout" in error_str:
                raise LLMProviderError(
                    f"Request timed out: {e}",
                    error_type=ErrorType.TIMEOUT,
                    original_error=e,
                )

            # Generic error
            raise LLMProviderError(
                f"Embedding failed: {e}",
                error_type=ErrorType.RECOVERABLE,
                original_error=e,
            )

    async def embed_batch(self, texts: list[str]) -> list[tuple[list[float], str, int]]:
        """Generate embeddings for multiple texts efficiently.

        Args:
            texts: List of texts to embed

        Returns:
            List of (embedding_vector, model_name, dimension) tuples

        Raises:
            LLMProviderError: On API errors
        """
        if not texts:
            return []

        try:
            # Voyage AI supports batch embedding natively
            response = self.client.embed(
                texts=texts,
                model=self.embedding_model,
            )

            results = []
            for embedding in response.embeddings:
                dimension = len(embedding)
                results.append((embedding, self.embedding_model, dimension))

            return results

        except Exception as e:
            logger.error(f"Voyage AI batch embedding error: {e}")

            # Check for rate limiting
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str:
                raise LLMProviderError(
                    f"Rate limited: {e}",
                    error_type=ErrorType.RATE_LIMIT,
                    original_error=e,
                )

            # Generic error
            raise LLMProviderError(
                f"Batch embedding failed: {e}",
                error_type=ErrorType.RECOVERABLE,
                original_error=e,
            )

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup (Voyage AI client doesn't require explicit cleanup)."""
        pass
