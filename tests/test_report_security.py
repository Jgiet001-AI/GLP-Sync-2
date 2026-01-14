"""Security tests for custom report builder.

Tests SQL injection prevention, input sanitization, and other security measures.
"""

import pytest

from src.glp.reports.query_builder import QueryBuilder, QueryBuilderError
from src.glp.reports.schemas import (
    AggregationFunction,
    FieldConfig,
    FilterConfig,
    FilterOperator,
    GroupingConfig,
    LogicOperator,
    ReportConfig,
    SortingConfig,
    SortDirection,
)
from src.glp.reports.security import (
    MAX_ARRAY_LENGTH,
    MAX_FIELDS,
    MAX_FILTERS,
    MAX_GROUPING,
    MAX_LIMIT,
    MAX_SORTING,
    MAX_STRING_VALUE_LENGTH,
    SecurityValidationError,
    sanitize_like_pattern,
    validate_config_complexity,
    validate_filter_value,
    validate_report_config,
)


class TestSQLInjectionPrevention:
    """Test SQL injection prevention mechanisms."""

    def test_field_whitelist_prevents_injection(self):
        """Invalid field names should be rejected."""
        config = ReportConfig(
            fields=[
                # Try to inject via field name
                FieldConfig(table="devices", field="id; DROP TABLE devices--"),
            ],
            filters=[],
            grouping=[],
            sorting=[],
        )

        builder = QueryBuilder()
        with pytest.raises(QueryBuilderError) as exc_info:
            builder.build_query(config)

        assert "Invalid field" in str(exc_info.value)

    def test_table_whitelist_prevents_injection(self):
        """Invalid table names should be rejected."""
        config = ReportConfig(
            fields=[
                # Try to inject via table name
                FieldConfig(table="devices; DROP TABLE users--", field="id"),
            ],
            filters=[],
            grouping=[],
            sorting=[],
        )

        builder = QueryBuilder()
        with pytest.raises(QueryBuilderError) as exc_info:
            builder.build_query(config)

        assert "Invalid table" in str(exc_info.value)

    def test_filter_value_sql_keywords_blocked(self):
        """SQL keywords in filter values should be blocked."""
        dangerous_values = [
            "admin' OR '1'='1",
            "1; DROP TABLE devices--",
            "1' UNION SELECT * FROM users--",
            "'; DELETE FROM devices WHERE '1'='1",
            "1' AND 1=1--",
            "admin'/**/OR/**/1=1--",
            "1'; EXEC xp_cmdshell('dir')--",
        ]

        for dangerous_value in dangerous_values:
            with pytest.raises(SecurityValidationError) as exc_info:
                validate_filter_value(dangerous_value, FilterOperator.EQUALS)

            assert "SQL keywords" in str(exc_info.value) or "disallowed" in str(exc_info.value)

    def test_parameterized_queries_used(self):
        """Verify that generated SQL uses parameterized queries."""
        config = ReportConfig(
            fields=[
                FieldConfig(table="devices", field="device_type"),
                FieldConfig(table="devices", field="id", aggregation=AggregationFunction.COUNT),
            ],
            filters=[
                FilterConfig(
                    table="devices",
                    field="device_name",
                    operator=FilterOperator.EQUALS,
                    value="test-device",
                ),
            ],
            grouping=[GroupingConfig(table="devices", field="device_type")],
            sorting=[],
            limit=100,
        )

        builder = QueryBuilder()
        sql, params = builder.build_query(config)

        # Verify SQL uses placeholders, not direct value interpolation
        assert "$param_" in sql
        assert "test-device" not in sql  # Value should NOT be in SQL string
        assert "test-device" in params.values()  # Value should be in params

    def test_comment_injection_blocked(self):
        """SQL comments in filter values should be blocked."""
        comment_values = [
            "test--",
            "test/*comment*/",
            "test; --comment",
            "test */ OR 1=1 /*",
        ]

        for value in comment_values:
            with pytest.raises(SecurityValidationError):
                validate_filter_value(value, FilterOperator.CONTAINS)


