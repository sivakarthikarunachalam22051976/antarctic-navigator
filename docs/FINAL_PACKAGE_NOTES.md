## v0.6.1 consolidated validation release

This release combines the v0.5.4 truth-hardening with v0.6.0 validation tooling, plus a release-level validation orchestrator and environment doctor. Historical accuracy numbers are never fabricated; historical scoring is reported as blocked until the required source datasets are actually present.

# Final package notes

This archive is a clean source-and-real-data snapshot of Antarctic Navigator.

Included:
- application source code
- documentation and scripts
- frontend package-lock/package.json
- validated real-data bundle
- the source NetCDF/CSV files used for that bundle
- VS Code Pylance workspace setting for the `backend` import root

Intentionally excluded because they are generated or machine-specific:
- `.git/`
- `venv/` / `.venv/`
- `frontend/node_modules/`
- `frontend/dist/`
- Python `__pycache__/` and `.pyc` files
- `.dodsrc` (local Earthdata/DAAC configuration)

Create the local virtual environment and install dependencies with the commands in `README.md` / `docs/REAL_DATA_SETUP.md` before running the project on another machine.


## v0.5.4 truth-hardening and route/control validation

- All six vessel profiles are exercised against the real Maitri→Bharati corridor.
- All three route objectives (Safest/Fastest/Balanced) are exercised.
- All mission profiles and priority/exposure selector values are exercised in the self-check.
- API smoke tests cover configuration, data status, iceberg projection, EPSG:3031 geometry, polar screening, route generation, and voyage simulation.
- Real-data mode is strict by default: missing real bundle no longer silently switches to synthetic data.
- Synthetic fallback is available only when explicitly setting `ALLOW_SYNTHETIC_FALLBACK=1` for offline testing.

- Truth-hardened model inventory: the MVP does not claim a trained deep-learning or classical ML model; its predictive layer is statistical and its optimisation/physics layers are explicit.
