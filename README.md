# GridEdge — NFL Player Props Analytics

A statistical analytics tool for NFL player props: recent-form and career
breakdowns, opponent defense matchups, a trained projection model with
over/under probabilities for any prop line, and a browsable board of live
sportsbook lines.

**Live app:** [nfl-player-props.vercel.app](https://nfl-player-props.vercel.app)

> GridEdge is an independent project, not affiliated with the NFL, NFLPA, or any
> team. Projections are statistical estimates for informational purposes only —
> not betting advice, and not a guarantee of future results.

## What it does

Pick a player and an opponent, and GridEdge shows:

- **Recent + season averages** for every prop stat that player actually has data for
- **Player stability** — coefficient-of-variation-based consistency rating (HIGH / MEDIUM / LOW)
- **Performance chart** — the player's output vs. what the selected defense allows, with Last 3 / 5 / 10 / Season / Career views and a prop-line reference line
- **Game log** — full week-by-week table, with over/under games highlighted once a prop line is entered
- **Defensive matchup** — the opponent's pass/run defense averages and live league rank (computed from the current season's team data)
- **Prop analysis** — enter any line and get a projection with over/under probabilities, plus a plain-English explanation of how the number was produced
- **Hit rates** — how often the player has actually cleared that line, over the last 3/5/10 games, this season, and their whole career
- **Odds Board** — a plain list of DraftKings/FanDuel/BetMGM/Caesars lines for a whole game; click any row to open that player's history and projection (needs a free API key; see below)
- **Model transparency** — every model explains what it looks at in plain language and links out to a description of the technique; the trained model reports its own measured accuracy on a season it never saw

## Architecture: there is no analytics server

GridEdge is a **static site**. The pandas work happens once, on a schedule, and
the results ship as JSON that a CDN serves; the browser holds those inputs and
does the joins and arithmetic itself.

```
   GitHub Actions (daily)                    Vercel CDN            Browser
   ─────────────────────                     ──────────            ───────
   nflverse ─▶ scripts/precompute.py ──▶ /data/*.json ──────▶ src/engine/*
              (pandas, model training)     ~670 KB gzip       (projection maths)

                                          /api/odds*  ◀────── live odds only
                                          (serverless, needs a secret key)
```

Why this shape:

- **Nothing to keep warm.** The previous FastAPI service ran on Render's free
  tier, which spins down when idle; a cold start measured **14.3 seconds**
  against **127 ms** warm. A CDN has no such state.
- **It costs nothing.** No always-on process, no paid instance.
- **It can't be taken down by a bad deploy.** There is no Python in production.
  If the refresh job breaks, the last good bundle keeps serving.
- **It doesn't constrain the analytics.** The bundle ships *data*, not
  precomputed answers: full game logs plus bounded aggregates. Any future
  question — cross-player correlations, league-wide screens, new stat slices —
  is answerable in the browser without changing the pipeline.

`backend/` still exists, but as a **build-time library, not a deployed
service**: `scripts/precompute.py` calls its route functions directly so the
bundle can't drift from the response shapes the frontend expects.

### Keeping the browser maths honest

The projection models were ported from Python to TypeScript, which is exactly
the kind of change that produces the same shapes with subtly different numbers.
So `scripts/precompute.py` emits **golden fixtures** straight from the Python
engine, and `frontend/src/engine/engine.test.ts` replays 200 of them against
the TypeScript. They currently agree to 1e-5 on every projection, probability,
matchup weight and hit rate.

If you change the maths: change the Python first, regenerate the bundle, then
mirror it in TypeScript until the fixtures pass again.

## Tech stack

- **Frontend:** React + TypeScript + Vite + Tailwind CSS v4, Headless UI, Recharts
- **Browser engine:** `frontend/src/engine/` — the projection models, matchup
  weight, hit rates and chart series, ported from `core/`
- **Analytics engine:** `core/` — pandas pipeline, closed-form probability
  models, and the trained ridge regression. Runs at build time only.
