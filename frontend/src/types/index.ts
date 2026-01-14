// API Types

// API Error Response from backend
// Handles both FastAPI standard errors (detail) and GLPError.to_dict() (message)
export interface ApiErrorResponse {
  detail?: string        // FastAPI standard error field
  message?: string       // GLPError.to_dict() field
  status_code?: number
  errors?: ValidationError[]
  recoverable?: boolean
  error_type?: string
  code?: string          // GLPError error code
}

// Custom Error class for structured API error handling
export class ApiError extends Error {
  status: number
  detail: string
  errors?: ValidationError[]
  recoverable: boolean
  errorType?: string
  code?: string

  constructor(response: ApiErrorResponse, status: number) {
    // Handle both FastAPI 'detail' and GLPError 'message' fields
    const errorMessage = response.detail || response.message || 'An error occurred'
    super(errorMessage)
    this.name = 'ApiError'
    this.status = status
    this.detail = errorMessage
    this.errors = response.errors
    this.recoverable = response.recoverable ?? false
    this.errorType = response.error_type
    this.code = response.code
  }

  get isValidationError(): boolean {
    return this.status === 400 || this.status === 422
  }

  get isAuthError(): boolean {
    return this.status === 401 || this.status === 403
  }

  get isNotFound(): boolean {
    return this.status === 404
  }

  get isServerError(): boolean {
    return this.status >= 500
  }
}

export interface DeviceAssignment {
  serial_number: string
  mac_address: string | null
  row_number: number
  device_id: string | null
  device_type: string | null
  model: string | null
  region: string | null
  status: 'not_in_db' | 'fully_assigned' | 'partial' | 'unassigned'
  current_subscription_id: string | null
  current_subscription_key: string | null
  current_application_id: string | null
  current_tags: Record<string, string>
  selected_subscription_id: string | null
  selected_application_id: string | null
  selected_region: string | null  // Region code (e.g., "us-west") - required with application_id
  selected_tags: Record<string, string>
  needs_creation: boolean
  needs_subscription_patch: boolean
  needs_application_patch: boolean
  needs_tag_patch: boolean
}

export interface ValidationError {
  row_number: number
  field: string
  message: string
}

export interface ProcessResponse {
  success: boolean
  devices: DeviceAssignment[]
  errors: ValidationError[]
  warnings: string[]
  total_rows: number
  devices_found: number
  devices_not_found: number
  fully_assigned: number
  partially_assigned: number
  unassigned: number
}

export interface Subscription {
  id: string
  key: string
  subscription_type: string
  tier: string
  tier_description: string | null
  quantity: number
  available_quantity: number
  start_time: string | null
  end_time: string | null
  days_remaining: number | null
  compatible_device_types: string[]
}

export interface Region {
  application_id: string
  region: string
  display_name: string
}

export interface Tag {
  key: string
  value: string
}

export interface OptionsResponse {
  subscriptions: Subscription[]
  regions: Region[]
  existing_tags: Tag[]
}

export interface DeviceSelection {
  serial_number: string
  device_id: string | null
  device_type: string | null
  mac_address: string | null
  // Current assignments (from database) - needed for gap detection
  current_subscription_id: string | null
  current_application_id: string | null
  current_tags: Record<string, string>
  // User selections
  selected_subscription_id: string | null
  selected_application_id: string | null
  selected_region: string | null  // Region code (e.g., "us-west") - required with application_id
  selected_tags: Record<string, string>
}

export interface ApplyRequest {
  devices: DeviceSelection[]
  wait_for_completion: boolean
}

export interface OperationResult {
  success: boolean
  operation_type: string
  device_ids: string[]
  device_serials: string[]
  error: string | null
  operation_url: string | null
}

export interface ApplyResponse {
  success: boolean
  operations: OperationResult[]
  devices_created: number
  subscriptions_assigned: number
  applications_assigned: number
  tags_updated: number
  errors: number
}

export interface ReportResponse {
  generated_at: string
  summary: {
    total_operations: number
    successful_operations: number
    failed_operations: number
  }
  breakdown: {
    devices_created: number
    subscriptions_assigned: number
    applications_assigned: number
    tags_updated: number
  }
  sync: {
    success: boolean
    devices_synced: number
    subscriptions_synced: number
  } | null
  operations: OperationResult[]
  errors: string[]
}

