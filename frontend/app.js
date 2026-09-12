import L from "leaflet";
import "leaflet/dist/leaflet.css";

const API_BASE = (import.meta.env.VITE_API_BASE || "http://localhost:8000").replace(/\/$/, "");
const REQUEST_TIMEOUT_MS = 15000;

const map = L.map("map", {
  minZoom: 2,
  maxZoom: 8,
}).setView([-69.5, 45], 4);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "© OpenStreetMap contributors",
  maxZoom: 8,
}).addTo(map);

const concentrationLayer = L.layerGroup().addTo(map);
const icebergLayer = L.layerGroup().addTo(map);
const routeLayer = L.layerGroup().addTo(map);
const stationLayer = L.layerGroup().addTo(map);

let routeStart = null;
let routeGoal = null;
let stationData = {};
let currentForecast = 3;
let currentForecastGrid = null;
let baseGrid = null;

function formatUtc(value) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toISOString().replace("T", " ").replace(".000Z", " UTC");
}

function renderDataStatus(status) {
  const container = document.getElementById("data-status");
  if (!container) return;

  const source = status.sources || {};

  const card = (item, dateLabel) => {
    const available = item.status === "available";
    return `
      <div class="freshness-card ${available ? "available" : "muted-card"}">
        <div class="freshness-title">${item.label}</div>
        <div class="freshness-source">${item.source || "Not connected"}</div>
        <div class="freshness-row"><span>${dateLabel}</span><strong>${item.observation_date || "Not available"}</strong></div>
        <div class="freshness-row"><span>Retrieved</span><strong>${formatUtc(item.retrieved_at_utc)}</strong></div>
      </div>`;
  };

  container.innerHTML =
    card(source.sea_ice || {}, "Observation") +
    card(source.icebergs || {}, "Source update") +
    card(source.currents || {}, "Observation") +
    card(source.wind || {}, "Analysis") +
    `<div class="freshness-footer">
      <div><span>Bundle generated</span><strong>${formatUtc(status.bundle_generated_at_utc)}</strong></div>
      <div><span>Routing status</span><strong>${status.routing_status || "Unknown"}</strong></div>
    </div>`;
}

async function loadDataStatus() {
  const data = await fetchJson("/api/data-status");
  renderDataStatus(data);
}

function setStatus(message, ok = false) {
  document.getElementById("status-text").textContent = message;
  document.getElementById("status-indicator").classList.toggle("ok", ok);
}

function displayDatasetLabel(meta = {}) {
  const kind = String(meta.dataset_kind || "unknown");
  if (kind === "real_seaice_and_usnic_icebergs" || kind === "real_seaice_usnic_icebergs") return "Real sea ice + USNIC icebergs";
  if (kind === "real_seaice_only") return "Real NSIDC sea ice";
  if (kind === "synthetic") return "Synthetic demo";
  return kind;
}

function setSourceMetadata(meta = {}) {
  document.getElementById("dataset-label").textContent = displayDatasetLabel(meta);

  const lines = [];
  if (meta.sea_ice_dataset || meta.source) {
    const source = meta.sea_ice_dataset
      ? `${meta.sea_ice_dataset} Version ${meta.sea_ice_version || "?"}`
      : meta.source;
    lines.push(`SEA ICE: ${source}`);
  }
  if (meta.observation_date) lines.push(`DATA DATE: ${meta.observation_date}`);
  if (meta.iceberg_source && Number(meta.iceberg_records_used) > 0) {
    lines.push(`ICEBERGS: ${meta.iceberg_source} (${meta.iceberg_records_used} in region)`);
  }
  if (meta.iceberg_observation_date) {
    lines.push(`ICEBERG UPDATE: ${meta.iceberg_observation_date}`);
  }
  if (meta.environmental_forcing) {
    lines.push(`FORCING: ${meta.environmental_forcing}`);
  }
  if (meta.trajectory_basis) {
    lines.push(`TRAJECTORY: ${meta.trajectory_basis}`);
  }
  if (meta.historical_validation_source) {
    lines.push(`VALIDATION: ${meta.historical_validation_source}`);
  }

  document.getElementById("source-note").textContent = lines.join("\n");
}

