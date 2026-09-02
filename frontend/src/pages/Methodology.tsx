import { Card, SectionHeading } from '../components/common/Card'

export default function Methodology() {
  return (
    <div className="mx-auto max-w-3xl px-4 pb-24 pt-8 sm:px-6 lg:px-8">
      <h1 className="text-2xl font-extrabold tracking-tight text-text sm:text-3xl">Methodology</h1>
      <p className="mt-2 text-sm text-text-muted">
        What GridEdge calculates, where the data comes from, and what the numbers do and don't mean.
      </p>

      <div className="mt-8 space-y-6">
        <Card>
          <SectionHeading title="Data Source" />
          <p className="text-sm leading-relaxed text-text-muted">
            All player, team, and schedule data comes from{' '}
            <a href="https://github.com/nflverse" target="_blank" rel="noreferrer" className="text-accent-soft underline underline-offset-2">
              nflverse
            </a>
            , a public, community-maintained dataset of NFL play-by-play and weekly statistics.
            GridEdge is an independent project and is not affiliated with the NFL, NFLPA, or any
            team. Team colors shown in the UI are used only as visual accents; no official team
            marks or logos are displayed.
          </p>
        </Card>

        <Card>
          <SectionHeading title="Recent Form & Stability" />
          <p className="text-sm leading-relaxed text-text-muted">
            For each prop stat, GridEdge computes the player's mean, standard deviation, and
            coefficient of variation (CV = std ÷ mean) across the season, after removing games
            that are statistical outliers (games more than 2.5 standard deviations from the
            player's average). A lower CV means more consistent week-to-week production. We bucket
            CV into <span className="font-semibold text-over">HIGH</span> (below 0.35),{' '}
            <span className="font-semibold text-warn">MEDIUM</span> (0.35–0.65), and{' '}
            <span className="font-semibold text-under">LOW</span> (above 0.65) stability ratings.
          </p>
        </Card>

        <Card>
          <SectionHeading title="Defensive Matchup & League Ranks" />
          <p className="text-sm leading-relaxed text-text-muted">
            Pass and rush defense numbers are each team's average allowed per game across their
            season so far. League ranks are computed by ranking all 32 teams against each other on
            the current dataset — rank 1 is always the most favorable defense for that stat (e.g.
            fewest passing yards allowed, or most interceptions forced). These ranks are calculated
            live from the loaded data, not hardcoded.
          </p>
        </Card>

        <Card>
          <SectionHeading title="Projection Model" />
          <div className="space-y-3 text-sm leading-relaxed text-text-muted">
            <p>
              <span className="font-semibold text-text">1. Recent-form distribution.</span> The
              model takes the player's last 3 games for the selected stat and fits a triangular
              distribution from the minimum, mean, and maximum of that window — a simple way to
              capture both central tendency and recent variability without assuming a specific
              statistical shape.
            </p>
            <p>
              <span className="font-semibold text-text">2. Matchup weight.</span> A weight shifts
              the distribution up or down based on the opponent:
            </p>
            <ul className="ml-4 list-disc space-y-1.5">
              <li>
                <span className="font-medium text-text">Quarterbacks:</span> weight = k × player's
                stat std-dev × −(opponent z-score), where the opponent's z-score compares their
                allowed average for that stat against the full-league mean and standard deviation.
              </li>
              <li>
                <span className="font-medium text-text">RB / WR / TE:</span> weight = k × (what
                the opponent allows to players at the same depth-chart rank − the league average at
                that rank). A player's depth-chart rank is resolved from nflverse depth charts via
                fuzzy name matching.
              </li>
            </ul>
            <p>
              <span className="font-semibold text-text">3. Simulation.</span> 10,000 samples are
              drawn from the fitted distribution and each is shifted by the matchup weight. The
              mean of the resulting simulated outcomes is the model's projection. The share of
              simulations at or above your entered line is the "over" probability; the remainder is
              "under."
            </p>
          </div>
        </Card>

        <Card className="border-warn/30 bg-warn/5">
          <SectionHeading title="Disclaimer" />
          <p className="text-sm leading-relaxed text-text-muted">
            Projections and probabilities on GridEdge are statistical estimates produced by a
            simplified model, not guarantees or professional betting advice. Historical performance
            does not guarantee future results — injuries, game script, weather, coaching decisions,
            and many other factors this model does not account for can materially change outcomes.
            This application is provided for informational and analytical purposes only.
          </p>
        </Card>
      </div>
    </div>
  )
}
