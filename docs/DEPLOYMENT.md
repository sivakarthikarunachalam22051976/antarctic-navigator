# Deployment runbook

## Repository layout

```text
antarctic-navigator/
├── backend/
├── frontend/
├── docs/
├── scripts/
├── render.yaml
└── requirements.txt
```

## Render backend

The included `render.yaml` configures:

- runtime: Python
- branch: `main`
- root directory: `backend`
- build: `pip install -r requirements.txt`
- start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- real bundle mode: `USE_REAL_DATA=1`
- auto deploy: commit
- health check: `/api/health`

Set in Render:

```text
USE_REAL_DATA=1
FRONTEND_URL=https://YOUR-VERCEL-DOMAIN.vercel.app
```

Use `USE_REAL_DATA=1` only when the compact `backend/data/real/navigator_bundle.json` is committed.

## Vercel frontend

Import the same GitHub repository with Root Directory set to `frontend`.

Set:

```text
VITE_API_BASE=https://YOUR-RENDER-SERVICE.onrender.com
```

The local `frontend/.env` can remain:

```text
VITE_API_BASE=http://localhost:8000
```

## Git-tracked data policy

Commit the compact processed bundle:

```text
backend/data/real/navigator_bundle.json
```

Do not commit raw downloaded NetCDF/CSV source files or the BYU historical archive. They are ignored by `.gitignore`.

## Daily prototype refresh

From the repository root:

```powershell
.\scripts\daily_refresh.ps1
```

By default this refreshes NSIDC G10016 V4 + current USNIC icebergs.

To also include OSCAR NRT currents:

```powershell
$env:ANTARCTIC_ENABLE_OSCAR="1"
.\scripts\daily_refresh.ps1
```

To include ERA5 wind, after configuring the CDS API:

```powershell
$env:ANTARCTIC_ENABLE_OSCAR="1"
$env:ANTARCTIC_ENABLE_ERA5="1"
.\scripts\daily_refresh.ps1
```

After conversion, publish the compact bundle:

```powershell
git add backend\data\real\navigator_bundle.json
git commit -m "Update Antarctic environmental data"
git push
```

Render auto-deploys from `main` after the push when Auto-Deploy is set to `On Commit`. The Vercel frontend does not need a manual redeploy for a data-only backend bundle change; it continues calling the same Render API URL.
