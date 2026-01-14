/**
 * Custom Reports API client for report builder CRUD operations.
 */

import axios, { AxiosError } from 'axios'
import type {
  CreateReportRequest,
  CustomReportListResponse,
  CustomReportResponse,
  ExecuteReportRequest,
  ExecuteReportResponse,
  FieldsResponse,
  UpdateReportRequest,
  ApiErrorResponse,
} from '../types'
import { ApiError } from '../types'

const api = axios.create({
  baseURL: '/api/reports',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Error interceptor - converts axios errors to structured ApiError
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

// Apply error interceptor
api.interceptors.response.use((response) => response, createErrorInterceptor())

export const customReportsApi = {
  /**
   * Get available fields metadata for report builder.
   */
  async getAvailableFields(): Promise<FieldsResponse> {
    const response = await api.get<FieldsResponse>('/fields')
    return response.data
  },

  /**
   * List all saved custom reports.
   */
  async listReports(page = 1, pageSize = 50): Promise<CustomReportListResponse> {
    const response = await api.get<CustomReportListResponse>('/custom', {
      params: { page, page_size: pageSize },
    })
    return response.data
  },

  /**
   * Get a single custom report by ID.
   */
  async getReport(id: string): Promise<CustomReportResponse> {
    const response = await api.get<CustomReportResponse>(`/custom/${id}`)
    return response.data
  },

  /**
   * Create a new custom report.
   */
  async createReport(request: CreateReportRequest): Promise<CustomReportResponse> {
    const response = await api.post<CustomReportResponse>('/custom', request)
    return response.data
  },

  /**
   * Update an existing custom report.
   */
  async updateReport(
    id: string,
    request: UpdateReportRequest
  ): Promise<CustomReportResponse> {
    const response = await api.put<CustomReportResponse>(`/custom/${id}`, request)
    return response.data
  },

  /**
   * Delete a custom report.
   */
  async deleteReport(id: string): Promise<void> {
    await api.delete(`/custom/${id}`)
  },

  /**
   * Execute a custom report and get results.
   */
  async executeReport(
    id: string,
    params: Partial<ExecuteReportRequest> = {}
  ): Promise<ExecuteReportResponse> {
    const request: ExecuteReportRequest = {
      format: params.format || 'json',
      page: params.page || 1,
      page_size: params.page_size || 100,
    }

    const response = await api.post<ExecuteReportResponse>(
      `/custom/${id}/execute`,
      request
    )
    return response.data
  },

  /**
   * Execute a custom report and download as file (CSV or XLSX).
   */
  async downloadReport(
    id: string,
    format: 'csv' | 'xlsx',
    filename?: string
  ): Promise<void> {
    const response = await api.post(
      `/custom/${id}/execute`,
      { format, page: 1, page_size: 999999 },
      { responseType: 'blob' }
    )

    const blob = response.data
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename || `custom_report_${id}_${new Date().toISOString().slice(0, 10)}.${format}`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  },
}

export default customReportsApi
