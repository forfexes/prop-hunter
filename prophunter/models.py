"""Pydantic models for type-safe data flow."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Prop(BaseModel):
    model_config = ConfigDict(extra="allow")
    player: str
    market: str
    odds: float = Field(gt=1.0, lt=1000.0)
    point: Optional[float] = None
    sport: str
    emoji: str
    game: str
    home: Optional[str] = None
    away: Optional[str] = None
    commence_time: Optional[datetime] = None
    pinnacle_odds: Optional[float] = None
    pinnacle_opp_odds: Optional[float] = None
    game_total: Optional[float] = None
    enrichment: Optional[str] = None
    features: dict = Field(default_factory=dict)


PickType = Literal["single", "ladder", "betbuilder", "kombi2", "big", "super"]


class LadderLeg(BaseModel):
    market: str
    odds: float = Field(gt=1.0)
    stake: float = Field(ge=0.0)


class Pick(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: PickType
    odds: float = Field(gt=1.0)
    stake: float = Field(ge=0.0, le=5.0)
    tier: Optional[int] = None
    emoji: Optional[str] = None
    player: Optional[str] = None
    team: Optional[str] = None
    market: Optional[str] = None
    direction: Optional[Literal["over", "under", "yes", "no"]] = None
    probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    analysis: Optional[str] = None
    legs: Optional[List[str]] = None
    picks: Optional[List[LadderLeg]] = None
    game: Optional[str] = None
    ev: Optional[float] = None
    edge_pct: Optional[float] = None

    @field_validator("stake")
    @classmethod
    def cap_stake(cls, v: float) -> float:
        return round(min(v, 5.0), 2)


class AIResponse(BaseModel):
    picks: List[Pick]


class HistoricalPick(BaseModel):
    date: str
    player: str
    team: str
    market: str
    sport: str
    odds: float
    stake: float
    direction: Optional[str] = None
    probability: Optional[float] = None
    dedup_key: str
    result: Optional[Literal["pending", "win", "loss", "push", "void"]] = "pending"
    profit: Optional[float] = None
    closing_odds: Optional[float] = None
    clv_pct: Optional[float] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def composite_dedup_key(player: str, market: str, point: Optional[float], direction: Optional[str]) -> str:
    return "|".join([
        (player or "").lower().strip(),
        (market or "").lower().strip(),
        f"{point:g}" if point is not None else "",
        (direction or "over").lower(),
    ])
