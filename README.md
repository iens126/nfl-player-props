# GridEdge — NFL Player Props Analytics

A statistical analytics tool for NFL player props: recent-form breakdowns, opponent
defense matchups, and a matchup-adjusted Monte Carlo projection with over/under
probabilities for any prop line.

**Live app:** _not yet deployed — see [Deployment](#deployment) below._

> GridEdge is an independent project, not affiliated with the NFL, NFLPA, or any
> team. Projections are statistical estimates for informational purposes only —
> not betting advice, and not a guarantee of future results.

## What it does

Pick a player and an opponent, and GridEdge shows:

- **Recent + season averages** for every prop stat that player actually has data for
- **Player stability** — coefficient-of-variation-based consistency rating (HIGH / MEDIUM / LOW)
- **Performance chart** — the player's weekly output vs. what the selected defense allows, with Last 3 / 5 / 10 / Season views and a prop-line reference line
- **Game log** — full week-by-week table, with over/under games highlighted once a prop line is entered
- **Defensive matchup** — the opponent's pass/run defense averages and live league rank (computed from the current season's team data)
- **Prop analysis** — enter any line and get a simulated projection with over/under probabilities, plus a plain-English explanation of how the number was produced

## Tech stack

- **Frontend:** React + TypeScript + Vite + Tailwind CSS v4, Headless UI (accessible dropdowns), Recharts
- **Backend:** FastAPI (Python), serving a clean JSON API over the analytics engine
- **Analytics engine:** `core/` — pandas-based data pipeline, unchanged in substance from the original project, refactored to be callable from a web backend (in-memory caching, no more global module-level execution)
- **Data source:** [nflverse](https://github.com/nflverse) via `nflreadpy` (team stats, player stats, depth charts, schedules)

## Project structure

```
core/       analytics engine — data loading, stability, defense analysis, Monte Carlo projection
backend/    FastAPI app that wraps core/ and exposes it as a JSON API
frontend/   React + Vite single-page app
render.yaml Render Blueprint for deploying the API
```

## How frontend and backend talk to each other

The frontend calls the backend over plain HTTP/JSON, using the base URL in
`VITE_API_BASE_URL` (a Vite env var, baked in at build time). In production
this points at the deployed Render API; locally it points at
`http://127.0.0.1:8000`. The backend allows cross-origin requests only from
the origins listed in its `CORS_ORIGINS` env var.

No cookies, sessions, or auth — every endpoint is read-only except the
projection endpoint, which is a stateless POST that runs a simulation and
returns the result.

## Running locally

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
uvicorn backend.main:app --reload --port 8000
```

The API is now at `http://127.0.0.1:8000` (interactive docs at `/docs`, health check at `/health`).

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.development   # VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

Open `http://localhost:5173`.

## Environment variables

**Backend** (`backend/.env.example`)

| Variable       | Purpose                                                                 |
| -------------- | ------------------------------------------------------------------------ |
| `CORS_ORIGINS` | Comma-separated list of origins allowed to call the API (your deployed frontend URL + `http://localhost:5173` for local dev) |

**Frontend** (`frontend/.env.example`)

| Variable              | Purpose                                    |
| --------------------- | ------------------------------------------- |
| `VITE_API_BASE_URL`   | Base URL of the FastAPI backend, no trailing slash |

## The data pipeline

1. `core/data_loader.py` pulls team stats, player stats, depth charts, and the
   schedule from nflverse via `nflreadpy`, and caches the resulting
   DataFrames in memory for 6 hours so repeated requests don't re-fetch/re-parse.
   Season selection is dynamic (nflreadpy resolves the current season from
   today's date), so the app tracks the season rollover automatically instead
   of a hardcoded year.
2. `core/stats_utils.py` computes per-stat mean/std/coefficient-of-variation
   after removing outlier games, and buckets that into a stability rating.
3. `core/defense_analysis.py` aggregates every team's pass/run defense and
   ranks all 32 teams against each other for each stat.
4. `core/monte_carlo_sim.py` is the projection engine: it fits a triangular
   distribution to a player's last 3 games, computes a matchup-adjustment
   weight from the opponent's defensive profile (different logic for QBs vs.
   skill positions — see the in-app Methodology page for the full writeup),
   runs 10,000 simulated draws, and returns a projection plus over/under
   probability for any line.
5. `backend/main.py` is a thin FastAPI layer that calls into `core/` and
   converts DataFrames into typed JSON responses — the frontend never sees
   pandas.

## Deployment

Both services deploy for free, straight from GitHub, with no server to manage:

- **Backend → [Render](https://render.com)** (free web service tier — sleeps
  after 15 minutes of inactivity, cold-starts in a few seconds on the next
  request; no credit card required)
- **Frontend → [Vercel](https://vercel.com)** (free static hosting for the
  Vite build, global CDN, automatic HTTPS, no credit card required)

### 1. Push this repo to GitHub

```bash
gh repo create gridedge --public --source=. --push
# or create a repo on github.com and:
git remote add origin <your-repo-url>
git push -u origin main
```

### 2. Deploy the API on Render

1. Sign in at [render.com](https://render.com) with GitHub.
2. **New → Blueprint**, pick this repo. Render reads `render.yaml` at the repo
   root and provisions the `gridedge-api` web service automatically.
3. Once deployed, note the service URL (e.g. `https://gridedge-api.onrender.com`).

### 3. Deploy the frontend on Vercel

1. Sign in at [vercel.com](https://vercel.com) with GitHub.
2. **Add New → Project**, pick this repo.
3. Set **Root Directory** to `frontend`. Vercel auto-detects the Vite preset
   (build command / output directory also come from `frontend/vercel.json`).
4. Add an environment variable: `VITE_API_BASE_URL` = the Render URL from step 2.
5. Deploy. Note the resulting URL (e.g. `https://gridedge.vercel.app`).

### 4. Connect them

Back in the Render dashboard, set the `CORS_ORIGINS` env var on `gridedge-api`
to your Vercel URL (comma-separate if you also want to allow a preview URL or
custom domain), and redeploy. Update the "Live app" link at the top of this
README with your Vercel URL.

### Alternative: Docker

`backend/Dockerfile` is provided for any platform that prefers a container
over Render's native Python runtime (build from the repo root: `docker build
-f backend/Dockerfile -t gridedge-api .`, context must be the repo root since
it copies both `backend/` and `core/`).

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
