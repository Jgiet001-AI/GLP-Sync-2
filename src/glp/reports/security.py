"""Security validation for custom report builder.

This module provides defense-in-depth security measures for the report builder:
- Input size limits to prevent DoS attacks
- SQL injection pattern detection (additional layer beyond parameterization)
- Value sanitization for pattern matching operators
- Configuration complexity limits
- Rate limiting support

These measures complement the core security in QueryBuilder:
- Field whitelisting (ALLOWED_FIELDS)
- Table whitelisting (ALLOWED_TABLES)
- Parameterized queries ($param_N placeholders)
"""

import logging
import re
from typing import Any

from .schemas import FilterOperator, ReportConfig

logger = logging.getLogger(__name__)

# ============================================
# Security Limits
# ============================================

# Maximum sizes to prevent DoS attacks
MAX_CONFIG_SIZE_BYTES = 100_000  # 100KB max for report config JSON
MAX_FILTER_VALUE_LENGTH = 1_000  # 1KB max for a single filter value
MAX_ARRAY_LENGTH = 100  # Max items in IN/NOT_IN arrays
MAX_STRING_VALUE_LENGTH = 500  # Max length for string filter values

# Complexity limits to prevent expensive queries
MAX_FIELDS = 50  # Max number of fields to select
MAX_FILTERS = 25  # Max number of filter conditions
MAX_GROUPING = 10  # Max number of grouping fields
MAX_SORTING = 10  # Max number of sorting fields
MAX_LIMIT = 10_000  # Max rows to return (hard cap)

# SQL injection patterns (defense in depth - parameterized queries are primary defense)
# These are blocked in filter values as an additional security layer
SQL_INJECTION_PATTERNS = [
    r"(\b(UNION|SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE)\b)",
    r"(--|;|\/\*|\*\/)",  # SQL comments and statement terminators
    r"(\bOR\b.*=.*)",  # Classic OR 1=1 patterns
    r"(\bAND\b.*=.*\bOR\b)",  # AND/OR manipulation
    r"(xp_|sp_|exec\s*\()",  # Stored procedure calls
    r"(\bINTO\b\s+(OUTFILE|DUMPFILE))",  # File operations
]

# Compile patterns for performance
INJECTION_REGEX = re.compile(
    "|".join(SQL_INJECTION_PATTERNS),
    re.IGNORECASE | re.MULTILINE
)


class SecurityValidationError(Exception):
    """Raised when security validation fails."""
    pass


# ============================================
# Validation Functions
# ============================================


def validate_config_size(config_json: str) -> None:
    """Validate that the configuration size is within limits.

    Args:
        config_json: JSON string of the report configuration

    Raises:
        SecurityValidationError: If config is too large
    """
    size_bytes = len(config_json.encode('utf-8'))
    if size_bytes > MAX_CONFIG_SIZE_BYTES:
        raise SecurityValidationError(
            f"Configuration too large: {size_bytes} bytes "
            f"(max: {MAX_CONFIG_SIZE_BYTES} bytes)"
        )


def validate_config_complexity(config: ReportConfig) -> None:
    """Validate that the configuration complexity is within limits.

    Prevents expensive queries that could cause DoS.

    Args:
        config: The report configuration

    Raises:
        SecurityValidationError: If config exceeds complexity limits
    """
    if len(config.fields) > MAX_FIELDS:
        raise SecurityValidationError(
            f"Too many fields: {len(config.fields)} (max: {MAX_FIELDS})"
        )

    if len(config.filters) > MAX_FILTERS:
        raise SecurityValidationError(
            f"Too many filters: {len(config.filters)} (max: {MAX_FILTERS})"
        )

    if len(config.grouping) > MAX_GROUPING:
        raise SecurityValidationError(
            f"Too many grouping fields: {len(config.grouping)} (max: {MAX_GROUPING})"
        )

    if len(config.sorting) > MAX_SORTING:
        raise SecurityValidationError(
            f"Too many sorting fields: {len(config.sorting)} (max: {MAX_SORTING})"
        )

    if config.limit and config.limit > MAX_LIMIT:
        raise SecurityValidationError(
            f"Limit too high: {config.limit} (max: {MAX_LIMIT})"
        )