class TestInputSizeValidation:
    """Test input size limits."""

    def test_filter_value_max_length(self):
        """Filter values exceeding max length should be rejected."""
        long_value = "x" * (MAX_STRING_VALUE_LENGTH + 1)

        with pytest.raises(SecurityValidationError) as exc_info:
            validate_filter_value(long_value, FilterOperator.EQUALS)

        assert "too long" in str(exc_info.value)

    def test_array_max_length(self):
        """Arrays exceeding max length should be rejected."""
        long_array = list(range(MAX_ARRAY_LENGTH + 1))

        with pytest.raises(SecurityValidationError) as exc_info:
            validate_filter_value(long_array, FilterOperator.IN)

        assert "Array too long" in str(exc_info.value)

    def test_array_item_max_length(self):
        """Array items exceeding max length should be rejected."""
        long_item = "x" * (MAX_STRING_VALUE_LENGTH + 1)
        array_with_long_item = [long_item]

        with pytest.raises(SecurityValidationError) as exc_info:
            validate_filter_value(array_with_long_item, FilterOperator.IN)

        assert "too long" in str(exc_info.value)

    def test_config_complexity_max_fields(self):
        """Configs with too many fields should be rejected."""
        config = ReportConfig(
            fields=[
                FieldConfig(table="devices", field="id", alias=f"field_{i}")
                for i in range(MAX_FIELDS + 1)
            ],
            filters=[],
            grouping=[],
            sorting=[],
        )

        with pytest.raises(SecurityValidationError) as exc_info:
            validate_config_complexity(config)

        assert "Too many fields" in str(exc_info.value)

    def test_config_complexity_max_filters(self):
        """Configs with too many filters should be rejected."""
        config = ReportConfig(
            fields=[FieldConfig(table="devices", field="id")],
            filters=[
                FilterConfig(
                    table="devices",
                    field="device_type",
                    operator=FilterOperator.EQUALS,
                    value=f"type_{i}",
                )
                for i in range(MAX_FILTERS + 1)
            ],
            grouping=[],
            sorting=[],
        )

        with pytest.raises(SecurityValidationError) as exc_info:
            validate_config_complexity(config)

        assert "Too many filters" in str(exc_info.value)

    def test_config_complexity_max_grouping(self):
        """Configs with too many grouping fields should be rejected."""
        config = ReportConfig(
            fields=[FieldConfig(table="devices", field="id")],
            filters=[],
            grouping=[
                GroupingConfig(table="devices", field="device_type")
                for _ in range(MAX_GROUPING + 1)
            ],
            sorting=[],
        )

        with pytest.raises(SecurityValidationError) as exc_info:
            validate_config_complexity(config)

        assert "Too many grouping" in str(exc_info.value)

    def test_config_complexity_max_sorting(self):
        """Configs with too many sorting fields should be rejected."""
        config = ReportConfig(
            fields=[FieldConfig(table="devices", field="id")],
            filters=[],
            grouping=[],
            sorting=[
                SortingConfig(table="devices", field="device_type", direction=SortDirection.ASC)
                for _ in range(MAX_SORTING + 1)
            ],
        )

        with pytest.raises(SecurityValidationError) as exc_info:
            validate_config_complexity(config)

        assert "Too many sorting" in str(exc_info.value)

    def test_config_complexity_max_limit(self):
        """Configs with excessive limits should be rejected."""
        config = ReportConfig(
            fields=[FieldConfig(table="devices", field="id")],
            filters=[],
            grouping=[],
            sorting=[],
            limit=MAX_LIMIT + 1,
        )

        with pytest.raises(SecurityValidationError) as exc_info:
            validate_config_complexity(config)

        assert "Limit too high" in str(exc_info.value)


class TestPatternInjection:
    """Test LIKE pattern abuse prevention."""

    def test_like_pattern_sanitization(self):
        """Special LIKE characters should be escaped."""
        # Test escaping of special characters
        assert sanitize_like_pattern("test%") == "test\\%"
        assert sanitize_like_pattern("test_") == "test\\_"
        assert sanitize_like_pattern("test\\") == "test\\\\"
        assert sanitize_like_pattern("%_test_%") == "\\%\\_test\\_\\%"

    def test_overly_broad_patterns_rejected(self):
        """Patterns that are too broad should be rejected."""
        broad_patterns = [
            "%",
            "%%",
            "_",
            "__",
            "%_",
        ]

        for pattern in broad_patterns:
            with pytest.raises(SecurityValidationError) as exc_info:
                validate_filter_value(pattern, FilterOperator.CONTAINS)

            assert "too broad" in str(exc_info.value).lower()

    def test_reasonable_patterns_allowed(self):
        """Reasonable patterns should be allowed."""
        good_patterns = [
            "test",
            "abc123",
            "valid_pattern",
            "dev",
        ]

        for pattern in good_patterns:
            # Should not raise
            validate_filter_value(pattern, FilterOperator.CONTAINS)


class TestNumericValueValidation:
    """Test numeric value validation."""

    def test_extremely_large_numbers_rejected(self):
        """Extremely large numbers should be rejected."""
        with pytest.raises(SecurityValidationError) as exc_info:
            validate_filter_value(1e16, FilterOperator.EQUALS)

        assert "too large" in str(exc_info.value)

    def test_extremely_negative_numbers_rejected(self):
        """Extremely negative numbers should be rejected."""
        with pytest.raises(SecurityValidationError) as exc_info:
            validate_filter_value(-1e16, FilterOperator.EQUALS)

        assert "too large" in str(exc_info.value)

    def test_reasonable_numbers_allowed(self):
        """Reasonable numbers should be allowed."""
        reasonable_values = [
            0,
            1,
            -1,
            100,
            -100,
            1000000,
            -1000000,
            3.14159,
            -2.71828,
        ]

        for value in reasonable_values:
            # Should not raise
            validate_filter_value(value, FilterOperator.EQUALS)


