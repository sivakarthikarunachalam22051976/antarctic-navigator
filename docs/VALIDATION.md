# Validation performed in this package build

- Python source compiles with `python -m compileall -q backend scripts`.
- Synthetic dataset generation runs successfully.
- Model smoke test exercises forecast, iceberg-risk field and Maitri→Bharati route search.
- FastAPI endpoint smoke test exercises health, config, grid, forecast, iceberg projection and route endpoints.
- The frontend uses the forecast horizon in both rendering and route requests.
- The backend reports whether the loaded dataset is synthetic or real-sea-ice-only.

A complete production validation still requires domain validation against historical observations, real wind/current/iceberg inputs, forecast skill metrics, operational review and certified navigational safety procedures.
