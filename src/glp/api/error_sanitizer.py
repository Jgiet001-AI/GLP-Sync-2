"""
Error Message Sanitization for API Responses.

This module ensures that sensitive information is never exposed
in API error responses. All error messages sent to clients are
sanitized to remove credentials, connection strings, file paths,
and other potentially sensitive data.

Security Principle: Never expose internal details - only safe, generic error messages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class SanitizationResult:
    """Result of error message sanitization.

    Attributes:
        sanitized_message: Sanitized error message (safe to return to client)
        redaction_count: Number of redactions made
        original_length: Length of original message
        sanitized_length: Length of sanitized message
    """

    sanitized_message: str
    redaction_count: int
    original_length: int
    sanitized_length: int

    @property
    def was_sanitized(self) -> bool:
        """Check if any redactions were made."""
        return self.redaction_count > 0


class ErrorSanitizer:
    """Sanitizer for error messages in API responses.

    Removes sensitive information like passwords, API keys, tokens,
    database connection strings, file paths, environment variables,
    and stack traces before returning errors to clients.

    Usage:
        sanitizer = ErrorSanitizer()
        result = sanitizer.sanitize(error_message)
        # Return result.sanitized_message to client
        # Log original error_message internally
    """

    # Patterns to sanitize with their replacements
    # Order matters - more specific patterns should come first
    DEFAULT_PATTERNS: list[tuple[str, str]] = [
        # Database connection strings (must come before generic passwords)
        (r'postgres(ql)?://[^\s\n]+', '[DATABASE_URL]'),
        (r'mysql://[^\s\n]+', '[DATABASE_URL]'),
        (r'mongodb(\+srv)?://[^\s\n]+', '[DATABASE_URL]'),
        (r'redis://[^\s\n]+', '[REDIS_URL]'),
        (r'sqlite:///[^\s\n]+', '[DATABASE_URL]'),

        # Authentication tokens and keys
        (r'bearer\s+[A-Za-z0-9_\-\.]+', 'Bearer [REDACTED]'),
        (r'authorization[:\s]+[^\s\n]+', 'Authorization: [REDACTED]'),
        (r'api[-_]?key[=:\s]+[^\s\n,;]+', 'api_key=[REDACTED]'),
        (r'api[-_]?secret[=:\s]+[^\s\n,;]+', 'api_secret=[REDACTED]'),
        (r'access[-_]?token[=:\s]+[^\s\n,;]+', 'access_token=[REDACTED]'),
        (r'refresh[-_]?token[=:\s]+[^\s\n,;]+', 'refresh_token=[REDACTED]'),
        (r'client[-_]?secret[=:\s]+[^\s\n,;]+', 'client_secret=[REDACTED]'),
        (r'client[-_]?id[=:\s]+[^\s\n,;]+', 'client_id=[REDACTED]'),

        # Passwords
        (r'password[=:\s]+[^\s\n,;]+', 'password=[REDACTED]'),
        (r'passwd[=:\s]+[^\s\n,;]+', 'passwd=[REDACTED]'),
        (r'pwd[=:\s]+[^\s\n,;]+', 'pwd=[REDACTED]'),

        # Secret/private keys
        (r'secret[=:\s]+[^\s\n,;]+', 'secret=[REDACTED]'),
        (r'private[-_]?key[=:\s]+[^\s\n,;]+', 'private_key=[REDACTED]'),

        # Environment variable names (common sensitive ones) - match when used as identifiers
        # Require uppercase and underscores to avoid matching normal words like "database"
        (r'\b(GLP_CLIENT_ID|GLP_CLIENT_SECRET|GLP_TOKEN_URL|REDIS_URL|JWT_SECRET|ANTHROPIC_API_KEY|OPENAI_API_KEY|ARUBA_CLIENT_ID|ARUBA_CLIENT_SECRET|ARUBA_TOKEN_URL)\b', '[ENV_VAR]'),
        # Match DATABASE_URL and API_KEY separately with stricter context
        (r'DATABASE_URL[=:\s]', '[ENV_VAR]='),
        (r'\bAPI_KEY\b(?=[=:\s])', '[ENV_VAR]'),

        # File paths (Unix and Windows)
        (r'/(?:home|root|usr|var|etc|opt|mnt)/[^\s\n,;]+', '[FILE_PATH]'),
        (r'[A-Z]:\\[^\s\n,;]+', '[FILE_PATH]'),
        (r'\./[^\s\n,;]+', '[FILE_PATH]'),

        # Stack traces (Python)
        (r'Traceback \(most recent call last\):[\s\S]*?(?=\n\n|\n[A-Z]|\Z)', '[STACK_TRACE]'),
        (r'File "([^"]+)", line \d+', 'File "[REDACTED]", line [REDACTED]'),

        # IP addresses (v4)
        (r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b', '[IP_ADDRESS]'),

        # MAC addresses
        (r'\b([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})\b', '[MAC_ADDRESS]'),

        # JWT tokens (three base64 segments separated by dots)
        (r'\beyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\b', '[JWT_REDACTED]'),

        # Long base64 strings (likely secrets/tokens)
        (r'\b[A-Za-z0-9+/]{40,}={0,2}\b', '[BASE64_REDACTED]'),

        # SSH private keys
        (r'-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----', '[PRIVATE_KEY]'),

        # Generic hex strings that look like secrets (32+ chars)
        (r'\b[0-9a-fA-F]{32,}\b', '[HEX_STRING]'),

        # AWS credentials
        (r'AKIA[0-9A-Z]{16}', '[AWS_ACCESS_KEY]'),
        (r'aws[-_]?secret[-_]?access[-_]?key[=:\s]+[^\s\n,;]+', 'aws_secret=[REDACTED]'),
    ]

    def __init__(
        self,
        patterns: Optional[list[tuple[str, str]]] = None,
        max_message_length: int = 500,
    ):
        """Initialize the sanitizer.

        Args:
            patterns: Custom patterns to use (defaults to DEFAULT_PATTERNS)
            max_message_length: Maximum length of sanitized message
        """
        self.patterns = patterns or self.DEFAULT_PATTERNS
        self.max_message_length = max_message_length
        # Compile patterns for performance
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in self.patterns
        ]

    def sanitize(self, message: str, error_type: Optional[str] = None) -> SanitizationResult:
        """Sanitize error message for safe client exposure.

        Args:
            message: Raw error message
            error_type: Optional error type/category for context

        Returns:
            SanitizationResult with sanitized message
        """
        if not message:
            return SanitizationResult(
                sanitized_message="An error occurred",
                redaction_count=0,
                original_length=0,
                sanitized_length=17,
            )

        original_length = len(message)
        sanitized = message
        redaction_count = 0

        # Apply all patterns
        for pattern, replacement in self._compiled_patterns:
            # Count matches before replacing
            matches = len(pattern.findall(sanitized))
            if matches > 0:
                redaction_count += matches
                sanitized = pattern.sub(replacement, sanitized)

        # Truncate if too long
        if len(sanitized) > self.max_message_length:
            sanitized = sanitized[: self.max_message_length] + "... [TRUNCATED]"

        # If message is empty after sanitization, provide generic message
        if not sanitized.strip():
            sanitized = "An error occurred"

        # Add error type prefix if provided
        if error_type and not sanitized.startswith(error_type):
            sanitized = f"{error_type}: {sanitized}"

        return SanitizationResult(
            sanitized_message=sanitized,
            redaction_count=redaction_count,
            original_length=original_length,
            sanitized_length=len(sanitized),
        )

    def add_pattern(self, pattern: str, replacement: str) -> None:
        """Add a custom sanitization pattern.

        Args:
            pattern: Regex pattern to match
            replacement: Replacement text
        """
        self.patterns.append((pattern, replacement))
        self._compiled_patterns.append(
            (re.compile(pattern, re.IGNORECASE), replacement)
        )

    def is_safe(self, message: str) -> bool:
        """Check if message contains any patterns that would be sanitized.

        Args:
            message: Message to check

        Returns:
            True if message appears safe (no sanitization needed)
        """
        for pattern, _ in self._compiled_patterns:
            if pattern.search(message):
                return False
        return True


# Singleton instance for convenience
_default_sanitizer: Optional[ErrorSanitizer] = None


def get_sanitizer() -> ErrorSanitizer:
    """Get the default error sanitizer instance."""
    global _default_sanitizer
    if _default_sanitizer is None:
        _default_sanitizer = ErrorSanitizer()
    return _default_sanitizer


def sanitize_error_message(
    message: str,
    error_type: Optional[str] = None,
) -> str:
    """Convenience function to sanitize error messages.

    Args:
        message: Raw error message
        error_type: Optional error type/category

    Returns:
        Sanitized error message safe for client exposure

    Example:
        >>> sanitize_error_message("Database error: postgresql://user:pass@localhost/db")
        'Database error: [DATABASE_URL]'
        >>> sanitize_error_message("Missing GLP_CLIENT_ID", "Configuration error")
        'Configuration error: Missing [ENV_VAR]'
    """
    sanitizer = get_sanitizer()
    result = sanitizer.sanitize(message, error_type)
    return result.sanitized_message


# Alias for convenience
sanitize = sanitize_error_message
