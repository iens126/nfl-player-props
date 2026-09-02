"""FastAPI layer around the core analytics engine (core/).

Every route here is a thin adapter: it calls into core/, converts the
resulting DataFrame/dict into a typed Pydantic response, and turns known
failure modes (player not found, bad stat category, insufficient data) into
clean 4xx responses instead of a stack trace.
"""

import logging
import os
import sys
import threading
from pathlib import Path

# Make sure the repo root (parent of backend/) is importable as `core` regardless
# of the working directory the process was started from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from core.data_loader import (
    bettable_columns, get_pos, find_player, load_player_data, load_team_data,
    load_team_meta, load_current_rosters, current_team_and_position,
    upcoming_schedule, clear_cache,
)
from core.stats_utils import determine_stability, stability_rating
from core.stat_visualization import comparison_series
from core.defense_analysis import defense_summary as core_defense_summary
from core.monte_carlo_sim import SIM_WINDOW
from core.projection import project as core_project
from core.projection_models import MODELS

from backend.schemas import (
    TeamOut, PlayerListItem, PlayerSummary, StabilityStat, GameLogResponse,
    ChartResponse, DefenseSummaryOut, ProjectionRequest, ProjectionResponse,
    ScheduleGame, ModelInfo,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("player_props_api")

POSITION_GROUPS = ['QB', 'WR', 'TE', 'RB']

app = FastAPI(
    title="NFL Player Props API",
    description="Analytics API for the NFL Player Props application.",
    version="1.0.0",
)

_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
def warm_cache():
    """Pull the nflverse datasets in the background as soon as the app boots.

    Render's free tier spins the service down when idle, so the first request
    after a wake-up would otherwise pay for both the container start *and* the
    dataset download. Warming in a daemon thread keeps startup (and the health
    check that gates traffic) instant, while making it likely the data is
    already resident by the time a user's first request lands.
    """
    def _warm():
        try:
            load_team_data()
            load_player_data()
            load_current_rosters()
            load_team_meta()
            logger.info("Warm-up complete: nflverse datasets cached")
        except Exception:
            # A failed warm-up is not fatal - the first request will just load
            # the data itself, exactly as it did before.
            logger.exception("Cache warm-up failed; falling back to lazy loading")

    threading.Thread(target=_warm, name="cache-warmup", daemon=True).start()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=500, content={"detail": "Something went wrong processing that request."})


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/admin/refresh-cache")
def refresh_cache():
    """Force the next data access to re-fetch from nflverse. Cheap and safe -
    no destructive effect, just drops the in-memory cache."""
    clear_cache()
    return {"status": "cache cleared"}


# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------

@app.get("/api/teams", response_model=list[TeamOut])
def list_teams():
    team_stats = load_team_data()
    meta = load_team_meta()
    teams = sorted(team_stats['team'].dropna().unique().tolist())
    return [
        TeamOut(
            abbr=t,
            name=meta.get(t, {}).get('full', t),
            color=meta.get(t, {}).get('color'),
            color2=meta.get(t, {}).get('color2'),
        )
        for t in teams
    ]


@app.get("/api/positions", response_model=list[str])
def list_positions():
    return POSITION_GROUPS


@app.get("/api/models", response_model=list[ModelInfo])
def list_models():
    """The projection models a client can ask for, for a model picker."""
    return [ModelInfo(key=k, description=v) for k, v in MODELS.items()]


@app.get("/api/players", response_model=list[PlayerListItem])
def list_players(
    team: str | None = Query(default=None, description="Team abbreviation, e.g. KC"),
    position: str | None = Query(default=None, description="Position group, e.g. WR"),
    q: str | None = Query(default=None, description="Case-insensitive substring search on player name"),
    limit: int = Query(default=50, ge=1, le=1000),
):
    # Current team/position comes from the live roster, not the stat lines -
    # a player's most recent stat row can be a season stale once they've been
    # traded, cut, or re-signed elsewhere in the offseason. Still require a
    # stat history so the app never lists a player it can't actually analyze.
    roster = load_current_rosters().reset_index().rename(columns={'full_name': 'player_display_name'})
    analyzable_names = set(load_player_data()['player_display_name'].unique())
    df = roster[roster['player_display_name'].isin(analyzable_names) & roster['position'].isin(POSITION_GROUPS)]

    if team:
        df = df[df['team'] == team.upper()]
    if position:
        df = df[df['position'] == position.upper()]
    if q:
        df = df[df['player_display_name'].str.contains(q, case=False, na=False)]

    unique = df.sort_values('player_display_name').head(limit)

    return [
        PlayerListItem(name=row['player_display_name'], team=row['team'], position=row['position'])
        for _, row in unique.iterrows()
    ]


