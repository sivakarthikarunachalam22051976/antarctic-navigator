# Real-data setup — Windows PowerShell

## 1. Current sea ice: NSIDC G10016 Version 4

The project is pinned to **G10016 Version 4**. The downloader finds the newest Antarctic daily file from the official NOAA@NSIDC HTTPS archive.

From the repository root:

```powershell
.\venv\Scripts\Activate.ps1
python backend\data\fetch_real_data.py
```

No daily `NSIDC_SHORT_NAME` or `NSIDC_VERSION` environment commands are required. The script defaults to G10016 V4.

The source NetCDF is stored under:

```text
backend/data/real/raw/
```

Raw source files are ignored by Git.

## 2. Current iceberg observations: USNIC

USNIC publishes a current Antarctic iceberg product and a CSV intended for application/database import.

```powershell
python backend\data\fetch_usnic_icebergs.py
```

The current CSV is saved as:

```text
backend/data/real/raw/usnic_antarctic_icebergs.csv
```

The bundle converter parses the current USNIC records and keeps the source update date/count in metadata.

## 3. Real ocean currents: NASA/JPL OSCAR NRT (optional but recommended)

The project can use **OSCAR_L4_OC_NRT_V2.0** for daily 0.25-degree surface currents. PO.DAAC states that the NRT product has approximately two-day latency and requires Earthdata access for protected downloads.

Installations are already covered by `earthaccess` in `requirements.txt`.

Run:

```powershell
python backend\data\fetch_oscar_currents.py
```

The newest downloaded NetCDF is stored under:

```text
backend/data/real/raw/environmental/oscar/
```

The converter automatically finds it, regrids `u` and `v` to the Navigator grid, and places the result into `current_u/current_v`.

## 4. Real wind/reanalysis: Copernicus ERA5 (optional)

ERA5 is a reanalysis dataset, not an instantaneous live forecast. The project uses a recent date by default (7 UTC days behind today) to allow for publication latency. You can override the date with `ERA5_DATE=YYYY-MM-DD`.

You need a Copernicus CDS account, an API token/configuration, and acceptance of the ERA5 dataset terms. The official CDS API documentation explains the current setup and `cdsapi` client.

Run:

```powershell
python backend\data\fetch_era5_wind.py
```

The wind NetCDF is stored under:

```text
backend/data/real/raw/environmental/era5/
```

The converter automatically regrids `u10/v10` to the Navigator grid and adds them to the bundle.

## 5. Build the application bundle

After downloading whichever real-data sources you have configured:

```powershell
python backend\data\convert_nsidc_bundle.py
```

Output:

```text
backend/data/real/navigator_bundle.json
```

This is the compact file used by the API and is the only real-data artifact intended for the SIH prototype Git repository.

## 6. Local real-data mode

```powershell
$env:USE_REAL_DATA="1"
cd backend
fastapi dev main.py
```

In another terminal:

```powershell
cd frontend
npm run dev
```

Open:

```text
http://localhost:5173
```

## 7. Historical BYU/NIC validation dataset

Download the current consolidated historical archive:

```powershell
python backend\data\fetch_byu_historical.py
```

Validate it:

```powershell
python backend\data\validate_byu_historical.py
```

Keep the extracted archive under:

```text
backend/data/real/historical/byu_v8.0/
```

It is a historical validation source, not a current iceberg feed.

## 8. Daily refresh

For current sea ice + current icebergs:

```powershell
.\scripts\daily_refresh.ps1
```

To include real OSCAR currents:

```powershell
$env:ANTARCTIC_ENABLE_OSCAR="1"
.\scripts\daily_refresh.ps1
```

To include ERA5 wind as well (after CDS API setup):

```powershell
$env:ANTARCTIC_ENABLE_OSCAR="1"
$env:ANTARCTIC_ENABLE_ERA5="1"
.\scripts\daily_refresh.ps1
```

The script then prints the Git commands used to publish the compact bundle.
