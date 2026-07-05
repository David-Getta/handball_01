"""Meccs-szimulátor: valósághű szintetikus Tracking videó nélkül (fejlesztéshez,
teszteléshez, a kliens fejlesztéséhez, a becslő demonstrálásához)."""

from .match_simulator import (
    simulate_ground_truth, simulate_with_panning_camera,
)

__all__ = ["simulate_ground_truth", "simulate_with_panning_camera"]
