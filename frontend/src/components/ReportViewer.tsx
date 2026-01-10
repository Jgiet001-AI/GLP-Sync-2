import { memo } from 'react'
import {
  CheckCircle,
  XCircle,
  Download,
  RefreshCw,
  ArrowRight,
} from 'lucide-react'
import clsx from 'clsx'
import type { ApplyResponse, ReportResponse } from '../types'

interface ReportViewerProps {
  applyResult: ApplyResponse | null
  report: ReportResponse | null
  onSync: () => void
  onReset: () => void
  isSyncing: boolean
}

export function ReportViewer({
  applyResult,
  report,
  onSync,
  onReset,
  isSyncing,
}: ReportViewerProps) {
  const handleDownload = async () => {
    try {
      const response = await fetch('/api/assignment/report/download')
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'assignment_report.xlsx'
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      console.error('Download failed:', error)
    }
  }

  return (
    <div className="space-y-6" data-testid="report-viewer">
      {/* Apply Results */}
      {applyResult && (
        <div className="card" data-testid="apply-results">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium text-white">Assignment Results</h3>
            {applyResult.success ? (
              <span className="badge badge-success flex items-center gap-1">
                <CheckCircle className="w-4 h-4" aria-hidden="true" />
                Success
              </span>
            ) : (
              <span className="badge badge-error flex items-center gap-1">
                <XCircle className="w-4 h-4" aria-hidden="true" />
                Errors
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <StatCard
              label="Devices Created"
              value={applyResult.devices_created}
              color="sky"
            />
            <StatCard
              label="Subscriptions"
              value={applyResult.subscriptions_assigned}
              color="violet"
            />
            <StatCard
              label="Applications"
              value={applyResult.applications_assigned}
              color="emerald"
            />
            <StatCard
              label="Tags Updated"
              value={applyResult.tags_updated}
              color="amber"
            />
          </div>

          {applyResult.errors > 0 && (
            <div
              className="bg-rose-500/10 border border-rose-500/30 rounded-lg p-4"
              role="alert"
              data-testid="apply-errors"
            >
              <p className="font-medium text-rose-400">
                {applyResult.errors} operation(s) failed
              </p>
              <ul className="mt-2 text-sm text-rose-300 list-disc list-inside">
                {applyResult.operations
                  .filter((op) => !op.success)
                  .map((op, i) => (
                    <li key={i}>
                      {op.operation_type}: {op.error || 'Unknown error'}
                    </li>
                  ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Sync Section */}
      <div className="card" data-testid="sync-section">
        <h3 className="text-lg font-medium text-white mb-4">Sync with GreenLake</h3>
        <p className="text-slate-400 mb-4">
          Sync the database with GreenLake to verify changes and update local data.
        </p>

        <button
          onClick={onSync}
          disabled={isSyncing}
          className="btn btn-primary flex items-center gap-2"
          data-testid="sync-btn"
        >
          <RefreshCw className={clsx('w-5 h-5', isSyncing && 'animate-spin')} aria-hidden="true" />
          {isSyncing ? 'Syncing...' : 'Sync Now'}
        </button>

        {/* Sync Results */}
        {report && (
          <div className="mt-6 p-4 bg-slate-800/50 rounded-lg" data-testid="sync-results">
            <h4 className="font-medium text-white mb-3">Sync Complete</h4>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-slate-400">Devices Synced</p>
                <p className="text-2xl font-bold text-hpe-green">
                  {report.sync?.devices_synced ?? 0}
                </p>
              </div>
              <div>
                <p className="text-sm text-slate-400">Subscriptions Synced</p>
                <p className="text-2xl font-bold text-hpe-purple">
                  {report.sync?.subscriptions_synced ?? 0}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-4">
        <button
          onClick={handleDownload}
          className="btn btn-secondary flex items-center gap-2"
          data-testid="download-report-btn"
        >
          <Download className="w-5 h-5" aria-hidden="true" />
          Download Report
        </button>

        <button
          onClick={onReset}
          className="btn btn-primary flex items-center gap-2"
          data-testid="start-new-btn"
        >
          <ArrowRight className="w-5 h-5" aria-hidden="true" />
          Start New Assignment
        </button>
      </div>
    </div>
  )
}

interface StatCardProps {
  label: string
  value: number
  color: 'sky' | 'violet' | 'emerald' | 'amber'
}

const StatCard = memo(function StatCard({ label, value, color }: StatCardProps) {
  const colorClasses = {
    sky: 'bg-sky-500/10 border-sky-500/30 text-sky-400',
    violet: 'bg-violet-500/10 border-violet-500/30 text-violet-400',
    emerald: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
    amber: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
  }

  return (
    <div className={clsx('rounded-lg border p-4', colorClasses[color])}>
      <p className="text-sm opacity-75">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  )
})
