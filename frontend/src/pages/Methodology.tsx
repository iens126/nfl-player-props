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
          <SectionHeading title="Trained Model" subtitle="The default when you pick &quot;Trained ridge regression&quot;" />
          <div className="space-y-3 text-sm leading-relaxed text-text-muted">
            <p>
              Nothing on this page is a language model's opinion about a game. The trained
              model is a{' '}
              <a
                href="https://en.wikipedia.org/wiki/Ridge_regression"
                target="_blank"
                rel="noreferrer"
                className="text-accent-soft underline underline-offset-2"
              >
                ridge regression
              </a>{' '}
              fitted in code to roughly 34,000 historical player-games across eight seasons.
              It worked out its own weights from that data — nobody hand-tuned which signals
              matter, and the app shows you which ones it ended up relying on.
            </p>
            <p>
              <span className="font-semibold text-text">What it looks at.</span> A player's
              recent and longer-run form, their recent usage (targets, carries or pass
              attempts — volume drives yardage), their career baseline, how erratic they are,
              how much history exists, what the opposing defense has given up to that
              position, and the week of the season.
            </p>
            <p>
              <span className="font-semibold text-text">How it avoids fooling itself.</span>{' '}
              Every feature for a given game is computed only from games played before it, and
              the model is scored on the most recent season, which it never trained on. Doing
              this the lazy way — shuffling games at random — would let the future leak into
              the past and produce accuracy that vanishes in real use.
            </p>
            <p>
              <span className="font-semibold text-text">Where the probability comes from.</span>{' '}
              Not an assumed bell curve: the model records how wrong it actually was on games
              it never saw, grouped by the size of the projection (a 5-yard projection misses
              by a little, a 60-yard one by a lot). The over probability is the share of those
              real historical errors that would have cleared your line.
            </p>
            <p>
              <span className="font-semibold text-text">How good is it?</span> The panel next
              to each projection reports the model's typical miss, how much of the
              game-to-game variation it explains, and its calibration — whether a stated 40%
              actually happened about 40% of the time. Be realistic about the ceiling: NFL
              production is mostly noise, and the model explains well under half the
              variation. It is a way of pricing uncertainty, not a forecast.
            </p>
          </div>
        </Card>

        <Card>
          <SectionHeading title="Hit Rates & Career Data" />
          <p className="text-sm leading-relaxed text-text-muted">
            Alongside every projection, GridEdge counts how many times the player has actually
            reached your line — over their last 3, 5 and 10 games, this season, and their
            whole career (eight seasons of game logs). This involves no modelling at all; it
            is a tally of games that happened. Where the career rate and the season rate
            diverge sharply, that usually reflects a change in role rather than luck, and the
            app flags it. The performance chart has a matching{' '}
            <span className="font-semibold text-text">Career</span> view.
          </p>
        </Card>

        <Card>
          <SectionHeading title="Sportsbook Odds" />
          <div className="space-y-3 text-sm leading-relaxed text-text-muted">
            <p>
              When an odds API key is configured, live lines from DraftKings, FanDuel, BetMGM
              and Caesars appear next to the model's number, via{' '}
              <a
                href="https://the-odds-api.com"
                target="_blank"
                rel="noreferrer"
                className="text-accent-soft underline underline-offset-2"
              >
                The Odds API
              </a>
              .
            </p>
            <p>
              A book's price converts to an{' '}
              <span className="font-semibold text-text">implied probability</span> that
              includes their margin — which is why the over and under add up to more than
              100%. A raw comparison against that number therefore overstates any
              disagreement, so the app shows the margin explicitly and refuses to compare
              against a book pricing a different line than the one you entered.
            </p>
            <p>
              A gap between the model and a book is a disagreement, not an edge. Books price
              in injuries, weather, game script and late news that this model never sees, and
              they are right far more often than a public model is. Informational only.
            </p>
          </div>
        </Card>

        <Card>
          <SectionHeading title="Specified Models" subtitle="The non-trained alternatives" />
          <div className="space-y-3 text-sm leading-relaxed text-text-muted">
            <p>
              <span className="font-semibold text-text">1. Recency-weighted form.</span> The model
              takes the player's last 10 games for the selected stat and weights them so recent
              games count for more — weights halve every three games back. This keeps the model
              responsive to current form without letting a single game define the whole picture.
              The <span className="font-medium text-text">effective sample size</span> shown with a
              projection is what that weighting leaves in statistical terms.
            </p>
            <p>
              <span className="font-semibold text-text">2. A shape that matches the stat.</span>{' '}
              Rather than assume one distribution for everything, the model fits the family that
              matches how the stat behaves:
            </p>
            <ul className="ml-4 list-disc space-y-1.5">
              <li>
                <span className="font-medium text-text">Yardage</span> uses a zero-inflated
                lognormal — continuous, non-negative, right-skewed (a ceiling game is further from
                the median than a floor game), with an explicit allowance for games held to zero.
              </li>
              <li>
                <span className="font-medium text-text">Counting stats</span> (receptions, carries,
                targets, touchdowns) use a negative binomial, which handles the game-to-game usage
                swings that make these more variable than a Poisson would allow. When a player is
                steady enough that variance doesn't exceed the mean, it collapses to Poisson.
              </li>
              <li>
                <span className="font-medium text-text">Smoothed empirical</span> uses the player's
                actual games with no assumed shape, which is the only option that can represent
                genuinely bimodal usage.
              </li>
            </ul>
            <p>
              With few games to go on, the spread is shrunk toward a league-typical value, so a
              short history yields a wider, less confident projection instead of false precision.
            </p>
            <p>
              <span className="font-semibold text-text">3. Matchup weight.</span> A weight shifts
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
                that rank). A player's depth-chart rank is resolved from nflverse depth charts by
                name, falling back to fuzzy matching.
              </li>
            </ul>
            <p>
              <span className="font-semibold text-text">4. Exact probabilities.</span> The
              over/under probabilities are the fitted distribution's mass above and below your line,
              computed in closed form rather than by sampling. That makes them exact and repeatable
              — the same inputs always return the same answer — and fast enough that every model is
              scored on every request. The{' '}
              <span className="font-medium text-text">model consensus</span> panel shows all of
              them: when they cluster, the read is robust; when they spread out, the answer depends
              heavily on which distribution you assume.
            </p>
            <p>
              The original <span className="font-medium text-text">triangular Monte Carlo</span>{' '}
              method — 10,000 samples from a triangle fitted to the last three games — remains
              selectable for comparison. It is bounded by the observed window, so lines outside a
              player's recent range resolve to 0% or 100%; the other models do not have that
              limitation.
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
