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
