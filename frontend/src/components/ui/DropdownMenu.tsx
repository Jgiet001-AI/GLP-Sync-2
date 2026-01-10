import { useState, useRef, useEffect } from 'react'
import { MoreVertical } from 'lucide-react'

interface DropdownMenuItem {
  label: string
  icon?: React.ReactNode
  onClick: () => void
  variant?: 'default' | 'danger'
  disabled?: boolean
}

interface DropdownMenuProps {
  items: DropdownMenuItem[]
  align?: 'left' | 'right'
}

export function DropdownMenu({ items, align = 'right' }: DropdownMenuProps) {
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  // Close on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        menuRef.current &&
        !menuRef.current.contains(event.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node)
      ) {
        setOpen(false)
      }
    }

    if (open) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  // Close on escape
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) {
        setOpen(false)
        buttonRef.current?.focus()
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [open])

  const handleItemClick = (item: DropdownMenuItem) => {
    if (!item.disabled) {
      item.onClick()
      setOpen(false)
    }
  }

  return (
    <div className="relative inline-block">
      <button
        ref={buttonRef}
        onClick={(e) => {
          e.stopPropagation()
          setOpen(!open)
        }}
        className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-white focus:outline-none focus:ring-2 focus:ring-hpe-green/50"
        aria-label="Open actions menu"
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <MoreVertical className="h-4 w-4" />
      </button>

      {open && (
        <div
          ref={menuRef}
          className={`absolute z-50 mt-1 min-w-[160px] rounded-xl border border-slate-700 bg-slate-800 py-1 shadow-xl ${
            align === 'right' ? 'right-0' : 'left-0'
          }`}
          role="menu"
        >
          {items.map((item, index) => (
            <button
              key={index}
              onClick={(e) => {
                e.stopPropagation()
                handleItemClick(item)
              }}
              disabled={item.disabled}
              className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors ${
                item.disabled
                  ? 'cursor-not-allowed text-slate-500'
                  : item.variant === 'danger'
                    ? 'text-rose-400 hover:bg-rose-500/10'
                    : 'text-slate-300 hover:bg-slate-700 hover:text-white'
              }`}
              role="menuitem"
            >
              {item.icon && <span className="h-4 w-4">{item.icon}</span>}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