async function fetchJson(path, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${API_BASE}${path}`, { signal: controller.signal });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : { detail: await response.text() };

    if (!response.ok) {
      throw new Error(payload?.detail || `Request failed (${response.status})`);
    }

    return payload;
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error("The backend took too long to respond. Please try again.");
    }
    if (error instanceof TypeError) {
      throw new Error(
        "Could not reach the Antarctic Navigator backend. Check that FastAPI is running.",
      );
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function concentrationColor(value) {
  const v = Math.max(0, Math.min(1, Number(value) || 0));
  const a = [230, 246, 250];
  const b = [20, 62, 82];
  const c = a.map((x, i) => Math.round(x + v * (b[i] - x)));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function renderSeaIce(grid) {
  baseGrid = grid;
  const values = currentForecastGrid || grid.concentration;
  concentrationLayer.clearLayers();

  const rows = grid.lat.length;
  const cols = grid.lat[0].length;
  const step = Math.max(1, Math.floor(Math.min(rows, cols) / 90));
  const latStep = Math.abs(grid.lat[Math.min(rows - 1, 1)][0] - grid.lat[0][0]) / 2 || 0.1;
  const lonStep = Math.abs(grid.lon[0][Math.min(cols - 1, 1)] - grid.lon[0][0]) / 2 || 0.25;

  for (let r = 0; r < rows; r += step) {
    for (let c = 0; c < cols; c += step) {
      const concentration = Number(values[r][c]) || 0;
      if (concentration < 0.03) continue;

      const lat = grid.lat[r][c];
      const lon = grid.lon[r][c];

      L.rectangle(
        [
          [lat - latStep, lon - lonStep],
          [lat + latStep, lon + lonStep],
        ],
        {
          color: "transparent",
          fillColor: concentrationColor(concentration),
          fillOpacity: 0.62,
          weight: 0,
          interactive: false,
        },
      ).addTo(concentrationLayer);
    }
  }
}

async function loadSeaIceGrid() {
  const data = await fetchJson("/api/seaice/grid");
  currentForecastGrid = data.concentration;
  renderSeaIce(data);
  setSourceMetadata(data.meta || {});

  const flatLat = data.lat.flat();
  const flatLon = data.lon.flat();
  const bounds = [
    [Math.min(...flatLat), Math.min(...flatLon)],
    [Math.max(...flatLat), Math.max(...flatLon)],
  ];
  map.fitBounds(bounds, { padding: [10, 10], maxZoom: 4 });
}

async function loadForecast() {
  const data = await fetchJson(
    `/api/seaice/forecast?horizon_days=${currentForecast}`,
  );

  currentForecastGrid = data.forecast[currentForecast - 1];
  if (baseGrid) renderSeaIce(baseGrid);

  document.getElementById("forecast-label").textContent =
    `Forecast day +${currentForecast}`;

  if (data.meta) setSourceMetadata(data.meta);
}

async function loadConfig() {
  const data = await fetchJson("/api/config");
  stationData = data.stations || {};
  stationLayer.clearLayers();

  Object.entries(stationData).forEach(([name, point]) => {
    const marker = L.circleMarker([point.lat, point.lon], {
      radius: 7,
      color: "#f6f1a8",
      fillColor: "#f6f1a8",
      fillOpacity: 1,
      weight: 2,
    });

    marker.bindPopup(
      `<b>${name}</b><br>` +
      `Indian Antarctic research station<br>` +
      `Route endpoint: ${Number(point.route_lat).toFixed(2)}, ${Number(point.route_lon).toFixed(2)}`,
    );

    marker.addTo(stationLayer);
  });
}

async function loadIcebergs() {
  const data = await fetchJson(
    `/api/icebergs/projected?hours_ahead=${currentForecast * 24}`,
  );

  const projectedIcebergs = data.icebergs || [];
  const list = document.getElementById("iceberg-list");

  icebergLayer.clearLayers();
  document.getElementById("iceberg-count").textContent = projectedIcebergs.length;
  list.innerHTML = "";

  projectedIcebergs.forEach((berg) => {
    L.circleMarker([berg.projected_lat, berg.projected_lon], {
      radius: 5,
      color: "#f2a154",
      fillColor: "#f2a154",
      fillOpacity: 0.9,
      weight: 1,
    })
      .bindPopup(
        `<b>${berg.id}</b><br>` +
        `Length: ${Number(berg.length_km || 0).toFixed(1)} km<br>` +
        `Observed: ${Number(berg.lat).toFixed(2)}, ${Number(berg.lon).toFixed(2)}<br>` +
        `Projected +${berg.hours_ahead}h: ${Number(berg.projected_lat).toFixed(2)}, ${Number(berg.projected_lon).toFixed(2)}<br>` +
        `${berg.source ? `Source: ${berg.source}<br>` : ""}` +
        `${berg.source_updated ? `Source update: ${berg.source_updated}` : ""}`,
      )
      .addTo(icebergLayer);

    const displacement = Math.hypot(
      berg.projected_lat - berg.lat,
      berg.projected_lon - berg.lon,
    );

    if (displacement > 0.00001) {
      L.polyline(
        [
          [berg.lat, berg.lon],
          [berg.projected_lat, berg.projected_lon],
        ],
        {
          color: "#f2a154",
          weight: 1,
          dashArray: "4,4",
          opacity: 0.7,
        },
      ).addTo(icebergLayer);
    }

    const item = document.createElement("div");
    item.className = "iceberg-item";
    item.innerHTML =
      `<span>${berg.id}</span>` +
      `<span class="size">${Number(berg.length_km || 0).toFixed(1)} km</span>`;
    list.appendChild(item);
  });

  if (data.meta) setSourceMetadata(data.meta);
}

function updateRouteUI() {
  document.getElementById("start-coord").textContent = routeStart
    ? `${routeStart.lat.toFixed(2)}, ${routeStart.lng.toFixed(2)}`
    : "—";

  document.getElementById("goal-coord").textContent = routeGoal
    ? `${routeGoal.lat.toFixed(2)}, ${routeGoal.lng.toFixed(2)}`
    : "—";

  document.getElementById("compute-route-btn").disabled = !(routeStart && routeGoal);
}

function stationRoutePoint(point) {
  return L.latLng(
    Number(point.route_lat ?? point.lat),
    Number(point.route_lon ?? point.lon),
  );
}

function selectStation(name) {
  const point = stationData[name];
  if (!point) return;

  const routePoint = stationRoutePoint(point);

  if (!routeStart || routeGoal) {
    routeStart = routePoint;
    routeGoal = null;
    routeLayer.clearLayers();
  } else {
    routeGoal = routePoint;
  }

  updateRouteUI();
  map.setView([point.lat, point.lon], 5);
}

document.querySelectorAll(".station-btn").forEach((button) => {
  button.addEventListener("click", () => selectStation(button.dataset.station));
});

map.on("click", (event) => {
  if (!routeStart || routeGoal) {
    routeStart = event.latlng;
    routeGoal = null;
    routeLayer.clearLayers();
  } else {
    routeGoal = event.latlng;
  }

  updateRouteUI();
});

document.getElementById("clear-route-btn").addEventListener("click", () => {
  routeStart = null;
  routeGoal = null;
  routeLayer.clearLayers();
  document.getElementById("route-result").textContent = "";
  updateRouteUI();
});

document.getElementById("compute-route-btn").addEventListener("click", async () => {
  const result = document.getElementById("route-result");
  if (!routeStart || !routeGoal) return;

  result.textContent = "Computing risk-aware route…";

  const vessel = document.getElementById("vessel-profile").value;

  try {
    const query = new URLSearchParams({
      start_lat: routeStart.lat,
      start_lon: routeStart.lng,
      goal_lat: routeGoal.lat,
      goal_lon: routeGoal.lng,
      horizon_days: currentForecast,
      vessel_profile: vessel,
    });

    const data = await fetchJson(`/api/route?${query}`, 30000);
    routeLayer.clearLayers();

    const points = data.path.map((point) => [point.lat, point.lon]);

    L.polyline(points, {
      color: "#4fd8e8",
      weight: 4,
      opacity: 0.95,
    }).addTo(routeLayer);

    L.circleMarker(points[0], {
      radius: 7,
      color: "#4fd8e8",
      fillColor: "#4fd8e8",
      fillOpacity: 1,
    }).addTo(routeLayer);

    L.circleMarker(points[points.length - 1], {
      radius: 7,
      color: "#9ff6c8",
      fillColor: "#9ff6c8",
      fillOpacity: 1,
    }).addTo(routeLayer);

    const snapNote =
      data.start_snapped_to_ocean || data.goal_snapped_to_ocean
        ? " · endpoint snapped to nearest navigable ocean cell"
        : "";

    const assessment = data.route_assessment || "Risk assessment unavailable.";
    const assessmentClass = assessment.startsWith("High") ? "route-warning" : "muted";

    result.innerHTML =
      `<span class="ok">Risk-weighted route found</span><br>` +
      `${data.distance_km.toFixed(0)} km · ` +
      `mean ice ${(100 * data.mean_ice_concentration).toFixed(0)}% · ` +
      `max ice ${(100 * data.max_ice_concentration).toFixed(0)}% · ` +
      `max iceberg risk ${(100 * data.max_iceberg_risk).toFixed(0)}%<br>` +
      `<span class="${assessmentClass}">${assessment}</span><br>` +
      `<span class="muted">Forecast +${data.horizon_days}d · ${data.vessel_profile}${snapNote}</span>`;
  } catch (error) {
    result.innerHTML = `<span class="err">${error.message}</span>`;
  }
});

document.getElementById("horizon-slider").addEventListener("input", async (event) => {
  currentForecast = Number(event.target.value);
  document.getElementById("horizon-value").textContent = currentForecast;

  try {
    await loadForecast();
    await loadIcebergs();
  } catch (error) {
    console.error(error);
    setStatus("Forecast unavailable", false);
  }
});

async function init() {
  try {
    setStatus("Loading polar data…");

    await Promise.all([
      loadConfig(),
      loadSeaIceGrid(),
      loadDataStatus(),
    ]);

    await loadForecast();
    await loadIcebergs();

    setStatus("Backend online", true);
  } catch (error) {
    setStatus("Backend unavailable — start FastAPI", false);
    console.error(error);
  }
}

updateRouteUI();
init();
