import { useState, useRef, useEffect } from 'react'

interface TooltipProps {
  content: React.ReactNode
  children: React.ReactNode
  position?: 'top' | 'bottom' | 'left' | 'right'
  delay?: number
}

export function Tooltip({ content, children, position = 'top', delay = 200 }: TooltipProps) {
  const [mounting, setMounting] = useState(false)
  const [visible, setVisible] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const fadeOutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showTooltip = () => {
    // Clear any pending hide timeout
    if (fadeOutRef.current) {
      clearTimeout(fadeOutRef.current)
      fadeOutRef.current = null
    }

    // Mount the element first, then make it visible after a brief delay
    setMounting(true)
    timeoutRef.current = setTimeout(() => {
      setVisible(true)
    }, delay)
  }

  const hideTooltip = () => {
    // Clear show timeout if still pending
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }

    // Fade out first, then unmount after transition completes
    setVisible(false)
    fadeOutRef.current = setTimeout(() => {
      setMounting(false)
    }, 150) // Match transition duration
  }

  // Cleanup timeouts on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      if (fadeOutRef.current) clearTimeout(fadeOutRef.current)
    }
  }, [])

  const positionClasses = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  }

  const arrowClasses = {
    top: 'top-full left-1/2 -translate-x-1/2 border-t-slate-700 border-x-transparent border-b-transparent',
    bottom: 'bottom-full left-1/2 -translate-x-1/2 border-b-slate-700 border-x-transparent border-t-transparent',
    left: 'left-full top-1/2 -translate-y-1/2 border-l-slate-700 border-y-transparent border-r-transparent',
    right: 'right-full top-1/2 -translate-y-1/2 border-r-slate-700 border-y-transparent border-l-transparent',
  }

  return (
    <div
      className="relative w-full"
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
    >
      {children}
      {mounting && (
        <div
          className={`absolute z-50 whitespace-nowrap rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-white shadow-xl transition-opacity duration-150 ${
            visible ? 'opacity-100' : 'opacity-0'
          } ${positionClasses[position]}`}
          role="tooltip"
        >
          {content}
          <div
            className={`absolute h-0 w-0 border-4 ${arrowClasses[position]}`}
            aria-hidden="true"
          />
        </div>
      )}
    </div>
  )
}

// Simpler inline tooltip for chart bars
interface ChartTooltipProps {
  visible: boolean
  content: React.ReactNode
  x: number
  y: number
}

export function ChartTooltip({ visible, content, x, y }: ChartTooltipProps) {
  if (!visible) return null

  return (
    <div
      className="pointer-events-none fixed z-50 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs shadow-xl transition-opacity duration-150 opacity-100"
      style={{
        left: x,
        top: y,
        transform: 'translate(-50%, -100%) translateY(-8px)',
      }}
    >
      {content}
    </div>
  )
}
