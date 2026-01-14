"""Query builder for generating safe SQL from report configurations.

This module provides a QueryBuilder class that converts report configurations
into safe, parameterized SQL queries. It prevents SQL injection by:
- Validating all field names against a whitelist
- Using parameterized queries for all values
- Never concatenating user input directly into SQL

The QueryBuilder supports:
- Field selection with aggregations
- WHERE filters with AND/OR logic
- GROUP BY clauses
- ORDER BY clauses
- LIMIT and OFFSET for pagination
"""

import logging
from typing import Any

from .schemas import (
    AggregationFunction,
    FieldConfig,
    FilterConfig,
    FilterOperator,
    LogicOperator,
    ReportConfig,
    SortDirection,
)

logger = logging.getLogger(__name__)


# ============================================
# Field Whitelist - Only these fields can be queried
# ============================================

ALLOWED_FIELDS = {
    "devices": {
        # Primary identifiers
        "id",
        "mac_address",
        "serial_number",
        "part_number",
        # Device info
        "device_type",
        "model",
        "region",
        "archived",
        "device_name",
        "secondary_name",
        "assigned_state",
        "resource_type",
        # IDs
        "tenant_workspace_id",
        "application_id",
        "application_resource_uri",
        "dedicated_platform_id",
        # Location fields
        "location_id",
        "location_name",
        "location_city",
        "location_state",
        "location_country",
        "location_postal_code",
        "location_street_address",
        "location_latitude",
        "location_longitude",
        "location_source",
        # Timestamps
        "created_at",
        "updated_at",
        "synced_at",
    },
    "subscriptions": {
        # Primary identifiers
        "id",
        "key",
        "resource_type",
        # Subscription info
        "subscription_type",
        "subscription_status",
        "quantity",
        "available_quantity",
        # SKU details
        "sku",
        "sku_description",
        # Time range
        "start_time",
        "end_time",
        # Tier information
        "tier",
        "tier_description",
        # Classification
        "product_type",
        "is_eval",
        # Order references
        "contract",
        "quote",
        "po",
        "reseller_po",
        # Timestamps
        "created_at",
        "updated_at",
        "synced_at",
    },
}

ALLOWED_TABLES = set(ALLOWED_FIELDS.keys())


class QueryBuilderError(Exception):
    """Raised when query building fails due to invalid configuration."""

    pass


