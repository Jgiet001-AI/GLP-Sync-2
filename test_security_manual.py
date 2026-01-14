#!/usr/bin/env python3
"""Manual security validation tests for custom report builder.

This script demonstrates the security validation in action.
Run this to verify that malicious inputs are properly rejected.

Usage:
    python3 test_security_manual.py
"""

from src.glp.reports.query_builder import QueryBuilder, QueryBuilderError
from src.glp.reports.schemas import (
    FieldConfig,
    FilterConfig,
    FilterOperator,
    LogicOperator,
    ReportConfig,
)
from src.glp.reports.security import SecurityValidationError, validate_report_config


def test_case(name: str, test_func):
    """Run a test case and print results."""
    print(f"\n{'='*70}")
    print(f"TEST: {name}")
    print('='*70)
    try:
        test_func()
        print("❌ FAIL: Expected SecurityValidationError or QueryBuilderError, but succeeded")
        return False
    except (SecurityValidationError, QueryBuilderError) as e:
        print(f"✅ PASS: Correctly rejected with error:")
        print(f"   {type(e).__name__}: {str(e)}")
        return True
    except Exception as e:
        print(f"⚠️  UNEXPECTED ERROR: {type(e).__name__}: {str(e)}")
        return False


def test_sql_injection_filter_value():
    """Test SQL injection in filter value."""
    config = ReportConfig(
        fields=[FieldConfig(table="devices", field="id")],
        filters=[
            FilterConfig(
                table="devices",
                field="device_name",
                operator=FilterOperator.EQUALS,
                value="admin' OR '1'='1",  # Classic SQL injection
            )
        ],
        grouping=[],
        sorting=[],
    )
    validate_report_config(config)


def test_sql_injection_union():
    """Test UNION-based SQL injection."""
    config = ReportConfig(
        fields=[FieldConfig(table="devices", field="id")],
        filters=[
            FilterConfig(
                table="devices",
                field="device_name",
                operator=FilterOperator.EQUALS,
                value="1' UNION SELECT * FROM users--",
            )
        ],
        grouping=[],
        sorting=[],
    )
    validate_report_config(config)


def test_invalid_table_name():
    """Test accessing invalid table."""
    config = ReportConfig(
        fields=[FieldConfig(table="pg_user", field="usename")],
        filters=[],
        grouping=[],
        sorting=[],
    )
    builder = QueryBuilder()
    builder.build_query(config)


def test_invalid_field_name():
    """Test accessing invalid field."""
    config = ReportConfig(
        fields=[FieldConfig(table="devices", field="password_hash")],
        filters=[],
        grouping=[],
        sorting=[],
    )
    builder = QueryBuilder()
    builder.build_query(config)


def test_field_injection():
    """Test SQL injection via field name."""
    config = ReportConfig(
        fields=[FieldConfig(table="devices", field="id; DROP TABLE devices--")],
        filters=[],
        grouping=[],
        sorting=[],
    )
    builder = QueryBuilder()
    builder.build_query(config)


def test_table_injection():
    """Test SQL injection via table name."""
    config = ReportConfig(
        fields=[FieldConfig(table="devices; DROP TABLE users--", field="id")],
        filters=[],
        grouping=[],
        sorting=[],
    )
    builder = QueryBuilder()
    builder.build_query(config)


def test_too_many_fields():
    """Test config with too many fields."""
    config = ReportConfig(
        fields=[
            FieldConfig(table="devices", field="id", alias=f"field_{i}")
            for i in range(51)  # MAX_FIELDS is 50
        ],
        filters=[],
        grouping=[],
        sorting=[],
    )
    validate_report_config(config)


def test_too_many_filters():
    """Test config with too many filters."""
    config = ReportConfig(
        fields=[FieldConfig(table="devices", field="id")],
        filters=[
            FilterConfig(
                table="devices",
                field="device_type",
                operator=FilterOperator.EQUALS,
                value=f"type_{i}",
            )
            for i in range(26)  # MAX_FILTERS is 25
        ],
        grouping=[],
        sorting=[],
    )
    validate_report_config(config)


def test_oversized_string():
    """Test filter value that's too long."""
    config = ReportConfig(
        fields=[FieldConfig(table="devices", field="id")],
        filters=[
            FilterConfig(
                table="devices",
                field="device_name",
                operator=FilterOperator.EQUALS,
                value="x" * 501,  # MAX_STRING_VALUE_LENGTH is 500
            )
        ],
        grouping=[],
        sorting=[],
    )
    validate_report_config(config)


def test_broad_like_pattern():
    """Test overly broad LIKE pattern."""
    config = ReportConfig(
        fields=[FieldConfig(table="devices", field="id")],
        filters=[
            FilterConfig(
                table="devices",
                field="device_name",
                operator=FilterOperator.CONTAINS,
                value="%",  # Too broad - just a wildcard
            )
        ],
        grouping=[],
        sorting=[],
    )
    validate_report_config(config)


def test_comment_injection():
    """Test SQL comment injection."""
    config = ReportConfig(
        fields=[FieldConfig(table="devices", field="id")],
        filters=[
            FilterConfig(
                table="devices",
                field="device_name",
                operator=FilterOperator.CONTAINS,
                value="test--",  # SQL comment
            )
        ],
        grouping=[],
        sorting=[],
    )
    validate_report_config(config)


def test_delete_injection():
    """Test DELETE statement injection."""
    config = ReportConfig(
        fields=[FieldConfig(table="devices", field="id")],
        filters=[
            FilterConfig(
                table="devices",
                field="device_name",
                operator=FilterOperator.EQUALS,
                value="'; DELETE FROM devices WHERE '1'='1",
            )
        ],
        grouping=[],
        sorting=[],
    )
    validate_report_config(config)


def main():
    """Run all manual security tests."""
    print("\n" + "="*70)
    print("CUSTOM REPORT BUILDER - SECURITY VALIDATION TESTS")
    print("="*70)
    print("\nThis script tests that malicious inputs are properly rejected.")
    print("Each test should PASS by correctly rejecting the malicious input.\n")

    tests = [
        ("SQL Injection - OR 1=1", test_sql_injection_filter_value),
        ("SQL Injection - UNION", test_sql_injection_union),
        ("Invalid Table Access - pg_user", test_invalid_table_name),
        ("Invalid Field Access", test_invalid_field_name),
        ("SQL Injection via Field Name", test_field_injection),
        ("SQL Injection via Table Name", test_table_injection),
        ("DoS - Too Many Fields", test_too_many_fields),
        ("DoS - Too Many Filters", test_too_many_filters),
        ("DoS - Oversized String", test_oversized_string),
        ("Pattern Abuse - Overly Broad LIKE", test_broad_like_pattern),
        ("SQL Comment Injection", test_comment_injection),
        ("DELETE Statement Injection", test_delete_injection),
    ]

    results = []
    for name, test_func in tests:
        result = test_case(name, test_func)
        results.append((name, result))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    passed = sum(1 for _, result in results if result)
    total = len(results)
    print(f"\nPassed: {passed}/{total}")

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")

    if passed == total:
        print("\n🎉 All security validations working correctly!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed!")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
