"""Pydantic schemas for custom report builder API request/response validation."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FilterOperator(str, Enum):
    """Available filter operators."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    BETWEEN = "between"
    IN = "in"
    NOT_IN = "not_in"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class LogicOperator(str, Enum):
    """Logical operators for combining filters."""

    AND = "AND"
    OR = "OR"


class AggregationFunction(str, Enum):
    """Available aggregation functions for grouping."""

    COUNT = "COUNT"
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"
    COUNT_DISTINCT = "COUNT_DISTINCT"


class SortDirection(str, Enum):
    """Sort direction options."""

    ASC = "ASC"
    DESC = "DESC"


class FieldType(str, Enum):
    """Field data types."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    UUID = "uuid"
    JSONB = "jsonb"


class ExportFormat(str, Enum):
    """Available export formats for report results."""

    JSON = "json"
    CSV = "csv"
    XLSX = "xlsx"


# ============================================
# Field and Filter Configuration
# ============================================


class FieldConfig(BaseModel):
    """Configuration for a selected field in the report."""

    table: str = Field(..., description="Source table name (e.g., 'devices', 'subscriptions')")
    field: str = Field(..., description="Field name from the table")
    alias: Optional[str] = Field(None, description="Display alias for the field")
    aggregation: Optional[AggregationFunction] = Field(
        None,
        description="Aggregation function to apply (if grouping is used)",
    )


class FilterConfig(BaseModel):
    """Configuration for a report filter."""

    field: str = Field(..., description="Field name to filter on")
    table: Optional[str] = Field(None, description="Table name (for disambiguation)")
    operator: FilterOperator = Field(..., description="Filter operator")
    value: Any = Field(..., description="Filter value (can be string, number, list, etc.)")
    logic: LogicOperator = Field(
        default=LogicOperator.AND,
        description="Logic operator to combine with next filter",
    )


class GroupingConfig(BaseModel):
    """Configuration for grouping results."""

    field: str = Field(..., description="Field name to group by")
    table: Optional[str] = Field(None, description="Table name (for disambiguation)")


class SortingConfig(BaseModel):
    """Configuration for sorting results."""

    field: str = Field(..., description="Field name to sort by")
    table: Optional[str] = Field(None, description="Table name (for disambiguation)")
    direction: SortDirection = Field(default=SortDirection.ASC, description="Sort direction")


class ReportConfig(BaseModel):
    """Complete report configuration."""

    fields: list[FieldConfig] = Field(
        default_factory=list,
        description="List of fields to include in the report",
    )
    filters: list[FilterConfig] = Field(
        default_factory=list,
        description="List of filters to apply",
    )
    grouping: list[GroupingConfig] = Field(
        default_factory=list,
        description="List of fields to group by",
    )
    sorting: list[SortingConfig] = Field(
        default_factory=list,
        description="List of sorting configurations",
    )
    limit: Optional[int] = Field(
        default=1000,
        description="Maximum number of rows to return",
        ge=1,
        le=10000,
    )


# ============================================
# Field Metadata
# ============================================


class FieldMetadata(BaseModel):
    """Metadata about an available field."""

    field_name: str = Field(..., description="Field name in the database")
    display_name: str = Field(..., description="Human-readable display name")
    data_type: FieldType = Field(..., description="Data type of the field")
    table: str = Field(..., description="Source table name")
    description: Optional[str] = Field(None, description="Field description")
    is_filterable: bool = Field(default=True, description="Whether field can be used in filters")
    is_groupable: bool = Field(default=True, description="Whether field can be grouped")
    is_sortable: bool = Field(default=True, description="Whether field can be sorted")
    available_operators: list[FilterOperator] = Field(
        default_factory=list,
        description="Available filter operators for this field",
    )


class TableMetadata(BaseModel):
    """Metadata about an available table."""

    table_name: str = Field(..., description="Table name in the database")
    display_name: str = Field(..., description="Human-readable display name")
    description: Optional[str] = Field(None, description="Table description")
    fields: list[FieldMetadata] = Field(
        default_factory=list,
        description="Available fields in this table",
    )


class FieldsResponse(BaseModel):
    """Response with available fields grouped by table."""

    tables: list[TableMetadata] = Field(
        default_factory=list,
        description="Available tables with their fields",
    )


# ============================================
# Report CRUD Requests/Responses
# ============================================


class CreateReportRequest(BaseModel):
    """Request to create a new custom report."""

    name: str = Field(..., description="Report template name", min_length=1, max_length=255)
    description: Optional[str] = Field(None, description="Optional report description")
    config: ReportConfig = Field(..., description="Report configuration")
    is_shared: bool = Field(default=False, description="Whether to share with other users")
    shared_with: list[str] = Field(
        default_factory=list,
        description="List of user IDs to share with",
    )


class UpdateReportRequest(BaseModel):
    """Request to update an existing report."""

    name: Optional[str] = Field(None, description="Updated report name", min_length=1, max_length=255)
    description: Optional[str] = None
    config: Optional[ReportConfig] = None
    is_shared: Optional[bool] = None
    shared_with: Optional[list[str]] = None


class ReportResponse(BaseModel):
    """Response with report details."""

    id: UUID
    name: str
    description: Optional[str] = None
    created_by: str
    config: ReportConfig
    is_shared: bool = False
    shared_with: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    last_executed_at: Optional[datetime] = None
    execution_count: int = 0

    class Config:
        from_attributes = True


class ReportListItem(BaseModel):
    """Summary item for report list."""

    id: UUID
    name: str
    description: Optional[str] = None
    created_by: str
    is_shared: bool = False
    created_at: datetime
    updated_at: datetime
    last_executed_at: Optional[datetime] = None
    execution_count: int = 0

    class Config:
        from_attributes = True


class ReportListResponse(BaseModel):
    """Response with list of reports."""

    reports: list[ReportListItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


# ============================================
# Report Execution
# ============================================


class ExecuteReportRequest(BaseModel):
    """Request to execute a report."""

    format: ExportFormat = Field(
        default=ExportFormat.JSON,
        description="Output format for results",
    )
    page: int = Field(default=1, description="Page number for pagination", ge=1)
    page_size: int = Field(default=100, description="Number of rows per page", ge=1, le=1000)


class ExecuteReportResponse(BaseModel):
    """Response from executing a report."""

    success: bool
    columns: list[str] = Field(default_factory=list, description="Column names in order")
    data: list[dict[str, Any]] = Field(default_factory=list, description="Result rows")
    total_rows: int = 0
    page: int = 1
    page_size: int = 100
    execution_time_ms: float = 0.0
    generated_sql: Optional[str] = Field(
        None,
        description="Generated SQL query (for debugging)",
    )
    errors: list[str] = Field(default_factory=list)
