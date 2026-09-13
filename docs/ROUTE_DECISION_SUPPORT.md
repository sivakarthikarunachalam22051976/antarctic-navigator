# Mission-Aware Route Decision Support

Antarctic Navigator now exposes three explainable route candidates for each routing request:

- **Route A — Safest:** stronger weighting on sea-ice exposure and projected iceberg risk.
- **Route B — Fastest:** strongest transit-distance preference while keeping land and 100% sea-ice cells excluded.
- **Route C — Balanced:** a middle ground between transit distance and environmental exposure.

The API selects one candidate as the recommendation using the selected mission, operational priority, maximum acceptable ice exposure, and data-freshness requirement.

## Mission controls

The prototype supports:

- `resupply` — resupply / station logistics
- `research_transit` — research transit
- `time_critical` — time-critical transfer

Operational priority can be:

- `safety_first`
- `balanced`
- `time_sensitive`

Maximum acceptable ice exposure can be:

- `low` (50%)
- `medium` (75%)
- `high` (95%)

The freshness selector is a provenance gate. It does not invent freshness for the sources. When the selected freshness requirement is not met by the available retrieval timestamps, the UI explicitly flags human review.

## Route explanation

Each candidate reports:

- total distance;
- environmental risk score;
- sea-ice exposure band;
- maximum projected iceberg risk;
- percentage longer than the shortest candidate;
- whether the route is within the selected maximum ice-exposure limit;
- a short explanation of why the candidate scored as it did.

The recommended route additionally reports the mission/priority context, source dates, and a human-in-the-loop warning.

## Technical honesty

This is explainable decision intelligence, not an autonomous navigation system. The current MVP uses a transparent sea-ice forecasting baseline, a simplified physics-informed iceberg drift model, an environmental risk field, and A* optimisation. It does not claim calibrated vessel fuel-consumption savings or certified navigational safety.
