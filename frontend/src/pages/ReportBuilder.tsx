import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { FileText, Plus, Loader2, Clock } from 'lucide-react'
import { ReportBuilderPanel } from '../components/reports/ReportBuilderPanel'
import { useReportBuilder } from '../hooks/useReportBuilder'
import type { CustomReportListItem } from '../types'

/**
 * Report Builder Page
 * Allows users to create custom reports with drag-and-drop interface
 */
export function ReportBuilder() {
  const [searchParams, setSearchParams] = useSearchParams()
  const reportId = searchParams.get('report')

  const {
    savedReports,
    isLoadingReports,
    loadReport,
    currentReport,
    resetConfig,
  } = useReportBuilder()

  const [isMounted, setIsMounted] = useState(false)

  // Handle URL param for loading a specific report
  useEffect(() => {
    if (!isMounted) {
      setIsMounted(true)
      return
    }

    if (reportId && savedReports?.reports) {
      const report = savedReports.reports.find((r) => r.id === reportId)
      if (report) {
        // Load the full report (we need to fetch it since list only has metadata)
        // For now, we'll need the full report which should be loaded by the hook
        loadReport(report as any) // Type assertion since list item matches report response structure
      }
    }
  }, [reportId, savedReports, loadReport, isMounted])

  const handleReportSelect = (report: CustomReportListItem) => {
    // Update URL param
    setSearchParams({ report: report.id })
    // Load the report
    loadReport(report as any)
  }

  const handleNewReport = () => {
    // Clear URL param
    setSearchParams({})
    // Reset configuration
    resetConfig()
  }

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Background effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
        <div className="absolute -top-1/2 -right-1/2 h-[1000px] w-[1000px] rounded-full bg-hpe-purple/5 blur-3xl" />
        <div className="absolute -bottom-1/2 -left-1/2 h-[1000px] w-[1000px] rounded-full bg-hpe-green/5 blur-3xl" />
      </div>

      <div className="relative">
        {/* Header */}
        <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-xl">
          <div className="mx-auto max-w-[1600px] px-6 py-6">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-white">
                  <span className="bg-gradient-to-r from-violet-400 to-violet-600 bg-clip-text text-transparent">
                    Custom Report Builder
                  </span>
                </h1>
                <p className="mt-1 text-sm text-slate-400">
                  Create and execute custom reports with drag-and-drop interface
                </p>
              </div>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-[1600px] px-6 py-8">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Sidebar - Saved Reports */}
            <aside className="lg:col-span-3">
              <div className="card sticky top-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-sm font-medium text-slate-200">Saved Reports</h2>
                  <button
                    onClick={handleNewReport}
                    className="btn btn-sm btn-primary flex items-center gap-1"
                    title="Create new report"
                    data-testid="new-report-btn"
                  >
                    <Plus className="h-4 w-4" />
                    New
                  </button>
                </div>

                {isLoadingReports ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
                  </div>
                ) : savedReports?.reports && savedReports.reports.length > 0 ? (
                  <div className="space-y-2 max-h-[600px] overflow-y-auto pr-2">
                    {savedReports.reports.map((report) => (
                      <button
                        key={report.id}
                        onClick={() => handleReportSelect(report)}
                        className={`w-full text-left rounded-lg border p-3 transition-all ${
                          currentReport?.id === report.id
                            ? 'border-violet-500/50 bg-violet-500/10'
                            : 'border-slate-700/50 bg-slate-800/30 hover:border-slate-600/50 hover:bg-slate-800/50'
                        }`}
                        data-testid={`saved-report-${report.id}`}
                      >
                        <div className="flex items-start gap-2">
                          <FileText className={`h-4 w-4 mt-0.5 flex-shrink-0 ${
                            currentReport?.id === report.id ? 'text-violet-400' : 'text-slate-400'
                          }`} />
                          <div className="flex-1 min-w-0">
                            <p className={`text-sm font-medium truncate ${
                              currentReport?.id === report.id ? 'text-violet-300' : 'text-slate-200'
                            }`}>
                              {report.name}
                            </p>
                            {report.description && (
                              <p className="text-xs text-slate-500 line-clamp-2 mt-1">
                                {report.description}
                              </p>
                            )}
                            <div className="flex items-center gap-1 mt-2 text-xs text-slate-500">
                              <Clock className="h-3 w-3" />
                              <span>
                                {new Date(report.updated_at).toLocaleDateString()}
                              </span>
                              {report.execution_count > 0 && (
                                <span className="ml-2">
                                  · {report.execution_count} run{report.execution_count !== 1 ? 's' : ''}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <FileText className="h-12 w-12 text-slate-700 mx-auto mb-3" />
                    <p className="text-sm text-slate-500">No saved reports</p>
                    <p className="text-xs text-slate-600 mt-1">
                      Create your first custom report
                    </p>
                  </div>
                )}

                {savedReports?.total && savedReports.total > savedReports.reports.length && (
                  <div className="mt-4 pt-4 border-t border-slate-700">
                    <p className="text-xs text-slate-500 text-center">
                      Showing {savedReports.reports.length} of {savedReports.total} reports
                    </p>
                  </div>
                )}
              </div>
            </aside>

            {/* Main Content - Report Builder */}
            <div className="lg:col-span-9">
              <ReportBuilderPanel />
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