@app.get("/api/schedule/upcoming", response_model=list[ScheduleGame])
def schedule_upcoming(days: int = Query(default=7, ge=1, le=30)):
    schedule = upcoming_schedule(days=days)
    games = []
    for _, row in schedule.iterrows():
        games.append(ScheduleGame(
            gameday=str(row['gameday']),
            home_team=row['home_team'],
            away_team=row['away_team'],
            week=int(row['week']) if 'week' in row and pd.notna(row['week']) else None,
        ))
    return games


# --------------------------------------------------------------------------
# Player analysis
# --------------------------------------------------------------------------

def _load_player_df(name: str) -> pd.DataFrame:
    df = find_player(name)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data found for player '{name}'")
    return df


@app.get("/api/players/{name}", response_model=PlayerSummary)
def player_summary(name: str):
    df = _load_player_df(name)
    available_stats = [c for c in bettable_columns if c in df.columns]

    _player_name, summary = determine_stability(df)
    stability = [
        StabilityStat(
            stat=stat,
            mean=float(row['mean']),
            std=float(row['std']),
            cv=float(row['cv']),
            rating=stability_rating(row['cv']),
        )
        for stat, row in summary.iterrows()
    ]

    season_averages = {c: float(df[c].mean()) for c in available_stats}
    recent = df.sort_values('week').tail(SIM_WINDOW)
    recent_averages = {c: float(recent[c].mean()) for c in available_stats}

    headshots = df['headshot_url'].dropna().unique() if 'headshot_url' in df.columns else []
    team, pos = current_team_and_position(name, df)

    return PlayerSummary(
        name=name,
        team=team,
        position=pos,
        headshot_url=headshots[0] if len(headshots) > 0 else None,
        games_played=len(df),
        available_stats=available_stats,
        stability=stability,
        season_averages=season_averages,
        recent_averages=recent_averages,
    )


@app.get("/api/players/{name}/gamelog", response_model=GameLogResponse)
def player_gamelog(name: str):
    df = _load_player_df(name)
    available_stats = [c for c in bettable_columns if c in df.columns]
    columns = ['week', 'opponent_team'] + available_stats

    rows = []
    for _, row in df.sort_values('week', ascending=False).iterrows():
        rec = {'week': int(row['week']), 'opponent': row['opponent_team']}
        for c in available_stats:
            rec[c] = float(row[c]) if pd.notna(row[c]) else None
        rows.append(rec)

    return GameLogResponse(player=name, columns=['week', 'opponent'] + available_stats, rows=rows)


@app.get("/api/players/{name}/chart", response_model=ChartResponse)
def player_chart(
    name: str,
    stat: str = Query(...),
    opponent: str = Query(..., min_length=2, max_length=4),
    range: str = Query(default="season", pattern="^(3|5|10|season)$"),
):
    _load_player_df(name)  # 404s cleanly if the player doesn't exist
    last_n = None if range == "season" else int(range)
    try:
        result = comparison_series(name, stat, opponent.upper(), last_n=last_n)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


# --------------------------------------------------------------------------
# Defense
# --------------------------------------------------------------------------

@app.get("/api/defense/{team}", response_model=DefenseSummaryOut)
def defense_matchup(team: str):
    team = team.upper()
    valid_teams = set(load_team_data()['team'].unique())
    if team not in valid_teams:
        raise HTTPException(status_code=404, detail=f"Unknown team '{team}'")
    return core_defense_summary(team)


# --------------------------------------------------------------------------
# Projection
# --------------------------------------------------------------------------

@app.post("/api/projection", response_model=ProjectionResponse)
def projection(req: ProjectionRequest):
    player_df = _load_player_df(req.player)
    player_team, _pos = current_team_and_position(req.player, player_df)

    if req.opponent == player_team:
        raise HTTPException(status_code=400, detail="Opponent must be different from the player's own team")

    valid_teams = set(load_team_data()['team'].unique())
    if req.opponent not in valid_teams:
        raise HTTPException(status_code=404, detail=f"Unknown opponent team '{req.opponent}'")

    if req.stat not in bettable_columns:
        raise HTTPException(status_code=400, detail=f"Unsupported stat category '{req.stat}'")

    if req.stat not in player_df.columns:
        raise HTTPException(status_code=400, detail=f"'{req.stat}' has no recorded data for {req.player}")

    if req.model not in MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model '{req.model}'")

    try:
        result = core_project(req.player, req.opponent, req.stat, req.line, model=req.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ProjectionResponse(
        player=req.player,
        opponent=req.opponent,
        stat=req.stat,
        line=req.line,
        **result,
    )
