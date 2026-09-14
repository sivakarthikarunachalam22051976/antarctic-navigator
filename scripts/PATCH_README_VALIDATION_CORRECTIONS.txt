ANTARCTIC NAVIGATOR — VALIDATION CORRECTION PATCH

This patch fixes validation methodology issues without altering the production routing/model code.

1) ICEBERG BACKTEST
- Scores only exact calendar horizons (+1d and +3d).
- Requires an observation exactly one day before initialization.
- No nearest-date substitution.
- Adds P90, P95, maximum error and explicit >100 km outlier count.
- Keeps the benchmark explicitly labeled as constant-velocity, NOT RK4 validation.

2) SEA-ICE BACKTEST
- Scores only exact calendar horizons, so missing dates can no longer shift a nominal 1/2/3/... day target onto a different date.
- Reports missing dates and skipped gap windows.
- Explicitly states that this historical validator evaluates the no-forcing persistence/seasonal component because historical OSCAR/ERA5 forcing was not supplied.
- Does not claim operational skill or superiority over persistence.

3) NSIDC GAP CHECK
- New scripts/check_nsidc_gaps.py reports calendar gaps.
- It never fabricates, interpolates, or substitutes missing observations.

IMPORTANT
The two NSIDC dates 2026-08-09 and 2026-08-10 are not merely a local validation bug. The directory listing supplied for the G02202 v6 historical dataset jumps directly from 2026-08-08 to 2026-08-11. Therefore those observations must NOT be invented or filled from another product. The corrected validator excludes affected forecast windows and records the gap.

This patch makes the validation honest and reproducible. It cannot make a scientific model “100% accurate”; it prevents the software from overstating what the available data can prove.
