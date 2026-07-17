"""Meccs-szimulátor: valósághű szintetikus Tracking videó nélkül (fejlesztéshez,
teszteléshez, a kliens fejlesztéséhez, a becslő demonstrálásához)."""

from .match_simulator import (
    append_demo_episodes, simulate_ground_truth,
    simulate_with_panning_camera,
)

__all__ = ["append_demo_episodes", "simulate_ground_truth",
           "simulate_with_panning_camera"]
