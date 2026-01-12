"""
Chain of Thought (CoT) Redaction for Security.

This module ensures that sensitive information is never stored
in raw CoT content. Only redacted summaries are persisted.

Security Principle: Never store raw CoT - only redacted summaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class RedactionResult:
    """Result of CoT redaction.

    Attributes:
        summary: Redacted summary text (safe to store)
        redaction_count: Number of redactions made
        original_length: Length of original text
        summary_length: Length of redacted summary
    """

    summary: str
    redaction_count: int
    original_length: int
    summary_length: int

    @property
    def was_redacted(self) -> bool:
        """Check if any redactions were made."""
        return self.redaction_count > 0


class CoTRedactor:
    """Redactor for Chain of Thought content.

    Removes sensitive information like passwords, API keys, tokens,
    IP addresses, and other potentially sensitive data before storage.

    Usage:
        redactor = CoTRedactor()
        result = redactor.redact(raw_thinking)
        # Store only result.summary, never the raw thinking
    """

    # Patterns to redact with their replacements
    # Order matters - more specific patterns should come first
    DEFAULT_PATTERNS: list[tuple[str, str]] = [
        # Authentication tokens and keys
        (r'bearer\s+[A-Za-z0-9_\-\.]+', 'Bearer [REDACTED]'),
        (r'authorization[:\s]+[^\s\n]+', 'Authorization: [REDACTED]'),
        (r'api[-_]?key[=:\s]+[^\s\n,;]+', 'api_key=[REDACTED]'),
        (r'api[-_]?secret[=:\s]+[^\s\n,;]+', 'api_secret=[REDACTED]'),
        (r'access[-_]?token[=:\s]+[^\s\n,;]+', 'access_token=[REDACTED]'),
        (r'refresh[-_]?token[=:\s]+[^\s\n,;]+', 'refresh_token=[REDACTED]'),
        (r'client[-_]?secret[=:\s]+[^\s\n,;]+', 'client_secret=[REDACTED]'),

        # Passwords
        (r'password[=:\s]+[^\s\n,;]+', 'password=[REDACTED]'),
        (r'passwd[=:\s]+[^\s\n,;]+', 'passwd=[REDACTED]'),
        (r'pwd[=:\s]+[^\s\n,;]+', 'pwd=[REDACTED]'),

        # Secret/private keys
        (r'secret[=:\s]+[^\s\n,;]+', 'secret=[REDACTED]'),
        (r'private[-_]?key[=:\s]+[^\s\n,;]+', 'private_key=[REDACTED]'),

        # Database connection strings
        (r'postgres(ql)?://[^\s\n]+', '[DATABASE_URL_REDACTED]'),
        (r'mysql://[^\s\n]+', '[DATABASE_URL_REDACTED]'),
        (r'mongodb(\+srv)?://[^\s\n]+', '[DATABASE_URL_REDACTED]'),
        (r'redis://[^\s\n]+', '[REDIS_URL_REDACTED]'),

        # AWS credentials
        (r'AKIA[0-9A-Z]{16}', '[AWS_ACCESS_KEY_REDACTED]'),
        (r'aws[-_]?secret[-_]?access[-_]?key[=:\s]+[^\s\n,;]+', 'aws_secret=[REDACTED]'),

        # IP addresses (v4)
        (r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b', '[IP_ADDRESS]'),

        # MAC addresses
        (r'\b([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})\b', '[MAC_ADDRESS]'),

        # JWT tokens (three base64 segments separated by dots)
        (r'\beyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\b', '[JWT_REDACTED]'),

        # Long base64 strings (likely secrets/tokens)
        (r'\b[A-Za-z0-9+/]{40,}={0,2}\b', '[BASE64_REDACTED]'),

        # SSH private keys
        (r'-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----', '[PRIVATE_KEY_REDACTED]'),

        # Generic hex strings that look like secrets (32+ chars)
        (r'\b[0-9a-fA-F]{32,}\b', '[HEX_STRING_REDACTED]'),
    ]

    def __init__(
        self,
        patterns: Optional[list[tuple[str, str]]] = None,
        max_summary_length: int = 1000,
    ):
        """Initialize the redactor.

        Args:
            patterns: Custom patterns to use (defaults to DEFAULT_PATTERNS)
            max_summary_length: Maximum length of the summary
        """
        self.patterns = patterns or self.DEFAULT_PATTERNS
        self.max_summary_length = max_summary_length
        # Compile patterns for performance
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in self.patterns
        ]

    def redact(self, text: str) -> RedactionResult:
        """Redact sensitive information from text.

        Args:
            text: Raw text to redact

        Returns:
            RedactionResult with redacted summary
        """
        if not text:
            return RedactionResult(
                summary="",
                redaction_count=0,
                original_length=0,
                summary_length=0,
            )

        original_length = len(text)
        redacted = text
        redaction_count = 0

        # Apply all patterns
        for pattern, replacement in self._compiled_patterns:
            # Count matches before replacing
            matches = len(pattern.findall(redacted))
            if matches > 0:
                redaction_count += matches
                redacted = pattern.sub(replacement, redacted)

        # Truncate if too long
        if len(redacted) > self.max_summary_length:
            redacted = redacted[: self.max_summary_length] + "... [TRUNCATED]"

        return RedactionResult(
            summary=redacted,
            redaction_count=redaction_count,
            original_length=original_length,
            summary_length=len(redacted),
        )

    def add_pattern(self, pattern: str, replacement: str) -> None:
        """Add a custom redaction pattern.

        Args:
            pattern: Regex pattern to match
            replacement: Replacement text
        """
        self.patterns.append((pattern, replacement))
        self._compiled_patterns.append(
            (re.compile(pattern, re.IGNORECASE), replacement)
        )

    def is_safe(self, text: str) -> bool:
        """Check if text contains any patterns that would be redacted.

        Args:
            text: Text to check

        Returns:
            True if text appears safe (no redactions needed)
        """
        for pattern, _ in self._compiled_patterns:
            if pattern.search(text):
                return False
        return True


# Singleton instance for convenience
_default_redactor: Optional[CoTRedactor] = None


def get_redactor() -> CoTRedactor:
    """Get the default CoT redactor instance."""
    global _default_redactor
    if _default_redactor is None:
        _default_redactor = CoTRedactor()
    return _default_redactor


def redact_cot(text: str) -> str:
    """Convenience function to redact CoT content.

    Args:
        text: Raw CoT text

    Returns:
        Redacted summary (safe to store)
    """
    return get_redactor().redact(text).summary
