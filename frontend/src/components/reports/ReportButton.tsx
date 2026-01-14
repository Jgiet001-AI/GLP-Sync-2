/**
 * ReportButton - A beautiful, reusable report download component.
 *
 * Features:
 * - Format selection dropdown (Excel/CSV)
 * - Loading state with spinner
 * - Toast notifications for success/error
 * - Consistent styling across all pages
 */

import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import {
  Download,
  FileSpreadsheet,
  FileText,
  ChevronDown,
  Loader2,
  Check,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { reportsApi, type ReportType, type ReportFormat, type ReportFilters } from '../../api/reports'

interface ReportButtonProps {
  /** Type of report to generate */
  reportType: ReportType
  /** Optional filters to apply to the report */
  filters?: ReportFilters
  /** Available formats (default: both Excel and CSV) */
  formats?: ReportFormat[]
  /** Button variant */
  variant?: 'primary' | 'secondary' | 'ghost'
  /** Button size */
  size?: 'sm' | 'md' | 'lg'
  /** Custom label */
  label?: string
  /** Additional class names */
  className?: string
  /** Disabled state */
  disabled?: boolean
}

const formatOptions: { value: ReportFormat; label: string; icon: typeof FileSpreadsheet }[] = [
  { value: 'xlsx', label: 'Excel (.xlsx)', icon: FileSpreadsheet },
  { value: 'csv', label: 'CSV (.csv)', icon: FileText },
]

export function ReportButton({
  reportType,
  filters,
  formats = ['xlsx', 'csv'],
  variant = 'secondary',
  size = 'md',
  label,
  className = '',
  disabled = false,
}: ReportButtonProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)
  const [downloadedFormat, setDownloadedFormat] = useState<ReportFormat | null>(null)
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, left: 0, width: 0 })
  const dropdownRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  // Update dropdown position when opened
  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect()
      setDropdownPosition({
        top: rect.bottom + window.scrollY + 4, // 4px gap (mt-1)
        left: rect.right + window.scrollX - 180, // Align to right, 180px is min-w-[180px]
        width: Math.max(rect.width, 180),
      })
    }
  }, [isOpen])

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  // Clear success indicator after delay
  useEffect(() => {
    if (downloadedFormat) {
      const timer = setTimeout(() => setDownloadedFormat(null), 2000)
      return () => clearTimeout(timer)
    }
  }, [downloadedFormat])

  const handleDownload = async (format: ReportFormat) => {
    setIsOpen(false)
    setIsDownloading(true)

    try {
      await reportsApi.downloadReport(reportType, format, filters)
      setDownloadedFormat(format)
      toast.success(`Report downloaded successfully`, {
        icon: format === 'xlsx' ? '📊' : '📄',
      })
    } catch (error) {
      console.error('Failed to download report:', error)
      toast.error(
        error instanceof Error
          ? `Download failed: ${error.message}`
          : 'Failed to download report. Please try again.'
      )
    } finally {
      setIsDownloading(false)
    }
  }

  // Quick download (Excel by default if available)
  const handleQuickDownload = () => {
    const defaultFormat = formats.includes('xlsx') ? 'xlsx' : formats[0]
    handleDownload(defaultFormat)
  }

  // Determine button label
  const buttonLabel = label || getDefaultLabel(reportType)

  // Size classes
  const sizeClasses = {
    sm: 'px-3 py-1.5 text-xs gap-1.5',
    md: 'px-4 py-2 text-sm gap-2',
    lg: 'px-5 py-2.5 text-base gap-2',
  }

  // Variant classes
  const variantClasses = {
    primary:
      'bg-hpe-green text-white hover:bg-hpe-green/90 border-hpe-green',
    secondary:
      'bg-slate-800 text-white hover:bg-slate-700 border-slate-700',
    ghost:
      'bg-transparent text-slate-300 hover:bg-slate-800 border-slate-700',
  }

  const availableFormats = formatOptions.filter((opt) => formats.includes(opt.value))
  const showDropdown = availableFormats.length > 1

  return (
    <>
      <div className={`relative inline-flex ${className}`}>
        {/* Main button */}
        <button
          ref={buttonRef}
          onClick={showDropdown ? () => setIsOpen(!isOpen) : handleQuickDownload}
          disabled={disabled || isDownloading}
          className={`
            inline-flex items-center justify-center rounded-lg border font-medium transition-all
            ${sizeClasses[size]}
            ${variantClasses[variant]}
            ${disabled || isDownloading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          `}
          aria-haspopup={showDropdown}
          aria-expanded={isOpen}
        >
          {isDownloading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : downloadedFormat ? (
            <Check className="h-4 w-4 text-emerald-400" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          <span>{buttonLabel}</span>
          {showDropdown && (
            <ChevronDown
              className={`h-4 w-4 transition-transform ${isOpen ? 'rotate-180' : ''}`}
            />
          )}
        </button>
      </div>

      {/* Dropdown menu - rendered as portal at document root */}
      {showDropdown && isOpen && createPortal(
        <div
          ref={dropdownRef}
          className="fixed z-[9999] min-w-[180px] rounded-lg border border-slate-700 bg-slate-800 py-1 shadow-xl animate-fade-in"
          style={{
            top: `${dropdownPosition.top}px`,
            left: `${dropdownPosition.left}px`,
          }}
          role="menu"
        >
          {availableFormats.map((format) => (
            <button
              key={format.value}
              onClick={() => handleDownload(format.value)}
              disabled={isDownloading}
              className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-slate-300 transition-colors hover:bg-slate-700 hover:text-white disabled:opacity-50"
              role="menuitem"
            >
              <format.icon className="h-4 w-4 text-slate-400" />
              <span>{format.label}</span>
              {format.value === 'xlsx' && (
                <span className="ml-auto rounded bg-hpe-green/20 px-1.5 py-0.5 text-[10px] font-medium text-hpe-green">
                  Recommended
                </span>
              )}
            </button>
          ))}
        </div>,
        document.body
      )}
    </>
  )
}

function getDefaultLabel(reportType: ReportType): string {
  switch (reportType) {
    case 'dashboard':
      return 'Export Report'
    case 'devices':
      return 'Export Devices'
    case 'subscriptions':
      return 'Export Subscriptions'
    case 'clients':
      return 'Export Clients'
    case 'assignment-template':
      return 'Download Template'
    default:
      return 'Export'
  }
}

export default ReportButton