// Custom Report Builder Types

// Filter operators for building report filters
export type FilterOperator =
  | 'equals'
  | 'not_equals'
  | 'contains'
  | 'not_contains'
  | 'starts_with'
  | 'ends_with'
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'between'
  | 'in'
  | 'not_in'
  | 'is_null'
  | 'is_not_null'

// Logical operators for combining filters
export type LogicOperator = 'AND' | 'OR'

// Aggregation functions for grouped fields
export type AggregationFunction =
  | 'COUNT'
  | 'SUM'
  | 'AVG'
  | 'MIN'
  | 'MAX'
  | 'COUNT_DISTINCT'

// Sort direction
export type SortDirection = 'ASC' | 'DESC'

// Field data types
export type FieldType =
  | 'string'
  | 'integer'
  | 'float'
  | 'boolean'
  | 'date'
  | 'datetime'
  | 'uuid'
  | 'jsonb'

// Export format options
export type ExportFormat = 'json' | 'csv' | 'xlsx'

// Configuration for a selected field in the report
export interface FieldConfig {
  table: string
  field: string
  alias: string | null
  aggregation: AggregationFunction | null
}

// Configuration for a report filter
export interface FilterConfig {
  field: string
  table: string | null
  operator: FilterOperator
  value: any
  logic: LogicOperator
}

// Configuration for grouping results
export interface GroupingConfig {
  field: string
  table: string | null
}

// Configuration for sorting results
export interface SortingConfig {
  field: string
  table: string | null
  direction: SortDirection
}

// Complete report configuration
export interface ReportConfig {
  fields: FieldConfig[]
  filters: FilterConfig[]
  grouping: GroupingConfig[]
  sorting: SortingConfig[]
  limit: number | null
}

// Metadata about an available field
export interface FieldMetadata {
  field_name: string
  display_name: string
  data_type: FieldType
  table: string
  description: string | null
  is_filterable: boolean
  is_groupable: boolean
  is_sortable: boolean
  available_operators: FilterOperator[]
}

// Metadata about an available table
export interface TableMetadata {
  table_name: string
  display_name: string
  description: string | null
  fields: FieldMetadata[]
}

// Response with available fields grouped by table
export interface FieldsResponse {
  tables: TableMetadata[]
}

// Request to create a new custom report
export interface CreateReportRequest {
  name: string
  description: string | null
  config: ReportConfig
  is_shared: boolean
  shared_with: string[]
}

// Request to update an existing custom report
export interface UpdateReportRequest {
  name?: string
  description?: string | null
  config?: ReportConfig
  is_shared?: boolean
  shared_with?: string[]
}

// Response with custom report details (prefixed to avoid conflict with assignment ReportResponse)
export interface CustomReportResponse {
  id: string
  name: string
  description: string | null
  created_by: string
  config: ReportConfig
  is_shared: boolean
  shared_with: string[]
  created_at: string
  updated_at: string
  last_executed_at: string | null
  execution_count: number
}

// Summary item for custom report list
export interface CustomReportListItem {
  id: string
  name: string
  description: string | null
  created_by: string
  is_shared: boolean
  created_at: string
  updated_at: string
  last_executed_at: string | null
  execution_count: number
}

// Response with list of custom reports
export interface CustomReportListResponse {
  reports: CustomReportListItem[]
  total: number
  page: number
  page_size: number
}

// Request to execute a custom report
export interface ExecuteReportRequest {
  format: ExportFormat
  page: number
  page_size: number
}

// Response from executing a custom report
export interface ExecuteReportResponse {
  success: boolean
  columns: string[]
  data: Record<string, any>[]
  total_rows: number
  page: number
  page_size: number
  execution_time_ms: number
  generated_sql: string | null
  errors: string[]
}

// UI State Types

export type WorkflowStep = 'upload' | 'review' | 'assign' | 'apply' | 'report'

// Per-type assignment configuration
export interface TypeAssignmentConfig {
  deviceType: string
  deviceCount: number
  selectedSubscriptionId: string | null
  selectedTags: Record<string, string>
  pendingTagKey: string
  pendingTagValue: string
}

