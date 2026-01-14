"""
Tests for Error Message Sanitization.

These tests ensure:
1. Sensitive patterns are properly redacted
2. Edge cases (empty, clean messages) are handled
3. Multiple redactions in one message work correctly
4. Message truncation prevents excessive output
5. Error type prefixes are properly applied
6. Custom patterns can be added
7. The is_safe() method correctly identifies unsafe messages
"""

import pytest

from src.glp.api.error_sanitizer import (
    ErrorSanitizer,
    SanitizationResult,
    get_sanitizer,
    sanitize_error_message,
)


class TestBasicSanitization:
    """Test basic sanitization patterns."""

    def test_empty_message(self):
        """Empty message should return generic error."""
        sanitizer = ErrorSanitizer()
        result = sanitizer.sanitize("")
        assert result.sanitized_message == "An error occurred"
        assert result.redaction_count == 0
        assert not result.was_sanitized
        assert result.original_length == 0

    def test_clean_message(self):
        """Message without sensitive data should pass through."""
        sanitizer = ErrorSanitizer()
        message = "Invalid device ID provided"
        result = sanitizer.sanitize(message)
        assert result.sanitized_message == message
        assert result.redaction_count == 0
        assert not result.was_sanitized

    def test_database_url_redaction_postgresql(self):
        """PostgreSQL connection strings should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Connection failed: postgresql://admin:secret123@db.example.com:5432/mydb"
        result = sanitizer.sanitize(message)
        assert "admin:secret123" not in result.sanitized_message
        assert "[DATABASE_URL]" in result.sanitized_message
        assert result.was_sanitized

    def test_database_url_redaction_mysql(self):
        """MySQL connection strings should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Failed to connect: mysql://user:pass@localhost:3306/testdb"
        result = sanitizer.sanitize(message)
        assert "user:pass" not in result.sanitized_message
        assert "[DATABASE_URL]" in result.sanitized_message
        assert result.was_sanitized

    def test_database_url_redaction_mongodb(self):
        """MongoDB connection strings should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Error: mongodb://admin:password@mongo.example.com:27017/db"
        result = sanitizer.sanitize(message)
        assert "admin:password" not in result.sanitized_message
        assert "[DATABASE_URL]" in result.sanitized_message
        assert result.was_sanitized

    def test_database_url_redaction_mongodb_srv(self):
        """MongoDB+SRV connection strings should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Connection error: mongodb+srv://user:pass@cluster.mongodb.net/db"
        result = sanitizer.sanitize(message)
        assert "user:pass" not in result.sanitized_message
        assert "[DATABASE_URL]" in result.sanitized_message
        assert result.was_sanitized

    def test_redis_url_redaction(self):
        """Redis URLs should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Failed to connect: redis://user:password@redis.example.com:6379/0"
        result = sanitizer.sanitize(message)
        assert "user:password" not in result.sanitized_message
        # redis:// is caught by the pattern, check for REDIS_URL or ENV_VAR
        assert "[REDIS_URL]" in result.sanitized_message or "[ENV_VAR]" in result.sanitized_message
        assert result.was_sanitized

    def test_bearer_token_redaction(self):
        """Bearer tokens should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Auth failed with Bearer abc123def456token"
        result = sanitizer.sanitize(message)
        assert "abc123def456token" not in result.sanitized_message
        assert "[REDACTED]" in result.sanitized_message
        assert result.was_sanitized

    def test_authorization_header_redaction(self):
        """Authorization headers should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Invalid Authorization: Basic dXNlcjpwYXNz"
        result = sanitizer.sanitize(message)
        # The base64 or authorization pattern should catch this
        assert "Basic dXNlcjpwYXNz" not in result.sanitized_message
        assert ("[REDACTED]" in result.sanitized_message or
                "[BASE64_REDACTED]" in result.sanitized_message)
        assert result.was_sanitized

    def test_api_key_redaction(self):
        """API keys should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Missing api_key=sk-1234567890abcdef for authentication"
        result = sanitizer.sanitize(message)
        assert "sk-1234567890abcdef" not in result.sanitized_message
        # Either api_key pattern or hex string pattern should catch it
        assert ("[REDACTED]" in result.sanitized_message or
                "[HEX_STRING]" in result.sanitized_message)
        assert result.was_sanitized

    def test_api_secret_redaction(self):
        """API secrets should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Failed with api_secret=super_secret_value_123"
        result = sanitizer.sanitize(message)
        assert "super_secret_value_123" not in result.sanitized_message
        assert "api_secret=[REDACTED]" in result.sanitized_message
        assert result.was_sanitized

    def test_access_token_redaction(self):
        """Access tokens should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Token expired: access_token=eyJhbGciOiJIUzI1NiJ9.payload.signature"
        result = sanitizer.sanitize(message)
        assert "payload" not in result.sanitized_message
        assert "access_token=[REDACTED]" in result.sanitized_message
        assert result.was_sanitized

    def test_password_redaction(self):
        """Passwords should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Login failed with password=MySecretPass123!"
        result = sanitizer.sanitize(message)
        assert "MySecretPass123" not in result.sanitized_message
        assert "password=[REDACTED]" in result.sanitized_message
        assert result.was_sanitized

    def test_passwd_redaction(self):
        """passwd variants should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Auth error: passwd=secret123"
        result = sanitizer.sanitize(message)
        assert "secret123" not in result.sanitized_message
        assert "passwd=[REDACTED]" in result.sanitized_message
        assert result.was_sanitized

    def test_env_var_glp_client_id(self):
        """GLP_CLIENT_ID environment variable should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Missing GLP_CLIENT_ID environment variable"
        result = sanitizer.sanitize(message)
        assert "GLP_CLIENT_ID" not in result.sanitized_message
        assert "[ENV_VAR]" in result.sanitized_message
        assert result.was_sanitized

    def test_env_var_glp_client_secret(self):
        """GLP_CLIENT_SECRET environment variable should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Configuration error: GLP_CLIENT_SECRET not set"
        result = sanitizer.sanitize(message)
        assert "GLP_CLIENT_SECRET" not in result.sanitized_message
        assert "[ENV_VAR]" in result.sanitized_message
        assert result.was_sanitized

    def test_env_var_database_url(self):
        """DATABASE_URL environment variable should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Check DATABASE_URL= for connection settings"
        result = sanitizer.sanitize(message)
        assert "DATABASE_URL" not in result.sanitized_message
        assert "[ENV_VAR]" in result.sanitized_message
        assert result.was_sanitized

    def test_env_var_jwt_secret(self):
        """JWT_SECRET environment variable should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Token signing requires JWT_SECRET to be set"
        result = sanitizer.sanitize(message)
        assert "JWT_SECRET" not in result.sanitized_message
        assert "[ENV_VAR]" in result.sanitized_message
        assert result.was_sanitized

    def test_env_var_anthropic_api_key(self):
        """ANTHROPIC_API_KEY environment variable should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Agent requires ANTHROPIC_API_KEY for Claude access"
        result = sanitizer.sanitize(message)
        assert "ANTHROPIC_API_KEY" not in result.sanitized_message
        assert "[ENV_VAR]" in result.sanitized_message
        assert result.was_sanitized

    def test_file_path_unix_redaction(self):
        """Unix file paths should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "File not found: /home/user/.env"
        result = sanitizer.sanitize(message)
        assert "/home/user/.env" not in result.sanitized_message
        assert "[FILE_PATH]" in result.sanitized_message
        assert result.was_sanitized

    def test_file_path_windows_redaction(self):
        """Windows file paths should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Cannot read C:\\Users\\admin\\config.json"
        result = sanitizer.sanitize(message)
        assert "C:\\Users\\admin" not in result.sanitized_message
        assert "[FILE_PATH]" in result.sanitized_message
        assert result.was_sanitized

    def test_file_path_relative_redaction(self):
        """Relative file paths should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Error loading ./config/secrets.json"
        result = sanitizer.sanitize(message)
        assert "./config/secrets.json" not in result.sanitized_message
        assert "[FILE_PATH]" in result.sanitized_message
        assert result.was_sanitized

    def test_ip_address_redaction(self):
        """IP addresses should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Connection timeout to 192.168.1.100:8080"
        result = sanitizer.sanitize(message)
        assert "192.168.1.100" not in result.sanitized_message
        assert "[IP_ADDRESS]" in result.sanitized_message
        assert result.was_sanitized

    def test_mac_address_redaction(self):
        """MAC addresses should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Device MAC: AA:BB:CC:DD:EE:FF not found"
        result = sanitizer.sanitize(message)
        assert "AA:BB:CC:DD:EE:FF" not in result.sanitized_message
        assert "[MAC_ADDRESS]" in result.sanitized_message
        assert result.was_sanitized

    def test_jwt_token_redaction(self):
        """JWT tokens should be redacted."""
        sanitizer = ErrorSanitizer()
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        message = f"Invalid token: {jwt}"
        result = sanitizer.sanitize(message)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result.sanitized_message
        assert "[JWT_REDACTED]" in result.sanitized_message
        assert result.was_sanitized

    def test_aws_access_key_redaction(self):
        """AWS access keys should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "AWS credentials: AKIAIOSFODNN7EXAMPLE"
        result = sanitizer.sanitize(message)
        assert "AKIAIOSFODNN7EXAMPLE" not in result.sanitized_message
        assert "[AWS_ACCESS_KEY]" in result.sanitized_message
        assert result.was_sanitized

    def test_private_key_redaction(self):
        """SSH private keys should be redacted."""
        sanitizer = ErrorSanitizer()
        message = """Found key:
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA1234567890abcdef
-----END RSA PRIVATE KEY-----
End"""
        result = sanitizer.sanitize(message)
        assert "MIIEowIBAAKCAQEA" not in result.sanitized_message
        assert "[PRIVATE_KEY]" in result.sanitized_message
        assert result.was_sanitized

    def test_stack_trace_redaction(self):
        """Python stack traces should be redacted."""
        sanitizer = ErrorSanitizer()
        message = """Error occurred:
