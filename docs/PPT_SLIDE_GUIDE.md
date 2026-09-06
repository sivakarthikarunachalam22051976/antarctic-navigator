# SIH PPT slide guide — Antarctic Navigator (SIH26059)

Verify the exact current template on your team's SIH portal before
finalizing — slide counts and section names have varied by edition, and
neither this guide nor any other AI-generated one is a substitute for
checking the actual document your screening committee will use. Multiple
independent sources point to a 6-slide idea-submission structure as the
common default; use that as your starting point.

## Slide 1 — Title
PS ID (SIH26059), exact PS title, theme (copy exact wording from the
portal), category (Software), team ID/name exactly as registered. No
college name or logo if your screening round requires anonymity. Visual:
a clean map of the Southern Ocean/Antarctica with Maitri and Bharati
marked — not a decorative AI-generated ice landscape.

## Slide 2 — Idea / Proposed Solution
One-line pitch: a decision-support system that fuses sea-ice forecasts,
iceberg drift, and vessel constraints to recommend lower-risk Antarctic
logistics routes. Show the problem in three short boxes (dynamic ice,
moving iceberg hazards, complex operator trade-offs), then a flowchart:
data → forecast + drift → combined risk field → route optimizer → route
options → operator decision. State your actual differentiator explicitly:
India-specific, explainable, offline-capable — not "first of its kind."

## Slide 3 — Technical Approach
Data sources (NSIDC sea-ice CDR, and — once you build them — ERA5 wind,
OSCAR currents, BYU iceberg tracks, NCPOR station context) feeding a
processing pipeline (ingestion → forecast + drift model → combined risk
field → vessel-specific A* routing → FastAPI → Leaflet map). Group tech
stack by function, not a flat language list — data / modelling /
optimisation / backend / visualisation. State plainly that the current
prototype uses an explainable statistical forecast baseline and a
simplified drift model, not a trained ML system — and that a production
version would validate against historical data with proper uncertainty
estimates. Honesty here reads as competence, not weakness.

## Slide 4 — Feasibility & Viability (business model goes here)
**Technical feasibility:** public data, no proprietary barrier; offline
demo capability as a deliberate reliability choice, not a limitation.
**Risk → mitigation table:** data latency → cached fallback; forecast
uncertainty → confidence framing, not false precision; iceberg position
error → risk zone rather than a point; venue network failure → offline
synthetic dataset always available.
**Revenue model — B2G primary** (NCPOR / Indian Antarctic Programme /
Ministry of Earth Sciences, as an operational planning tool), **B2B
secondary** (polar logistics/expedition operators; insurers only once you
have an actual validated risk-reduction case study, not before). Revenue
streams: licensing, data/API subscription, deployment & support — don't
invent specific rupee figures without market validation to back them.
**Scalability:** state the real architectural property you have —
stateless API layer, sea-ice/scientific data separated from route/session
data — rather than a specific user-count claim you haven't benchmarked.

## Slide 5 — Impact & Benefits
Before/after visual: static fragmented ice information + manual
interpretation → dynamic risk map + route options + operator decision.
Benefit categories: safety (earlier hazard visibility), efficiency (avoid
unnecessary high-ice exposure), adaptability (recompute as forecasts
update), India-specific value (built around actual Indian Antarctic
station logistics), reusability (architecture generalizes to other polar
environmental decision support). Don't cite specific percentage
improvements (fuel saved, time saved) unless you've actually measured
them against historical routes — say "target: quantify against historical
backtesting" instead.

## Slide 6 — Research & References
NSIDC (sea-ice CDR, G02202/G10016), Bigg et al. (1997) for iceberg
dynamics, and — importantly — acknowledge PolarRoute (British Antarctic
Survey, open source) and IcySea (commercial, Drift+Noise/Norwegian
Meteorological Institute) as related prior work you're aware of and
positioning against, not competing to hide from a judge who already
knows about them. If asked "isn't this already done?", answer directly:
"Yes, polar route planning exists — our contribution is an India-specific,
explainable, offline-capable workflow for Antarctic research logistics,
not a claim that route optimization itself is new."

## General formatting
Diagrams and maps over paragraphs — aim for the content to communicate in
under a minute of scanning. Keep bullets short. Use your own generated
route/risk output as a screenshot rather than a mockup wherever possible —
a real screenshot of your own working system is stronger evidence than
any illustration.