class TestFullConfigValidation:
    """Test end-to-end config validation."""

    def test_valid_config_passes(self):
        """A valid configuration should pass all validation."""
        config = ReportConfig(
            fields=[
                FieldConfig(table="devices", field="device_type"),
                FieldConfig(table="devices", field="id", aggregation=AggregationFunction.COUNT),
            ],
            filters=[
                FilterConfig(
                    table="devices",
                    field="archived",
                    operator=FilterOperator.EQUALS,
                    value=False,
                ),
                FilterConfig(
                    table="devices",
                    field="device_name",
                    operator=FilterOperator.CONTAINS,
                    value="switch",
                    logic=LogicOperator.AND,
                ),
            ],
            grouping=[GroupingConfig(table="devices", field="device_type")],
            sorting=[SortingConfig(table="devices", field="device_type", direction=SortDirection.ASC)],
            limit=100,
        )

        # Should not raise
        validate_report_config(config)

    def test_malicious_config_rejected(self):
        """A malicious configuration should be rejected."""
        config = ReportConfig(
            fields=[FieldConfig(table="devices", field="id")],
            filters=[
                FilterConfig(
                    table="devices",
                    field="device_name",
                    operator=FilterOperator.EQUALS,
                    value="admin' OR '1'='1",  # SQL injection attempt
                ),
            ],
            grouping=[],
            sorting=[],
        )

        with pytest.raises(SecurityValidationError):
            validate_report_config(config)


class TestFieldNameValidation:
    """Test that only whitelisted fields are allowed."""

    def test_system_table_access_blocked(self):
        """Access to system tables should be blocked."""
        config = ReportConfig(
            fields=[
                FieldConfig(table="pg_user", field="usename"),  # Try to access postgres system table
            ],
            filters=[],
            grouping=[],
            sorting=[],
        )

        builder = QueryBuilder()
        with pytest.raises(QueryBuilderError) as exc_info:
            builder.build_query(config)

        assert "Invalid table" in str(exc_info.value)

    def test_information_schema_blocked(self):
        """Access to information_schema should be blocked."""
        config = ReportConfig(
            fields=[
                FieldConfig(table="information_schema", field="tables"),
            ],
            filters=[],
            grouping=[],
            sorting=[],
        )

        builder = QueryBuilder()
        with pytest.raises(QueryBuilderError):
            builder.build_query(config)

    def test_only_allowed_fields_accepted(self):
        """Only fields in the whitelist should be accepted."""
        # Valid fields from whitelist
        valid_config = ReportConfig(
            fields=[
                FieldConfig(table="devices", field="id"),
                FieldConfig(table="devices", field="device_type"),
                FieldConfig(table="devices", field="serial_number"),
            ],
            filters=[],
            grouping=[],
            sorting=[],
        )

        builder = QueryBuilder()
        sql, params = builder.build_query(valid_config)
        assert "devices.id" in sql
        assert "devices.device_type" in sql

        # Invalid field not in whitelist
        invalid_config = ReportConfig(
            fields=[
                FieldConfig(table="devices", field="nonexistent_field"),
            ],
            filters=[],
            grouping=[],
            sorting=[],
        )

        with pytest.raises(QueryBuilderError) as exc_info:
            builder.build_query(invalid_config)

        assert "Invalid field" in str(exc_info.value)


class TestNullValueHandling:
    """Test that null values are handled securely."""

    def test_null_filter_values_allowed(self):
        """Null filter values should be allowed for IS_NULL operators."""
        # Should not raise
        validate_filter_value(None, FilterOperator.IS_NULL)
        validate_filter_value(None, FilterOperator.IS_NOT_NULL)

    def test_null_in_equals_allowed(self):
        """Null values should be allowed in EQUALS filters."""
        # Should not raise (though may not make semantic sense)
        validate_filter_value(None, FilterOperator.EQUALS)


class TestBooleanValueHandling:
    """Test boolean value handling."""

    def test_boolean_values_allowed(self):
        """Boolean values should be allowed."""
        validate_filter_value(True, FilterOperator.EQUALS)
        validate_filter_value(False, FilterOperator.EQUALS)

    def test_boolean_in_config(self):
        """Boolean values should work in full config."""
        config = ReportConfig(
            fields=[FieldConfig(table="devices", field="archived")],
            filters=[
                FilterConfig(
                    table="devices",
                    field="archived",
                    operator=FilterOperator.EQUALS,
                    value=True,
                ),
            ],
            grouping=[],
            sorting=[],
        )

        # Should not raise
        validate_report_config(config)

        # Should generate valid SQL
        builder = QueryBuilder()
        sql, params = builder.build_query(config)
        assert "archived" in sql
        assert True in params.values()