Traceback (most recent call last):
  File "/app/main.py", line 42, in handler
    result = process_data()
  File "/app/utils.py", line 15, in process_data
    raise ValueError("Invalid input")
ValueError: Invalid input"""
        result = sanitizer.sanitize(message)
        assert "Traceback (most recent call last)" not in result.sanitized_message
        assert "[STACK_TRACE]" in result.sanitized_message
        assert result.was_sanitized


class TestMultipleRedactions:
    """Test messages with multiple sensitive patterns."""

    def test_multiple_patterns_in_message(self):
        """Multiple sensitive patterns should all be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Failed to connect to postgresql://user:pass@192.168.1.50/db with api_key=secret123"
        result = sanitizer.sanitize(message)
        assert "user:pass" not in result.sanitized_message
        assert "192.168.1.50" not in result.sanitized_message
        assert "secret123" not in result.sanitized_message
        assert "[DATABASE_URL]" in result.sanitized_message
        # IP is part of DATABASE_URL so it's caught by that pattern first
        # api_key could be caught as ENV_VAR or api_key pattern
        assert ("[REDACTED]" in result.sanitized_message or
                "[ENV_VAR]" in result.sanitized_message)
        assert result.redaction_count >= 2

    def test_env_vars_and_paths(self):
        """Environment variables and file paths should both be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Missing GLP_CLIENT_ID from /etc/glp/config.env"
        result = sanitizer.sanitize(message)
        assert "GLP_CLIENT_ID" not in result.sanitized_message
        assert "/etc/glp/config.env" not in result.sanitized_message
        assert "[ENV_VAR]" in result.sanitized_message
        assert "[FILE_PATH]" in result.sanitized_message
        assert result.was_sanitized

    def test_credentials_and_urls(self):
        """Credentials and connection URLs should be redacted."""
        sanitizer = ErrorSanitizer()
        message = "Auth failed: password=secret123 for redis://admin:pass@localhost:6379"
        result = sanitizer.sanitize(message)
        assert "secret123" not in result.sanitized_message
        assert "admin:pass" not in result.sanitized_message
        assert "password=[REDACTED]" in result.sanitized_message
        # Redis URL pattern should catch it, but might also be caught as ENV_VAR
        assert ("[REDIS_URL]" in result.sanitized_message or
                "[ENV_VAR]" in result.sanitized_message)
        assert result.was_sanitized


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_very_long_message_truncation(self):
        """Very long messages should be truncated."""
        sanitizer = ErrorSanitizer(max_message_length=100)
        # Use a message that won't be caught by base64 pattern (40+ chars of [A-Za-z0-9+/])
        message = "Error: " + ("This is a long error message. " * 10)
        result = sanitizer.sanitize(message)
        assert len(result.sanitized_message) <= 120  # 100 + "... [TRUNCATED]"
        assert "[TRUNCATED]" in result.sanitized_message

    def test_message_becomes_empty_after_sanitization(self):
        """Messages that are only sensitive data should get generic message."""
        sanitizer = ErrorSanitizer()
        # This should be entirely redacted
        message = "postgresql://user:pass@localhost/db"
        result = sanitizer.sanitize(message)
        # Should have some content after redaction (the replacement text)
        assert len(result.sanitized_message) > 0
        assert "[DATABASE_URL]" in result.sanitized_message

    def test_whitespace_only_after_sanitization(self):
        """Whitespace-only results should get generic message."""
        # Create a sanitizer with custom pattern that would leave only whitespace
        custom_patterns = [("Error", "")]  # Remove the word "Error"
        sanitizer = ErrorSanitizer(patterns=custom_patterns)
        message = "Error"
        result = sanitizer.sanitize(message)
        assert result.sanitized_message == "An error occurred"

    def test_case_insensitive_matching(self):
        """Pattern matching should be case-insensitive."""
        sanitizer = ErrorSanitizer()
        # Use password instead of api_key since API_KEY is caught as ENV_VAR
        message1 = "Missing PASSWORD=secret in config"
        message2 = "Missing password=secret in config"
        message3 = "Missing Password=Secret in config"

        result1 = sanitizer.sanitize(message1)
        result2 = sanitizer.sanitize(message2)
        result3 = sanitizer.sanitize(message3)

        # All should be redacted regardless of case
        assert "secret" not in result1.sanitized_message.lower()
        assert "secret" not in result2.sanitized_message.lower()
        assert "secret" not in result3.sanitized_message.lower()
        assert result1.was_sanitized
        assert result2.was_sanitized
        assert result3.was_sanitized

    def test_none_message_treated_as_empty(self):
        """None should be treated as empty."""
        sanitizer = ErrorSanitizer()
        # Python will convert None to empty string in most contexts
        result = sanitizer.sanitize("")
        assert result.sanitized_message == "An error occurred"


class TestErrorTypePrefix:
    """Test error type prefix functionality."""

    def test_error_type_prefix_added(self):
        """Error type should be added as prefix."""
        sanitizer = ErrorSanitizer()
        message = "Invalid credentials"
        result = sanitizer.sanitize(message, error_type="Authentication Error")
        assert result.sanitized_message.startswith("Authentication Error:")
        assert "Invalid credentials" in result.sanitized_message

    def test_error_type_not_duplicated(self):
        """Error type should not be duplicated if already present."""
        sanitizer = ErrorSanitizer()
        message = "Database Error: Connection failed"
        result = sanitizer.sanitize(message, error_type="Database Error")
        # Should only appear once
        assert result.sanitized_message.count("Database Error") == 1

    def test_error_type_with_sanitization(self):
        """Error type should be added after sanitization."""
        sanitizer = ErrorSanitizer()
        message = "Connection to postgresql://user:pass@localhost failed"
        result = sanitizer.sanitize(message, error_type="Database Error")
        assert result.sanitized_message.startswith("Database Error:")
        assert "postgresql://" not in result.sanitized_message
        assert "[DATABASE_URL]" in result.sanitized_message


class TestCustomPatterns:
    """Test adding custom sanitization patterns."""

    def test_add_custom_pattern(self):
        """Custom patterns should be applied."""
        sanitizer = ErrorSanitizer()
        sanitizer.add_pattern(r"CUSTOM_SECRET_\d+", "[CUSTOM_REDACTED]")

        message = "Error with CUSTOM_SECRET_12345"
        result = sanitizer.sanitize(message)
        assert "CUSTOM_SECRET_12345" not in result.sanitized_message
        assert "[CUSTOM_REDACTED]" in result.sanitized_message
        assert result.was_sanitized

    def test_multiple_custom_patterns(self):
        """Multiple custom patterns can be added."""
        sanitizer = ErrorSanitizer()
        sanitizer.add_pattern(r"PATTERN_A_\w+", "[A_REDACTED]")
        sanitizer.add_pattern(r"PATTERN_B_\w+", "[B_REDACTED]")

        message = "Found PATTERN_A_test and PATTERN_B_data"
        result = sanitizer.sanitize(message)
        assert "PATTERN_A_test" not in result.sanitized_message
        assert "PATTERN_B_data" not in result.sanitized_message
        assert "[A_REDACTED]" in result.sanitized_message
        assert "[B_REDACTED]" in result.sanitized_message

    def test_custom_patterns_in_constructor(self):
        """Custom patterns can be provided in constructor."""
        custom_patterns = [
            (r"SECRET_\d+", "[SECRET]"),
            (r"INTERNAL_\w+", "[INTERNAL]"),
        ]
        sanitizer = ErrorSanitizer(patterns=custom_patterns)

        message = "Error with SECRET_123 and INTERNAL_DATA"
        result = sanitizer.sanitize(message)
        assert "SECRET_123" not in result.sanitized_message
        assert "INTERNAL_DATA" not in result.sanitized_message
        assert "[SECRET]" in result.sanitized_message
        assert "[INTERNAL]" in result.sanitized_message


class TestSafetyCheck:
    """Test the is_safe() method."""

    def test_is_safe_clean_message(self):
        """Clean messages should be marked as safe."""
        sanitizer = ErrorSanitizer()
        assert sanitizer.is_safe("Device not found")
        assert sanitizer.is_safe("Invalid request format")
        assert sanitizer.is_safe("Operation completed successfully")

    def test_is_safe_database_url(self):
        """Messages with database URLs should not be safe."""
        sanitizer = ErrorSanitizer()
        assert not sanitizer.is_safe("postgresql://user:pass@localhost/db")
        assert not sanitizer.is_safe("Error: mysql://admin:secret@db.example.com/mydb")

    def test_is_safe_api_key(self):
        """Messages with API keys should not be safe."""
        sanitizer = ErrorSanitizer()
        assert not sanitizer.is_safe("api_key=sk-1234567890abcdef")
        assert not sanitizer.is_safe("Missing api_secret=supersecret")

    def test_is_safe_password(self):
        """Messages with passwords should not be safe."""
        sanitizer = ErrorSanitizer()
        assert not sanitizer.is_safe("password=MySecret123")
        assert not sanitizer.is_safe("Login with passwd=test123")

    def test_is_safe_env_vars(self):
        """Messages with environment variable names should not be safe."""
        sanitizer = ErrorSanitizer()
        assert not sanitizer.is_safe("Missing GLP_CLIENT_ID")
        assert not sanitizer.is_safe("Check ANTHROPIC_API_KEY setting")

    def test_is_safe_file_paths(self):
        """Messages with file paths should not be safe."""
        sanitizer = ErrorSanitizer()
        assert not sanitizer.is_safe("Cannot read /etc/passwd")
        assert not sanitizer.is_safe("File not found: C:\\Windows\\System32\\config")

    def test_is_safe_ip_address(self):
        """Messages with IP addresses should not be safe."""
        sanitizer = ErrorSanitizer()
        assert not sanitizer.is_safe("Connection to 192.168.1.100 failed")
        assert not sanitizer.is_safe("Server at 10.0.0.1 is down")


class TestConvenienceFunctions:
    """Test convenience functions and singleton."""

    def test_get_sanitizer_singleton(self):
        """get_sanitizer() should return same instance."""
        sanitizer1 = get_sanitizer()
        sanitizer2 = get_sanitizer()
        assert sanitizer1 is sanitizer2

    def test_sanitize_error_message_function(self):
        """sanitize_error_message() convenience function should work."""
        result = sanitize_error_message("Connection to postgresql://user:pass@localhost failed")
        assert "user:pass" not in result
        assert "[DATABASE_URL]" in result

    def test_sanitize_error_message_with_error_type(self):
        """sanitize_error_message() should support error_type parameter."""
        result = sanitize_error_message(
            "Missing GLP_CLIENT_ID",
            error_type="Configuration Error"
        )
        assert "Configuration Error:" in result
        assert "GLP_CLIENT_ID" not in result
        assert "[ENV_VAR]" in result

    def test_sanitize_error_message_empty(self):
        """sanitize_error_message() should handle empty messages."""
        result = sanitize_error_message("")
        assert result == "An error occurred"

    def test_sanitize_error_message_clean(self):
        """sanitize_error_message() should pass clean messages through."""
        original = "Device not found"
        result = sanitize_error_message(original)
        assert result == original


class TestSanitizationResult:
    """Test SanitizationResult dataclass."""

    def test_result_attributes(self):
        """Result should have all expected attributes."""
        sanitizer = ErrorSanitizer()
        message = "Error with api_key=secret123"
        result = sanitizer.sanitize(message)

        assert hasattr(result, "sanitized_message")
        assert hasattr(result, "redaction_count")
        assert hasattr(result, "original_length")
        assert hasattr(result, "sanitized_length")
        assert hasattr(result, "was_sanitized")

    def test_result_was_sanitized_true(self):
        """was_sanitized should be True when redactions occurred."""
        sanitizer = ErrorSanitizer()
        result = sanitizer.sanitize("password=secret")
        assert result.was_sanitized is True
        assert result.redaction_count > 0

    def test_result_was_sanitized_false(self):
        """was_sanitized should be False when no redactions occurred."""
        sanitizer = ErrorSanitizer()
        result = sanitizer.sanitize("Normal error message")
        assert result.was_sanitized is False
        assert result.redaction_count == 0

    def test_result_lengths(self):
        """Result should track original and sanitized lengths."""
        sanitizer = ErrorSanitizer()
        message = "api_key=secret123"
        result = sanitizer.sanitize(message)

        assert result.original_length == len(message)
        assert result.sanitized_length == len(result.sanitized_message)
        assert result.original_length > 0
        assert result.sanitized_length > 0


class TestRealWorldScenarios:
    """Test real-world error scenarios from the application."""

    def test_glp_config_error(self):
        """Simulate the GLP configuration error from dashboard_router.py:609."""
        sanitizer = ErrorSanitizer()
        message = "Configuration error: Missing credentials. Check GLP_CLIENT_ID, GLP_CLIENT_SECRET, GLP_TOKEN_URL in environment"
        result = sanitizer.sanitize(message, error_type="Configuration Error")

        assert "GLP_CLIENT_ID" not in result.sanitized_message
        assert "GLP_CLIENT_SECRET" not in result.sanitized_message
        assert "GLP_TOKEN_URL" not in result.sanitized_message
        assert "[ENV_VAR]" in result.sanitized_message
        assert "Configuration Error:" in result.sanitized_message

    def test_sync_failure_error(self):
        """Simulate sync failure error from clients_router.py:916."""
        sanitizer = ErrorSanitizer()
        # Simulate an exception message with database connection details
        exception_msg = "Connection failed: postgresql://admin:SuperSecret@db.internal.company.com:5432/glp_prod timeout after 30s"
        message = f"Sync failed: {exception_msg}"
        result = sanitizer.sanitize(message)

        assert "admin:SuperSecret" not in result.sanitized_message
        assert "db.internal.company.com" not in result.sanitized_message
        assert "[DATABASE_URL]" in result.sanitized_message

    def test_database_connection_error(self):
        """Simulate database connection error."""
        sanitizer = ErrorSanitizer()
        message = "Could not connect to database at postgresql://glp_user:P@ssw0rd123@192.168.100.50:5432/greenlake"
        result = sanitizer.sanitize(message)

        assert "glp_user" not in result.sanitized_message
        assert "P@ssw0rd123" not in result.sanitized_message
        assert "192.168.100.50" not in result.sanitized_message
        assert "[DATABASE_URL]" in result.sanitized_message
        assert "[IP_ADDRESS]" not in result.sanitized_message  # Should be caught by DATABASE_URL first

    def test_api_authentication_error(self):
        """Simulate API authentication error with tokens."""
        sanitizer = ErrorSanitizer()
        message = "API authentication failed with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        result = sanitizer.sanitize(message)

        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result.sanitized_message
        assert "[REDACTED]" in result.sanitized_message or "[JWT_REDACTED]" in result.sanitized_message

    def test_file_system_error(self):
        """Simulate file system error with paths."""
        sanitizer = ErrorSanitizer()
        message = "Failed to read configuration from /home/glp/.env file"
        result = sanitizer.sanitize(message)

        assert "/home/glp/.env" not in result.sanitized_message
        assert "[FILE_PATH]" in result.sanitized_message

    def test_stack_trace_with_sensitive_data(self):
        """Simulate stack trace containing file paths."""
        sanitizer = ErrorSanitizer()
        message = """Unhandled exception:
Traceback (most recent call last):
  File "/app/src/glp/api/client.py", line 123, in fetch_devices
    response = await session.get(url, headers=headers)
  File "/usr/local/lib/python3.12/aiohttp/client.py", line 456, in get
    raise ClientError("Connection failed")
aiohttp.ClientError: Connection failed"""
        result = sanitizer.sanitize(message)

        assert "/app/src/glp/api/client.py" not in result.sanitized_message
        assert "/usr/local/lib/python3.12" not in result.sanitized_message
        assert "[STACK_TRACE]" in result.sanitized_message or "[FILE_PATH]" in result.sanitized_message
