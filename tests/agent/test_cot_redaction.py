"""
Tests for Chain of Thought (CoT) redaction.

Ensures sensitive data is never stored or streamed in raw form.
"""

import pytest

from src.glp.agent.security.cot_redactor import (
    CoTRedactor,
    RedactionResult,
    get_redactor,
    redact_cot,
)


@pytest.fixture
def redactor():
    """Create a CoTRedactor instance."""
    return CoTRedactor()


class TestPasswordRedaction:
    """Tests for password redaction."""

    def test_redact_password_equals(self, redactor):
        """Passwords with = are redacted."""
        text = "The password=secret123 was found"
        result = redactor.redact(text)
        assert "secret123" not in result.summary
        assert "REDACTED" in result.summary
        assert result.was_redacted

    def test_redact_password_colon(self, redactor):
        """Passwords with : are redacted."""
        text = "password: myP@ssw0rd! in config"
        result = redactor.redact(text)
        assert "myP@ssw0rd!" not in result.summary
        assert result.was_redacted

    def test_redact_passwd_variant(self, redactor):
        """passwd variant is redacted."""
        text = "Found passwd=hunter2 in file"
        result = redactor.redact(text)
        assert "hunter2" not in result.summary


class TestAPIKeyRedaction:
    """Tests for API key redaction."""

    def test_redact_api_key(self, redactor):
        """API keys are redacted."""
        text = "api_key=sk-1234567890abcdef"
        result = redactor.redact(text)
        assert "sk-1234567890abcdef" not in result.summary
        assert result.was_redacted

    def test_redact_api_secret(self, redactor):
        """API secrets are redacted."""
        text = "The api-secret: abc123xyz789 was exposed"
        result = redactor.redact(text)
        assert "abc123xyz789" not in result.summary


