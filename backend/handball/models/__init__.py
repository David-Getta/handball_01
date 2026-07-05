"""Adatmodellek: a központi Tracking (`tracking`) és a létszám-/esemény-idővonal
(`events`). Ezek tiszta stdlib dataclass-ok, JSON-ra szerializálva — ez a
backend és a Flutter-kliens közötti szerződés."""

from .tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from .events import RosterTimeline, Suspension

__all__ = [
    "Match", "MatchMeta", "Frame", "PlayerPosition", "Ball", "Team",
    "PositionSource", "RosterTimeline", "Suspension",
]
