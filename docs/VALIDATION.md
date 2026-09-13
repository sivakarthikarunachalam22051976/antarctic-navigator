# Validation performed in this repository

## Automated software checks

Run:

```powershell
python scripts\self_check.py
```

This check:

- compiles the backend Python source;
- loads the bundled synthetic dataset;
- creates a multi-day sea-ice forecast;
- projects synthetic icebergs once;
- builds iceberg risk from already-projected positions;
- computes a Maitri → Bharati route;
- validates representative USNIC CSV parsing/date handling;
- validates compact JSON integrity;
- exercises the environmental NetCDF regridding helpers with tiny NetCDF fixtures.

A compatibility alias is also available:

```powershell
python scripts\smoke_test.py
```

## API smoke checks

The package was checked against the synthetic dataset for:

- `/`
- `/api/health`
- `/api/config`
- `/api/seaice/grid`
- `/api/seaice/forecast`
- `/api/icebergs`
- `/api/icebergs/projected`
- `/api/route`

## Real-data checks

The real-data scripts validate downloaded file existence/non-empty content, real observation dates, required variables/coordinates, and source metadata. The converter also uses the G10016 V4 surface-type mask when present.

Current real environmental forcing support:

- OSCAR NRT currents can be downloaded and regridded into `current_u/current_v`; the validator requires a decoded source date and retrieval timestamp when this source is present.
- ERA5 wind can be downloaded and regridded into `wind_u/wind_v` when CDS credentials are configured; the validator requires a decoded analysis date and retrieval timestamp when this source is present.
- Real-bundle validation also exercises the standard-vessel Maitri → Bharati route against the current risk-weighted router.

## Scientific/operational validation still required

No software-only test can establish operational navigation safety. The following require domain data and historical backtesting:

- sea-ice forecast skill;
- iceberg trajectory error against held-out tracks;
- uncertainty calibration;
- vessel-specific fuel/time modeling;
- route performance against historical conditions;
- operational maritime review and certification, if ever pursued.

This remains decision-support software, not certified navigation software.
