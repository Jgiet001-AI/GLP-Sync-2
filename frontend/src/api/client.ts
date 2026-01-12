import axios, { AxiosError } from 'axios'
import type {
  AddDevicesRequest,
  AddDevicesResponse,
  ApplyRequest,
  ApplyResponse,
  DashboardResponse,
  DeviceListResponse,
  FilterOptions,
  OptionsResponse,
  ProcessResponse,
  ReportResponse,
  SubscriptionListResponse,
} from '../types'
import { ApiError, ApiErrorResponse } from '../types'

// Get API key from environment (Vite uses VITE_ prefix)
const API_KEY = import.meta.env.VITE_API_KEY || ''

// Create base headers with optional API key
const createHeaders = () => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (API_KEY) {
    headers['X-API-Key'] = API_KEY
  }
  return headers
}

const api = axios.create({
  baseURL: '/api/assignment',
  headers: createHeaders(),
})

const dashboardApi = axios.create({
  baseURL: '/api/dashboard',
  headers: createHeaders(),
})

// Error interceptor factory - converts axios errors to structured ApiError
const createErrorInterceptor = () => {
  return (error: AxiosError<ApiErrorResponse>) => {
    if (error.response) {
      // Server responded with an error status
      const data = error.response.data || { detail: 'An unknown error occurred' }
      throw new ApiError(data, error.response.status)
    } else if (error.request) {
      // Request was made but no response received (network error)
      throw new ApiError(
        { detail: 'Network error: Unable to reach server' },
        0
      )
    } else {
      // Error in request setup
      throw new ApiError(
        { detail: error.message || 'Request configuration error' },
        0
      )
    }
  }
}

// Apply error interceptors to all API instances
api.interceptors.response.use((response) => response, createErrorInterceptor())
dashboardApi.interceptors.response.use((response) => response, createErrorInterceptor())

