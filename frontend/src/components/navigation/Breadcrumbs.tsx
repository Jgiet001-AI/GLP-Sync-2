import { useMemo } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { ChevronRight, Home, Server, Shield, Users, Upload, LayoutDashboard } from 'lucide-react'

/**
 * Breadcrumb Navigation Component
 * Shows current location with active filters and enables quick navigation
 */

interface BreadcrumbItem {
  label: string
  href: string
  icon?: typeof Home
  isFilter?: boolean
  filterKey?: string
}

// Page configuration
const pageConfig: Record<string, { label: string; icon: typeof Home }> = {
  '/': { label: 'Dashboard', icon: LayoutDashboard },
  '/devices': { label: 'Devices', icon: Server },
  '/subscriptions': { label: 'Subscriptions', icon: Shield },
  '/clients': { label: 'Clients', icon: Users },
  '/assignment': { label: 'Assignment', icon: Upload },
}

// Filter display configuration
const filterConfig: Record<string, { label: string; formatValue?: (v: string) => string }> = {
  device_type: { label: 'Type' },
  region: { label: 'Region' },
  assigned_state: {
    label: 'Status',
    formatValue: (v) =>
      v === 'ASSIGNED_TO_SERVICE' ? 'Assigned' : v === 'UNASSIGNED' ? 'Unassigned' : v,
  },
  subscription_type: {
    label: 'Type',
    formatValue: (v) => v.replace('CENTRAL_', ''),
  },
  status: { label: 'Status' },
  search: { label: 'Search' },
}

export function Breadcrumbs() {
  const location = useLocation()
  const [searchParams] = useSearchParams()

  const breadcrumbs = useMemo<BreadcrumbItem[]>(() => {
    const items: BreadcrumbItem[] = []

    // Always start with home
    items.push({
      label: 'Home',
      href: '/',
      icon: Home,
    })

    // Add current page if not home
    const currentPage = pageConfig[location.pathname]
    if (currentPage && location.pathname !== '/') {
      items.push({
        label: currentPage.label,
        href: location.pathname,
        icon: currentPage.icon,
      })
    }

    // Add active filters as breadcrumb items
    searchParams.forEach((value, key) => {
      if (filterConfig[key] && value) {
        const config = filterConfig[key]
        const displayValue = config.formatValue ? config.formatValue(value) : value

        // Build URL without this filter for removal
        const newParams = new URLSearchParams(searchParams)
        newParams.delete(key)
        const removeHref = `${location.pathname}${newParams.toString() ? `?${newParams.toString()}` : ''}`

        items.push({
          label: `${config.label}: ${displayValue}`,
          href: removeHref,
          isFilter: true,
          filterKey: key,
        })
      }
    })

    return items
  }, [location.pathname, searchParams])

  // Don't show breadcrumbs on dashboard with no filters
  if (breadcrumbs.length <= 1) return null

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-sm">
      {breadcrumbs.map((item, index) => {
        const isLast = index === breadcrumbs.length - 1
        const Icon = item.icon

        // Filter breadcrumbs should always be clickable for removal
        // even when they're the last item
        const shouldBeLink = !isLast || item.isFilter

        return (
          <div key={`${item.href}-${index}`} className="flex items-center">
            {index > 0 && (
              <ChevronRight className="mx-1 h-4 w-4 text-slate-600" aria-hidden="true" />
            )}

            {shouldBeLink ? (
              <Link
                to={item.href}
                className={`flex items-center gap-1.5 transition-colors ${
                  item.isFilter
                    ? isLast
                      ? 'rounded-full bg-hpe-green/10 px-2.5 py-1 text-xs font-medium text-hpe-green hover:bg-hpe-green/20'
                      : 'rounded-full bg-slate-700/50 px-2.5 py-1 text-xs font-medium text-slate-300 hover:bg-slate-700 hover:text-white'
                    : 'text-slate-400 hover:text-white'
                }`}
                aria-current={isLast ? 'page' : undefined}
              >
                {Icon && <Icon className="h-3.5 w-3.5" />}
                {item.label}
              </Link>
            ) : (
              <span
                className="flex items-center gap-1.5 font-medium text-white"
                aria-current="page"
              >
                {Icon && <Icon className="h-3.5 w-3.5" />}
                {item.label}
              </span>
            )}
          </div>
        )
      })}
    </nav>
  )
}

/**
 * Compact breadcrumb for use in page headers
 */
export function CompactBreadcrumb({
  items,
}: {
  items: Array<{ label: string; href?: string }>
}) {
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-xs text-slate-400">
      {items.map((item, index) => (
        <div key={index} className="flex items-center">
          {index > 0 && <ChevronRight className="mx-1 h-3 w-3" />}
          {item.href ? (
            <Link to={item.href} className="hover:text-white transition-colors">
              {item.label}
            </Link>
          ) : (
            <span className="text-slate-300">{item.label}</span>
          )}
        </div>
      ))}
    </nav>
  )
}
