"""Physics-informed polar intelligence helpers.

These helpers deliberately stay transparent: they provide numerical integration,
ship-performance estimates, polar geometry and a screening-level safety layer.
They are decision-support estimates, not certified navigation calculations.
"""
from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np
from pyproj import Transformer


POLAR_STEREOGRAPHIC = Transformer.from_crs(
    "EPSG:4326", "EPSG:3031", always_xy=True
)

# Representative, publicly described vessel presets.  Values are planning
# parameters, not a claim of class certification for a particular voyage.
ADVANCED_VESSELS: dict[str, dict[str, Any]] = {
    "standard": {
        "label": "Standard vessel",
        "ice_class": "PC7",
        "power_mw": 8.0,
        "design_speed_kn": 13.0,
        "ice_speed_floor_kn": 1.0,
        "max_concentration": 0.85,
    },
    "ice_capable": {
        "label": "Ice-capable vessel",
        "ice_class": "PC5",
        "power_mw": 13.5,
        "design_speed_kn": 14.0,
        "ice_speed_floor_kn": 2.0,
        "max_concentration": 0.95,
    },
    "sagar_nidhi": {
        "label": "ORV Sagar Nidhi",
        "ice_class": "PC7",
        "power_mw": 5.6,
        "design_speed_kn": 13.0,
        "ice_speed_floor_kn": 0.5,
        "max_concentration": 0.85,
    },
    "vasiliy_golovnin": {
        "label": "MV Vasiliy Golovnin",
        "ice_class": "PC5",
        "power_mw": 13.5,
        "design_speed_kn": 14.0,
        "ice_speed_floor_kn": 1.5,
        "max_concentration": 0.95,
    },
    "arc7": {
        "label": "Generic Arc7 resupply vessel",
        "ice_class": "Arc7",
        "power_mw": 13.0,
        "design_speed_kn": 14.0,
        "ice_speed_floor_kn": 2.0,
        "max_concentration": 0.98,
    },
    "planned_pc4": {
        "label": "Planned Indian polar vessel (notional)",
        "ice_class": "PC4",
        "power_mw": 12.0,
        "design_speed_kn": 14.0,
        "ice_speed_floor_kn": 2.5,
        "max_concentration": 0.99,
    },
}

# Screening bands only. Full POLARIS requires ice type/thickness and certified
# vessel data, neither of which is present in this MVP's real-data bundle.
POLARIS_SCREENING = {
    "PC7": (0.65, 0.85),
    "PC5": (0.80, 0.95),
    "PC4": (0.90, 0.99),
    "Arc7": (0.92, 0.99),
}


def polar_stereographic_xy(lat: float, lon: float) -> tuple[float, float]:
    """Return Antarctic EPSG:3031 x/y metres."""
    x, y = POLAR_STEREOGRAPHIC.transform(float(lon), float(lat))
    return float(x), float(y)


def _lindqvist_resistance_factor(ice_concentration: float, ice_thickness_m: float = 1.0) -> float:
    """Transparent Lindqvist-inspired relative resistance term.

    The real Lindqvist formulation needs vessel geometry and ice properties.
    This MVP exposes a bounded planning approximation rather than pretending to
    reproduce a validated hull-specific resistance model.
    """
    c = float(np.clip(ice_concentration, 0.0, 1.0))
    h = max(0.0, float(ice_thickness_m))
    return float(1.0 + 2.8 * c**1.35 * (0.65 + 0.35 * min(h, 2.5)))


def attainable_speed_kn(
    vessel_profile: str,
    ice_concentration: float,
    ice_thickness_m: float = 1.0,
) -> float:
    vessel = ADVANCED_VESSELS.get(vessel_profile, ADVANCED_VESSELS["standard"])
    resistance = _lindqvist_resistance_factor(ice_concentration, ice_thickness_m)
    open_water = float(vessel["design_speed_kn"])
    # Speed loss is deliberately bounded and monotonic with environmental load.
    speed = open_water / math.sqrt(resistance)
    if ice_concentration >= vessel["max_concentration"]:
        return 0.0
    return float(max(vessel["ice_speed_floor_kn"], speed))


def polar_safety_screen(
    vessel_profile: str,
    ice_concentration: float,
) -> dict[str, Any]:
    vessel = ADVANCED_VESSELS.get(vessel_profile, ADVANCED_VESSELS["standard"])
    ice_class = str(vessel["ice_class"])
    allowed, hard = POLARIS_SCREENING.get(
        ice_class,
        (0.70, float(vessel["max_concentration"])),
    )
    c = float(np.clip(ice_concentration, 0.0, 1.0))
    if c >= hard:
        status = "BLOCK"
        reason = "Concentration exceeds the vessel's screening limit."
    elif c >= allowed:
        status = "REVIEW"
        reason = "High ice exposure requires human review."
    else:
        status = "PASS"
        reason = "Within the screening band for this vessel profile."
    return {
        "status": status,
        "reason": reason,
        "ice_class": ice_class,
        "screening_limit": allowed,
        "hard_screening_limit": hard,
        "is_full_polaris": False,
    }


