"""Tests for the CORS allow-list.

These exist because of a real outage: CORS_ORIGINS was maintained only as a
Render dashboard value, a Blueprint re-sync rewrote it from render.yaml back to
`http://localhost:5173`, and the deployed frontend lost access to its own API.
Every panel showed "Could not reach the API" while the API itself was healthy,
because a CORS rejection surfaces in the browser as a generic fetch failure.

The guarantee worth pinning is that the deployed frontend is allowed no matter
what the environment says.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.main import (  # noqa: E402
    _BASELINE_ORIGINS, _origin_regex, resolve_cors_origins,
)

PRODUCTION = "https://nfl-player-props.vercel.app"


def test_production_frontend_is_allowed_when_the_env_var_is_unset():
    assert PRODUCTION in resolve_cors_origins(None)


def test_production_frontend_survives_the_blueprint_reset_that_caused_the_outage():
    """The exact broken value: localhost only, as render.yaml used to pin it."""
    assert PRODUCTION in resolve_cors_origins("http://localhost:5173")


def test_production_frontend_survives_an_unrelated_override():
    assert PRODUCTION in resolve_cors_origins("https://props.example.com")


def test_local_dev_origins_are_always_allowed():
    origins = resolve_cors_origins(None)
    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:5173" in origins


def test_configured_origins_are_added_not_substituted():
    origins = resolve_cors_origins("https://a.example.com,https://b.example.com")
    assert "https://a.example.com" in origins
    assert "https://b.example.com" in origins
    for baseline in _BASELINE_ORIGINS:
        assert baseline in origins


def test_blank_and_messy_values_are_ignored():
    assert resolve_cors_origins("") == _BASELINE_ORIGINS
    assert resolve_cors_origins("  ,  ,") == _BASELINE_ORIGINS
    assert resolve_cors_origins(" https://x.example.com , ") == [
        *_BASELINE_ORIGINS, "https://x.example.com",
    ]


def test_no_duplicates_when_a_baseline_origin_is_also_configured():
    origins = resolve_cors_origins(PRODUCTION)
    assert origins.count(PRODUCTION) == 1


def test_vercel_preview_deployments_match_the_regex():
    pattern = re.compile(_origin_regex)
    for preview in [
        "https://nfl-player-props-git-main-iens126.vercel.app",
        "https://nfl-player-props-abc123.vercel.app",
    ]:
        assert pattern.fullmatch(preview), preview


def test_regex_does_not_match_unrelated_vercel_projects():
    pattern = re.compile(_origin_regex)
    for other in [
        "https://some-other-app.vercel.app",
        "https://nfl-player-props.evil.com",
        "http://nfl-player-props-x.vercel.app",  # not https
    ]:
        assert not pattern.fullmatch(other), other
