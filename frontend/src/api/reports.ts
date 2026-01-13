/**
 * Reports API client for downloading CSV/Excel exports.
 */

import axios from 'axios'

const api = axios.create({
  baseURL: '/api/reports',
})

export interface ReportFilters {
  // Dashboard
  expiring_days?: number
  // Devices
  device_type?: string
  region?: string
  assigned_state?: string
  // Subscriptions
  subscription_type?: string
  status?: string
  // Clients
  type?: string
  health?: string
  site_id?: string
  // Common
  search?: string
  limit?: number
}

export type ReportFormat = 'xlsx' | 'csv'

export type ReportType = 'dashboard' | 'devices' | 'subscriptions' | 'clients' | 'assignment-template'

/**
 * Download a report file.
 */
async function downloadReport(
  reportType: ReportType,
  format: ReportFormat,
  filters?: ReportFilters
): Promise<Blob> {
  let url: string
  const params: Record<string, string | number | undefined> = {
    format,
    ...filters,
  }

  switch (reportType) {
    case 'dashboard':
      url = '/dashboard/export'
      break
    case 'devices':
      url = '/devices/export'
      break
    case 'subscriptions':
      url = '/subscriptions/export'
      break
    case 'clients':
      url = '/clients/export'
      break
    case 'assignment-template':
      url = '/assignment/template'
      break
    default:
      throw new Error(`Unknown report type: ${reportType}`)
  }

  const response = await api.get(url, {
    params,
    responseType: 'blob',
  })

  return response.data
}

/**
 * Trigger download of a blob as a file.
 */
function triggerDownload(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

/**
 * Generate a timestamped filename.
 */
function generateFilename(reportType: ReportType, format: ReportFormat): string {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)

  switch (reportType) {
    case 'assignment-template':
      return `device_assignment_template.${format}`
    default:
      return `hpe_greenlake_${reportType}_${timestamp}.${format}`
  }
}

export const reportsApi = {
  /**
   * Download a report and trigger browser download.
   */
  async downloadReport(
    reportType: ReportType,
    format: ReportFormat = 'xlsx',
    filters?: ReportFilters
  ): Promise<void> {
    const blob = await downloadReport(reportType, format, filters)
    const filename = generateFilename(reportType, format)
    triggerDownload(blob, filename)
  },

  /**
   * Download dashboard report.
   */
  async downloadDashboardReport(format: ReportFormat = 'xlsx', expiringDays = 90): Promise<void> {
    return this.downloadReport('dashboard', format, { expiring_days: expiringDays })
  },

  /**
   * Download devices report with current filters.
   */
  async downloadDevicesReport(
    format: ReportFormat = 'xlsx',
    filters?: Pick<ReportFilters, 'device_type' | 'region' | 'assigned_state' | 'search' | 'limit'>
  ): Promise<void> {
    return this.downloadReport('devices', format, filters)
  },

  /**
   * Download subscriptions report with current filters.
   */
  async downloadSubscriptionsReport(
    format: ReportFormat = 'xlsx',
    filters?: Pick<ReportFilters, 'subscription_type' | 'status' | 'search' | 'limit'>
  ): Promise<void> {
    return this.downloadReport('subscriptions', format, filters)
  },

  /**
   * Download clients report with current filters.
   */
  async downloadClientsReport(
    format: ReportFormat = 'xlsx',
    filters?: Pick<ReportFilters, 'type' | 'status' | 'health' | 'site_id' | 'limit'>
  ): Promise<void> {
    return this.downloadReport('clients', format, filters)
  },

  /**
   * Download assignment template.
   */
  async downloadAssignmentTemplate(format: ReportFormat = 'xlsx'): Promise<void> {
    return this.downloadReport('assignment-template', format)
  },
}

export default reportsApi
