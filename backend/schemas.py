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


class ModelInfo(BaseModel):
    key: str
    description: str


class ScheduleGame(BaseModel):
    gameday: str
    home_team: str
    away_team: str
    week: Optional[int] = None


class ErrorResponse(BaseModel):
    detail: str
