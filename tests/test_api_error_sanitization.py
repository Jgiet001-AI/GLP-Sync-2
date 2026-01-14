#!/usr/bin/env python3
"""Integration tests for API error response sanitization.

Tests cover:
    - HTTPException sanitization in routers
    - Generic exception sanitization in exception handlers
    - Dashboard router error responses
    - Clients router error responses
    - Assignment router error responses
    - Agent router error responses
    - Verification that sensitive info is never exposed
    - Verification that error patterns are correctly sanitized

Note: These tests verify the sanitization logic directly rather than making
actual HTTP requests to avoid dependency complexity. The exception handlers
in app.py are simple wrappers around sanitize_error_message, so testing
the sanitization function with realistic error scenarios provides comprehensive
coverage of the security requirements.
"""

import sys

import pytest

sys.path.insert(0, str(__file__).rsplit("/tests", 1)[0])

from src.glp.api.error_sanitizer import sanitize_error_message


# ============================================
# Router Error Scenarios
# ============================================

class TestDashboardRouterErrors:
    """Test error sanitization in dashboard router error scenarios."""

    def test_config_error_sanitizes_env_vars(self):
        """Configuration error should sanitize environment variable names."""
        error_message = "Missing GLP_CLIENT_ID, GLP_CLIENT_SECRET, and GLP_TOKEN_URL"

        sanitized = sanitize_error_message(error_message, "Configuration error")

        # Should NOT contain environment variable names
        assert "GLP_CLIENT_ID" not in sanitized
        assert "GLP_CLIENT_SECRET" not in sanitized
        assert "GLP_TOKEN_URL" not in sanitized
        assert "[ENV_VAR]" in sanitized

    def test_sync_error_sanitizes_database_url(self):
        """Sync failure should sanitize database URLs."""
        error_message = "Sync failed: Connection to postgresql://user:pass@localhost:5432/glpdb failed"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain database URL or credentials
        assert "postgresql://" not in sanitized
        assert "user:pass" not in sanitized
        assert "localhost:5432" not in sanitized
        assert "[DATABASE_URL]" in sanitized

    def test_sync_error_sanitizes_multiple_env_vars(self):
        """Should sanitize multiple environment variables in one message."""
        error_message = "Check GLP_CLIENT_ID, GLP_CLIENT_SECRET, GLP_TOKEN_URL, and DATABASE_URL configuration"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain any env var names
        assert "GLP_CLIENT_ID" not in sanitized
        assert "GLP_CLIENT_SECRET" not in sanitized
        assert "GLP_TOKEN_URL" not in sanitized
        assert "DATABASE_URL" not in sanitized
        assert "[ENV_VAR]" in sanitized


class TestClientsRouterErrors:
    """Test error sanitization in clients router error scenarios."""

    def test_sync_error_sanitizes_file_paths(self):
        """Client sync error should not expose file paths."""
        error_message = "Failed to read /etc/secrets/api_key.json"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain file path
        assert "/etc/secrets" not in sanitized
        assert "api_key.json" not in sanitized
        assert "[FILE_PATH]" in sanitized

    def test_site_error_sanitizes_database_connection(self):
        """Site error should sanitize database connection strings."""
        error_message = "Database error: postgresql://admin:secret@db.internal:5432/glp"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain connection string
        assert "postgresql://" not in sanitized
        assert "admin:secret" not in sanitized
        assert "db.internal" not in sanitized
        assert "[DATABASE_URL]" in sanitized

    def test_site_not_found_sanitizes_query_details(self):
        """Site not found should not expose SQL details."""
        error_message = "Site not found: SELECT * FROM sites WHERE id='abc' failed at /var/lib/db/query.py:45"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain file paths
        assert "/var/lib/db" not in sanitized
        assert "query.py" not in sanitized
        assert "[FILE_PATH]" in sanitized


class TestAssignmentRouterErrors:
    """Test error sanitization in assignment router error scenarios."""

    def test_upload_error_sanitizes_file_paths(self):
        """Upload error should not expose server file paths."""
        error_message = "Failed to save uploaded file to /var/uploads/temp_abc123.xlsx"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain file path
        assert "/var/uploads" not in sanitized
        assert "temp_abc123.xlsx" not in sanitized
        assert "[FILE_PATH]" in sanitized

    def test_apply_error_sanitizes_bearer_tokens(self):
        """Apply assignment error should sanitize bearer tokens."""
        error_message = "API call failed: Authorization Bearer abc123token456 rejected"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain bearer token
        # The pattern matches "bearer <token>" so it should be redacted
        assert "abc123token456" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_apply_error_sanitizes_api_keys(self):
        """Apply assignment error should sanitize API keys."""
        error_message = "Authentication failed: api_key=sk-1234567890abcdef invalid"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain API key value
        assert "sk-1234567890abcdef" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_sse_error_sanitizes_credentials(self):
        """SSE stream errors should sanitize credentials."""
        error_message = "Stream error: client_secret=very-secret-value-123 is invalid"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain secret value
        assert "very-secret-value-123" not in sanitized
        assert "[REDACTED]" in sanitized


