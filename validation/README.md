# Validation evidence

This directory stores **measured outputs only**. Empty/missing historical reports are intentional; the project never invents accuracy numbers.

## Run the complete release validation

```powershell
$env:USE_REAL_DATA="1"
$env:ALLOW_SYNTHETIC_FALLBACK="0"
python scripts\run_full_validation.py
```

The orchestrator always runs:
- project self-check;
- real-bundle validation;
- deterministic iceberg-position route robustness.

It runs historical iceberg and sea-ice scoring only when their required datasets are actually present. Missing historical data is reported as `BLOCKED`, never as a successful validation.

## Historical iceberg data

Run:

```powershell
python backend\data\fetch_byu_historical.py
python backend\data\validate_byu_historical.py
python scripts\validate_iceberg_backtest.py --tracks backend\data\real\historical\byu_v8.0
```

The current backtest reports a **constant-velocity benchmark**. It does not mislabel that benchmark as RK4 validation. A true historical RK4 score requires historical environmental forcing matched to the forecast start date.

## Historical sea ice

Place consecutive historical NSIDC daily NetCDF files in `backend/data/real/historical/nsidc/`, then:

```powershell
python scripts\validate_seaice_forecast.py --data-dir backend\data\real\historical\nsidc
```

## Route robustness

```powershell
python scripts\route_robustness.py --horizon 3 --vessel standard
```

This is deterministic sensitivity analysis, not a confidence interval and not a probability-of-collision estimate.