export const assignmentApi = {
  /**
   * Upload an Excel file and parse devices
   */
  async uploadExcel(file: File): Promise<ProcessResponse> {
    const formData = new FormData()
    formData.append('file', file)

    const response = await api.post<ProcessResponse>('/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  },

  /**
   * Get available options for assignment
   */
  async getOptions(deviceType?: string): Promise<OptionsResponse> {
    const params = deviceType ? { device_type: deviceType } : {}
    const response = await api.get<OptionsResponse>('/options', { params })
    return response.data
  },

  /**
   * Apply assignments to devices
   */
  async applyAssignments(request: ApplyRequest): Promise<ApplyResponse> {
    const response = await api.post<ApplyResponse>('/apply', request)
    return response.data
  },

  /**
   * Sync with GreenLake and get report
   */
  async syncAndReport(): Promise<ReportResponse> {
    const response = await api.post<ReportResponse>('/sync', {
      sync_devices: true,
      sync_subscriptions: true,
    })
    return response.data
  },

  /**
   * Download report as Excel
   */
  async downloadReport(): Promise<Blob> {
    const response = await api.get('/report/download', {
      responseType: 'blob',
    })
    return response.data
  },

  /**
   * Health check
   */
  async healthCheck(): Promise<{ status: string }> {
    const response = await api.get('/health')
    return response.data
  },

  /**
   * Add devices to GreenLake
   */
  async addDevices(request: AddDevicesRequest): Promise<AddDevicesResponse> {
    const response = await api.post<AddDevicesResponse>('/devices/add', request)
    return response.data
  },
}

export interface DeviceListParams {
  page?: number
  page_size?: number
  search?: string
  device_type?: string
  region?: string
  assigned_state?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export interface SubscriptionListParams {
  page?: number
  page_size?: number
  search?: string
  subscription_type?: string
  subscription_status?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export interface SyncResponse {
  status: string
  message: string
  started_at?: string
  devices?: {
    total?: number
    upserted?: number
    errors?: number
    fetched?: number
    synced_at?: string
  }
  subscriptions?: {
    total?: number
    upserted?: number
    errors?: number
    fetched?: number
    synced_at?: string
  }
}

// Clients API
const clientsApi = axios.create({
  baseURL: '/api/clients',
  headers: createHeaders(),
})

// Apply error interceptor to clients API
clientsApi.interceptors.response.use((response) => response, createErrorInterceptor())

// Types for Clients API
export interface ClientItem {
  id: number
  site_id: string
  site_name?: string
  mac: string
  name?: string
  health?: string
  status?: string
  status_reason?: string
  type?: string
  ipv4?: string
  ipv6?: string
  network?: string  // WiFi network name (SSID)
  vlan_id?: string
  port?: string
  role?: string
  connected_device_serial?: string
  connected_to?: string
  connected_since?: string
  last_seen_at?: string
  tunnel?: string
  tunnel_id?: number
  key_management?: string
  authentication?: string
  updated_at?: string
}

export interface ClientListResponse {
  items: ClientItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface SiteStats {
  site_id: string
  site_name?: string
  client_count: number
  connected_count: number
  wired_count: number
  wireless_count: number
  good_health_count: number
  fair_health_count: number
  poor_health_count: number
  device_count: number
  last_synced_at?: string
}

export interface SiteListResponse {
  items: SiteStats[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface ClientsSummary {
  total_clients: number
  connected: number
  disconnected: number
  failed: number
  blocked: number
  wired: number
  wireless: number
  health_good: number
  health_fair: number
  health_poor: number
  health_unknown: number
  total_sites: number
  last_sync_at?: string
}

export interface SiteClientsParams {
  page?: number
  page_size?: number
  status?: string
  health?: string
  type?: string
  search?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export interface FilteredClientsParams {
  page?: number
  page_size?: number
  type?: string  // Comma-delimited for multiple values
  status?: string  // Comma-delimited for multiple values
  health?: string  // Comma-delimited for multiple values
  site_id?: string  // Comma-delimited for multiple values
  network?: string  // Comma-delimited for multiple values
  vlan?: string  // Comma-delimited for multiple values
  role?: string  // Comma-delimited for multiple values
  tunnel?: string  // Comma-delimited for multiple values
  auth?: string  // Comma-delimited for multiple values
  key_mgmt?: string  // Comma-delimited for multiple values
  connected_to?: string  // Comma-delimited for multiple values
  subnet?: string  // IP subnet prefix
  search?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export interface ClientFilterOptions {
  sites: Array<{ id: string; name: string }>
  networks: string[]
  vlans: string[]
  roles: string[]
  tunnels: string[]
  authentications: string[]
  key_managements: string[]
  connected_devices: string[]
  subnets: string[]
}

export const clientsApiClient = {
  /**
   * Get clients summary statistics
   */
  async getSummary(): Promise<ClientsSummary> {
    const response = await clientsApi.get<ClientsSummary>('/summary')
    return response.data
  },

  /**
   * Get available filter options (distinct values for each filter field)
   */
  async getFilterOptions(): Promise<ClientFilterOptions> {
    const response = await clientsApi.get<ClientFilterOptions>('/filter-options')
    return response.data
  },

  /**
   * Get filtered clients across all sites
   */
  async getFilteredClients(params: FilteredClientsParams = {}): Promise<ClientListResponse> {
    const response = await clientsApi.get<ClientListResponse>('/filtered', { params })
    return response.data
  },

  /**
   * Get list of sites with statistics
   */
  async getSites(params: {
    page?: number
    page_size?: number
    search?: string
    sort_by?: string
    sort_order?: 'asc' | 'desc'
  } = {}): Promise<SiteListResponse> {
    const response = await clientsApi.get<SiteListResponse>('/sites', { params })
    return response.data
  },

  /**
   * Get clients for a specific site
   */
  async getSiteClients(siteId: string, params: SiteClientsParams = {}): Promise<ClientListResponse> {
    const response = await clientsApi.get<ClientListResponse>(`/sites/${encodeURIComponent(siteId)}`, { params })
    return response.data
  },

  /**
   * Search clients across all sites
   */
  async searchClients(query: string, params: {
    page?: number
    page_size?: number
  } = {}): Promise<ClientListResponse> {
    const response = await clientsApi.get<ClientListResponse>('/search', {
      params: { q: query, ...params },
    })
    return response.data
  },

  /**
   * Trigger clients and firmware sync
   */
  async triggerSync(): Promise<{
    status: string
    message: string
    started_at?: string
    clients?: Record<string, unknown>
    firmware?: Record<string, unknown>
  }> {
    const response = await clientsApi.post('/sync')
    return response.data
  },
}

export const dashboardApiClient = {
  /**
   * Get dashboard data
   */
  async getDashboard(expiringDays = 90): Promise<DashboardResponse> {
    const response = await dashboardApi.get<DashboardResponse>('', {
      params: { expiring_days: expiringDays },
    })
    return response.data
  },

  /**
   * Trigger sync with GreenLake API
   */
  async triggerSync(): Promise<SyncResponse> {
    const response = await dashboardApi.post<SyncResponse>('/sync')
    return response.data
  },

  /**
   * Search devices
   */
  async searchDevices(query: string, limit = 20): Promise<DeviceListResponse> {
    const response = await dashboardApi.get<DeviceListResponse>('/devices/search', {
      params: { q: query, limit },
    })
    return response.data
  },

  /**
   * Get paginated list of devices
   */
  async getDevices(params: DeviceListParams = {}): Promise<DeviceListResponse> {
    const response = await dashboardApi.get<DeviceListResponse>('/devices', { params })
    return response.data
  },

  /**
   * Get paginated list of subscriptions
   */
  async getSubscriptions(params: SubscriptionListParams = {}): Promise<SubscriptionListResponse> {
    const response = await dashboardApi.get<SubscriptionListResponse>('/subscriptions', { params })
    return response.data
  },

  /**
   * Get filter options for devices and subscriptions
   */
  async getFilterOptions(): Promise<FilterOptions> {
    const response = await dashboardApi.get<FilterOptions>('/filters')
    return response.data
  },
}

export default api
