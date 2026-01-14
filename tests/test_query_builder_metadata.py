"""Tests for query builder field metadata service."""

import pytest

from src.glp.reports.query_builder import (
    ALLOWED_FIELDS,
    get_available_fields,
    get_available_tables,
    get_operators_for_field_type,
)
from src.glp.reports.schemas import FieldType, FilterOperator


def test_get_operators_for_field_type():
    """Test getting operators for different field types."""
    # String fields should have text operators
    string_ops = get_operators_for_field_type(FieldType.STRING)
    assert FilterOperator.CONTAINS in string_ops
    assert FilterOperator.STARTS_WITH in string_ops
    assert FilterOperator.EQUALS in string_ops

    # Integer fields should have numeric operators
    int_ops = get_operators_for_field_type(FieldType.INTEGER)
    assert FilterOperator.GT in int_ops
    assert FilterOperator.LT in int_ops
    assert FilterOperator.BETWEEN in int_ops
    assert FilterOperator.CONTAINS not in int_ops

    # Boolean fields should have limited operators
    bool_ops = get_operators_for_field_type(FieldType.BOOLEAN)
    assert FilterOperator.EQUALS in bool_ops
    assert FilterOperator.GT not in bool_ops
    assert FilterOperator.CONTAINS not in bool_ops


def test_get_available_fields_devices():
    """Test getting fields for devices table."""
    fields = get_available_fields("devices")

    # Should return all device fields
    assert len(fields) == len(ALLOWED_FIELDS["devices"])

    # Check a few specific fields
    field_names = [f.field_name for f in fields]
    assert "id" in field_names
    assert "device_type" in field_names
    assert "mac_address" in field_names
    assert "serial_number" in field_names

    # Check metadata is complete
    for field in fields:
        assert field.field_name
        assert field.display_name
        assert field.data_type
        assert field.table == "devices"
        assert isinstance(field.is_filterable, bool)
        assert isinstance(field.is_groupable, bool)
        assert isinstance(field.is_sortable, bool)
        assert len(field.available_operators) > 0


def test_get_available_fields_subscriptions():
    """Test getting fields for subscriptions table."""
    fields = get_available_fields("subscriptions")

    # Should return all subscription fields
    assert len(fields) == len(ALLOWED_FIELDS["subscriptions"])

    # Check a few specific fields
    field_names = [f.field_name for f in fields]
    assert "id" in field_names
    assert "subscription_type" in field_names
    assert "sku" in field_names
    assert "quantity" in field_names


def test_get_available_fields_invalid_table():
    """Test getting fields for invalid table raises error."""
    from src.glp.reports.query_builder import QueryBuilderError

    with pytest.raises(QueryBuilderError, match="Invalid table"):
        get_available_fields("invalid_table")


def test_get_available_tables():
    """Test getting all available tables."""
    tables = get_available_tables()

    # Should have both devices and subscriptions
    assert len(tables) >= 2
    table_names = [t.table_name for t in tables]
    assert "devices" in table_names
    assert "subscriptions" in table_names

    # Each table should have fields
    for table in tables:
        assert table.table_name
        assert table.display_name
        assert len(table.fields) > 0

    # Devices table should have proper metadata
    devices_table = next(t for t in tables if t.table_name == "devices")
    assert devices_table.display_name == "Devices"
    assert "Device inventory" in devices_table.description


def test_field_operators_match_type():
    """Test that fields have appropriate operators for their type."""
    fields = get_available_fields("devices")

    # Find a string field
    string_field = next(f for f in fields if f.data_type == FieldType.STRING)
    assert FilterOperator.CONTAINS in string_field.available_operators

    # Find an integer/float field
    numeric_fields = [f for f in fields if f.data_type in [FieldType.INTEGER, FieldType.FLOAT]]
    if numeric_fields:
        numeric_field = numeric_fields[0]
        assert FilterOperator.GT in numeric_field.available_operators
        assert FilterOperator.CONTAINS not in numeric_field.available_operators

    # Find a boolean field
    bool_fields = [f for f in fields if f.data_type == FieldType.BOOLEAN]
    if bool_fields:
        bool_field = bool_fields[0]
        assert FilterOperator.EQUALS in bool_field.available_operators
        assert FilterOperator.GT not in bool_field.available_operators
