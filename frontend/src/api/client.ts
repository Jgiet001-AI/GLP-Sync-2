import axios from 'axios'
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

const api = axios.create({
  baseURL: '/api/assignment',
  headers: {
    'Content-Type': 'application/json',
  },
})

const dashboardApi = axios.create({
  baseURL: '/api/dashboard',
  headers: {
    'Content-Type': 'application/json',
  },
})

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
