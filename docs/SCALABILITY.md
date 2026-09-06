# Scalability notes — from hackathon prototype to production

This describes what would change to take the prototype toward a production
deployment. It's a roadmap for your slides and Q&A prep, not something
that's built — don't present it as already implemented.

## What's true right now (be honest about this)

The current backend loads one dataset into memory (`_dataset` global in
`main.py`) and computes forecast/route on every request. That's completely
fine for a hackathon demo and a handful of concurrent judges hitting it,
and it is honest to say the API layer is already stateless — each request
is independent, nothing but the loaded dataset is shared server-side state.
It is not honest to say it's already load-tested at any particular scale,
because it hasn't been.

## What would actually need to change to scale

**Cache repeated computation.** Forecast and route requests for the same
horizon/vessel/region are currently recomputed from scratch every time.
A production version would cache forecast grids and common route queries
(Redis is a reasonable choice) so repeated requests don't redo the same
A* search.

**Move heavy computation off the request path.** Forecasting and routing
over a larger grid than this demo's 60x180 would be too slow to compute
synchronously inside an HTTP request. An async worker queue (e.g. Celery
or RQ) would let the API return quickly while the actual computation runs
in the background, with the client polling or getting a websocket update.

**Separate scientific data from transactional data.** Route history, user
sessions, and station metadata belong in a normal relational store (e.g.
PostgreSQL, with PostGIS if you want to do server-side geospatial queries
on routes/stations). Large gridded scientific data (sea-ice fields, wind/
current fields) doesn't belong in a relational database — object storage
with a format built for it (Zarr or Cloud-Optimized GeoTIFF) scales much
better for that kind of array data.

**Stateless API + load balancer.** Because there's no per-request server-
side session state today, horizontally scaling the API layer behind a
load balancer is straightforward once the dataset itself is served from
shared storage/cache rather than loaded into each process's memory
independently.

**Offline/edge mode for actual field use.** If this were ever used on an
actual vessel or at a station with unreliable connectivity, the
architecture should support a cached local copy of the latest forecast
and route recommendations that keeps working without a live connection —
similar in spirit to the demo's offline synthetic fallback, but backed by
real cached data instead.

## What NOT to claim on a slide

Don't say "this scales to 100,000 users" — you have no benchmark to back
that number, and a judge who asks "how do you know" will have a fair
question you can't answer. Do say: "the API layer is stateless, scientific
data is separated from transactional data, and the heaviest computation
(forecasting, routing) is designed to move to asynchronous workers — which
is what horizontal scalability actually requires architecturally." That's
a defensible, technically accurate claim rather than an invented number.
