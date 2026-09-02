export function Footer() {
  return (
    <footer className="border-t border-border/80 py-8">
      <div className="mx-auto max-w-7xl px-4 text-xs leading-relaxed text-text-faint sm:px-6 lg:px-8">
        <p>
          GridEdge is an independent analytics project and is not affiliated with, endorsed by, or
          sponsored by the NFL or any team. Projections and probabilities are statistical model
          outputs generated from historical performance data — they are estimates, not guarantees,
          and past results do not predict future outcomes. For informational and analytical
          purposes only.
        </p>
        <p className="mt-3">Data via nflverse. © {new Date().getFullYear()} GridEdge.</p>
      </div>
    </footer>
  )
}
