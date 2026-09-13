# Real-world data sources and how the app uses them

## Sea ice — current

**NOAA/NSIDC G10016 Version 4** is the project's current near-real-time Antarctic sea-ice concentration input. The project downloads the latest Antarctic daily file from the official NOAA@NSIDC HTTPS archive and regrids the South Polar EPSG:3412 field to the application's operating grid.

Official: https://nsidc.org/data/g10016/versions/4

## Sea ice — historical validation

**NOAA/NSIDC G02202 Version 6** is the final CDR and is reserved for historical evaluation/backtesting rather than the current daily feed.

Official: https://nsidc.org/data/g02202/versions/6

## Icebergs — current

**U.S. National Ice Center (USNIC) Antarctic Iceberg product** is the primary current iceberg source. The current product is updated weekly and provides CSV/GIS data with iceberg identifiers, dimensions, positions, region and update information.

Official: https://usicecenter.gov/Products/Antarcicebergs

`fetch_usnic_icebergs.py` discovers the current CSV link from the official page. `integrate_usnic_icebergs.py` normalizes common CSV field layouts into the Navigator schema and records the source update date.

## Icebergs — historical validation

**BYU/NIC consolidated Antarctic iceberg database v8.0** is used for historical tracks and validation/backtesting. The current listed consolidated release covers 1978 through April 22, 2025, so it is intentionally not treated as a current 2026 feed.

Official: https://www.scp.byu.edu/iceberg/database1.html

## Ocean currents — current/near-real-time optional layer

**NASA/JPL PO.DAAC OSCAR_L4_OC_NRT_V2.0** provides daily global 0.25-degree surface currents, with approximately two-day latency according to the PO.DAAC catalog. The current adapter uses Earthdata authentication, downloads recent granules, reads total surface-current `u`/`v`, and regrids them to the Navigator grid.

Official: https://podaac.jpl.nasa.gov/dataset/OSCAR_L4_OC_NRT_V2.0

## Wind — reanalysis optional layer

**Copernicus/ECMWF ERA5** is available through the CDS API. The project can download a recent Antarctic subset containing 10-m `u10/v10` wind components. ERA5 is a reanalysis, so its availability is delayed relative to a live forecast; it is appropriate for recent/historical environmental forcing and model development.

Official API setup: https://cds.climate.copernicus.eu/how-to-api

## What the real bundle means

The bundle is explicit about which layers are present:

- `real_seaice_only` — real NSIDC sea ice, no current USNIC iceberg file available.
- `real_seaice_usnic_icebergs` — real NSIDC sea ice + current USNIC iceberg observations.
- Environmental metadata identifies whether OSCAR currents and/or ERA5 winds are actually present.

The application must not claim operational navigation accuracy simply because a real dataset is present. Forecast skill, iceberg-trajectory accuracy, fuel modeling and route safety still require scientific validation and historical backtesting.
