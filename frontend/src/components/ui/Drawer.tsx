import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'

interface DrawerProps {
  open: boolean
  onClose: () => void
  title: string
  subtitle?: string
  children: React.ReactNode
  width?: 'sm' | 'md' | 'lg' | 'xl'
}

const widthClasses = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
}

export function Drawer({ open, onClose, title, subtitle, children, width = 'lg' }: DrawerProps) {
  const drawerRef = useRef<HTMLDivElement>(null)
  const [isVisible, setIsVisible] = useState(false)
  const [shouldRender, setShouldRender] = useState(false)

  // Animation state management
  useEffect(() => {
    if (open) {
      // Mount the component, then trigger slide-in animation
      setShouldRender(true)
      // Small delay to ensure DOM is ready before animating
      const timer = setTimeout(() => setIsVisible(true), 10)
      return () => clearTimeout(timer)
    } else {
      // Trigger slide-out animation
      setIsVisible(false)
      // Delay unmounting until animation completes (300ms duration)
      const timer = setTimeout(() => setShouldRender(false), 300)
      return () => clearTimeout(timer)
    }
  }, [open])

  // Handle escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) {
        onClose()
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [open, onClose])

  // Focus trap
  useEffect(() => {
    if (open && drawerRef.current) {
      const focusableElements = drawerRef.current.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      const firstElement = focusableElements[0] as HTMLElement
      firstElement?.focus()
    }
  }, [open])

  // Prevent body scroll when open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  if (!shouldRender) return null

  return (
    <div className="fixed inset-0 z-50 overflow-hidden" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/80 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <div className="fixed inset-y-0 right-0 flex max-w-full pl-10">
        <div
          ref={drawerRef}
          className={`w-screen ${widthClasses[width]} transform transition-transform duration-300 ease-in-out`}
        >
          <div className="flex h-full flex-col overflow-y-auto bg-slate-800 shadow-xl">
            {/* Header */}
            <div className="sticky top-0 z-10 border-b border-slate-700 bg-slate-800/95 px-6 py-4 backdrop-blur-sm">
              <div className="flex items-start justify-between">
                <div>
                  <h2 id="drawer-title" className="text-lg font-semibold text-white">
                    {title}
                  </h2>
                  {subtitle && (
                    <p className="mt-1 text-sm text-slate-400">{subtitle}</p>
                  )}
                </div>
                <button
                  onClick={onClose}
                  className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-700 hover:text-white"
                  aria-label="Close drawer"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 px-6 py-4">
              {children}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// Detail row component for drawer content
interface DetailRowProps {
  label: string
  value: React.ReactNode
  mono?: boolean
}

export function DetailRow({ label, value, mono = false }: DetailRowProps) {
  return (
    <div className="flex items-start justify-between py-3 border-b border-slate-700/50 last:border-0">
      <span className="text-sm text-slate-400">{label}</span>
      <span className={`text-sm text-white text-right ${mono ? 'font-mono' : ''}`}>
        {value || '-'}
      </span>
    </div>
  )
}

// Section component for grouping details
interface DetailSectionProps {
  title: string
  children: React.ReactNode
}

export function DetailSection({ title, children }: DetailSectionProps) {
  return (
    <div className="mb-6">
      <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-500">
        {title}
      </h3>
      <div className="rounded-xl border border-slate-700/50 bg-slate-900/50 p-4">
        {children}
      </div>
    </div>
  )
}
