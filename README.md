# Antarctic Navigator — Ultimate Mission-Aware Polar Decision-Support Prototype

**Build: v0.5.0 · SIH26059**

**SIH26059 · Software**

Antarctic Navigator is a decision-support prototype for Antarctic logistics. It combines sea-ice concentration, iceberg observations, simplified iceberg drift physics, vessel-specific routing costs, and risk-aware A* pathfinding.

## Real-data integrity

Real source-derived data is the production default (`USE_REAL_DATA=1`). The backend will not silently substitute the synthetic fixture. If the real bundle is missing, startup fails unless an operator explicitly sets `ALLOW_SYNTHETIC_FALLBACK=1` for offline software testing. The packaged real bundle contains NSIDC G10016 v4 sea ice, USNIC iceberg observations, OSCAR NRT currents and ERA5 wind metadata.

Synthetic data remains in the repository only for deterministic automated tests and offline development.

## What the complete build supports

This package is the Antarctic Navigator codebase upgraded with selected, defensible capabilities observed in a separate public SIH26059 reference implementation. It does **not** copy that project's code, synthetic environmental fields, trained weights, or unsupported performance claims. The production/demo path remains grounded in the packaged source-derived real-data bundle.

- **NSIDC G10016 Version 4** — current near-real-time Antarctic sea-ice input.
- **USNIC Antarctic Icebergs** — current weekly iceberg observations.
- **OSCAR NRT V2.0** — optional real surface-current forcing for iceberg drift.
- **ERA5 10-m winds** — optional recent/reanalysis wind forcing for iceberg drift; this is not an instantaneous live forecast.
- **Transparent sea-ice forecast baseline** — short horizon, not a trained ML model.
- **RK4 iceberg drift + uncertainty ensemble** — fourth-order numerical integration of the transparent free-drift field, with a small screening ensemble around the projected position.
- **Physics-informed vessel performance** — transparent Lindqvist-inspired ice-resistance scaling estimates attainable speed degradation by vessel profile; it is clearly labelled as a planning model, not a certified hull-performance model.
- **Polar safety screening** — vessel ice-class/concentration screening inspired by the POLARIS concept, explicitly marked as non-regulatory and not a full POLARIS implementation.
- **EPSG:3031 geometry** — Antarctic polar stereographic coordinates are available for route endpoints and future polar map upgrades while the current Leaflet UI remains simple and familiar.
- **Risk-weighted A*** — partial sea ice receives a steep cost; 100% concentration cells remain hard exclusions; route results include an environmental-exposure assessment.
- **Mission-aware route alternatives** — returns Route A (Safest), Route B (Fastest) and Route C (Balanced), then recommends the best candidate for the selected mission and operational priority.
- **Explainable route reasoning** — exposes risk score, distance versus shortest, ice/iceberg exposure, selected constraints, source dates, and a concise "Why selected?" explanation.
- **Voyage intelligence simulator** — the selected route can be replayed as a vessel-performance estimate with model ETA, attainable speed, environmental alerts, and a clearly labelled fuel-consumption proxy.
- **Human-in-the-loop decision support** — operators choose mission, vessel, priority, maximum acceptable ice exposure, and data-freshness requirement; the system does not autonomously control a vessel.
- **G10016 surface mask** — when present, the converter protects routing from land/coast cells.
- **G02202 Version 6** — historical sea-ice validation/backtesting source.
- **BYU/NIC v8.0** — historical iceberg-track validation/backtesting source.
- **Synthetic fallback** — fully offline demo data remains bundled for reliability.
- **Offline-first architecture** — no external API key is required for the core demo; the real-data bundle can be refreshed separately when connectivity is available.

## Data-status honesty

The API/UI reports the actual data basis instead of calling every run "live":

- `synthetic` — offline bundled demo data.
- `real_seaice_only` — real NSIDC sea ice without a current USNIC CSV.
- `real_seaice_usnic_icebergs` — real NSIDC sea ice + current USNIC observations.
- `environmental_forcing` — explicitly states whether OSCAR currents and/or ERA5 wind are present.
- `trajectory_basis` — explains whether the drift projection is externally forced or stationary fallback.
- Per-source observation/update dates + retrieval timestamps — used by `/api/data-status` and the dashboard freshness panel.

## Current vs historical data

```text
CURRENT
NSIDC G10016 v4 ──→ sea ice
USNIC ─────────────→ current iceberg observations
OSCAR NRT ─────────→ optional current forcing
ERA5 ──────────────→ optional recent/reanalysis wind

HISTORICAL / VALIDATION
NSIDC G02202 v6 ───→ historical sea-ice evaluation
BYU/NIC v8.0 ──────→ historical iceberg tracks
```

## Project structure

