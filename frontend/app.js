import L from "leaflet";
import "leaflet/dist/leaflet.css";

const API_BASE = (import.meta.env.VITE_API_BASE || "http://localhost:8000").replace(/\/$/, "");
const REQUEST_TIMEOUT_MS = 15000;
const ROUTE_TIMEOUT_MS = 30000;

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
let routeCandidates = [];
let recommendedRouteId = null;

const ROUTE_STYLES = {
  A: { color: "#72e5ad", label: "Safest", dashArray: "7,6" },
  B: { color: "#f2a154", label: "Fastest", dashArray: "4,6" },
  C: { color: "#4fd8e8", label: "Balanced", dashArray: null },
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatUtc(value) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toISOString().replace("T", " ").replace(".000Z", " UTC");
}

function riskBand(value) {
  const score = Math.max(0, Math.min(1, Number(value) || 0));
  if (score < 0.33) return "Low";
  if (score < 0.66) return "Moderate";
  return "High";
}

function renderDataStatus(status) {
  const container = document.getElementById("data-status");
  if (!container) return;

  const source = status.sources || {};
  const rows = [
    ["SEA ICE", source.sea_ice || {}, "Observation"],
    ["ICEBERGS", source.icebergs || {}, "Source update"],
    ["OCEAN CURRENTS", source.currents || {}, "Observation"],
    ["WIND", source.wind || {}, "Analysis"],
  ];

  const sourceRows = rows.map(([label, item, dateLabel]) => {
    const available = item.status === "available";
    const date = item.observation_date || "Not available";
    const retrieved = formatUtc(item.retrieved_at_utc);
    const statusLabel = available ? "Available" : "Not connected";

    return `
      <tr>
        <th scope="row">
          <span class="source-name">${escapeHtml(label)}</span>
          <span class="source-provider">${escapeHtml(item.source || "Not connected")}</span>
        </th>
        <td>
          <span class="source-date-label">${escapeHtml(dateLabel)}</span>
          <strong>${escapeHtml(date)}</strong>
        </td>
        <td>${escapeHtml(retrieved)}</td>
        <td><span class="source-status ${available ? "available" : "unavailable"}">${statusLabel}</span></td>
      </tr>`;
  }).join("");

  const realActive = status.real_data_active === true;
  const integrity = realActive
    ? `<div class="data-integrity real"><strong>REAL DATA ACTIVE</strong><span>Source-derived environmental bundle is driving this application.</span></div>`
    : `<div class="data-integrity warning"><strong>SYNTHETIC / OFFLINE MODE</strong><span>Not suitable for the real-data demonstration.</span></div>`;

  container.innerHTML = `
    ${integrity}
    <div class="freshness-table-wrap">
      <table class="freshness-table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Data date</th>
            <th>Retrieved</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>${sourceRows}</tbody>
      </table>
    </div>
    <div class="freshness-summary">
      <div>
        <span>Bundle generated</span>
        <strong>${escapeHtml(formatUtc(status.bundle_generated_at_utc))}</strong>
      </div>
      <div>
        <span>Routing status</span>
        <strong>${escapeHtml(status.routing_status || "Unknown")}</strong>
      </div>
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
  if (meta.real_data_active === true) return "REAL DATA ACTIVE · NSIDC + USNIC + OSCAR + ERA5";
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
  if (meta.iceberg_observation_date) lines.push(`ICEBERG UPDATE: ${meta.iceberg_observation_date}`);
  if (meta.environmental_forcing) lines.push(`FORCING: ${meta.environmental_forcing}`);
  if (meta.trajectory_basis) lines.push(`TRAJECTORY: ${meta.trajectory_basis}`);
  if (meta.historical_validation_source) lines.push(`VALIDATION: ${meta.historical_validation_source}`);

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
      throw new Error("Could not reach the Antarctic Navigator backend. Check that FastAPI is running.");
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
  const data = await fetchJson(`/api/seaice/forecast?horizon_days=${currentForecast}`);
  currentForecastGrid = data.forecast[currentForecast - 1];
  if (baseGrid) renderSeaIce(baseGrid);

  document.getElementById("forecast-label").textContent = `Forecast day +${currentForecast}`;
  if (data.meta) setSourceMetadata(data.meta);
}

function populateSelect(select, entries, selected) {
  select.innerHTML = entries
    .map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`)
    .join("");
  if (selected) select.value = selected;
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
      `<b>${escapeHtml(name)}</b><br>` +
      `Indian Antarctic research station<br>` +
      `Route endpoint: ${Number(point.route_lat).toFixed(2)}, ${Number(point.route_lon).toFixed(2)}`,
    );

    marker.addTo(stationLayer);
  });

  const vesselEntries = Object.entries(data.vessel_profiles || {}).map(([value, item]) => [value, item.label || value]);
  const missionEntries = Object.entries(data.mission_profiles || {}).map(([value, item]) => [value, item.label]);
  const priorityEntries = Object.entries(data.priority_profiles || {}).map(([value, item]) => [value, item.label]);
  const exposureEntries = Object.entries(data.ice_exposure_limits || {}).map(([value]) => [value, value.charAt(0).toUpperCase() + value.slice(1)]);
  const freshnessEntries = (data.freshness_options_hours || [24, 48, 72, 168]).map((hours) => [String(hours), `< ${hours}h`]);

  populateSelect(document.getElementById("vessel-profile"), vesselEntries, "ice_capable");
  populateSelect(document.getElementById("mission-profile"), missionEntries, "resupply");
  populateSelect(document.getElementById("route-priority"), priorityEntries, "balanced");
  populateSelect(document.getElementById("max-ice-exposure"), exposureEntries, "medium");
  populateSelect(document.getElementById("freshness-requirement"), freshnessEntries, "48");
}