def validate_filter_value(value: Any, operator: FilterOperator) -> None:
    """Validate a filter value for security issues.

    Checks for:
    - SQL injection patterns (defense in depth)
    - Excessive size
    - Array length limits
    - Pattern abuse

    Args:
        value: The filter value
        operator: The filter operator being used

    Raises:
        SecurityValidationError: If value fails validation
    """
    if value is None:
        return  # Null values are OK

    # Check string values
    if isinstance(value, str):
        # Check length
        if len(value) > MAX_STRING_VALUE_LENGTH:
            raise SecurityValidationError(
                f"Filter value too long: {len(value)} chars "
                f"(max: {MAX_STRING_VALUE_LENGTH})"
            )

        # Check for SQL injection patterns (defense in depth)
        if INJECTION_REGEX.search(value):
            logger.warning(f"Potential SQL injection attempt detected: {value[:100]}")
            raise SecurityValidationError(
                "Filter value contains disallowed SQL keywords or patterns"
            )

        # For pattern operators, check for wildcard abuse
        if operator in [FilterOperator.CONTAINS, FilterOperator.STARTS_WITH, FilterOperator.ENDS_WITH]:
            # Pattern like "%" or "%%" can be expensive
            cleaned = value.replace('%', '').replace('_', '')
            if len(cleaned) < 2:
                raise SecurityValidationError(
                    f"Pattern too broad for {operator.value} operator. "
                    "Provide at least 2 non-wildcard characters."
                )

    # Check array values (for IN/NOT_IN/BETWEEN)
    elif isinstance(value, list):
        if len(value) > MAX_ARRAY_LENGTH:
            raise SecurityValidationError(
                f"Array too long: {len(value)} items (max: {MAX_ARRAY_LENGTH})"
            )

        # Validate each item in the array
        for item in value:
            if isinstance(item, str) and len(item) > MAX_STRING_VALUE_LENGTH:
                raise SecurityValidationError(
                    f"Array item too long: {len(item)} chars "
                    f"(max: {MAX_STRING_VALUE_LENGTH})"
                )
            if isinstance(item, str) and INJECTION_REGEX.search(item):
                raise SecurityValidationError(
                    "Array item contains disallowed SQL keywords or patterns"
                )

    # Check numeric values (prevent extreme values that could cause issues)
    elif isinstance(value, (int, float)):
        # Check for extremely large numbers that could cause overflow
        if abs(value) > 1e15:
            raise SecurityValidationError(
                f"Numeric value too large: {value} (max: ±1e15)"
            )


def validate_report_config(config: ReportConfig, config_json: str = None) -> None:
    """Comprehensive validation of a report configuration.

    Performs all security checks:
    - Config size validation
    - Complexity limits
    - Filter value validation

    Args:
        config: The report configuration to validate
        config_json: Optional JSON string representation for size validation

    Raises:
        SecurityValidationError: If any validation fails
    """
    # Validate config size if JSON provided
    if config_json:
        validate_config_size(config_json)

    # Validate complexity
    validate_config_complexity(config)

    # Validate all filter values
    for filter_config in config.filters:
        validate_filter_value(filter_config.value, filter_config.operator)

    logger.debug(
        f"Security validation passed: {len(config.fields)} fields, "
        f"{len(config.filters)} filters, {len(config.grouping)} grouping, "
        f"{len(config.sorting)} sorting"
    )


def sanitize_like_pattern(value: str) -> str:
    """Sanitize a value for use in LIKE/ILIKE patterns.

    Escapes special characters that have meaning in SQL LIKE patterns.

    Args:
        value: The value to sanitize

    Returns:
        Sanitized value with LIKE special chars escaped
    """
    # Escape backslash first (escape character)
    value = value.replace('\\', '\\\\')
    # Escape percent and underscore (LIKE wildcards)
    value = value.replace('%', '\\%')
    value = value.replace('_', '\\_')
    return value


# ============================================
# Rate Limiting Support
# ============================================

# Rate limit configuration for report execution
# These can be overridden by environment variables in production
REPORT_EXEC_RATE_LIMIT = 10  # Max executions per minute per user
REPORT_EXEC_WINDOW_SECONDS = 60  # 1 minute window


def get_rate_limit_key(user_id: str) -> str:
    """Get Redis key for rate limiting report execution.

    Args:
        user_id: User identifier (or "api-user" if no auth)

    Returns:
        Redis key for this user's rate limit
    """
    import time
    bucket = int(time.time() // REPORT_EXEC_WINDOW_SECONDS)
    return f"rate_limit:report_exec:{user_id}:{bucket}"
