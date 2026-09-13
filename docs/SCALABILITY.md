# Scalability notes — Antarctic Navigator

The current project is a hackathon prototype, not a 100,000-user benchmarked production platform.

## What is implemented today

- Stateless HTTP API behavior.
- Scientific data loaded from a compact bundle.
- Separate frontend and backend deployments are supported.
- Request-level timeouts prevent a hung API call from hanging the UI indefinitely.
- The local synthetic dataset remains an offline fallback.

## Production architecture

```text
Browser / operators
        ↓
CDN / frontend
        ↓
Load balancer
        ↓
Stateless FastAPI API instances
        ↓
Redis cache ────────┐
                    ↓
             Async workers
                    ↓
         Forecast / route compute
                    ↓
       Object storage for scientific data
                    ↓
            PostGIS / PostgreSQL
```

### Scientific data

Keep large gridded data out of the transactional database. A production pipeline should store NetCDF/Zarr/COG-style scientific products in object storage and expose processed/cached subsets to the API.

### Forecast and routing

The current 60×180 grid is intentionally small. A production service would move heavier forecasts and routing into asynchronous workers and cache common route/horizon combinations.

### Offline field use

An edge cache should retain the latest validated real dataset and route products so an Antarctic vessel/station can continue operating during an internet outage.

## What not to claim

Do not claim a measured capacity such as 100,000 simultaneous users without a load test. State the architectural scalability mechanisms instead.
