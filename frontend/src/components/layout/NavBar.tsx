import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Bars3Icon, XMarkIcon, ChartBarSquareIcon, SunIcon, MoonIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { useTheme } from '../../lib/theme'

const LINKS = [
  { to: '/', label: 'Dashboard' },
  { to: '/methodology', label: 'Methodology' },
]

export function NavBar() {
  const [open, setOpen] = useState(false)
  const { theme, toggle } = useTheme()

  return (
    <header className="sticky top-0 z-40 border-b border-border/80 bg-canvas/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <NavLink to="/" className="flex items-center gap-2.5" onClick={() => setOpen(false)}>
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-cyan">
            <ChartBarSquareIcon className="h-5 w-5 text-white" />
          </span>
          <span className="text-lg font-bold tracking-tight text-text">
            Grid<span className="text-accent-soft">Edge</span>
          </span>
        </NavLink>

        <nav className="ml-auto hidden items-center gap-1 sm:flex">
          {LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === '/'}
              className={({ isActive }) =>
                clsx(
                  'rounded-lg px-3.5 py-2 text-sm font-medium transition-colors',
                  isActive ? 'bg-surface-2 text-text' : 'text-text-muted hover:text-text',
                )
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-1">
          <button
            onClick={toggle}
            className="rounded-lg p-2 text-text-muted transition-colors hover:bg-surface-2 hover:text-text"
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          >
            {theme === 'dark' ? <SunIcon className="h-5 w-5" /> : <MoonIcon className="h-5 w-5" />}
          </button>

          <button
            className="rounded-lg p-2 text-text-muted sm:hidden"
            onClick={() => setOpen((v) => !v)}
            aria-label="Toggle navigation"
          >
            {open ? <XMarkIcon className="h-6 w-6" /> : <Bars3Icon className="h-6 w-6" />}
          </button>
        </div>
      </div>

      {open && (
        <nav className="flex flex-col gap-1 border-t border-border px-4 py-3 sm:hidden">
          {LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === '/'}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                clsx(
                  'rounded-lg px-3.5 py-2.5 text-sm font-medium',
                  isActive ? 'bg-surface-2 text-text' : 'text-text-muted',
                )
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  )
}