class TestTokenRedaction:
    """Tests for token redaction."""

    def test_redact_bearer_token(self, redactor):
        """Bearer tokens are redacted."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature"
        result = redactor.redact(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result.summary
        assert result.was_redacted

    def test_redact_access_token(self, redactor):
        """Access tokens are redacted."""
        text = "access_token=gho_16C7e42F292c6912E7710c838347Ae178B4a"
        result = redactor.redact(text)
        assert "gho_16C7e42F292c6912E7710c838347Ae178B4a" not in result.summary

    def test_redact_refresh_token(self, redactor):
        """Refresh tokens are redacted."""
        text = "refresh_token: xyz123abc456def"
        result = redactor.redact(text)
        assert "xyz123abc456def" not in result.summary


class TestConnectionStringRedaction:
    """Tests for connection string redaction."""

    def test_redact_postgres_url(self, redactor):
        """PostgreSQL URLs are redacted."""
        text = "Connect to postgres://user:password@host:5432/db"
        result = redactor.redact(text)
        assert "password" not in result.summary
        assert "DATABASE_URL_REDACTED" in result.summary

    def test_redact_mysql_url(self, redactor):
        """MySQL URLs are redacted."""
        text = "mysql://admin:secret@localhost/mydb"
        result = redactor.redact(text)
        assert "secret" not in result.summary

    def test_redact_mongodb_url(self, redactor):
        """MongoDB URLs are redacted."""
        text = "mongodb+srv://user:pass@cluster.mongodb.net/db"
        result = redactor.redact(text)
        assert "pass" not in result.summary

    def test_redact_redis_url(self, redactor):
        """Redis URLs are redacted."""
        text = "redis://default:authstring@redis-host:6379"
        result = redactor.redact(text)
        assert "authstring" not in result.summary


class TestAWSCredentialRedaction:
    """Tests for AWS credential redaction."""

    def test_redact_aws_access_key(self, redactor):
        """AWS access key IDs are redacted."""
        text = "Found AKIAIOSFODNN7EXAMPLE in config"
        result = redactor.redact(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result.summary
        assert "AWS_ACCESS_KEY_REDACTED" in result.summary

    def test_redact_aws_secret_key(self, redactor):
        """AWS secret access keys are redacted."""
        text = "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        result = redactor.redact(text)
        assert "wJalrXUtnFEMI" not in result.summary


class TestNetworkAddressRedaction:
    """Tests for IP and MAC address redaction."""

    def test_redact_ipv4_address(self, redactor):
        """IPv4 addresses are redacted."""
        text = "Server at 192.168.1.100 is responding"
        result = redactor.redact(text)
        assert "192.168.1.100" not in result.summary
        assert "[IP_ADDRESS]" in result.summary or "IP_REDACTED" in result.summary

    def test_redact_mac_address_colon(self, redactor):
        """MAC addresses with colons are redacted."""
        text = "Device MAC: 00:1A:2B:3C:4D:5E"
        result = redactor.redact(text)
        assert "00:1A:2B:3C:4D:5E" not in result.summary

    def test_redact_mac_address_dash(self, redactor):
        """MAC addresses with dashes are redacted."""
        text = "MAC address 00-1A-2B-3C-4D-5E found"
        result = redactor.redact(text)
        assert "00-1A-2B-3C-4D-5E" not in result.summary


class TestSafeContentPreservation:
    """Tests that safe content is preserved."""

    def test_preserve_regular_text(self, redactor):
        """Regular text without sensitive data is preserved."""
        text = "The device has 4 CPUs and 16GB RAM"
        result = redactor.redact(text)
        assert result.summary == text
        assert not result.was_redacted
        assert result.redaction_count == 0

    def test_preserve_technical_info(self, redactor):
        """Technical information is preserved."""
        text = "Model: ProLiant DL380 Gen10, Serial: ABC123"
        result = redactor.redact(text)
        assert "ProLiant DL380 Gen10" in result.summary
        assert "ABC123" in result.summary

    def test_preserve_numbers(self, redactor):
        """Regular numbers are not redacted."""
        text = "Processing 1234 devices took 5678 seconds"
        result = redactor.redact(text)
        assert "1234" in result.summary
        assert "5678" in result.summary


class TestRedactionResult:
    """Tests for RedactionResult metadata."""

    def test_redaction_count(self, redactor):
        """Redaction count is accurate."""
        text = "password=abc api_key=xyz access_token=secret123"
        result = redactor.redact(text)
        assert result.redaction_count >= 2  # At minimum password and api_key are redacted

    def test_length_tracking(self, redactor):
        """Original and summary lengths are tracked."""
        text = "password=verylongsecretpassword123"
        result = redactor.redact(text)
        assert result.original_length == len(text)
        assert result.summary_length == len(result.summary)

    def test_was_redacted_flag(self, redactor):
        """was_redacted flag is correct."""
        clean = redactor.redact("No secrets here")
        assert not clean.was_redacted

        sensitive = redactor.redact("password=secret")
        assert sensitive.was_redacted


class TestConvenienceFunction:
    """Tests for the convenience redact_cot function."""

    def test_redact_cot_function(self):
        """redact_cot returns just the summary."""
        result = redact_cot("The password=secret was found")
        assert isinstance(result, str)
        assert "secret" not in result
        assert "REDACTED" in result

    def test_get_redactor_singleton(self):
        """get_redactor returns singleton instance."""
        r1 = get_redactor()
        r2 = get_redactor()
        assert r1 is r2


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_string(self, redactor):
        """Empty string is handled."""
        result = redactor.redact("")
        assert result.summary == ""
        assert not result.was_redacted

    def test_none_like_input(self, redactor):
        """Whitespace-only input is handled."""
        result = redactor.redact("   \n\t  ")
        assert not result.was_redacted

    def test_multiple_secrets_same_line(self, redactor):
        """Multiple secrets on same line are all redacted."""
        text = "password=abc api_key=def secret=ghi"
        result = redactor.redact(text)
        assert "abc" not in result.summary
        assert "def" not in result.summary
        assert "ghi" not in result.summary

    def test_multiline_redaction(self, redactor):
        """Redaction works across multiple lines."""
        text = """Line 1: password=secret1
        Line 2: api_key=secret2
        Line 3: normal text"""
        result = redactor.redact(text)
        assert "secret1" not in result.summary
        assert "secret2" not in result.summary
        assert "normal text" in result.summary