class QueryBuilder:
    """Generates safe SQL queries from report configurations.

    This class validates all inputs against a whitelist and uses parameterized
    queries to prevent SQL injection attacks.

    Example:
        config = ReportConfig(
            fields=[
                FieldConfig(table="devices", field="device_type"),
                FieldConfig(table="devices", field="id", aggregation=AggregationFunction.COUNT),
            ],
            filters=[
                FilterConfig(
                    field="archived",
                    table="devices",
                    operator=FilterOperator.EQUALS,
                    value=False,
                ),
            ],
            grouping=[GroupingConfig(field="device_type", table="devices")],
            limit=100,
        )

        builder = QueryBuilder()
        sql, params = builder.build_query(config)
    """

    def __init__(self):
        """Initialize the query builder."""
        self.param_counter = 0
        self.params: dict[str, Any] = {}

    def build_query(self, config: ReportConfig, offset: int = 0) -> tuple[str, dict[str, Any]]:
        """Build a complete SQL query from a report configuration.

        Args:
            config: The report configuration
            offset: Row offset for pagination (default: 0)

        Returns:
            A tuple of (sql_query, parameters_dict)

        Raises:
            QueryBuilderError: If the configuration is invalid
        """
        # Reset state for new query
        self.param_counter = 0
        self.params = {}

        # Validate configuration
        self._validate_config(config)

        # Build query parts
        select_clause = self._build_select(config)
        from_clause = self._build_from(config)
        where_clause = self._build_where(config)
        group_clause = self._build_group_by(config)
        order_clause = self._build_order_by(config)
        limit_clause = self._build_limit(config, offset)

        # Combine into final query
        query_parts = [select_clause, from_clause]

        if where_clause:
            query_parts.append(where_clause)

        if group_clause:
            query_parts.append(group_clause)

        if order_clause:
            query_parts.append(order_clause)

        if limit_clause:
            query_parts.append(limit_clause)

        sql = "\n".join(query_parts)

        logger.debug(f"Generated SQL: {sql}")
        logger.debug(f"Parameters: {self.params}")

        return sql, self.params

    def _validate_config(self, config: ReportConfig) -> None:
        """Validate that all fields and tables in the config are allowed.

        Args:
            config: The report configuration to validate

        Raises:
            QueryBuilderError: If any invalid fields or tables are found
        """
        # Validate fields
        for field_config in config.fields:
            if field_config.table not in ALLOWED_TABLES:
                raise QueryBuilderError(f"Invalid table: {field_config.table}")
            if field_config.field not in ALLOWED_FIELDS[field_config.table]:
                raise QueryBuilderError(
                    f"Invalid field: {field_config.table}.{field_config.field}"
                )

        # Validate filters
        for filter_config in config.filters:
            table = filter_config.table or self._infer_table(filter_config.field)
            if table not in ALLOWED_TABLES:
                raise QueryBuilderError(f"Invalid table in filter: {table}")
            if filter_config.field not in ALLOWED_FIELDS[table]:
                raise QueryBuilderError(f"Invalid field in filter: {table}.{filter_config.field}")

        # Validate grouping
        for group_config in config.grouping:
            table = group_config.table or self._infer_table(group_config.field)
            if table not in ALLOWED_TABLES:
                raise QueryBuilderError(f"Invalid table in grouping: {table}")
            if group_config.field not in ALLOWED_FIELDS[table]:
                raise QueryBuilderError(
                    f"Invalid field in grouping: {table}.{group_config.field}"
                )

        # Validate sorting
        for sort_config in config.sorting:
            table = sort_config.table or self._infer_table(sort_config.field)
            if table not in ALLOWED_TABLES:
                raise QueryBuilderError(f"Invalid table in sorting: {table}")
            if sort_config.field not in ALLOWED_FIELDS[table]:
                raise QueryBuilderError(f"Invalid field in sorting: {table}.{sort_config.field}")

    def _infer_table(self, field: str) -> str:
        """Infer which table a field belongs to.

        Args:
            field: The field name

        Returns:
            The table name

        Raises:
            QueryBuilderError: If the field is ambiguous or not found
        """
        tables_with_field = [
            table for table, fields in ALLOWED_FIELDS.items() if field in fields
        ]

        if len(tables_with_field) == 0:
            raise QueryBuilderError(f"Field not found in any table: {field}")
        if len(tables_with_field) > 1:
            raise QueryBuilderError(
                f"Ambiguous field '{field}' exists in multiple tables: {tables_with_field}. "
                "Please specify the table explicitly."
            )

        return tables_with_field[0]

    def _build_select(self, config: ReportConfig) -> str:
        """Build the SELECT clause.

        Args:
            config: The report configuration

        Returns:
            The SELECT clause
        """
        if not config.fields:
            # If no fields specified, select all from the first table
            # Default to devices if no filters specify otherwise
            table = "devices"
            if config.filters:
                table = config.filters[0].table or self._infer_table(config.filters[0].field)
            return f"SELECT * FROM {table}"

        select_items = []
        for field_config in config.fields:
            table = field_config.table
            field = field_config.field
            alias = field_config.alias

            # Build the field expression
            if field_config.aggregation:
                # Apply aggregation function
                agg = field_config.aggregation.value
                if agg == "COUNT_DISTINCT":
                    expr = f"COUNT(DISTINCT {table}.{field})"
                else:
                    expr = f"{agg}({table}.{field})"
            else:
                expr = f"{table}.{field}"

            # Add alias if specified
            if alias:
                expr += f' AS "{alias}"'

            select_items.append(expr)

        return "SELECT " + ", ".join(select_items)

    def _build_from(self, config: ReportConfig) -> str:
        """Build the FROM clause.

        Args:
            config: The report configuration

        Returns:
            The FROM clause
        """
        # Determine which tables are needed
        tables = set()

        for field_config in config.fields:
            tables.add(field_config.table)

        for filter_config in config.filters:
            table = filter_config.table or self._infer_table(filter_config.field)
            tables.add(table)

        if not tables:
            # Default to devices if no tables specified
            tables.add("devices")

        if len(tables) == 1:
            # Single table query
            return f"FROM {list(tables)[0]}"
        else:
            # Multi-table query - for now, we only support single table
            # Future enhancement: support JOINs
            raise QueryBuilderError(
                "Multi-table queries are not yet supported. "
                "Please select fields from only one table."
            )

    def _build_where(self, config: ReportConfig) -> str:
        """Build the WHERE clause from filters.

        Args:
            config: The report configuration

        Returns:
            The WHERE clause, or empty string if no filters
        """
        if not config.filters:
            return ""

        conditions = []
        for i, filter_config in enumerate(config.filters):
            condition = self._build_filter_condition(filter_config)
            conditions.append(condition)

            # Add logic operator between conditions (except for the last one)
            if i < len(config.filters) - 1:
                logic = filter_config.logic.value
                conditions.append(logic)

        return "WHERE " + " ".join(conditions)

    def _build_filter_condition(self, filter_config: FilterConfig) -> str:
        """Build a single filter condition.

        Args:
            filter_config: The filter configuration

        Returns:
            The filter condition as SQL
        """
        table = filter_config.table or self._infer_table(filter_config.field)
        field = f"{table}.{filter_config.field}"
        operator = filter_config.operator
        value = filter_config.value

        # Handle operators that don't need a parameter
        if operator == FilterOperator.IS_NULL:
            return f"{field} IS NULL"
        elif operator == FilterOperator.IS_NOT_NULL:
            return f"{field} IS NOT NULL"

        # For all other operators, use parameterized queries
        param_name = self._add_param(value)

        if operator == FilterOperator.EQUALS:
            return f"{field} = ${param_name}"
        elif operator == FilterOperator.NOT_EQUALS:
            return f"{field} != ${param_name}"
        elif operator == FilterOperator.GT:
            return f"{field} > ${param_name}"
        elif operator == FilterOperator.GTE:
            return f"{field} >= ${param_name}"
        elif operator == FilterOperator.LT:
            return f"{field} < ${param_name}"
        elif operator == FilterOperator.LTE:
            return f"{field} <= ${param_name}"
        elif operator == FilterOperator.CONTAINS:
            # Wrap value with % for ILIKE pattern matching
            self.params[param_name] = f"%{value}%"
            return f"{field} ILIKE ${param_name}"
        elif operator == FilterOperator.NOT_CONTAINS:
            self.params[param_name] = f"%{value}%"
            return f"{field} NOT ILIKE ${param_name}"
        elif operator == FilterOperator.STARTS_WITH:
            self.params[param_name] = f"{value}%"
            return f"{field} ILIKE ${param_name}"
        elif operator == FilterOperator.ENDS_WITH:
            self.params[param_name] = f"%{value}"
            return f"{field} ILIKE ${param_name}"
        elif operator == FilterOperator.IN:
            # For IN operator, value should be a list
            if not isinstance(value, list):
                raise QueryBuilderError(f"IN operator requires a list value, got: {type(value)}")
            return f"{field} = ANY(${param_name})"
        elif operator == FilterOperator.NOT_IN:
            if not isinstance(value, list):
                raise QueryBuilderError(
                    f"NOT_IN operator requires a list value, got: {type(value)}"
                )
            return f"{field} != ALL(${param_name})"
        elif operator == FilterOperator.BETWEEN:
            # For BETWEEN, value should be a list of [min, max]
            if not isinstance(value, list) or len(value) != 2:
                raise QueryBuilderError(
                    f"BETWEEN operator requires a list of [min, max], got: {value}"
                )
            param_min = self._add_param(value[0])
            param_max = self._add_param(value[1])
            return f"{field} BETWEEN ${param_min} AND ${param_max}"
        else:
            raise QueryBuilderError(f"Unsupported operator: {operator}")

    def _build_group_by(self, config: ReportConfig) -> str:
        """Build the GROUP BY clause.

        Args:
            config: The report configuration

        Returns:
            The GROUP BY clause, or empty string if no grouping
        """
        if not config.grouping:
            return ""

        group_fields = []
        for group_config in config.grouping:
            table = group_config.table or self._infer_table(group_config.field)
            field = f"{table}.{group_config.field}"
            group_fields.append(field)

        return "GROUP BY " + ", ".join(group_fields)

    def _build_order_by(self, config: ReportConfig) -> str:
        """Build the ORDER BY clause.

        Args:
            config: The report configuration

        Returns:
            The ORDER BY clause, or empty string if no sorting
        """
        if not config.sorting:
            return ""

        order_items = []
        for sort_config in config.sorting:
            table = sort_config.table or self._infer_table(sort_config.field)
            field = f"{table}.{sort_config.field}"
            direction = sort_config.direction.value
            order_items.append(f"{field} {direction}")

        return "ORDER BY " + ", ".join(order_items)

    def _build_limit(self, config: ReportConfig, offset: int) -> str:
        """Build the LIMIT and OFFSET clause.

        Args:
            config: The report configuration
            offset: The row offset for pagination

        Returns:
            The LIMIT/OFFSET clause
        """
        limit = config.limit or 1000  # Default limit

        if offset > 0:
            return f"LIMIT {limit} OFFSET {offset}"
        else:
            return f"LIMIT {limit}"

    def _add_param(self, value: Any) -> str:
        """Add a parameter to the params dict and return its placeholder name.

        Args:
            value: The parameter value

        Returns:
            The parameter placeholder name (e.g., "param_1")
        """
        self.param_counter += 1
        param_name = f"param_{self.param_counter}"
        self.params[param_name] = value
        return param_name
