# Antarctic Navigator — Sea-Ice & Iceberg Navigation Decision Support System

SIH26059 · Ministry of Earth Sciences · Software

Fuses sea-ice concentration forecasts, iceberg drift projections, and
vessel-specific ice tolerance into a risk-aware route between two points —
by default, between India's Maitri and Bharati Antarctic research stations.

## Positioning note (read this before your PPT)

Don't pitch this as "nobody has built polar route planning before" — that's
false and a judge can find it in one search. The British Antarctic Survey's
**PolarRoute** (open source, `pip install polar-route`) and the commercial
**IcySea** app both do related things. Your defensible differentiator is:
this is an **India-specific, explainable, offline-capable workflow** built
around Indian Antarctic Programme logistics (Maitri/Bharati), not a claim
that route optimization itself is novel. Say that directly if asked.

## What's real and what's simplified (read this next)

- **Drift physics** is a simplified free-drift approximation (current +
  wind rotated by an empirical Coriolis deflection angle), inspired by but
  not equal to the full Bigg et al. (1997) iceberg dynamics model. Cite
  Bigg et al. as the fuller model this approximates.
- **Sea-ice forecasting** is a lightweight, explainable persistence-based
  baseline, not a trained ML/physical model. The forecast horizon slider
  does genuinely re-query and re-render a different forecast field, but day-
  to-day change is intentionally subtle (a few tenths of a percent) — this
  is a transparent baseline, not a dramatic prediction engine. Say so if asked.
- **Only the sea-ice layer has a real-data path wired up currently.** Wind,
  current, and iceberg fields are synthetic even when you load real NSIDC
  sea-ice data — `convert_nsidc_bundle.py` says so explicitly in its output
  metadata (`dataset_kind: real_seaice_only`). Don't claim an all-real
  pipeline until you've actually built adapters for the other three.
- Ships with a **synthetic offline dataset** by default so the whole system
  runs with zero API keys and zero internet dependency — critical for demo
  reliability at a venue with unreliable wifi.

## Project structure

```
antarctic-navigator/
├── backend/
│   ├── main.py                       # FastAPI app + routes
│   ├── config.py                     # Grid bounds + Maitri/Bharati coordinates
│   ├── models/
│   │   ├── drift_model.py            # Iceberg free-drift physics
│   │   ├── seaice_forecast.py        # Sea-ice concentration forecast baseline
│   │   └── router.py                 # A* routing, vessel profiles, iceberg risk cost
│   └── data/
│       ├── sample_data_generator.py  # Generates the synthetic demo dataset
│       ├── fetch_real_data.py        # Downloads real NSIDC data (needs Earthdata login)
│       ├── convert_nsidc_bundle.py   # Converts downloaded NetCDF into the app's bundle format
│       └── sample/                   # Pre-generated synthetic data (ready to run)
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js                        # Leaflet dashboard: stations, vessel profile, route planner
├── docs/
│   ├── DATA_SOURCES.md               # Real data sources + how to plug them in
│   ├── VALIDATION.md                 # What was actually checked in this build, and what wasn't
│   ├── PPT_SLIDE_GUIDE.md            # Slide-by-slide SIH presentation guidance
│   └── SCALABILITY.md                # Production scaling architecture notes
├── scripts/
│   └── smoke_test.py                 # End-to-end model pipeline check (Maitri → Bharati route)
├── requirements.txt
└── README.md
```

## Setup

### Windows PowerShell note (read this if you saw a numpy build error)

If `pip install` tried to compile numpy from source and failed with a
"meson"/"Unknown compiler" error, that means numpy couldn't find a
prebuilt wheel for your Python version — usually because you're on a very
new Python release (3.14+) and an old pinned version doesn't publish
wheels for it yet. `requirements.txt` now uses minimum-version bounds
(`numpy>=2.1`, etc.) instead of exact pins specifically to avoid this —
pip will pick whatever current wheel actually supports your Python
version. If you still hit a build error, upgrade pip first
(`python -m pip install --upgrade pip`) and retry.

Also: PowerShell doesn't have a `source` command (that's bash). Use the
PowerShell-native activation command below.

### 1. Backend

```powershell
cd antarctic-navigator-v2-final\backend

python -m venv venv
.\venv\Scripts\Activate.ps1
# If PowerShell blocks script execution, run this once first:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

pip install --upgrade pip
pip install -r ..\requirements.txt

python data\sample_data_generator.py   # only needed once, already pre-run

fastapi dev main.py
```

macOS/Linux equivalent:

```bash
cd antarctic-navigator-v2-final/backend
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r ../requirements.txt
python data/sample_data_generator.py
fastapi dev main.py
```

`fastapi dev` (from the `fastapi[standard]` package) runs on
http://localhost:8000 with auto-reload — same idea as `uvicorn --reload`,
just the newer built-in CLI. Check http://localhost:8000/docs for
interactive API docs — worth showing judges live.

Sanity-check the whole model pipeline without starting a server (works
from any directory — it locates `backend/` relative to its own file path):

```bash
python scripts/smoke_test.py
```

### 2. Frontend — Vite on port 5173

```bash
cd antarctic-navigator-v2-final/frontend
npm install
npm run dev
```

Open http://localhost:5173. Use the station buttons (Maitri / Bharati) for
a one-click demo route, or click anywhere on the map to set custom points.

(The plain `python -m http.server` approach still works too if you'd
rather skip npm entirely — either serves the same static files.)

### 3. Switching to real sea-ice data

Run these from inside `backend/` (same folder as `main.py`):

```bash
export NSIDC_SHORT_NAME=G10016    # near-real-time; use G02202 for the final, more-delayed CDR
python data/fetch_real_data.py       # prompts for free NASA Earthdata login
python data/convert_nsidc_bundle.py  # reprojects onto the app's grid
export USE_REAL_DATA=1
fastapi dev main.py
```

See `docs/DATA_SOURCES.md` for what's real vs. synthetic in that path, and
`docs/VALIDATION.md` for exactly what has and hasn't been checked in this
build.

## Extra packages needed

Everything is in `requirements.txt`, including `pyproj` (for the real-data
coordinate reprojection in `convert_nsidc_bundle.py`) and `cdsapi` (if you
add real ECMWF ERA5 wind data — see `docs/DATA_SOURCES.md`). One
`pip install -r requirements.txt` covers all of it — no separate manual
installs.