```text
antarctic-navigator/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── requirements.txt
│   ├── models/
│   │   ├── drift_model.py
│   │   ├── polar_intelligence.py
│   │   ├── router.py
│   │   └── seaice_forecast.py
│   └── data/
│       ├── sample_data_generator.py
│       ├── fetch_real_data.py
│       ├── fetch_usnic_icebergs.py
│       ├── fetch_oscar_currents.py
│       ├── fetch_era5_wind.py
│       ├── fetch_byu_historical.py
│       ├── validate_byu_historical.py
│       ├── convert_nsidc_bundle.py
│       ├── integrate_usnic_icebergs.py
│       ├── sample/
│       ├── real/
│       └── test/
├── frontend/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.js
│   └── .env
├── docs/
├── scripts/
├── render.yaml
└── requirements.txt
```

## Local setup — Windows PowerShell

From the repository root:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\self_check.py
```

Start backend:

```powershell
cd backend
fastapi dev main.py
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

Backend health:

```text
http://127.0.0.1:8000/api/health
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## Current real-data workflow

### NSIDC sea ice

```powershell
python backend\data\fetch_real_data.py
```

### USNIC current icebergs

```powershell
python backend\data\fetch_usnic_icebergs.py
```

### Optional OSCAR currents

Requires your NASA Earthdata Login for PO.DAAC protected data access:

```powershell
python backend\data\fetch_oscar_currents.py
```

### Optional ERA5 wind

Requires a Copernicus CDS account, API token/configuration, and acceptance of the dataset terms:

```powershell
python backend\data\fetch_era5_wind.py
```

### Convert all available current data into the compact application bundle

```powershell
python backend\data\convert_nsidc_bundle.py
python scripts\validate_real_bundle.py
```

The compact bundle is:

```text
backend/data/real/navigator_bundle.json
```

## Daily refresh for the SIH prototype

Refresh current real data (NSIDC + USNIC):

```powershell
.\scripts\daily_refresh.ps1
```

To include OSCAR currents and ERA5 wind in the same refresh, enable both for the PowerShell session first:

```powershell
$env:ANTARCTIC_ENABLE_OSCAR="1"
$env:ANTARCTIC_ENABLE_ERA5="1"
.\scripts\daily_refresh.ps1
```

The refresh script converts and validates the compact bundle after the downloads complete. If either optional source fails, the existing cached source file is preserved and the converter can continue with whatever validated forcing is available.

After the bundle validates:

```powershell
git add backend\data\real\navigator_bundle.json
git commit -m "Update Antarctic environmental data"
git push
```

## Historical validation data

Download the current BYU/NIC consolidated archive:

```powershell
python backend\data\fetch_byu_historical.py
```

Validate the extracted collection:

```powershell
python backend\data\validate_byu_historical.py
```

Historical data is kept separate from current operational inputs.

## Frontend route-decision UI (fixed package)

The shipped frontend is the mission-aware UI and must display:

- Route A — Safest
- Route B — Fastest
- Route C — Balanced
- Recommended Route
- Why selected? explanation

The route comparison is rendered as a compact table, and Data freshness & provenance is rendered as a source table with data date, retrieval time, and status. The old single-line `Risk-weighted route found ...` presentation is not part of this package.

If a local browser still shows the old single-route message, it is serving an older frontend copy. Stop the old Vite process, open this package's `frontend` directory, install dependencies, and restart Vite:

```powershell
cd frontend
npm install
npm run dev
```

Then hard-refresh the browser (`Ctrl+Shift+R`). Confirm that the page contains the **Mission-aware routing** controls and the map legend **A Safest · B Fastest · C Balanced**.

The backend must also be the `backend/main.py` shipped in this package. From the `backend` directory, `http://127.0.0.1:8000/` should return the API service status rather than 404.

## Deployment

See `docs/DEPLOYMENT.md` for the GitHub → Render → Vercel setup.

The included `render.yaml` configures a Python backend rooted at `backend`, serves the committed real-data bundle (`USE_REAL_DATA=1`), and uses `On Commit` deployment with `/api/health` health checks.

## Validation and scientific limitations

Run:

```powershell
python scripts\self_check.py
```

Software checks validate the bundled prototype and parser/regridding logic. Scientific/operational accuracy still requires historical backtesting, uncertainty calibration, vessel-performance validation, and domain review.

This is decision-support software, not certified maritime navigation software.


## Why these additions were selected

| Capability | Antarctic Navigator | Added from reference idea | Data/claim boundary |
|---|---|---|---|
| Real environmental bundle | Yes | — | NSIDC + USNIC + OSCAR + ERA5 |
| Mission-aware A/B/C routing | Yes | — | Same A* engine, different objectives |
| RK4 iceberg drift | Yes | Yes | Physics-informed, not operationally validated |
| Uncertainty ensemble | Yes | Yes | Screening uncertainty, not calibrated probability |
| Vessel performance | Yes | Yes | Planning approximation, not certified hull performance |
| POLARIS layer | Screening | Yes | Reference/screening only, not regulatory certification |
| EPSG:3031 geometry | Yes | Yes | Endpoint/path geometry support |
| Voyage simulation | Yes | Yes | ETA/fuel planning proxy, not measured savings |
| Synthetic-trained ML models | No | Deliberately excluded | Avoids presenting unvalidated/synthetic-trained AI as operational |
| Full autonomous navigation | No | Deliberately excluded | Human operator remains in control |