async function loadIcebergs() {
  const data = await fetchJson(`/api/icebergs/projected?hours_ahead=${currentForecast * 24}`);
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
        `<b>${escapeHtml(berg.id)}</b><br>` +
        `Length: ${Number(berg.length_km || 0).toFixed(1)} km<br>` +
        `Observed: ${Number(berg.lat).toFixed(2)}, ${Number(berg.lon).toFixed(2)}<br>` +
        `Projected +${berg.hours_ahead}h: ${Number(berg.projected_lat).toFixed(2)}, ${Number(berg.projected_lon).toFixed(2)}<br>` +
        `${berg.source ? `Source: ${escapeHtml(berg.source)}<br>` : ""}` +
        `${berg.source_updated ? `Source update: ${escapeHtml(berg.source_updated)}` : ""}`,
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
      `<span>${escapeHtml(berg.id)}</span>` +
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

function drawRouteOnMap(candidate, selectedRouteId = recommendedRouteId) {
  const style = ROUTE_STYLES[candidate.id] || ROUTE_STYLES.C;
  const points = candidate.path.map((point) => [point.lat, point.lon]);
  const selected = candidate.id === selectedRouteId;

  if (points.length < 2) return;

  L.polyline(points, {
    color: style.color,
    weight: selected ? 5 : 2.5,
    opacity: selected ? 0.98 : 0.50,
    dashArray: selected ? null : style.dashArray,
    interactive: true,
  })
    .bindPopup(
      `<b>Route ${escapeHtml(candidate.id)} — ${escapeHtml(candidate.label)}</b><br>` +
      `Distance: ${candidate.distance_km.toFixed(0)} km<br>` +
      `Risk score: ${candidate.risk_score.toFixed(2)}<br>` +
      `Ice exposure: ${escapeHtml(candidate.exposure_band)}<br>` +
      `Iceberg risk: ${escapeHtml(riskBand(candidate.max_iceberg_risk))}`,
    )
    .addTo(routeLayer);

  if (selected) {
    L.circleMarker(points[0], {
      radius: 7,
      color: style.color,
      fillColor: style.color,
      fillOpacity: 1,
    }).addTo(routeLayer);

    L.circleMarker(points[points.length - 1], {
      radius: 7,
      color: "#9ff6c8",
      fillColor: "#9ff6c8",
      fillOpacity: 1,
    }).addTo(routeLayer);
  }
}

function renderAllRoutes(selectedRouteId = recommendedRouteId) {
  routeLayer.clearLayers();
  routeCandidates.forEach((candidate) => drawRouteOnMap(candidate, selectedRouteId));
}

function routeDistanceText(candidate) {
  const gap = Number(candidate.distance_over_shortest_pct || 0);
  if (candidate.id === "B" || gap < 0.05) return "Shortest distance";
  return `+${gap.toFixed(1)}% vs shortest`;
}

async function loadVoyageSimulation(data) {
  const container = document.getElementById("voyage-result");
  if (!container || !data?.requested_start || !data?.requested_goal) return;
  container.innerHTML = `<div class="voyage-loading">Running vessel performance simulation…</div>`;

  const query = new URLSearchParams({
    start_lat: data.requested_start.lat,
    start_lon: data.requested_start.lon,
    goal_lat: data.requested_goal.lat,
    goal_lon: data.requested_goal.lon,
    horizon_days: currentForecast,
    vessel_profile: document.getElementById("vessel-profile").value,
    mission: document.getElementById("mission-profile").value,
    priority: document.getElementById("route-priority").value,
    max_ice_exposure: document.getElementById("max-ice-exposure").value,
    freshness_requirement_hours: document.getElementById("freshness-requirement").value,
  });

  try {
    const payload = await fetchJson(`/api/voyage-simulation?${query}`, ROUTE_TIMEOUT_MS);
    const sim = payload.simulation || {};
    const screen = payload.screening || {};
    const alertCount = Array.isArray(sim.alerts) ? sim.alerts.length : 0;
    container.innerHTML = `
      <div class="voyage-card">
        <div class="voyage-header">
          <span class="eyebrow">Voyage intelligence</span>
          <strong>Route ${escapeHtml(payload.route_id || "—")}</strong>
        </div>
        <div class="voyage-metrics">
          <div><span>Model ETA</span><strong>${Number(sim.eta_days || 0).toFixed(2)} d</strong></div>
          <div><span>Speed model</span><strong>${Number(sim.vessel?.design_speed_kn || 0).toFixed(1)} kn</strong></div>
          <div><span>Fuel proxy</span><strong>${Number(sim.estimated_fuel_t || 0).toFixed(1)} t</strong></div>
          <div><span>Alerts</span><strong>${alertCount}</strong></div>
        </div>
        <div class="screening-row ${screen.status === "BLOCK" ? "screen-block" : screen.status === "REVIEW" ? "screen-review" : "screen-pass"}">
          <strong>Polar safety screening: ${escapeHtml(screen.status || "UNKNOWN")}</strong>
          <span>${escapeHtml(screen.reason || "Screening result unavailable")}</span>
        </div>
        <div class="voyage-notice">${escapeHtml(sim.fuel_basis || payload.notice || "Planning estimate only.")}</div>
      </div>`;
  } catch (error) {
    container.innerHTML = `<div class="voyage-card muted">Voyage simulation unavailable: ${escapeHtml(error.message)}</div>`;
  }
}

function renderRouteAlternatives(data) {
  const result = document.getElementById("route-result");
  routeCandidates = data.alternatives || [];
  recommendedRouteId = data.recommendation?.route_id || (routeCandidates[0]?.id ?? null);

  if (!routeCandidates.length) {
    result.innerHTML = `<span class="err">No route candidates were returned.</span>`;
    return;
  }

  renderAllRoutes(recommendedRouteId);

  const recommended = routeCandidates.find((item) => item.id === recommendedRouteId) || routeCandidates[0];
  const missionLabel = data.mission_label || data.mission || "Mission";
  const priorityLabel = data.priority_label || data.priority || "Balanced";
  const freshnessText = data.freshness?.requirement_met
    ? `Met (<${data.freshness_requirement_hours}h)`
    : `Not fully met (<${data.freshness_requirement_hours}h)`;

  const rows = routeCandidates.map((candidate) => {
    const style = ROUTE_STYLES[candidate.id] || ROUTE_STYLES.C;
    const selected = candidate.id === recommendedRouteId;
    const exposure = candidate.exposure_band || riskBand(candidate.risk_score);
    const objective = candidate.label || "Route";
    const distance = Number(candidate.distance_km || 0).toFixed(0);
    const meanIce = (100 * Number(candidate.mean_ice_concentration || 0)).toFixed(0);
    const maxIce = (100 * Number(candidate.max_ice_concentration || 0)).toFixed(0);
    const icebergRisk = (100 * Number(candidate.max_iceberg_risk || 0)).toFixed(0);
    const distanceText = routeDistanceText(candidate);

    return `
      <tr class="route-table-row ${selected ? "recommended" : ""}" data-route-id="${escapeHtml(candidate.id)}" tabindex="0" role="button" aria-label="Select Route ${escapeHtml(candidate.id)} — ${escapeHtml(objective)}" style="--route-accent:${style.color}">
        <th scope="row">
          <span class="route-id">Route ${escapeHtml(candidate.id)}</span>
          <span class="route-objective">${escapeHtml(objective)}</span>
          ${selected ? `<span class="recommended-tag">RECOMMENDED</span>` : ""}
        </th>
        <td>${distance} km<span class="table-subtext">${escapeHtml(distanceText)}</span></td>
        <td>${meanIce}%</td>
        <td>${maxIce}%</td>
        <td>${icebergRisk}%</td>
        <td><span class="exposure-badge exposure-${exposure.toLowerCase()}">${escapeHtml(exposure)}</span></td>
      </tr>`;
  }).join("");

  const explanation = (recommended.explanation || [])
    .map((reason) => `<li>${escapeHtml(reason)}</li>`)
    .join("");

  const dataUsed = data.data_used || {};

  result.innerHTML = `
    <div class="route-result-header">
      <div>
        <span class="eyebrow">Route decision support</span>
        <strong>3 candidate routes evaluated</strong>
      </div>
      <span class="route-status-chip">${escapeHtml(data.vessel_profile || "Vessel")}</span>
    </div>

    <div class="route-context">
      <span>${escapeHtml(missionLabel)}</span>
      <span>${escapeHtml(priorityLabel)}</span>
      <span>Max ice ${escapeHtml(data.max_ice_exposure_label || "75%")}</span>
      <span>Freshness ${escapeHtml(freshnessText)}</span>
    </div>

    <div class="route-table-wrap">
      <table class="route-table">
        <thead>
          <tr>
            <th>Route</th>
            <th>Distance</th>
            <th>Mean ice</th>
            <th>Max ice</th>
            <th>Iceberg risk</th>
            <th>Exposure</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>

    <div class="recommendation-card">
      <div class="recommendation-title">
        <span>Recommended Route</span>
        <strong>Route ${escapeHtml(recommended.id)} — ${escapeHtml(recommended.label)}</strong>
      </div>
      <div class="recommendation-metrics">
        <div><span>Distance</span><strong>${recommended.distance_km.toFixed(0)} km</strong></div>
        <div><span>Mean ice</span><strong>${(100 * recommended.mean_ice_concentration).toFixed(0)}%</strong></div>
        <div><span>Max ice</span><strong>${(100 * recommended.max_ice_concentration).toFixed(0)}%</strong></div>
        <div><span>Max iceberg risk</span><strong>${(100 * recommended.max_iceberg_risk).toFixed(0)}%</strong></div>
      </div>
      ${recommended.closest_projected_iceberg ? `
      <div class="closest-berg">
        <span>Closest projected iceberg</span>
        <strong>${escapeHtml(recommended.closest_projected_iceberg.name)} · ${Number(recommended.closest_projected_iceberg.distance_km).toFixed(1)} km</strong>
      </div>` : ""}
      <div class="recommendation-why">
        <strong>Why selected?</strong>
        <ul>${explanation || "<li>Selected by the mission-aware recommendation layer.</li>"}</ul>
      </div>
      <div class="route-assessment ${recommended.route_assessment.startsWith("High") ? "route-warning" : "muted"}">${escapeHtml(recommended.route_assessment)}</div>
    </div>

    <div class="data-used">
      <strong>Environmental evidence used</strong>
      <span>NSIDC ${escapeHtml(dataUsed.sea_ice?.observation_date || "—")}</span>
      <span>USNIC ${escapeHtml(dataUsed.icebergs?.observation_date || "—")}</span>
      <span>OSCAR ${escapeHtml(dataUsed.currents?.observation_date || "—")}</span>
      <span>ERA5 ${escapeHtml(dataUsed.wind?.analysis_date || "—")}</span>
    </div>

    <div class="human-review-note">Human-in-the-loop: route output is decision support, not autonomous navigation.</div>
  `;

  const selectRoute = (row) => {
    const selectedId = row.dataset.routeId;
    renderAllRoutes(selectedId);
    result.querySelectorAll(".route-table-row").forEach((item) => {
      item.classList.toggle("selected", item.dataset.routeId === selectedId);
    });
  };

  result.querySelectorAll(".route-table-row").forEach((row) => {
    row.addEventListener("click", () => selectRoute(row));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectRoute(row);
      }
    });
  });
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
  routeCandidates = [];
  recommendedRouteId = null;
  routeLayer.clearLayers();
  document.getElementById("route-result").textContent = "";
  document.getElementById("voyage-result").textContent = "";
  updateRouteUI();
});

