# ERA5 / Copernicus CDS configuration on Windows

The project already includes `cdsapi`; no extra Python package is required beyond `requirements.txt`.

## One-time setup

1. Create/sign in to a Copernicus Climate Data Store account.
2. Open your CDS profile and copy the two-line personal-access-token configuration shown there.
3. Accept the ERA5 dataset Terms of Use on the ERA5 dataset download page.
4. On Windows, create this file:

```text
C:\Users\YOUR_WINDOWS_USERNAME\.cdsapirc
```

with:

```text
url: https://cds.climate.copernicus.eu/api
key: YOUR_PERSONAL_ACCESS_TOKEN
```

Do not commit this file to GitHub and do not paste the token into the project source code.

## Verify the configuration

From the project root:

```powershell
python scripts\check_era5_config.py
```

Expected:

```text
CDS_CONFIG_OK file
```

## Download ERA5 wind

```powershell
python backend\data\fetch_era5_wind.py
```

The script defaults to a date seven days behind UTC today to allow for normal ERA5 publication latency. You can override it with:

```powershell
$env:ERA5_DATE="2026-09-01"
```

or:

```powershell
$env:ERA5_LAG_DAYS="7"
```

## Alternative: environment variables

Instead of `.cdsapirc`, you can set:

```powershell
$env:CDSAPI_URL="https://cds.climate.copernicus.eu/api"
$env:CDSAPI_KEY="YOUR_PERSONAL_ACCESS_TOKEN"
python backend\data\fetch_era5_wind.py
```

This is for the current PowerShell session only and is not written to the repository.
