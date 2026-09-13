# Data freshness and provenance

Antarctic Navigator distinguishes the date represented by a source from the time that the source file was ingested into the application bundle. The dashboard therefore does not describe every source as “live”.

Each real bundle records:

- **Sea-ice observation** — date represented by the NSIDC G10016 Version 4 file.
- **Iceberg source update** — latest update date contained in the current USNIC CSV.
- **Ocean-current observation** — date represented by the OSCAR NRT source file.
- **Wind analysis** — date represented by the ERA5 `valid_time` field.
- **Retrieved** — UTC timestamp taken from the source file's local filesystem modification time when it is ingested into `navigator_bundle.json`.
- **Bundle generated** — UTC time at which `navigator_bundle.json` was written.

Different providers publish with different latency/schedules, so an observation/analysis date can legitimately be older than the bundle-generation time. The UI shows the per-source date and retrieval time rather than a generic “live data” label.

The `/api/data-status` endpoint exposes the same structured metadata used by the frontend. If OSCAR or ERA5 is present, the bundle validator requires both its source date and retrieval timestamp to be populated.
