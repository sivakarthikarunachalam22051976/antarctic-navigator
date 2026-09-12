"""Explainable A* routing over sea-ice and iceberg risk."""
from __future__ import annotations

import heapq
import math

import numpy as np


VESSEL_PROFILES = {
    # Partial sea ice remains traversable but receives an increasingly steep
    # cost. A cell at 100% concentration is treated as a hard exclusion.
    # This avoids the previous 0.90/0.98 cutoffs that could disconnect real
    # station routes because of coarse-grid interpolation.
    "standard": {
        "ice_penalty": 11.0,
        "ice_exponent": 2.0,
        "blocked_threshold": 1.0,
        "iceberg_weight": 18.0,
    },
    "ice_capable": {
        "ice_penalty": 6.0,
        "ice_exponent": 1.7,
        "blocked_threshold": 1.0,
        "iceberg_weight": 12.0,
    },
}


NEIGHBOURS = (
    (-1, 0),
    (1, 0),
    (0, -1),
    (0, 1),
    (-1, -1),
    (-1, 1),
    (1, -1),
    (1, 1),
)


def _heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _step_cost(
    ice: float,
    diagonal: bool,
    risk: float,
    profile: dict[str, float],
) -> float:
    distance = math.sqrt(2.0) if diagonal else 1.0
    return distance * (
        1.0
        + profile["ice_penalty"] * max(0.0, ice) ** profile["ice_exponent"]
        + profile["iceberg_weight"] * max(0.0, risk)
    )


def find_route(
    concentration: np.ndarray,
    start: tuple[int, int],
    goal: tuple[int, int],
    iceberg_risk: np.ndarray | None = None,
    vessel_profile: str = "standard",
    navigable_mask: np.ndarray | None = None,
) -> tuple[list[tuple[int, int]], float]:
    """Find a lowest-cost route without traversing blocked/land cells."""
    profile = VESSEL_PROFILES.get(
        vessel_profile,
        VESSEL_PROFILES["standard"],
    )

    concentration = np.asarray(concentration, dtype=float)
    rows, cols = concentration.shape

    if navigable_mask is None:
        navigable = np.ones_like(concentration, dtype=bool)
    else:
        navigable = np.asarray(navigable_mask, dtype=bool)
        if navigable.shape != concentration.shape:
            raise ValueError("navigable_mask must have the same shape as concentration.")

    risk = (
        np.zeros_like(concentration, dtype=float)
        if iceberg_risk is None
        else np.asarray(iceberg_risk, dtype=float)
    )
    if risk.shape != concentration.shape:
        raise ValueError("iceberg_risk must have the same shape as concentration.")

    if not (0 <= start[0] < rows and 0 <= start[1] < cols):
        raise ValueError("Start point is outside the routing grid.")
    if not (0 <= goal[0] < rows and 0 <= goal[1] < cols):
        raise ValueError("Destination point is outside the routing grid.")

    if not navigable[start]:
        raise ValueError("Start point is not on a navigable ocean cell.")
    if not navigable[goal]:
        raise ValueError("Destination point is not on a navigable ocean cell.")

    if concentration[start] >= profile["blocked_threshold"]:
        raise ValueError("Start point lies inside an impassable ice cell for this vessel profile.")
    if concentration[goal] >= profile["blocked_threshold"]:
        raise ValueError("Destination lies inside an impassable ice cell for this vessel profile.")

    frontier: list[tuple[float, tuple[int, int]]] = [(0.0, start)]
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    cost_so_far: dict[tuple[int, int], float] = {start: 0.0}

    while frontier:
        _, current = heapq.heappop(frontier)

        if current == goal:
            break

        current_cost = cost_so_far[current]
        r, c = current

        for dr, dc in NEIGHBOURS:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue

            next_cell = (nr, nc)
            if not navigable[next_cell]:
                continue
            if concentration[next_cell] >= profile["blocked_threshold"]:
                continue

            new_cost = current_cost + _step_cost(
                float(concentration[nr, nc]),
                dr != 0 and dc != 0,
                float(risk[nr, nc]),
                profile,
            )

            if next_cell not in cost_so_far or new_cost < cost_so_far[next_cell]:
                cost_so_far[next_cell] = new_cost
                came_from[next_cell] = current
                priority = new_cost + _heuristic(next_cell, goal)
                heapq.heappush(frontier, (priority, next_cell))

    if goal not in came_from:
        raise ValueError("No safe route exists through the current forecast risk field.")

    path: list[tuple[int, int]] = []
    current: tuple[int, int] | None = goal
    while current is not None:
        path.append(current)
        current = came_from[current]

    path.reverse()
    return path, float(cost_so_far[goal])
