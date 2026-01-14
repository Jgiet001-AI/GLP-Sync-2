"""
Error Message Sanitization for API Responses.

This module ensures that sensitive information is never exposed
in API error responses. All error messages sent to clients are
sanitized to remove credentials, connection strings, file paths,
and other potentially sensitive data.

Security Principle: Never expose internal details - only safe, generic error messages.

Why Sanitization Matters
------------------------
API error messages can inadvertently leak sensitive information:
- Database connection strings with credentials
- API keys and authentication tokens
- File paths revealing system structure
- Stack traces exposing code internals
- Environment variable names and values
- IP addresses and network topology

This module prevents such leaks by automatically redacting sensitive
patterns before error messages reach clients, while preserving the
original detailed errors for internal logging.

Usage Examples
--------------

Basic Usage (FastAPI Exception Handler):
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse
    from src.glp.api.error_sanitizer import sanitize_error_message

    app = FastAPI()

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        error_msg = str(exc)

        # Log original error internally (NEVER send to client)
        logger.error(f"Internal error: {error_msg}", exc_info=exc)

        # Sanitize before returning to client
        safe_msg = sanitize_error_message(error_msg, "Internal server error")

        return JSONResponse(
            status_code=500,
            content={"detail": safe_msg}
        )

Instance-Based Usage:
    from src.glp.api.error_sanitizer import ErrorSanitizer

    sanitizer = ErrorSanitizer()

    try:
        conn = connect("postgresql://admin:secret123@db.internal/prod")
    except Exception as e:
        result = sanitizer.sanitize(str(e))
        if result.was_sanitized:
            logger.warning(f"Sanitized {result.redaction_count} sensitive items")
        return {"error": result.sanitized_message}

    # Original: "Connection failed to postgresql://admin:secret123@db.internal/prod"
    # Sanitized: "Connection failed to [DATABASE_URL]"

Custom Patterns:
    from src.glp.api.error_sanitizer import ErrorSanitizer

    # Add organization-specific patterns
    sanitizer = ErrorSanitizer()
    sanitizer.add_pattern(
        r'tenant[-_]?id[=:\s]+[^\s,;]+',
        'tenant_id=[REDACTED]'
    )
    sanitizer.add_pattern(
        r'customer[-_]?key[=:\s]+[^\s,;]+',
        'customer_key=[REDACTED]'
    )

    # Now handles custom patterns too
    msg = "Failed for tenant_id=acme-corp-12345"
    result = sanitizer.sanitize(msg)
    # Returns: "Failed for tenant_id=[REDACTED]"

Checking Safety Before Exposure:
    from src.glp.api.error_sanitizer import get_sanitizer

    sanitizer = get_sanitizer()
    error_msg = "Connection timeout after 30s"

    if sanitizer.is_safe(error_msg):
        # No sensitive data detected, safe to return as-is
        return {"error": error_msg}
    else:
        # Contains sensitive data, sanitize first
        return {"error": sanitizer.sanitize(error_msg).sanitized_message}

What Gets Sanitized
-------------------
The module includes comprehensive pattern matching for:

1. Database Connections:
   - PostgreSQL: postgresql://user:pass@host/db → [DATABASE_URL]
   - MySQL: mysql://user:pass@host/db → [DATABASE_URL]
   - MongoDB: mongodb+srv://user:pass@host/db → [DATABASE_URL]
   - Redis: redis://user:pass@host:6379 → [REDIS_URL]

2. Authentication:
   - API keys: api_key=sk_live_abc123 → api_key=[REDACTED]
   - Bearer tokens: Bearer eyJhbG... → Bearer [REDACTED]
   - Client secrets: client_secret=abc123 → client_secret=[REDACTED]
   - JWT tokens: eyJhbGc...eyJzdW...signature → [JWT_REDACTED]

3. Credentials:
   - Passwords: password=secret123 → password=[REDACTED]
   - Private keys: -----BEGIN PRIVATE KEY----- → [PRIVATE_KEY]
   - AWS keys: AKIAIOSFODNN7EXAMPLE → [AWS_ACCESS_KEY]

4. System Information:
   - File paths: /home/user/app/config.py → [FILE_PATH]
   - Stack traces: Traceback (most recent... → [STACK_TRACE]
   - IP addresses: 192.168.1.100 → [IP_ADDRESS]
   - Environment vars: GLP_CLIENT_SECRET → [ENV_VAR]

5. Other Sensitive Data:
   - MAC addresses: 00:1B:44:11:3A:B7 → [MAC_ADDRESS]
   - Base64 strings (40+ chars): YWJjZGVm... → [BASE64_REDACTED]
   - Hex strings (32+ chars): a1b2c3d4... → [HEX_STRING]

Integration Patterns
--------------------

With FastAPI HTTPException:
    from fastapi import HTTPException
    from src.glp.api.error_sanitizer import sanitize_error_message

    def get_device(device_id: str):
        try:
            return fetch_device(device_id)
        except DatabaseError as e:
            # Original: "Connection to postgresql://user:pass@host/db failed"
            safe_msg = sanitize_error_message(str(e), "Database error")
            # Sanitized: "Database error: Connection to [DATABASE_URL] failed"
            raise HTTPException(status_code=500, detail=safe_msg)

With Custom Exception Classes:
    from src.glp.api.error_sanitizer import ErrorSanitizer

    class SafeAPIException(Exception):
        '''Exception that auto-sanitizes error messages.'''

        def __init__(self, message: str):
            self.raw_message = message
            sanitizer = ErrorSanitizer()
            result = sanitizer.sanitize(message)
            super().__init__(result.sanitized_message)
            self.was_sanitized = result.was_sanitized

    # Usage
    raise SafeAPIException("Failed to auth with api_key=sk_live_abc123")
    # Client sees: "Failed to auth with api_key=[REDACTED]"

Performance Considerations
--------------------------
- Patterns are compiled once at initialization for speed
- Regex matching is O(n) where n is message length
- Use singleton get_sanitizer() for shared instance
- Pattern order matters: specific patterns before generic ones

Security Best Practices
-----------------------
1. ALWAYS sanitize errors before client exposure
2. ALWAYS log original errors internally (server-side only)
3. NEVER skip sanitization "just this once"
4. Add custom patterns for organization-specific secrets
5. Use error_type parameter for context (e.g., "Database error")
6. Review and update patterns as new secret types emerge
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

    Basic Usage:
        sanitizer = ErrorSanitizer()
        result = sanitizer.sanitize(error_message)
        # Return result.sanitized_message to client
        # Log original error_message internally

    Advanced Usage Examples:

        # Example 1: Database connection error
        error = "Cannot connect to postgresql://admin:secret@db.prod.local/users"
        result = sanitizer.sanitize(error, error_type="Database error")
        print(result.sanitized_message)
        # Output: "Database error: Cannot connect to [DATABASE_URL]"
        print(f"Redacted {result.redaction_count} items")
        # Output: "Redacted 1 items"

        # Example 2: Multiple sensitive items
        error = "Auth failed: api_key=sk_live_abc123, secret=xyz789, ip=192.168.1.50"
        result = sanitizer.sanitize(error)
        print(result.sanitized_message)
        # Output: "Auth failed: api_key=[REDACTED], secret=[REDACTED], ip=[IP_ADDRESS]"
        print(result.was_sanitized)
        # Output: True

        # Example 3: Stack trace redaction
        error = '''Traceback (most recent call last):
          File "/app/handlers.py", line 42, in process
            connect(os.environ["DATABASE_URL"])
        DatabaseError: connection refused'''
        result = sanitizer.sanitize(error)
        # Stack trace and file paths are redacted

        # Example 4: Custom patterns for your domain
        sanitizer = ErrorSanitizer()
        sanitizer.add_pattern(
            r'order[-_]?id[=:\s]+[A-Z0-9\-]+',
            'order_id=[REDACTED]'
        )
        error = "Payment failed for order_id=ORD-2024-12345"
        result = sanitizer.sanitize(error)
        # Output: "Payment failed for order_id=[REDACTED]"

        # Example 5: Check before sanitizing
        error1 = "Connection timeout after 30 seconds"
        error2 = "Connection to postgresql://user:pass@host/db failed"

        if sanitizer.is_safe(error1):
            # Safe to return as-is
            return error1
        else:
            return sanitizer.sanitize(error1).sanitized_message

        if sanitizer.is_safe(error2):
            return error2  # Won't execute
        else:
            return sanitizer.sanitize(error2).sanitized_message
            # Returns: "Connection to [DATABASE_URL] failed"

        # Example 6: Custom max length
        long_error_sanitizer = ErrorSanitizer(max_message_length=100)
        very_long_error = "Error: " + "x" * 200
        result = long_error_sanitizer.sanitize(very_long_error)
        print(result.sanitized_message)
        # Output: "Error: xxxx... [TRUNCATED]" (max 100 chars)

    Attributes:
        patterns: List of (regex_pattern, replacement) tuples
        max_message_length: Maximum length of sanitized messages
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