- **Build-time API:** FastAPI in `backend/`, used by the precompute script
- **Data source:** [nflverse](https://github.com/nflverse) via `nflreadpy` (eight seasons)
- **Odds:** [The Odds API](https://the-odds-api.com) (optional, free tier)

## Project structure

```
core/                analytics engine — data loading, stability, defense
                     analysis, projection models, trained model, odds client
backend/             FastAPI app; now a build-time library, not a service
scripts/
  precompute.py      builds the static bundle + parity fixtures
  check_bundle.py    sanity + model-regression guards for CI
api/                 Vercel serverless functions (live odds only)
frontend/
  src/engine/        the browser-side maths, ported from core/
  public/data/       the generated bundle (committed, served by the CDN)
tests/               Python suites: projection maths, ML model, odds, CORS
.github/workflows/   scheduled data refresh
vercel.json          static hosting + serverless function config
```

## Running locally

You need Python once, to build the data bundle. After that the app is just a
static site.

### 1. Build the data bundle

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && cd ..
python scripts/precompute.py --out frontend/public/data
```

Takes about 20 seconds and writes ~670 KB gzipped. Add `--skip-models` to skip
retraining (much faster) or `--players 25` for a quick partial build.

The bundle is committed to the repo, so if you only want to run the frontend
you can skip this entirely.

### 2. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. No backend process — everything except live odds
is computed in the browser from `frontend/public/data`.

### 3. Live odds locally (optional)

The odds endpoints are serverless functions, so they need the Vercel CLI:

```bash
npm i -g vercel
ODDS_API_KEY=your-key vercel dev
```

Without it, the odds panels explain that they're unconfigured and everything
else works normally.

## Environment variables

**Build time / serverless functions**

| Variable       | Purpose                                                                 |
| -------------- | ------------------------------------------------------------------------ |
| `ODDS_API_KEY` | Optional. Enables the Odds Board and per-player lines — free key at [the-odds-api.com](https://the-odds-api.com). Set it in the Vercel dashboard. |
| `ODDS_CACHE_MINUTES` | Optional (default 10). How long odds are cached; higher spends fewer API credits |
| `CAREER_SEASONS` | Optional (default 8). Seasons of history the precompute loads |

**Frontend** (`frontend/.env.example`)

| Variable                | Purpose                                                    |
| ----------------------- | ---------------------------------------------------------- |
| `VITE_ODDS_BASE_URL`    | Optional. Where the odds functions live; empty means same-origin `/api`, which is what you want on Vercel. |

There is no `CORS_ORIGINS` any more: the data is same-origin static files, and
the odds functions are served from the same domain as the app.

## The data pipeline

1. `core/data_loader.py` pulls team stats, player stats, depth charts, rosters,
   and the schedule from nflverse via `nflreadpy`, and caches the resulting
   DataFrames in memory for 6 hours so repeated requests don't re-fetch/re-parse.
   Season selection is dynamic (nflreadpy resolves the current season from
   today's date), so the app tracks the season rollover automatically instead
   of a hardcoded year. A player's current team/position always comes from
   the live roster (`load_rosters`), not their stat lines - stat lines only
   update once games are played, so during an offseason they'd otherwise
   still show a player's team from months-old games, missing any trades or
   cuts since.
2. `core/stats_utils.py` computes per-stat mean/std/coefficient-of-variation
   after removing outlier games, and buckets that into a stability rating.
3. `core/defense_analysis.py` aggregates every team's pass/run defense and
   ranks all 32 teams against each other for each stat.
4. `core/monte_carlo_sim.py` computes the matchup-adjustment weight from the
   opponent's defensive profile (different logic for QBs vs. skill positions —
   see the in-app Methodology page for the full writeup) and still holds the
   original triangular Monte Carlo sampler.
5. `core/projection_models.py` holds the probability models, and
   `core/projection.py` orchestrates them: it builds a recency-weighted window
   of a player's last 10 games, applies the matchup weight, and evaluates the
   line. Models are **closed-form rather than sampled**, which makes them
   exact, deterministic (the same inputs always return the same answer), and
   fast enough that every model is scored on every request — that's what the
   "model consensus" panel shows. See below for why the triangular sampler was
   demoted to a comparison option.
6. `backend/main.py` is a thin FastAPI layer that calls into `core/` and
   converts DataFrames into typed JSON responses — the frontend never sees
   pandas.

### Why the projection model changed

The original engine fit a triangular distribution to the min/mean/max of a
player's last 3 games and drew 10,000 samples from it. That had four problems:

- **It could report a hard 0%.** A triangular is bounded by the window it was
  fit to, so a player whose last three games topped out at 70 yards got exactly
  0% for an 80-yard line — not a credible answer.
- **Three games is a tiny sample**, and one outlier redefined the whole shape.
- **Sampling made results wobble** — the same request twice returned different
  numbers, which reads as a bug.
- **A triangle doesn't match the data.** Yardage is continuous, non-negative
  and right-skewed with real zero games; receptions and touchdowns are discrete
  counts. Neither is triangular.

The current models fit shapes that match the stat (zero-inflated lognormal for
yardage, negative binomial for counts, a smoothed empirical fit that assumes no
shape at all), weight recent games more heavily over a longer window, and shrink
the spread toward a league-typical value when there's little history — so a
thin sample produces a wider, less confident projection rather than false
precision. `tests/test_projection_models.py` pins these properties down.

## Where the numbers come from

The projection is produced by code, not by a language model. Two kinds of model
are available, and the difference matters:

- **Trained** (`ml`) — a ridge regression fitted to roughly 34,000 historical
  player-games. It learned its own weights from the data; the UI shows which
  signals it actually leans on (measured by permutation importance) and how
  accurate it was on a held-out season. Its uncertainty comes from the errors
  it really made, banded by projection size, so a probability reflects this
  model's own track record rather than an assumed curve.
- **Specified** (`ensemble`, `lognormal`, `negbin`, `empirical`, `triangular`)
  — probability distributions chosen by hand to match how each stat behaves.
  Nothing is learned; they are fitted to one player's recent games.

Both are auditable in the repo, and every model is scored on every request so
the consensus panel can show where they disagree.

Two properties are enforced by tests because they are the easy things to get
silently wrong:

- **No leakage.** Every feature for a game is built only from games before it,
  and validation is a time split on the most recent season. Shuffling rows
  would leak the future into the past and inflate the accuracy.
- **Calibration.** When the model says 40%, that should happen about 40% of the
  time. It is checked on held-out games, and reported in the UI.

Football is mostly noise: the model explains under half the game-to-game
variation, which is normal for this problem. The app says so rather than
implying more precision than exists.

## Live sportsbook odds (optional)

Set `ODDS_API_KEY` to switch on the **Odds Board** — a browsable list of
DraftKings/FanDuel/BetMGM/Caesars lines for a whole game, where any row opens
that player's history and projection. The same lines also appear on a player's
own page. Nothing is scored, ranked, or flagged as value: it is a listing, not
a recommender. Get a free key at [the-odds-api.com](https://the-odds-api.com)
(500 credits/month).

Player props are billed **per event per market**, so responses are cached for
`ODDS_CACHE_MINUTES` (default 10) and only the market currently on screen is
ever requested. Without a key nothing breaks — the panel explains that it is
unconfigured.

The comparison shown is the model's over probability against the book's
*implied* probability. Implied probability includes the book's margin, so the
two sides of a market sum to over 100%; the app says so, and refuses to compare
against a book that is pricing a different number than the one you entered.

## Tests

The projection maths has a test suite covering the properties that make a
projection trustworthy — closed-form results agreeing with brute-force
sampling, probabilities monotone in the line, confidence that scales with
evidence, and no crashes on degenerate windows (a single game, all zeros).

```bash
backend/.venv/bin/python tests/test_projection_models.py   # distribution maths
backend/.venv/bin/python tests/test_ml_model.py            # trained model + hit rates
backend/.venv/bin/python tests/test_odds.py                # sportsbook client
```

The odds tests use a recorded response shape, so they cover the parsing,
player matching and every degraded path without needing a key or a network
call — that code would otherwise ship unexercised.

It also runs under `pytest` if you have it, but needs no test dependency in the
deployed image.

## Deployment

One Vercel project, free tier, no server to manage and nothing to keep warm.

### 1. Deploy to Vercel

1. Sign in at [vercel.com](https://vercel.com) with GitHub.
2. **Add New → Project**, pick this repo.
3. Leave **Root Directory** as the repo root — `vercel.json` handles the rest
   (it builds `frontend/`, serves `frontend/dist`, and picks up the Python
   functions in `api/`).
4. Optionally add `ODDS_API_KEY` to enable live odds.
5. Deploy.

That's the whole deployment. The data bundle is committed, so it ships with the
build.

### 2. Turn on the scheduled refresh

`.github/workflows/refresh-data.yml` rebuilds the bundle daily at 09:15 UTC and
commits it, which triggers a Vercel redeploy. It needs no secrets — just make
sure Actions is enabled for the repo.

You can also run it by hand from the Actions tab (**Refresh data bundle → Run
workflow**), with an option to skip model retraining for a faster data-only run.

### Retiring the old Render service

The FastAPI service is no longer used by the site and can be deleted from the
Render dashboard. `render.yaml` and `backend/Dockerfile` are kept so the API can
still be run as a service if you ever want it (`uvicorn backend.main:app`), but
nothing in production depends on it.

## Maintenance

Steady-state upkeep is close to zero, but the failure mode is quiet rather than
loud: if the refresh stops, the CDN keeps serving the last good bundle and the
site looks healthy while going stale. Three things guard against that.

1. **The footer shows the data's age**, and warns after 36 hours — a failed
   refresh becomes visible rather than silent.
2. **`scripts/check_bundle.py` runs in CI** before anything is committed. It
   fails the build on a stale timestamp, too few players or teams, an index
   entry with no data file behind it, empty aggregates, or a malformed player
   file.
3. **A model-regression guard** fails the build if validation error rises more
   than 15% against the previous bundle — a bad upstream data week can't
   silently ship a worse model.

Things worth knowing:

- **GitHub disables scheduled workflows on public repos after ~60 days of
  repository inactivity.** It emails a warning first. If the loop ever goes
  quiet during a long off-season, re-enable it from the Actions tab.
- **Season rollover is the one predictable annual chore**, in early September.
  nflverse resolves "current season" differently for stats (last completed
  season) than for rosters (current roster year), and the precompute has to
  pick correctly for each; the `CAREER_SEASONS` window also slides.
- **Upstream schema changes** break the build rather than the site. The last
  good bundle keeps serving while you fix it — but only if you read the failure
  email.

## Testing what was built

- `cd frontend && npx tsc -b && npm run build` — typecheck + production build
- `cd backend && source .venv/bin/activate && uvicorn backend.main:app --port 8000` — then hit `/health`, `/docs`, and the endpoints under `/api/*`
- Full user flow (team/position/player selection, prop line, chart, game log, defense matchup, methodology) was exercised end-to-end in a real browser during development.

## Known limitations

- Free-tier hosting means the API may take a few seconds to respond after a
  period of inactivity (cold start) — this is expected and acceptable for a
  portfolio-stage project.
- The projection model is intentionally simple (see Methodology in-app for
  the full explanation) and does not account for injuries, weather, game
  script, or other real-world factors.