def _derivative(
    lat: float,
    lon: float,
    velocity_at: Callable[[float, float], tuple[float, float]],
) -> tuple[float, float]:
    """Derivative in degrees/hour from an east/north velocity in m/s."""
    u, v = velocity_at(lat, lon)
    metres_per_degree_lat = 111_320.0
    metres_per_degree_lon = max(10_000.0, metres_per_degree_lat * math.cos(math.radians(lat)))
    return (
        float(v) * 3600.0 / metres_per_degree_lat,
        float(u) * 3600.0 / metres_per_degree_lon,
    )


def rk4_iceberg_step(
    lat: float,
    lon: float,
    dt_hours: float,
    velocity_at: Callable[[float, float], tuple[float, float]],
) -> tuple[float, float]:
    """Fourth-order Runge-Kutta integration of the drift field."""
    dt = float(dt_hours)
    k1 = _derivative(lat, lon, velocity_at)
    k2 = _derivative(lat + 0.5 * dt * k1[0], lon + 0.5 * dt * k1[1], velocity_at)
    k3 = _derivative(lat + 0.5 * dt * k2[0], lon + 0.5 * dt * k2[1], velocity_at)
    k4 = _derivative(lat + dt * k3[0], lon + dt * k3[1], velocity_at)
    return (
        lat + dt * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]) / 6.0,
        lon + dt * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]) / 6.0,
    )


def simulate_voyage(
    path: list[dict[str, float]],
    vessel_profile: str,
    concentration_at: Callable[[float, float], float],
    iceberg_risk_at: Callable[[float, float], float],
    step_km: float = 25.0,
) -> dict[str, Any]:
    """Estimate hourly-ish voyage performance along a chosen route.

    Fuel is an engineering proxy based on installed power and time; it is not a
    measured fuel-consumption prediction.
    """
    if len(path) < 2:
        return {"hours": 0.0, "distance_km": 0.0, "estimated_fuel_t": 0.0, "segments": [], "alerts": []}

    vessel = ADVANCED_VESSELS.get(vessel_profile, ADVANCED_VESSELS["standard"])
    points = [dict(p) for p in path]
    segments: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    total_km = 0.0
    total_hours = 0.0
    total_fuel = 0.0

    # Marine gas oil planning proxy: 205 g/kWh. This is explicitly a proxy.
    sfoc_t_per_mwh = 0.205

    def haversine(a: dict[str, float], b: dict[str, float]) -> float:
        r = 6371.0088
        p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
        dp = math.radians(b["lat"] - a["lat"])
        dl = math.radians(b["lon"] - a["lon"])
        q = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return r * 2 * math.asin(min(1.0, math.sqrt(q)))

    for index, (a, b) in enumerate(zip(points, points[1:]), start=1):
        distance = haversine(a, b)
        mid = {"lat": (a["lat"] + b["lat"]) / 2, "lon": (a["lon"] + b["lon"]) / 2}
        ice = float(np.clip(concentration_at(mid["lat"], mid["lon"]), 0.0, 1.0))
        berg = float(np.clip(iceberg_risk_at(mid["lat"], mid["lon"]), 0.0, 1.0))
        speed = attainable_speed_kn(vessel_profile, ice)
        if speed <= 0.01:
            status = "BLOCKED"
            hours = float("inf")
        else:
            hours = distance / (speed * 1.852)
            status = "ALERT" if ice >= 0.75 or berg >= 0.60 else "NORMAL"

        fuel_t = 0.0 if not math.isfinite(hours) else float(vessel["power_mw"] * hours * sfoc_t_per_mwh)
        total_km += distance
        if math.isfinite(hours):
            total_hours += hours
            total_fuel += fuel_t

        segment = {
            "index": index,
            "distance_km": round(distance, 2),
            "ice_concentration": round(ice, 3),
            "iceberg_risk": round(berg, 3),
            "attainable_speed_kn": round(speed, 2),
            "hours": None if not math.isfinite(hours) else round(hours, 2),
            "estimated_fuel_t": round(fuel_t, 2),
            "status": status,
        }
        segments.append(segment)
        if status != "NORMAL":
            alerts.append({"segment": index, "status": status, "reason": "Elevated environmental exposure or vessel speed degradation."})

    return {
        "distance_km": round(total_km, 1),
        "hours": round(total_hours, 1),
        "eta_days": round(total_hours / 24.0, 2),
        "estimated_fuel_t": round(total_fuel, 1),
        "fuel_basis": "Planning proxy: installed power × voyage time × 205 g/kWh; not measured consumption.",
        "segments": segments,
        "alerts": alerts,
        "vessel": vessel,
    }
