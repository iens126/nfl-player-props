"""Sanity checks on a built data bundle, before it gets committed and served.

A static site fails quietly: if the refresh produces a broken or truncated
bundle, the CDN keeps serving it and the app looks fine while being wrong. So
the pipeline fails loudly here instead — every check is something that has
either bitten this project or would be invisible from the outside.

Usage:
    python scripts/check_bundle.py DIR [--compare-metrics OLD_MANIFEST]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# A refresh that makes the model meaningfully worse is more likely to be a bad
# upstream data week than a genuine improvement, so it stops the pipeline.
MAE_REGRESSION_TOLERANCE = 0.15  # 15% worse
MIN_PLAYERS = 200
MIN_TEAMS = 32


class Failures(list):
    def check(self, condition: bool, message: str) -> None:
        if not condition:
            self.append(message)


def load(path: Path):
    with path.open() as handle:
        return json.load(handle)


def check_bundle(root: Path) -> Failures:
    failures = Failures()

    required = ['manifest.json', 'index.json', 'reference.json', 'aggregates.json']
    for name in required:
        failures.check((root / name).exists(), f"missing {name}")
    if failures:
        return failures

    manifest = load(root / 'manifest.json')
    index = load(root / 'index.json')
    reference = load(root / 'reference.json')
    aggregates = load(root / 'aggregates.json')

    # Freshness: a manifest stamped in the past means the build reused stale
    # state; one stamped in the future means a clock problem.
    generated = datetime.fromisoformat(manifest['generated_at'])
    age_hours = (datetime.now(timezone.utc) - generated).total_seconds() / 3600
    failures.check(-1 < age_hours < 24, f"manifest generated_at is {age_hours:.1f}h old")

    # Volume: catches a truncated or partially-failed build.
    players = index['players']
    failures.check(len(players) >= MIN_PLAYERS, f"only {len(players)} players indexed")
    failures.check(len(reference['teams']) >= MIN_TEAMS, f"only {len(reference['teams'])} teams")
    failures.check(len(reference['schedule']) > 0, "schedule is empty")

    # Every indexed player must actually have a file - an index entry without
    # one is a guaranteed 404 the moment someone selects that player.
    missing = [p['name'] for p in players if not (root / f"players/{p['slug']}.json").exists()]
    failures.check(not missing, f"{len(missing)} indexed players have no data file: {missing[:5]}")

    # Defense summaries back the matchup panel for every possible opponent.
    for team in reference['teams']:
        failures.check(
            (root / f"defense/{team['abbr']}.json").exists(),
            f"missing defense summary for {team['abbr']}",
        )

    # Aggregates the projection maths reads; empty means every weight is zero.
    for key in ('position_allowed', 'signal_reliability', 'defense_weekly', 'league_team_stats'):
        failures.check(bool(aggregates.get(key)), f"aggregates.{key} is empty")

    constants = aggregates.get('constants', {})
    failures.check(bool(constants.get('current_season')), "constants.current_season missing")
    failures.check(bool(constants.get('stat_map')), "constants.stat_map missing")

    # Spot-check one player file end to end.
    sample = root / f"players/{players[0]['slug']}.json"
    player = load(sample)
    failures.check('summary' in player and 'games' in player, f"{sample.name} is malformed")
    failures.check(len(player.get('games', [])) > 0, f"{sample.name} has no games")

    return failures


def check_metrics(root: Path, previous: Path) -> Failures:
    """Compare trained-model accuracy against the last good build."""
    failures = Failures()
    before = load(previous).get('model_metrics', {})
    after = load(root / 'manifest.json').get('model_metrics', {})

    if not before:
        return failures

    for stat, old in before.items():
        new = after.get(stat)
        if not new:
            failures.append(f"{stat}: model disappeared from this build")
            continue
        old_mae, new_mae = old.get('val_mae'), new.get('val_mae')
        if not old_mae or not new_mae:
            continue
        if new_mae > old_mae * (1 + MAE_REGRESSION_TOLERANCE):
            failures.append(
                f"{stat}: validation error rose from {old_mae:.2f} to {new_mae:.2f} "
                f"(>{MAE_REGRESSION_TOLERANCE:.0%} worse)"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('--compare-metrics', help='previous manifest.json to compare against')
    args = parser.parse_args()

    root = Path(args.directory)
    failures = check_metrics(root, Path(args.compare_metrics)) if args.compare_metrics \
        else check_bundle(root)

    if failures:
        print(f"Bundle check FAILED ({len(failures)} problem(s)):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("Bundle check passed.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