class TestAgentRouterErrors:
    """Test error sanitization in agent router error scenarios."""

    def test_websocket_error_sanitizes_redis_url(self):
        """WebSocket errors should sanitize Redis URLs."""
        error_message = "Failed to connect to redis://user:password@redis.example.com:6379/0"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain Redis URL or credentials
        assert "redis://" not in sanitized
        assert "password" not in sanitized
        assert "redis.example.com" not in sanitized
        # Redis URLs are caught by the redis:// pattern
        assert "[REDIS_URL]" in sanitized or "[ENV_VAR]" in sanitized

    def test_chat_error_sanitizes_api_keys(self):
        """Chat errors should sanitize LLM API keys."""
        error_message = "Anthropic API error: ANTHROPIC_API_KEY='sk-ant-1234567890' is invalid"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain API key or env var name
        assert "ANTHROPIC_API_KEY" not in sanitized
        assert "sk-ant-1234567890" not in sanitized

    def test_ticket_auth_error_sanitizes_tokens(self):
        """Ticket auth errors should sanitize ticket tokens."""
        error_message = "Invalid ticket: access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain JWT
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
        assert "[JWT_REDACTED]" in sanitized or "[REDACTED]" in sanitized


# ============================================
# Exception Handler Scenarios
# ============================================

class TestGenericExceptionHandler:
    """Test generic exception handler sanitization scenarios."""

    def test_sanitizes_python_tracebacks(self):
        """Should sanitize full Python tracebacks."""
        error_message = """Traceback (most recent call last):
  File "/usr/local/app/src/glp/api/client.py", line 123, in fetch
    raise RuntimeError("Internal error")
RuntimeError: Internal error"""

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain traceback or file paths
        assert "Traceback (most recent call last):" not in sanitized
        assert "/usr/local/app" not in sanitized
        assert "client.py" not in sanitized
        assert "[STACK_TRACE]" in sanitized or "[FILE_PATH]" in sanitized

    def test_sanitizes_ip_addresses(self):
        """Should sanitize IP addresses from errors."""
        error_message = "Failed to connect to 192.168.1.100:5432"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain IP address
        assert "192.168.1.100" not in sanitized
        assert "[IP_ADDRESS]" in sanitized

    def test_sanitizes_mac_addresses(self):
        """Should sanitize MAC addresses from errors."""
        error_message = "Device with MAC address AA:BB:CC:DD:EE:FF not found"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain MAC address
        assert "AA:BB:CC:DD:EE:FF" not in sanitized
        assert "[MAC_ADDRESS]" in sanitized

    def test_sanitizes_multiple_patterns(self):
        """Should sanitize multiple patterns in one message."""
        error_message = (
            "Database error at postgresql://admin:secret@10.0.0.5:5432/db. "
            "API key api_key=sk-1234567890abcdef. "
            "Token: Bearer abc123xyz. "
            "Config: GLP_CLIENT_ID=my-client-id"
        )

        sanitized = sanitize_error_message(error_message)

        # All sensitive info should be redacted
        assert "postgresql://" not in sanitized
        assert "admin:secret" not in sanitized
        assert "10.0.0.5" not in sanitized
        assert "sk-1234567890abcdef" not in sanitized
        assert "abc123xyz" not in sanitized
        assert "GLP_CLIENT_ID" not in sanitized
        assert "my-client-id" not in sanitized

        # Redaction markers should be present
        assert "[DATABASE_URL]" in sanitized or "[REDACTED]" in sanitized


class TestHTTPExceptionHandler:
    """Test HTTPException handler sanitization scenarios."""

    def test_sanitizes_database_urls(self):
        """HTTPException with database URL should be sanitized."""
        error_message = "Database connection failed: postgresql://user:password@db.example.com:5432/mydb"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain connection details
        assert "postgresql://" not in sanitized
        assert "password" not in sanitized
        assert "db.example.com" not in sanitized
        assert "[DATABASE_URL]" in sanitized

    def test_sanitizes_jwt_tokens(self):
        """HTTPException with JWT token should be sanitized."""
        error_message = "Invalid token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"

        sanitized = sanitize_error_message(error_message)

        # JWT should be redacted
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
        assert "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c" not in sanitized
        assert "[JWT_REDACTED]" in sanitized

    def test_sanitizes_authorization_headers(self):
        """HTTPException with authorization header should be sanitized."""
        error_message = "Request failed with authorization: Bearer sk-live-abc123xyz456"

        sanitized = sanitize_error_message(error_message)

        # Should NOT contain authorization token
        assert "sk-live-abc123xyz456" not in sanitized
        assert "[REDACTED]" in sanitized