document.getElementById("compute-route-btn").addEventListener("click", async () => {
  const result = document.getElementById("route-result");
  if (!routeStart || !routeGoal) return;

  result.textContent = "Computing mission-aware route alternatives…";

  const vessel = document.getElementById("vessel-profile").value;
  const mission = document.getElementById("mission-profile").value;
  const priority = document.getElementById("route-priority").value;
  const maxIceExposure = document.getElementById("max-ice-exposure").value;
  const freshnessRequirementHours = document.getElementById("freshness-requirement").value;

  try {
    const query = new URLSearchParams({
      start_lat: routeStart.lat,
      start_lon: routeStart.lng,
      goal_lat: routeGoal.lat,
      goal_lon: routeGoal.lng,
      horizon_days: currentForecast,
      vessel_profile: vessel,
      mission,
      priority,
      max_ice_exposure: maxIceExposure,
      freshness_requirement_hours: freshnessRequirementHours,
    });

    const data = await fetchJson(`/api/route?${query}`, ROUTE_TIMEOUT_MS);
    renderRouteAlternatives(data);
    await loadVoyageSimulation(data);
    setStatus(`3 decision routes + voyage simulation computed`, true);
  } catch (error) {
    result.innerHTML = `<span class="err">${escapeHtml(error.message)}</span>`;
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
