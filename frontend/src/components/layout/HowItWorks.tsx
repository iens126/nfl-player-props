import { useEffect, useState } from 'react'
import {
  ChevronDownIcon,
  CursorArrowRaysIcon,
  PencilSquareIcon,
  ChartBarIcon,
} from '@heroicons/react/24/outline'
import clsx from 'clsx'

const STORAGE_KEY = 'gridedge-guide-collapsed'

const STEPS = [
  {
    icon: CursorArrowRaysIcon,
    title: 'Pick a player and a matchup',
    body: 'Choose from the upcoming games above, or filter by team and position. The opponent defaults to their next scheduled opponent.',
  },
  {
    icon: PencilSquareIcon,
    title: 'Enter the prop line',
    body: "Type the number the sportsbook is offering — say 62.5 receiving yards. Every panel below updates against that line.",
  },
  {
    icon: ChartBarIcon,
    title: 'Read the probabilities',
    body: 'The model gives the chance of going over and under, plus how it got there: recent form, matchup adjustment, and how much the models agree.',
  },
]

/**
 * Short explainer at the top of the dashboard. Expanded by default so a
 * first-time visitor knows what the tool is for; collapsed state is remembered
 * so it doesn't nag people who already know.
 */
export function HowItWorks({ startCollapsed = false }: { startCollapsed?: boolean } = {}) {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      // An explicit choice wins; otherwise collapse when the caller says the
      // page already has something more useful to show.
      if (stored !== null) return stored === '1'
    } catch {
      // Storage unavailable - fall through to the caller's preference.
    }
    return startCollapsed
  })

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0')
    } catch {
      // Storage unavailable - the preference just won't persist.
    }
  }, [collapsed])

  return (
    <section className="mb-6 overflow-hidden rounded-2xl border border-accent/25 bg-gradient-to-br from-accent/8 via-surface to-cyan/8">
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        aria-expanded={!collapsed}
        className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left sm:px-6"
      >
        <div className="min-w-0">
          <h2 className="text-sm font-bold uppercase tracking-wider text-accent-soft">
            How GridEdge works
          </h2>
          <p className="mt-1 text-sm text-text-muted">
            Enter any prop line and get a probability it goes over — built from the player's recent
            form and how the opposing defense performs against players like them.
          </p>
        </div>
        <ChevronDownIcon
          className={clsx(
            'h-5 w-5 shrink-0 text-text-faint transition-transform duration-200',
            !collapsed && 'rotate-180',
          )}
        />
      </button>

      {!collapsed && (
        <div className="border-t border-border/70 px-5 pb-5 pt-5 sm:px-6">
          <ol className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {STEPS.map((step, i) => (
              <li key={step.title} className="flex gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent/12 text-accent-soft">
                  <step.icon className="h-5 w-5" />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-text">
                    <span className="text-text-faint">{i + 1}.</span> {step.title}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-text-muted">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>

          <p className="mt-5 rounded-xl bg-surface-2/80 px-4 py-3 text-xs leading-relaxed text-text-muted">
            <span className="font-semibold text-text">A note on the numbers.</span> These are
            statistical estimates from past performance, not predictions or betting advice. A 60%
            over probability means the model expects that result in roughly 6 of 10 similar
            situations — it says nothing about any single game.
          </p>
        </div>
      )}
    </section>
  )
}
