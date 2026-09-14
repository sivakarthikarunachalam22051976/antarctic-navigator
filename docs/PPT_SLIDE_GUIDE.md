# SIH PPT slide guide — Antarctic Navigator (SIH26059)

Verify the exact current SIH template on your team's portal before submission. This guide is content guidance, not a replacement for the official template.

## Slide 1 — Title

Show: PS ID SIH26059, exact official PS title, theme as written in the portal, Software category, team ID/name. Follow the anonymity rule required by your round.

Visual: a clean Antarctic/Southern Ocean map with Maitri and Bharati marked. Avoid decorative AI-generated Antarctic art.

## Slide 2 — Proposed Solution

One-line pitch: an explainable decision-support workflow that combines changing sea ice, iceberg observations/trajectories and vessel constraints to recommend mission-aware logistics route options.

Main visual:

`Data → Forecast + Drift → Combined Risk Field → A* Route Alternatives → Mission-Aware Recommendation → Operator Decision`

Prototype decision view:

`Route A — Safest | Route B — Fastest | Route C — Balanced → Recommended Route + Why selected?`

USP: **India-focused + explainable + multi-source + human-in-the-loop Antarctic logistics decision support**.

Do not claim that polar route optimisation itself has never been built; related systems such as BAS PolarRoute exist.

## Slide 3 — Technical Approach

Visual data flow:

`NSIDC sea ice + USNIC iceberg observations + OSCAR NRT currents + ERA5 wind → data normalisation → statistical sea-ice forecast + RK4 physics-informed iceberg drift → vessel-aware risk assessment → risk field → A* Route A/B/C → mission-aware recommendation → FastAPI → Leaflet`

Show the real-data freshness/provenance panel. The current prototype uses a transparent hybrid sea-ice forecast: persistence + seasonal correction, plus conservative semi-Lagrangian advection when matched OSCAR/ERA5 forcing is available. The iceberg model is a simplified physics-informed free-drift approximation integrated with RK4. Do not present either as a trained ML/deep-learning model.

## Slide 4 — Feasibility & Viability

Three blocks:

1. Technical feasibility — public scientific data, modular pipeline, offline fallback.
2. Risk → mitigation — latency → cached data; uncertainty → confidence framing; network failure → offline fallback; observation error → spatial risk zone.
3. Business model — B2G primary (research/Antarctic logistics operations), B2B secondary (polar logistics/analytics). Revenue streams: annual licence, integration/API access, deployment/support.

Scalability visual: CDN → stateless API → cache → async workers → scientific object storage → PostGIS/PostgreSQL.

## Slide 5 — Impact & Benefits

Use a before/after diagram rather than paragraphs:

`Fragmented information → manual interpretation → route choice`

versus

`Current environmental data → risk map → route options → operator decision`

Do not invent fuel/time percentages without backtesting.

## Slide 6 — Research & References

Include NSIDC G10016 V4, NSIDC G02202 V6, USNIC Antarctic Icebergs, BYU/NIC v8.0, the iceberg-dynamics literature used as background, and related polar route-planning work. Include the GitHub QR code to the working repository.

## Data claims

When using the real-data prototype, use precise language:

- G10016 V4 = near-real-time sea-ice concentration input.
- USNIC = current weekly Antarctic iceberg observations.
- BYU/NIC v8.0 = historical iceberg tracks for validation/backtesting.
- Wind/current forcing remains explicitly identified in the UI until a validated real forcing adapter is connected.

Do not write "operational navigation" or "100% safe route".