export interface AssignmentState {
  devices: DeviceAssignment[]
  selectedDevices: Set<string> // serial numbers
  options: OptionsResponse | null
  applyResult: ApplyResponse | null
  report: ReportResponse | null
}

// Dashboard Types

export interface DeviceStats {
  total: number
  assigned: number
  unassigned: number
  archived: number
}

export interface DeviceTypeBreakdown {
  device_type: string
  count: number
  assigned: number
  unassigned: number
}

export interface RegionBreakdown {
  region: string
  count: number
}

export interface SubscriptionStats {
  total: number
  active: number
  expired: number
  expiring_soon: number
  total_licenses: number
  available_licenses: number
  utilization_percent: number
}

export interface SubscriptionTypeBreakdown {
  subscription_type: string
  count: number
  total_quantity: number
  available_quantity: number
}

export interface ExpiringItem {
  id: string
  identifier: string
  item_type: 'device' | 'subscription'
  sub_type: string | null
  end_time: string
  days_remaining: number
}

export interface SyncHistoryItem {
  id: number
  resource_type: string
  started_at: string
  completed_at: string | null
  status: string
  records_fetched: number
  records_inserted: number
  records_updated: number
  records_errors: number
  duration_ms: number | null
}

export interface DashboardResponse {
  generated_at: string
  device_stats: DeviceStats
  device_by_type: DeviceTypeBreakdown[]
  device_by_region: RegionBreakdown[]
  subscription_stats: SubscriptionStats
  subscription_by_type: SubscriptionTypeBreakdown[]
  expiring_items: ExpiringItem[]
  sync_history: SyncHistoryItem[]
  last_sync_at: string | null
  last_sync_status: string | null
}

// Device List Types

export interface DeviceListItem {
  id: string
  serial_number: string
  mac_address: string | null
  device_type: string | null
  model: string | null
  region: string | null
  device_name: string | null
  assigned_state: string | null
  location_city: string | null
  location_country: string | null
  subscription_key: string | null
  subscription_type: string | null
  subscription_end: string | null
  updated_at: string | null
  // GreenLake tags
  tags: Record<string, string>
  // Aruba Central fields - Core
  central_status: string | null
  central_device_name: string | null
  central_device_type: string | null
  // Aruba Central fields - Hardware
  central_model: string | null
  central_part_number: string | null
  // Aruba Central fields - Connectivity
  central_ipv4: string | null
  central_ipv6: string | null
  central_software_version: string | null
  central_uptime_millis: number | null
  central_last_seen_at: string | null
  // Aruba Central fields - Deployment
  central_deployment: string | null
  central_device_role: string | null
  central_device_function: string | null
  // Aruba Central fields - Location
  central_site_name: string | null
  central_cluster_name: string | null
  // Aruba Central fields - Config
  central_config_status: string | null
  central_config_last_modified_at: string | null
  // Platform presence flags
  in_central: boolean
  in_greenlake: boolean
}

export interface DeviceListResponse {
  items: DeviceListItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// Subscription List Types

export interface SubscriptionListItem {
  id: string
  key: string
  subscription_type: string | null
  subscription_status: string | null
  tier: string | null
  sku: string | null
  quantity: number
  available_quantity: number
  used_quantity: number
  start_time: string | null
  end_time: string | null
  days_remaining: number | null
  is_eval: boolean
  device_count: number
}

export interface SubscriptionListResponse {
  items: SubscriptionListItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// Filter Options

export interface FilterOptions {
  device_types: string[]
  regions: string[]
  subscription_types: string[]
  subscription_statuses: string[]
}

// Add Devices to GreenLake Types

export interface AddDeviceItem {
  serial_number: string
  mac_address: string
  device_type: string
  part_number?: string
  tags?: Record<string, string>
}

export interface AddDevicesRequest {
  devices: AddDeviceItem[]
  wait_for_completion: boolean
}

export interface AddDeviceResult {
  serial_number: string
  success: boolean
  device_id: string | null
  error: string | null
  operation_url: string | null
}

export interface AddDevicesResponse {
  success: boolean
  devices_added: number
  devices_failed: number
  results: AddDeviceResult[]
  errors: string[]
}