# ============================================
# Real-World Error Patterns
# ============================================

class TestRealWorldErrorPatterns:
    """Test sanitization with real-world error patterns."""

    def test_aws_credentials_sanitized(self):
        """AWS credentials should be sanitized."""
        error = "AWS error: AKIAIOSFODNN7EXAMPLE with aws_secret_access_key=wJalrXUtnFEMI/K7MDENG"

        sanitized = sanitize_error_message(error)

        assert "AKIAIOSFODNN7EXAMPLE" not in sanitized
        assert "wJalrXUtnFEMI" not in sanitized
        assert "[AWS_ACCESS_KEY]" in sanitized
        assert "[REDACTED]" in sanitized

    def test_mongodb_connection_string_sanitized(self):
        """MongoDB connection strings should be sanitized."""
        error = "MongoError: mongodb+srv://dbuser:dbpass@cluster0.mongodb.net/mydb"

        sanitized = sanitize_error_message(error)

        assert "mongodb+srv://" not in sanitized
        assert "dbuser:dbpass" not in sanitized
        assert "[DATABASE_URL]" in sanitized

    def test_mysql_connection_string_sanitized(self):
        """MySQL connection strings should be sanitized."""
        error = "Connection failed: mysql://root:password123@mysql.internal:3306/production"

        sanitized = sanitize_error_message(error)

        assert "mysql://" not in sanitized
        assert "password123" not in sanitized
        assert "[DATABASE_URL]" in sanitized

    def test_private_key_sanitized(self):
        """Private keys should be sanitized."""
        error = """Certificate error: -----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z9Ld1XO7w...
-----END RSA PRIVATE KEY-----"""

        sanitized = sanitize_error_message(error)

        assert "-----BEGIN RSA PRIVATE KEY-----" not in sanitized
        assert "MIIEpAIBAAKCAQEA0Z9Ld1XO7w" not in sanitized
        assert "[PRIVATE_KEY]" in sanitized

    def test_hex_secrets_sanitized(self):
        """Long hex strings (likely secrets) should be sanitized."""
        error = "Token validation failed: 0123456789abcdef0123456789abcdef0123456789abcdef"

        sanitized = sanitize_error_message(error)

        # Long string should be redacted (hex pattern or base64 pattern)
        assert "0123456789abcdef0123456789abcdef" not in sanitized
        assert "[HEX_STRING]" in sanitized or "[BASE64_REDACTED]" in sanitized

    def test_base64_secrets_sanitized(self):
        """Long base64 strings (likely secrets) should be sanitized."""
        error = "Decryption failed: dGhpc2lzYXZlcnlsb25nc2VjcmV0YmFzZTY0c3RyaW5ndGhhdHNob3VsZGJlcmVkYWN0ZWQ="

        sanitized = sanitize_error_message(error)

        # Long base64 string should be redacted
        assert "dGhpc2lzYXZlcnlsb25nc2VjcmV0YmFzZTY0c3RyaW5ndGhhdHNob3VsZGJlcmVkYWN0ZWQ=" not in sanitized
        assert "[BASE64_REDACTED]" in sanitized


# ============================================
# Edge Cases and Error Handling
# ============================================

