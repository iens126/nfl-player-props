"""Pydantic response/request models for the API. Keeps DataFrames out of the
HTTP layer - every route hands the frontend clean, typed JSON."""

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class TeamOut(BaseModel):
    abbr: str
    name: str
    color: Optional[str] = None
    color2: Optional[str] = None


class PlayerListItem(BaseModel):
    name: str
    team: str
    position: str


class StabilityStat(BaseModel):
    stat: str
    mean: float
    std: float
    cv: float
    rating: Optional[str] = None


class PlayerSummary(BaseModel):
    name: str
    team: str
    position: str
    headshot_url: Optional[str] = None
    games_played: int
    available_stats: list[str]
    stability: list[StabilityStat]
    season_averages: dict[str, float]
    recent_averages: dict[str, float]


class GameLogResponse(BaseModel):
    player: str
    columns: list[str]
    rows: list[dict[str, Any]]


class ChartWeek(BaseModel):
    week: int
    season: Optional[int] = None
    label: Optional[str] = None
    opponent: Optional[str] = None
    player_value: Optional[float] = None
    defense_allowed: Optional[float] = None


class ChartResponse(BaseModel):
    stat: str
    defense_stat: str
    defense_team: str
    weeks: list[ChartWeek]
    player_average: Optional[float] = None
    defense_average: Optional[float] = None


class DefenseStatRank(BaseModel):
    rank: int
    of: int
    value: float


class DefenseSection(BaseModel):
    weekly: list[dict[str, Any]]
    season_average: dict[str, Optional[float]]
    recent_average: dict[str, Optional[float]]
    league_rank: dict[str, DefenseStatRank]
    league_size: int


class DefenseSummaryOut(BaseModel):
    team: str
    passing: DefenseSection
    rushing: DefenseSection


class ProjectionRequest(BaseModel):
    player: str = Field(min_length=1, max_length=100)
    opponent: str = Field(min_length=2, max_length=4)
    stat: str = Field(min_length=1, max_length=50)
    line: float = Field(gt=0, le=2000)
    model: str = Field(default='ensemble', max_length=32)

    @field_validator('opponent')
    @classmethod
    def uppercase_opponent(cls, v: str) -> str:
        return v.strip().upper()


class ProjectionResponse(BaseModel):
    player: str
    opponent: str
    stat: str
    line: float
    projection: float
    prob_over: float
    prob_under: float
    weight: float
    model: str
    model_label: str
    form_average: float
    season_average: float
    recent_games: int
    effective_games: float
    std_dev: float
    window_games: int
    # Every model's over probability for this same line, so the UI can show
    # whether the models agree (a tight cluster) or the answer depends heavily
    # on the assumed distribution shape (a wide spread).
    alternatives: dict[str, float]
    # How often the player actually reached this line, by lookback window.
    hit_rates: list["HitRate"] = []
    ml_projection: Optional[float] = None


class HitRate(BaseModel):
    window: str
    games: int
    hits: int
    rate: float
    average: float


class FeatureImportance(BaseModel):
    feature: str
    label: str
    share: float


class ModelInfo(BaseModel):
    key: str
    description: str
    # Layman-facing explanation of the approach, what it looks at, and where
    # to read more about the technique itself.
    summary: Optional[str] = None
    attends_to: list[str] = []
    learn_more_url: Optional[str] = None
    learn_more_label: Optional[str] = None
    trained: bool = False
    metrics: Optional[dict] = None
    importance: list[FeatureImportance] = []


class BookLine(BaseModel):
    book: str
    line: Optional[float] = None
    over_price: Optional[float] = None
    under_price: Optional[float] = None
    implied_over: Optional[float] = None
    implied_under: Optional[float] = None
    last_update: Optional[str] = None


class OddsResponse(BaseModel):
    status: str
    message: Optional[str] = None
    books: list[BookLine] = []
    consensus_line: Optional[float] = None
    # Carried so the client can request this game's alternate ladder without
    # re-resolving the matchup. response_model filters unknown fields, so
    # omitting it here silently dropped it from the payload.
    event_id: Optional[str] = None
    market: Optional[str] = None
    fetched_at: Optional[str] = None
    requests_remaining: Optional[str] = None


class AlternateBookPrice(BaseModel):
    book: str
    over_price: Optional[float] = None
    under_price: Optional[float] = None


class AlternateLine(BaseModel):
    line: float
    books: list[AlternateBookPrice] = []


class AlternatesResponse(BaseModel):
    status: str
    message: Optional[str] = None
    player: Optional[str] = None
    stat: Optional[str] = None
    lines: list[AlternateLine] = []
    fetched_at: Optional[str] = None
    requests_remaining: Optional[str] = None


class OddsGame(BaseModel):
    id: str
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    commence_time: Optional[str] = None


class OddsGamesResponse(BaseModel):
    status: str
    message: Optional[str] = None
    games: list[OddsGame] = []


class OddsBoardEntry(BaseModel):
    player: str
    consensus_line: Optional[float] = None
    books: list[BookLine] = []
    # Resolved from the roster so a click through to the analysis page carries
    # the matchup it came from instead of re-guessing it. Null when the book's
    # spelling of the name doesn't match nflverse's.
    team: Optional[str] = None
    opponent: Optional[str] = None


class OddsBoardResponse(BaseModel):
    status: str
    message: Optional[str] = None
    entries: list[OddsBoardEntry] = []
    game: Optional[OddsGame] = None
    market: Optional[str] = None
    stat: Optional[str] = None
    fetched_at: Optional[str] = None
    requests_remaining: Optional[str] = None


class ScheduleGame(BaseModel):
    gameday: str
    home_team: str
    away_team: str
    week: Optional[int] = None


class ErrorResponse(BaseModel):
    detail: str
