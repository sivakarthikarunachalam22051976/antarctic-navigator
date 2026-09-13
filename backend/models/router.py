"""Explainable A* routing with mission-aware route alternatives."""
from __future__ import annotations

import heapq
import math
from typing import Any

import numpy as np


VESSEL_PROFILES = {
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


ROUTE_OBJECTIVES = {
    "safest": {
        "label": "Safest",
        "description": "Minimises modeled environmental exposure while preserving navigability.",
        "ice_multiplier": 2.0,
        "iceberg_multiplier": 2.2,
    },
    "fastest": {
        "label": "Fastest",
        "description": "Finds the shortest traversable path while retaining land and 100% sea-ice hard exclusions.",
        "ice_multiplier": 0.0,
        "iceberg_multiplier": 0.0,
    },
    "balanced": {
        "label": "Balanced",
        "description": "Trades off distance, sea-ice exposure and projected iceberg risk.",
        "ice_multiplier": 1.0,
        "iceberg_multiplier": 1.0,
    },
}


MISSION_PROFILES: dict[str, dict[str, Any]] = {
    "resupply": {
        "label": "Resupply / station logistics",
        "description": "Protect mission reliability while limiting unnecessary environmental exposure.",
        "weights": {"distance": 0.25, "risk": 0.40, "iceberg": 0.20, "freshness": 0.15},
    },
    "research_transit": {
        "label": "Research transit",
        "description": "Balance transit efficiency with environmental conditions for planned research movement.",
        "weights": {"distance": 0.35, "risk": 0.30, "iceberg": 0.20, "freshness": 0.15},
    },
    "time_critical": {
        "label": "Time-critical transfer",
        "description": "Prioritise shorter transit while retaining hard ice and land exclusions.",
        "weights": {"distance": 0.55, "risk": 0.20, "iceberg": 0.15, "freshness": 0.10},
    },
}


PRIORITY_PROFILES: dict[str, dict[str, Any]] = {
    "safety_first": {
        "label": "Safety first",
        "weights": {"distance": 0.20, "risk": 0.50, "iceberg": 0.25, "freshness": 0.05},
    },
    "balanced": {
        "label": "Balanced",
        "weights": {"distance": 0.35, "risk": 0.35, "iceberg": 0.20, "freshness": 0.10},
    },
    "time_sensitive": {
        "label": "Time sensitive",
        "weights": {"distance": 0.55, "risk": 0.20, "iceberg": 0.15, "freshness": 0.10},
    },
}


ICE_EXPOSURE_LIMITS = {
    "low": 0.50,
    "medium": 0.75,
    "high": 0.95,
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
    extra_cost: float = 0.0,
) -> float:
    distance = math.sqrt(2.0) if diagonal else 1.0
    return distance * (
        1.0
        + profile["ice_penalty"] * max(0.0, ice) ** profile["ice_exponent"]
        + profile["iceberg_weight"] * max(0.0, risk)
    ) + max(0.0, float(extra_cost))


def find_route(
    concentration: np.ndarray,
    start: tuple[int, int],
    goal: tuple[int, int],
    iceberg_risk: np.ndarray | None = None,
    vessel_profile: str = "standard",
    navigable_mask: np.ndarray | None = None,
    objective: str = "balanced",
    extra_cost_grid: np.ndarray | None = None,
) -> tuple[list[tuple[int, int]], float]:
    """Find a lowest-cost route using a transparent objective profile."""
    vessel = VESSEL_PROFILES.get(
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

    if extra_cost_grid is None:
        extra = np.zeros_like(concentration, dtype=float)
    else:
        extra = np.asarray(extra_cost_grid, dtype=float)
        if extra.shape != concentration.shape:
            raise ValueError("extra_cost_grid must have the same shape as concentration.")

    if not (0 <= start[0] < rows and 0 <= start[1] < cols):
        raise ValueError("Start point is outside the routing grid.")
    if not (0 <= goal[0] < rows and 0 <= goal[1] < cols):
        raise ValueError("Destination point is outside the routing grid.")

    if not navigable[start]:
        raise ValueError("Start point is not on a navigable ocean cell.")
    if not navigable[goal]:
        raise ValueError("Destination point is not on a navigable ocean cell.")

    if concentration[start] >= vessel["blocked_threshold"]:
        raise ValueError("Start point lies inside an impassable ice cell for this vessel profile.")
    if concentration[goal] >= vessel["blocked_threshold"]:
        raise ValueError("Destination lies inside an impassable ice cell for this vessel profile.")

    objective_config = ROUTE_OBJECTIVES.get(
        objective,
        ROUTE_OBJECTIVES["balanced"],
    )
    profile = dict(vessel)
    profile["ice_penalty"] *= float(objective_config["ice_multiplier"])
    profile["iceberg_weight"] *= float(objective_config["iceberg_multiplier"])

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
                float(extra[nr, nc]),
            )

            if next_cell not in cost_so_far or new_cost < cost_so_far[next_cell]:
                cost_so_far[next_cell] = new_cost
                came_from[next_cell] = current
                priority = new_cost + _heuristic(next_cell, goal)
                heapq.heappush(frontier, (priority, next_cell))

    if goal not in came_from:
        raise ValueError("No route exists through the current forecast risk field under the selected constraints.")

    path: list[tuple[int, int]] = []
    current: tuple[int, int] | None = goal
    while current is not None:
        path.append(current)
        current = came_from[current]

    path.reverse()
    return path, float(cost_so_far[goal])


def exposure_band(risk_score: float) -> str:
    score = float(np.clip(risk_score, 0.0, 1.0))
    if score < 0.33:
        return "Low"
    if score < 0.66:
        return "Moderate"
    return "High"
