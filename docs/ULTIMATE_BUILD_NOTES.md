# Ultimate build notes — v0.5.0

This release keeps Antarctic Navigator's source-derived real-data pipeline and adds selected capabilities observed in a separate public SIH26059 reference implementation.

Added/retained:
- Real NSIDC G10016 v4 + USNIC + OSCAR NRT + ERA5 bundle as production/demo data.
- Strict real-data default; synthetic fixture is test/offline only and requires explicit opt-in.
- RK4 iceberg drift with small uncertainty ensemble.
- Vessel-specific ice-performance planning model.
- Polar safety screening inspired by POLARIS, explicitly non-regulatory.
- Antarctic EPSG:3031 geometry.
- Voyage intelligence with ETA, alerts and fuel planning proxy.
- Mission-aware A/B/C routing, explainability and provenance.
- Closest projected iceberg-to-route metric.

Intentionally excluded:
- Synthetic environmental fields as the production dataset.
- Competitor trained model weights.
- Claims of operational validation that the available data does not support.
- Full regulatory POLARIS certification.
- Autonomous vessel control.
- Measured fuel/time savings.

The reference project was used only for feature comparison; its source code is not included.