class TestEdgeCases:
    """Test edge cases in error sanitization."""

    def test_preserves_safe_error_messages(self):
        """Should preserve error messages without sensitive info."""
        message = "Invalid input: field 'name' is required"

        sanitized = sanitize_error_message(message)

        # Should be unchanged
        assert sanitized == message

    def test_handles_empty_message(self):
        """Should handle empty error messages gracefully."""
        sanitized = sanitize_error_message("")

        # Should provide generic message
        assert sanitized == "An error occurred"

    def test_handles_none_message(self):
        """Should handle None error messages gracefully."""
        sanitized = sanitize_error_message(None)

        # Should provide generic message (None gets converted to empty string)
        assert "error" in sanitized.lower()

    def test_truncates_very_long_messages(self):
        """Should truncate extremely long error messages."""
        # Create a very long message with mixed content that won't match patterns
        long_message = "Error message: " + ("abcd efgh " * 100)

        sanitized = sanitize_error_message(long_message)

        # Should be truncated
        assert len(sanitized) <= 520  # max_length + some overhead
        assert "[TRUNCATED]" in sanitized or len(sanitized) < len(long_message)

    def test_adds_error_type_prefix(self):
        """Should add error type prefix when provided."""
        message = "Connection timeout"
        error_type = "Database Error"

        sanitized = sanitize_error_message(message, error_type)

        assert sanitized.startswith("Database Error:")

    def test_sanitizes_multiple_database_urls(self):
        """Should sanitize multiple database URLs in one message."""
        message = (
            "Failed to connect to postgresql://user:pass@db1:5432/prod "
            "and fallback postgresql://user:pass@db2:5432/backup"
        )

        sanitized = sanitize_error_message(message)

        # Both URLs should be redacted
        assert "postgresql://" not in sanitized
        assert "user:pass" not in sanitized
        assert "db1:5432" not in sanitized
        assert "db2:5432" not in sanitized
        assert "[DATABASE_URL]" in sanitized

    def test_sanitizes_windows_file_paths(self):
        """Should sanitize Windows file paths."""
        message = "Failed to read C:\\Users\\admin\\secrets\\config.ini"

        sanitized = sanitize_error_message(message)

        assert "C:\\Users\\admin\\secrets" not in sanitized
        assert "[FILE_PATH]" in sanitized

    def test_sanitizes_mixed_case_env_vars(self):
        """Should sanitize environment variables regardless of context."""
        message = "Missing environment variable: GLP_CLIENT_SECRET not set"

        sanitized = sanitize_error_message(message)

        assert "GLP_CLIENT_SECRET" not in sanitized
        assert "[ENV_VAR]" in sanitized


# ============================================
# Security Verification Tests
# ============================================

class TestSecurityRequirements:
    """Verify that security requirements are met."""

    def test_no_environment_variables_leaked(self):
        """Ensure no common environment variable names are leaked."""
        env_vars = [
            "GLP_CLIENT_ID", "GLP_CLIENT_SECRET", "GLP_TOKEN_URL",
            "DATABASE_URL", "REDIS_URL", "JWT_SECRET",
            "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
            "ARUBA_CLIENT_ID", "ARUBA_CLIENT_SECRET"
        ]

        for env_var in env_vars:
            message = f"Configuration error: {env_var} is not set"
            sanitized = sanitize_error_message(message)

            # Should NOT contain the env var name
            assert env_var not in sanitized, f"{env_var} was leaked in sanitized message"
            assert "[ENV_VAR]" in sanitized

    def test_no_database_credentials_leaked(self):
        """Ensure no database credentials are leaked."""
        db_urls = [
            "postgresql://user:pass@localhost/db",
            "mysql://root:secret@mysql:3306/prod",
            "mongodb://admin:password@mongo:27017/app",
            "redis://user:pass@redis:6379/0",
            "sqlite:///var/db/data.db"
        ]

        for db_url in db_urls:
            message = f"Connection failed: {db_url}"
            sanitized = sanitize_error_message(message)

            # Should NOT contain the URL
            assert "://" not in sanitized or "[DATABASE_URL]" in sanitized or "[REDIS_URL]" in sanitized
            # Should NOT contain credentials
            assert "pass" not in sanitized or "password" in message.lower()
            assert "secret" not in sanitized

    def test_no_api_keys_leaked(self):
        """Ensure no API keys are leaked."""
        api_patterns = [
            "api_key=sk-1234567890",
            "api_secret=secret-abc123",
            "access_token=token-xyz789",
            "client_secret=cs-secret123"
        ]

        for pattern in api_patterns:
            message = f"Authentication failed: {pattern}"
            sanitized = sanitize_error_message(message)

            # Value should be redacted
            assert "sk-1234567890" not in sanitized
            assert "secret-abc123" not in sanitized
            assert "token-xyz789" not in sanitized
            assert "cs-secret123" not in sanitized
            assert "[REDACTED]" in sanitized

    def test_no_file_paths_leaked(self):
        """Ensure no file paths are leaked."""
        file_paths = [
            "/etc/secrets/api_key.json",
            "/var/lib/app/config.ini",
            "/home/admin/.ssh/id_rsa",
            "C:\\Windows\\System32\\config.xml"
        ]

        for path in file_paths:
            message = f"Failed to read {path}"
            sanitized = sanitize_error_message(message)

            # Path should be redacted
            assert path not in sanitized
            assert "[FILE_PATH]" in sanitized

    def test_no_stack_traces_leaked(self):
        """Ensure no stack traces are leaked."""
        message = """Traceback (most recent call last):
  File "/app/src/main.py", line 42, in main
    process_data()
  File "/app/src/processor.py", line 123, in process_data
    raise ValueError("Processing failed")
ValueError: Processing failed"""

        sanitized = sanitize_error_message(message)

        # Stack trace should be redacted
        assert "Traceback (most recent call last):" not in sanitized
        assert "/app/src/main.py" not in sanitized
        assert "[STACK_TRACE]" in sanitized or "[FILE_PATH]" in sanitized


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
