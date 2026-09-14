# Validation and scientific evidence

Antarctic Navigator now includes an explicit validation workflow so that model claims are tied to measured evidence rather than architecture names.

## A. Historical iceberg trajectory validation

Source: **BYU/NIC consolidated Antarctic iceberg database v8.0** for historical tracks.

Run:

```powershell
python backend\data\fetch_byu_historical.py
python backend\data\validate_byu_historical.py
python scripts\validate_iceberg_backtest.py --tracks backend\data\real\historical\byu_v8.0
```

The supplied backtest script first calculates a transparent **constant-velocity benchmark**. It deliberately does not call that RK4 validation. A valid RK4 historical score requires environmental forcing from the same historical dates (currents/wind) so the model receives the information that would actually have been available at the forecast start.

Metrics reported when the benchmark is run:

- median trajectory error (km)
- MAE (km)
- RMSE (km)
- 90th-percentile error (km)

No value should be inserted into the PPT unless it is produced by the script from held-out observations.

## B. Quantitative sea-ice forecast validation

Use historical NSIDC daily concentration files and run:

```powershell
python scripts\validate_seaice_forecast.py --data-dir C:\path\to\historical\nsidc
```

The validator compares:

1. Antarctic Navigator's **adaptive persistence + seasonal correction fallback**; the live serving path adds conservative semi-Lagrangian advection when matched environmental forcing is available
2. Pure persistence

for 1–7 day horizons, reporting:

- MAE
- RMSE
- bias
- Pearson correlation

This makes the baseline measurable before any ML model is introduced.

## C. Route robustness

The current real-data bundle can be stress-tested without pretending that iceberg uncertainty is perfectly known:

```powershell
$env:USE_REAL_DATA="1"
$env:ALLOW_SYNTHETIC_FALLBACK="0"
python scripts\route_robustness.py --horizon 3 --vessel standard
```

The test applies ±5 km, ±10 km and ±20 km radial position perturbations in eight bearings. It reports reroute success and the risk experienced by the baseline corridor under the perturbed fields.

The result is **sensitivity analysis**, not a confidence interval or a probability-of-collision estimate.

## D. Model comparison policy

A future ML model should be compared with the transparent baseline only after the baseline has been scored on held-out historical observations. The comparison should use the same dates, same target variables and same metrics.

The project intentionally does not claim a ConvLSTM/CNN/LSTM/U-Net/Random Forest/XGBoost/Transformer model in the MVP. Model complexity is not treated as evidence of predictive skill.

## Operational limitation

No software-only test establishes navigation safety. Operational deployment would additionally require validated vessel-specific performance, higher-resolution/operational ice information, uncertainty calibration, domain-expert review and regulatory/certification processes.
