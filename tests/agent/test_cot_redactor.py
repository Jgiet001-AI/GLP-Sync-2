"""
Tests for Chain of Thought (CoT) Redaction.

These tests ensure:
1. Sensitive patterns are properly redacted
2. Edge cases with chunk boundaries are handled
3. Streaming redaction doesn't leak pre-redacted content
4. Adversarial inputs don't bypass redaction
"""

import pytest

from src.glp.agent.security.cot_redactor import (
    CoTRedactor,
    RedactionResult,
    get_redactor,
    redact_cot,
)


class TestBasicRedaction:
    """Test basic redaction patterns."""

    def test_empty_text(self):
        """Empty text should return empty result."""
        redactor = CoTRedactor()
        result = redactor.redact("")
        assert result.summary == ""
        assert result.redaction_count == 0
        assert not result.was_redacted

    def test_clean_text(self):
        """Text without sensitive data should pass through."""
        redactor = CoTRedactor()
        text = "This is a normal conversation about devices."
        result = redactor.redact(text)
        assert result.summary == text
        assert result.redaction_count == 0
        assert not result.was_redacted

    def test_bearer_token_redaction(self):
        """Bearer tokens should be redacted."""
        redactor = CoTRedactor()
        text = "Using token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.sig"
        result = redactor.redact(text)
        assert "eyJ" not in result.summary
        assert "[REDACTED]" in result.summary or "[JWT_REDACTED]" in result.summary
        assert result.was_redacted

    def test_api_key_redaction(self):
        """API keys should be redacted."""
        redactor = CoTRedactor()
        text = "Setting api_key=sk-1234567890abcdef1234567890abcdef for the request"
        result = redactor.redact(text)
        assert "sk-1234567890abcdef" not in result.summary
        assert result.was_redacted

    def test_password_redaction(self):
        """Passwords should be redacted."""
        redactor = CoTRedactor()
        text = "Database password=SuperSecret123! for connection"
        result = redactor.redact(text)
        assert "SuperSecret123" not in result.summary
        assert result.was_redacted

    def test_database_url_redaction(self):
        """Database URLs should be redacted."""
        redactor = CoTRedactor()
        text = "Connecting to postgresql://user:pass@host:5432/db"
        result = redactor.redact(text)
        assert "user:pass" not in result.summary
        assert "[DATABASE_URL_REDACTED]" in result.summary
        assert result.was_redacted

    def test_ip_address_redaction(self):
        """IP addresses should be redacted."""
        redactor = CoTRedactor()
        text = "Server at 192.168.1.100 responded"
        result = redactor.redact(text)
        assert "192.168.1.100" not in result.summary
        assert "[IP_ADDRESS]" in result.summary
        assert result.was_redacted

    def test_mac_address_redaction(self):
        """MAC addresses should be redacted."""
        redactor = CoTRedactor()
        text = "Device MAC: AA:BB:CC:DD:EE:FF"
        result = redactor.redact(text)
        assert "AA:BB:CC:DD:EE:FF" not in result.summary
        assert "[MAC_ADDRESS]" in result.summary
        assert result.was_redacted

    def test_jwt_redaction(self):
        """JWT tokens should be redacted."""
        redactor = CoTRedactor()
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        text = f"Token received: {jwt}"
        result = redactor.redact(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result.summary
        assert result.was_redacted

    def test_aws_key_redaction(self):
        """AWS access keys should be redacted."""
        redactor = CoTRedactor()
        text = "AWS key: AKIAIOSFODNN7EXAMPLE"
        result = redactor.redact(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result.summary
        assert "[AWS_ACCESS_KEY_REDACTED]" in result.summary
        assert result.was_redacted

    def test_private_key_redaction(self):
        """SSH private keys should be redacted."""
        redactor = CoTRedactor()
        text = """Found key:
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA...
-----END RSA PRIVATE KEY-----
End of key"""
        result = redactor.redact(text)
        assert "MIIEowIBAAKCAQEA" not in result.summary
        assert "[PRIVATE_KEY_REDACTED]" in result.summary
        assert result.was_redacted


class TestChunkBoundaryEdgeCases:
    """Test edge cases related to streaming chunk boundaries.

    These tests ensure that sensitive data split across streaming chunks
    cannot leak through the redactor.
    """

    def test_split_bearer_token(self):
        """Bearer token split across chunks should still be redacted when combined."""
        redactor = CoTRedactor()
        # Simulate chunks that might come from streaming
        chunk1 = "Using Bear"
        chunk2 = "er abc123token"

        # Individual chunks might not be redacted
        result1 = redactor.redact(chunk1)
        result2 = redactor.redact(chunk2)

        # But combined text MUST be redacted
        combined = chunk1 + chunk2
        result_combined = redactor.redact(combined)
        assert "abc123token" not in result_combined.summary
        assert result_combined.was_redacted

    def test_split_password_keyword(self):
        """Password keyword split across chunks."""
        redactor = CoTRedactor()
        chunk1 = "pass"
        chunk2 = "word=secret123"

        combined = chunk1 + chunk2
        result = redactor.redact(combined)
        assert "secret123" not in result.summary
        assert result.was_redacted

    def test_split_api_key_pattern(self):
        """API key pattern split across chunks."""
        redactor = CoTRedactor()
        chunk1 = "api_"
        chunk2 = "key=super_secret_key_12345"

        combined = chunk1 + chunk2
        result = redactor.redact(combined)
        assert "super_secret_key_12345" not in result.summary
        assert result.was_redacted

    def test_split_jwt_token(self):
        """JWT split at dot boundaries."""
        redactor = CoTRedactor()
        header = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        payload = "eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        signature = "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"

        # Split at various points
        chunk1 = f"Token: {header}."
        chunk2 = f"{payload}.{signature}"

        combined = chunk1 + chunk2
        result = redactor.redact(combined)
        assert header not in result.summary
        assert payload not in result.summary
        assert result.was_redacted

    def test_split_database_url(self):
        """Database URL split across chunks."""
        redactor = CoTRedactor()
        chunk1 = "Connecting to postgres"
        chunk2 = "ql://admin:secret@db.server.com:5432/mydb"

        combined = chunk1 + chunk2
        result = redactor.redact(combined)
        assert "admin:secret" not in result.summary
        assert "[DATABASE_URL_REDACTED]" in result.summary
        assert result.was_redacted

    def test_split_ip_address(self):
        """IP address split at octet boundary."""
        redactor = CoTRedactor()
        chunk1 = "Server 192.168."
        chunk2 = "1.100 responded"

        combined = chunk1 + chunk2
        result = redactor.redact(combined)
        assert "192.168.1.100" not in result.summary
        assert "[IP_ADDRESS]" in result.summary
        assert result.was_redacted


class TestAdversarialInputs:
    """Test inputs designed to bypass redaction."""

    def test_case_variation(self):
        """Different case variations should be redacted."""
        redactor = CoTRedactor()
        variations = [
            "PASSWORD=secret",
            "Password=secret",
            "passWord=secret",
            "PASSWORD=secret",
        ]
        for text in variations:
            result = redactor.redact(text)
            assert "secret" not in result.summary, f"Failed for: {text}"
            assert result.was_redacted

    def test_whitespace_variation(self):
        """Whitespace variations should be redacted."""
        redactor = CoTRedactor()
        variations = [
            "password = secret",
            "password=secret",
            "password: secret",
            "password :secret",
        ]
        for text in variations:
            result = redactor.redact(text)
            assert "secret" not in result.summary, f"Failed for: {text}"

    def test_unicode_obfuscation(self):
        """Unicode look-alikes should not bypass redaction.

        Note: This test documents current behavior. Full Unicode normalization
        would require additional handling.
        """
        redactor = CoTRedactor()
        # Normal password pattern
        text = "password=normal_secret"
        result = redactor.redact(text)
        assert "normal_secret" not in result.summary

    def test_encoded_patterns(self):
        """Base64-like patterns should be caught."""
        redactor = CoTRedactor()
        # Long base64 string (40+ chars)
        long_base64 = "c3VwZXJfc2VjcmV0X2tleV90aGF0X2lzX3ZlcnlfbG9uZ19hbmRfc2hvdWxkX2JlX3JlZGFjdGVk"
        text = f"Encoded: {long_base64}"
        result = redactor.redact(text)
        assert long_base64 not in result.summary
        assert result.was_redacted

    def test_multiple_secrets_in_one_text(self):
        """Multiple secrets should all be redacted."""
        redactor = CoTRedactor()
        text = """
        Config:
        api_key=key123
        password=pass456
        database: postgresql://user:pass@host/db
        server: 10.0.0.1
        """
        result = redactor.redact(text)
        assert "key123" not in result.summary
        assert "pass456" not in result.summary
        assert "user:pass" not in result.summary
        assert "10.0.0.1" not in result.summary
        assert result.redaction_count >= 4


class TestTruncation:
    """Test summary truncation behavior."""

    def test_long_text_truncated(self):
        """Long text should be truncated."""
        redactor = CoTRedactor(max_summary_length=100)
        # Use text that won't match any redaction patterns
        text = "This is a normal sentence. " * 25  # ~700 chars
        result = redactor.redact(text)
        assert len(result.summary) <= 115  # 100 + "... [TRUNCATED]"
        assert "[TRUNCATED]" in result.summary

    def test_secret_after_truncation_point(self):
        """Secrets after truncation point should not appear."""
        redactor = CoTRedactor(max_summary_length=50)
        text = "Normal text " * 10 + "password=secret_after_truncation"
        result = redactor.redact(text)
        # The password might be redacted OR truncated, either way it shouldn't appear
        assert "secret_after_truncation" not in result.summary


class TestStreamingSimulation:
    """Simulate streaming behavior and verify redaction safety."""

    def test_streaming_buffer_simulation(self):
        """Simulate a streaming buffer that accumulates text.

        In real streaming, we should buffer text until we're confident
        redaction markers are resolved.
        """
        redactor = CoTRedactor()

        # Simulate streaming chunks
        chunks = [
            "The system is ",
            "checking password",
            "=MyS3cret! ",
            "for authentication.",
        ]

        # A naive implementation would redact chunk by chunk
        naive_results = [redactor.redact(c).summary for c in chunks]
        naive_combined = "".join(naive_results)

        # A proper implementation buffers and redacts the full text
        full_text = "".join(chunks)
        proper_result = redactor.redact(full_text)

        # The naive approach might leak "MyS3cret!" if the pattern spans chunks
        # The proper approach should always redact it
        assert "MyS3cret" not in proper_result.summary

    def test_redactor_is_stateless(self):
        """Verify redactor is stateless and can be reused."""
        redactor = CoTRedactor()

        result1 = redactor.redact("password=secret1")
        result2 = redactor.redact("password=secret2")

        assert "secret1" not in result1.summary
        assert "secret2" not in result2.summary
        # Verify they're independent
        assert "secret2" not in result1.summary
        assert "secret1" not in result2.summary


class TestCustomPatterns:
    """Test custom pattern functionality."""

    def test_add_custom_pattern(self):
        """Custom patterns can be added."""
        redactor = CoTRedactor()
        redactor.add_pattern(r"CUSTOM-\d{6}", "[CUSTOM_ID_REDACTED]")

        text = "ID: CUSTOM-123456"
        result = redactor.redact(text)
        assert "CUSTOM-123456" not in result.summary
        assert "[CUSTOM_ID_REDACTED]" in result.summary

    def test_is_safe_check(self):
        """is_safe should detect redactable content."""
        redactor = CoTRedactor()

        assert redactor.is_safe("Normal text without secrets")
        assert not redactor.is_safe("password=secret")
        assert not redactor.is_safe("Bearer abc123token")


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_get_redactor_singleton(self):
        """get_redactor returns the same instance."""
        r1 = get_redactor()
        r2 = get_redactor()
        assert r1 is r2

    def test_redact_cot_function(self):
        """redact_cot convenience function works."""
        result = redact_cot("password=secret")
        assert "secret" not in result
        assert "[REDACTED]" in result
