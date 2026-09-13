# Refresh the compact real-data bundle used by the SIH prototype.
# Run from the repository root in PowerShell.
#
# Default: NSIDC sea ice + current USNIC iceberg observations.
# Optional real environmental forcing:
#   $env:ANTARCTIC_ENABLE_OSCAR="1"  -> NASA/JPL OSCAR NRT currents
#   $env:ANTARCTIC_ENABLE_ERA5="1"   -> Copernicus ERA5 wind (requires CDS setup)

$ErrorActionPreference = "Stop"

python backend\data\fetch_real_data.py
python backend\data\fetch_usnic_icebergs.py

if ($env:ANTARCTIC_ENABLE_OSCAR -eq "1") {
    try {
        python backend\data\fetch_oscar_currents.py
        if ($LASTEXITCODE -ne 0) {
            throw "OSCAR downloader exited with code $LASTEXITCODE."
        }
    } catch {
        Write-Warning "OSCAR refresh failed; the existing cached OSCAR file will be kept if present. $($_.Exception.Message)"
    }
}

if ($env:ANTARCTIC_ENABLE_ERA5 -eq "1") {
    try {
        python backend\data\fetch_era5_wind.py
        if ($LASTEXITCODE -ne 0) {
            throw "ERA5 downloader exited with code $LASTEXITCODE."
        }
    } catch {
        Write-Warning "ERA5 refresh failed; the existing cached ERA5 file will be kept if present. $($_.Exception.Message)"
    }
}

python backend\data\convert_nsidc_bundle.py
python scripts\validate_real_bundle.py

Write-Host "Real-data bundle refreshed:" -ForegroundColor Green
Get-Item backend\data\real\navigator_bundle.json |
    Select-Object FullName, Length, LastWriteTime

Write-Host "Publish the compact bundle when you are ready:" -ForegroundColor Cyan
Write-Host "git add backend\data\real\navigator_bundle.json"
Write-Host "git commit -m `"Update Antarctic environmental data`""
Write-Host "git push"
