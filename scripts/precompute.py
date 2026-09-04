"""Build the static data bundle the frontend runs on.

The app used to need a live Python server for every page view. Almost none of
that work is actually per-request: nflverse box scores only change after games
are played, and the derived aggregates change with them. So this script does
the pandas work once, on a schedule, and writes plain JSON that a CDN can
serve. The browser then holds the inputs and does the joins and arithmetic
itself.

The important design rule is **ship data, not answers**. It would be smaller
still to precompute, say, every chart the UI can draw - but chart is
player x stat x opponent x range, which is millions of combinations and, worse,
freezes the app's analysis into whatever questions it asks today. Shipping the
underlying game logs and a handful of bounded aggregates costs about 700 KB
gzipped for the entire league across eight seasons, and leaves every future
question (cross-player correlations, league-wide screens, new stat slices)
answerable without touching this pipeline.

Route functions from backend/main.py are called directly rather than
reimplemented, so the bundle cannot drift from the API's response shapes.

Usage:
    python scripts/precompute.py [--out DIR] [--players N] [--skip-models]
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from core.data_loader import (
    bettable_columns, load_career_data, load_current_rosters, load_team_data,
    load_team_meta, pass_def, run_def, upcoming_schedule,
)
from core.monte_carlo_sim import POSITION_K, DEFAULT_K, STAT_MAP, by_positon_rank, pos_rank_map
from core.ml_model import USAGE_COLUMNS
from core.projection_models import HALF_LIFE_GAMES, MAX_WINDOW

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("precompute")

POSITION_GROUPS = ['QB', 'WR', 'TE', 'RB']
BUNDLE_VERSION = 1


def slug(name: str) -> str:
    """Filesystem- and URL-safe key for a player name."""
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', str(name).lower())).strip('-')


def _as_json(value):
    """Route functions return either a Pydantic model or a plain dict."""
    return value.model_dump(mode='json') if hasattr(value, 'model_dump') else value


def _clean(value, precision: int = 4):
    """NaN/NaT -> None, numpy scalars -> plain Python, recursively.

    Rounding keeps the bundle small; `precision` is raised for the parity
    fixtures, where a rounded expectation would mean the TypeScript port could
    only ever be checked as loosely as the fixture was written.
    """
    if isinstance(value, dict):
        return {k: _clean(v, precision) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v, precision) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else round(float(value), precision)
    if isinstance(value, float):
        return None if pd.isna(value) else round(value, precision)
    if value is pd.NaT or (not isinstance(value, (list, dict, str, bool)) and pd.isna(value)):
        return None
    return value


class Writer:
    """Writes JSON files and tracks what the bundle costs."""

    def __init__(self, root: Path):
        self.root = root
        self.files: list[tuple[str, int, int]] = []

    def write(self, relative: str, payload, precision: int = 4) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = json.dumps(_clean(payload, precision), separators=(',', ':')).encode()
        path.write_bytes(blob)
        self.files.append((relative, len(blob), len(gzip.compress(blob))))

    def report(self, group_prefixes: tuple[str, ...] = ('players/', 'defense/')) -> dict:
        grouped: dict[str, list[int]] = {}
        for name, raw, gz in self.files:
            key = next((p + '*' for p in group_prefixes if name.startswith(p)), name)
            grouped.setdefault(key, [0, 0, 0])
            grouped[key][0] += 1
            grouped[key][1] += raw
            grouped[key][2] += gz

        logger.info("\n%-28s %7s %12s %12s", "artifact", "files", "raw", "gzipped")
        for key, (count, raw, gz) in sorted(grouped.items(), key=lambda kv: -kv[1][2]):
            logger.info("%-28s %7d %10.1f KB %10.1f KB", key, count, raw / 1024, gz / 1024)
        total_raw = sum(f[1] for f in self.files)
        total_gz = sum(f[2] for f in self.files)
        logger.info("%-28s %7d %10.1f KB %10.1f KB", "TOTAL", len(self.files),
                    total_raw / 1024, total_gz / 1024)
        return {'files': len(self.files), 'raw_bytes': total_raw, 'gzip_bytes': total_gz}


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

def build_reference(writer: Writer) -> None:
    """Teams, positions and the schedule - small, and needed on first paint."""
    from backend.main import list_teams, schedule_upcoming

    # The odds provider names teams in full; the app works in abbreviations.
    # Emitted from the Python map so the two can't drift.
    from core.odds import ABBR_BY_TEAM_NAME

    writer.write('reference.json', {
        'teams': [_as_json(t) for t in list_teams()],
        'positions': POSITION_GROUPS,
        'schedule': [_as_json(g) for g in schedule_upcoming(days=200)],
        'team_abbr_by_name': dict(ABBR_BY_TEAM_NAME),
    })


def candidate_players() -> list:
    """Everyone the app is willing to analyse, per the live roster."""
    from backend.main import list_players
    return list_players(team=None, position=None, q=None, limit=1000)


def write_player_index(writer: Writer, players: list, available: set[str]) -> None:
    """The player picker.

    Written *after* the per-player files and filtered to those that exist:
    an index entry with no data file behind it is a guaranteed 404 the moment
    someone selects that player. The two lists can otherwise disagree because
    the index takes its position from the current roster while the game log
    takes it from the stat lines - a fullback listed at RB, for instance.
    """
    writer.write('index.json', {
        'players': [
            {'name': p.name, 'slug': slug(p.name), 'team': p.team, 'position': p.position}
            for p in players if p.name in available
        ],
    })


def build_players(writer: Writer, names: list[str]) -> list[str]:
    """Per-player summary plus the full career game log.

    One file each, ~2 KB gzipped, so the app fetches only the player being
    looked at. The game log is the raw material every client-side calculation
    works from - hit rates, the chart, and the projection window all derive
    from it rather than from anything precomputed here.
    """
    from backend.main import player_summary
    from fastapi import HTTPException

    # No position filter here: the index already decided who is analysable,
    # using the roster's position. Filtering again on the stat-line position
    # drops players the two datasets label differently.
    career = load_career_data()
    log_columns = ['season', 'week', 'team', 'opponent_team', 'position'] + \
                  [c for c in bettable_columns if c in career.columns]
    by_player = {n: g for n, g in career.groupby('player_display_name', observed=True)}

    written: list[str] = []
    for name in names:
        try:
            summary = _as_json(player_summary(name))
        except HTTPException:
            continue
        except Exception:
            logger.warning("  skipped %s (summary failed)", name)
            continue

        games = by_player.get(name)
        if games is None or games.empty:
            continue

        games = games.sort_values(['season', 'week'])[log_columns]
        writer.write(f'players/{slug(name)}.json', {
            'summary': summary,
            'games': games.to_dict('records'),
        })
        written.append(name)
    return written


def build_defense(writer: Writer, teams: list[str]) -> None:
    """Per-team defensive summaries. Depends only on the team, so all 32 fit."""
    from backend.main import defense_matchup
    from core.defense_roles import defense_roles
    from fastapi import HTTPException

    for team in teams:
        try:
            summary = _as_json(defense_matchup(team))
        except HTTPException:
            continue
        # What this defense allowed by opposing role, from play-by-play. Purely
        # descriptive - see core/defense_roles.py for why it isn't predictive.
        try:
            summary['roles'] = defense_roles(team)
        except Exception:
            logger.warning("  role breakdown failed for %s", team)
            summary['roles'] = []
        writer.write(f'defense/{team}.json', summary)


def build_aggregates(writer: Writer, teams: list[str], positions: list[str]) -> None:
    """Everything the projection and chart maths need beyond a player's own games.

    All of it is keyed by team/position/stat rather than by player, which is
    what keeps the bundle small: 32 teams x 4 positions x 12 stats is under two
    thousand rows, versus the millions it would take to precompute answers.
    """
    team_stats = load_team_data()

    # League mean/std per team stat, for the QB matchup z-score.
    league = {
        stat: {'mean': float(team_stats[stat].mean()), 'std': float(team_stats[stat].std())}
        for stat in {s for s, _ in STAT_MAP.values()} if stat in team_stats.columns
    }

    # What each defense allows, weekly - the chart's comparison bar and the
    # QB weight's team average both read from this.
    defense_weekly = {}
    for team in teams:
        entry = {}
        for kind, frame in (('pass', pass_def(team)), ('run', run_def(team))):
            cols = [c for c in frame.columns if c not in ('Team', 'Opponent')]
            entry[kind] = frame[cols].to_dict('records')
        defense_weekly[team] = entry

    # Positional rank aggregates: what a defense allows to a WR1 vs a WR2, and
    # the league baseline at each rank.
    # Every position an indexed player is labelled with in their stat lines -
    # not just the four the picker groups by. A fullback listed at RB on the
    # roster still has FB stat lines, and the matchup weight looks the rank up
    # by that stat-line position, so leaving FB out silently zeroed his weight.
    rank_aggregates = {}
    for pos in positions:
        for stat in bettable_columns:
            for defense in ['NFL'] + teams:
                try:
                    frame = by_positon_rank(defense, pos, stat)
                except Exception:
                    continue
                means = frame['mean'].tolist()
                if all(pd.isna(m) for m in means):
                    continue
                rank_aggregates[f'{defense}|{pos}|{stat}'] = means

    # Career chart reference: what a defense allowed to a position, per season.
    career = load_career_data()
    career = career[career['position'].isin(positions)]
    career_allowed: dict[str, dict] = {}
    grouped = career.groupby(['opponent_team', 'position', 'season'], observed=True)
    for (defense, pos, season), chunk in grouped:
        key = f'{defense}|{pos}'
        bucket = career_allowed.setdefault(key, {})
        bucket[str(int(season))] = {
            stat: float(chunk[stat].mean())
            for stat in bettable_columns
            if stat in chunk.columns and not pd.isna(chunk[stat].mean())
        }

    ranks = {k: (None if (isinstance(v, float) and np.isnan(v)) else int(v))
             for k, v in pos_rank_map().items()}

    # Six decimals rather than the default four: the matchup weight is a
    # difference of two of these averages scaled by k, so rounding here shows
    # up directly in every projection. The extra precision costs a few KB.
    writer.write('aggregates.json', {
        'league_team_stats': league,
        'defense_weekly': defense_weekly,
        'rank_aggregates': rank_aggregates,
        'career_defense_allowed': career_allowed,
        'depth_chart_ranks': ranks,
        'constants': {
            'stat_map': {k: list(v) for k, v in STAT_MAP.items()},
            'position_k': POSITION_K,
            'default_k': DEFAULT_K,
            'half_life_games': HALF_LIFE_GAMES,
            'max_window': MAX_WINDOW,
            'bettable_columns': bettable_columns,
            # The season load_player_data() resolves to. The projection window
            # and the matchup weight both work off "this season only", so the
            # browser has to know where the career log stops being history.
            'current_season': int(load_team_data()['season'].max()),
            'usage_columns': USAGE_COLUMNS,
        },
    }, precision=6)


def build_models(writer: Writer) -> dict:
    """Trained model coefficients, small enough to run inference in the browser.

    Residuals are stored as percentiles rather than the full training sample:
    they are only ever consumed as a quantile lookup, and the downsample is
    lossless to four decimal places while cutting the payload ~100x.
    """
    from backend.main import list_models
    from core.ml_model import get_model

    percentiles = np.arange(0, 100.5, 0.5)
    models, metrics = {}, {}

    for stat in bettable_columns:
        try:
            trained = get_model(stat)
        except Exception:
            logger.warning("  model training failed for %s", stat)
            continue
        if trained is None:
            continue
        models[stat] = {
            'features': trained.features,
            'weights': trained.weights.tolist(),
            'mean': trained.mean.tolist(),
            'scale': trained.scale.tolist(),
            'bin_edges': trained.bin_edges.tolist(),
            'residual_percentiles': [
                np.percentile(r, percentiles).round(3).tolist() for r in trained.residuals
            ],
            'metrics': trained.metrics,
            'importance': trained.importance[:6],
        }
        metrics[stat] = trained.metrics

    writer.write('models.json', {
        'models': models,
        'catalog': [_as_json(m) for m in list_models(stat=None)],
    })
    return metrics


def build_fixtures(writer: Writer, names: list[str]) -> None:
    """Golden outputs, so the TypeScript port can be checked against Python.

    Porting the projection maths to the browser is the one part of this
    migration that can silently produce different numbers. These fixtures pin
    what the Python engine returns for a spread of real players, stats and
    lines; the frontend test suite replays them.
    """
    from core.projection import project

    cases, sample = [], names[:400]
    rng = np.random.default_rng(7)
    for name in sample:
        for stat in ('receiving_yards', 'receptions', 'rushing_yards', 'passing_yards'):
            for opponent in ('BAL', 'KC'):
                for line in (0.5, 25.5, 60.5):
                    try:
                        result = project(name, opponent, stat, line, model='ensemble')
                    except Exception:
                        continue
                    cases.append({
                        'player': name, 'stat': stat, 'opponent': opponent, 'line': line,
                        'expected': {
                            'projection': result['projection'],
                            'prob_over': result['prob_over'],
                            'weight': result['weight'],
                            'form_average': result['form_average'],
                            'alternatives': result['alternatives'],
                            'hit_rates': result['hit_rates'],
                        },
                    })
                    if len(cases) >= 250:
                        break
                if len(cases) >= 250:
                    break
            if len(cases) >= 250:
                break
        if len(cases) >= 250:
            break

    if len(cases) > 200:
        keep = rng.choice(len(cases), 200, replace=False)
        cases = [cases[i] for i in sorted(keep)]
    writer.write('fixtures.json', {'cases': cases}, precision=12)
    logger.info("  %d parity fixtures", len(cases))


# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='frontend/public/data', help='output directory')
    parser.add_argument('--players', type=int, default=0, help='limit players (for a quick run)')
    parser.add_argument('--skip-models', action='store_true')
    parser.add_argument('--skip-fixtures', action='store_true')
    args = parser.parse_args()

    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    writer = Writer(root)
    started = time.time()

    logger.info("Building static bundle -> %s", root)

    teams = sorted(load_team_data()['team'].dropna().unique().tolist())

    logger.info("  reference data...")
    build_reference(writer)

    logger.info("  player index...")
    players = candidate_players()
    if args.players:
        players = players[:args.players]
    names = [p.name for p in players]

    logger.info("  %d player files...", len(names))
    written = build_players(writer, names)
    write_player_index(writer, players, set(written))
    if len(written) != len(names):
        logger.info("    (%d indexed players had no usable game log)", len(names) - len(written))

    logger.info("  defense summaries...")
    build_defense(writer, teams)

    logger.info("  aggregates...")
    career_all = load_career_data()
    positions = sorted(
        career_all[career_all['player_display_name'].isin(written)]['position']
        .dropna().astype(str).unique().tolist()
    )
    logger.info("    positions covered: %s", ', '.join(positions))
    build_aggregates(writer, teams, positions)

    metrics = {}
    if not args.skip_models:
        logger.info("  training models...")
        metrics = build_models(writer)

    if not args.skip_fixtures:
        logger.info("  parity fixtures...")
        build_fixtures(writer, written)

    career = load_career_data()
    seasons = sorted(int(s) for s in career['season'].dropna().unique())

    # The manifest is what makes staleness visible: the UI reads generated_at
    # and can say how old the data is, so a silently failed refresh doesn't
    # look like a healthy site serving last week's numbers.
    writer.write('manifest.json', {
        'version': BUNDLE_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'seasons': seasons,
        'players': len(written),
        'teams': len(teams),
        'model_metrics': metrics,
    })

    stats = writer.report()
    logger.info("\nDone in %.0fs — %.0f KB gzipped over the wire for the whole league.",
                time.time() - started, stats['gzip_bytes'] / 1024)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
