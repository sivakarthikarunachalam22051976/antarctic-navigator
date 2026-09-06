# Real-world data sources

This build ships with a synthetic dataset so it runs standalone. Here's
where the real thing comes from, what's actually wired up already, and
what still needs work — verified, not guessed.

## 1. Sea-ice concentration — wired up

- **Source:** NOAA/NSIDC Climate Data Record of Passive Microwave Sea Ice
  Concentration. Two products:
  - **G02202** — the final, quality-controlled CDR (updated every few
    months, best for a backtested/historical demo).
  - **G10016** — the Near-Real-Time companion (fills the gap until the
    next G02202 release; use this if you want the most current data).
- **Access:** create a free account at https://urs.earthdata.nasa.gov/,
  then run:
  ```bash
  export NSIDC_SHORT_NAME=G10016   # or G02202
  python backend/data/fetch_real_data.py
  python backend/data/convert_nsidc_bundle.py
  ```
  `fetch_real_data.py` uses `earthaccess` (NASA's official client) to
  search and download; `convert_nsidc_bundle.py` reprojects the NetCDF
  grid (EPSG:3412, NSIDC South Polar Stereographic) onto this app's
  lat/lon grid using `pyproj` + `scipy.interpolate`.
- **What you get:** real sea-ice concentration only. The converter's
  output metadata explicitly says `dataset_kind: real_seaice_only` and
  zeros out wind/current/iceberg fields rather than silently reusing
  synthetic values as if they were real — check that field before you
  claim "real data" anywhere in your pitch.

## 2. Iceberg positions/tracks — not yet wired up

- **Source:** the Antarctic iceberg tracking database maintained by
  Brigham Young University's Center for Remote Sensing (large icebergs
  tracked via scatterometer). Search "BYU Antarctic iceberg tracking
  database" for the current download page — it has moved before, so
  don't hardcode the URL into a slide as permanent.
- **Access:** typically a direct CSV/text download, no login required, no
  stable REST API as of this writing.
- **Status:** there's no adapter for this yet in the codebase. If you
  build one, save the export to `backend/data/real/iceberg_tracks_real.csv`
  and write a loader that feeds into the same `icebergs` list shape used
  by the synthetic generator (`id`, `lat`, `lon`, `length_km`).

## 3. Wind and ocean currents — not yet wired up

- **Wind:** ECMWF ERA5 reanalysis via the Copernicus Climate Data Store
  (`cdsapi`, already in requirements.txt) — needs a free CDS API key from
  https://cds.climate.copernicus.eu/.
- **Ocean currents:** NOAA OSCAR surface currents, or a regional ocean
  model output — worth asking your mentor directly whether NCPOR or the
  Indian Antarctic Programme can share something for the hackathon.
- **Status:** same as icebergs — no adapter built yet. Until one exists,
  the drift model and iceberg-risk routing run on the synthetic wind/
  current fields even when sea-ice is real. Be explicit about this in
  your technical slide rather than letting it sound like everything is real.

## Practical advice for the demo itself

Don't depend on live calls to any of the above during your actual judging
slot. Download and cache real data ahead of time, exactly the way this
repo ships a pre-generated synthetic file as the offline fallback. Keep
that fallback wired in (`USE_REAL_DATA=0` is the default) even after you
add real data, so a bad venue connection can't take down your demo.
