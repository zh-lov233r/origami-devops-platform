/*
中文：Artifact Dashboard 前端逻辑，从 FastAPI artifact API 拉取报告并渲染表格、延迟和审计摘要。
English: Artifact Dashboard frontend logic fetching FastAPI artifact APIs and rendering tables, latency, and audit summaries.
*/

const ENDPOINTS = {
  scenario: "/api/reports/scenario",
  benchmark: "/api/reports/benchmark",
  events: "/api/events/scenario?limit=500",
  audit: "/api/audit/scenario?limit=100",
  history: "/api/history/runs?limit=25",
  scenarios: "/api/scenarios",
  saveScenario: "/api/scenarios",
  runScenario: "/runs/scenario",
  runBenchmark: "/runs/benchmark",
};

const ACTION_BUTTON_IDS = [
  "run-scenario-button",
  "run-benchmark-button",
  "refresh-button",
  "save-scenario-button",
  "save-run-scenario-button",
];

document.addEventListener("DOMContentLoaded", () => {
  registerActionButtons();
  registerScenarioBuilder();
  loadDashboard();
});

async function loadDashboard() {
  try {
    const [
      scenarioPayload,
      benchmarkPayload,
      eventPayload,
      auditPayload,
      historyPayload,
      scenariosPayload,
    ] =
      await Promise.all([
        fetchJson(ENDPOINTS.scenario),
        fetchJson(ENDPOINTS.benchmark),
        fetchJson(ENDPOINTS.events),
        fetchJson(ENDPOINTS.audit),
        fetchJson(ENDPOINTS.history),
        fetchJson(ENDPOINTS.scenarios),
      ]);

    renderDashboard(
      scenarioPayload,
      benchmarkPayload,
      eventPayload,
      auditPayload,
      historyPayload,
      scenariosPayload,
    );
  } catch (error) {
    renderFatalError(error);
  }
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} returned ${response.status}`);
  }
  return response.json();
}

async function postJson(url, payload = null) {
  const options = { method: "POST" };
  if (payload !== null) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(payload);
  }

  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(await errorMessage(response, url));
  }
  return response.json();
}

async function errorMessage(response, url) {
  try {
    const payload = await response.json();
    return payload.detail || `${url} returned ${response.status}`;
  } catch {
    return `${url} returned ${response.status}`;
  }
}

function registerActionButtons() {
  document.getElementById("run-scenario-button").addEventListener("click", () => {
    runDashboardAction("Scenario run", ENDPOINTS.runScenario);
  });
  document.getElementById("run-benchmark-button").addEventListener("click", () => {
    runDashboardAction("Benchmark run", ENDPOINTS.runBenchmark);
  });
  document.getElementById("refresh-button").addEventListener("click", () => {
    refreshArtifacts();
  });
}

function registerScenarioBuilder() {
  document.getElementById("scenario-builder-form").addEventListener("submit", (event) => {
    event.preventDefault();
    saveScenarioFromBuilder(false);
  });
  document.getElementById("save-run-scenario-button").addEventListener("click", () => {
    saveScenarioFromBuilder(true);
  });
}

async function runDashboardAction(label, url) {
  setActionBusy(true);
  setActionStatus(`${label} running`, "info");

  try {
    await postJson(url);
    await loadDashboard();
    setActionStatus(`${label} complete at ${new Date().toLocaleTimeString()}`, "pass");
  } catch (error) {
    setActionStatus(`${label} failed: ${error.message}`, "fail");
  } finally {
    setActionBusy(false);
  }
}

async function saveScenarioFromBuilder(runAfterSave) {
  setActionBusy(true);
  setBuilderStatus("Saving scenario", "info");

  try {
    const saved = await postJson(ENDPOINTS.saveScenario, buildScenarioPayload());
    await loadDashboard();
    setBuilderStatus(`Saved ${saved.scenario.id}`, "pass");

    if (runAfterSave) {
      setActionStatus("Scenario run running", "info");
      await postJson(ENDPOINTS.runScenario);
      await loadDashboard();
      setActionStatus(`Scenario run complete at ${new Date().toLocaleTimeString()}`, "pass");
    }
  } catch (error) {
    setBuilderStatus(error.message, "fail");
  } finally {
    setActionBusy(false);
  }
}

function buildScenarioPayload() {
  const observation = {
    mission_type: "carry_go_delivery",
    position: [numberValue("builder-position-x"), numberValue("builder-position-y")],
    target: [numberValue("builder-target-x"), numberValue("builder-target-y")],
    sensor_bias: 0.01,
    payload_kg: numberValue("builder-payload-kg"),
    payload_locked: checkedValue("builder-payload-locked"),
    battery_pct: numberValue("builder-battery-pct"),
    nearest_human_distance_m: numberValue("builder-human-distance"),
    state_age_s: numberValue("builder-state-age"),
    sensor_blackout: checkedValue("builder-sensor-blackout"),
    floor_mu_observed: numberValue("builder-floor-mu"),
    camera_lux_reference: 500,
    camera_lux_current: numberValue("builder-camera-lux"),
    camera_sharpness: 0.96,
    imu_vibration_rms: numberValue("builder-imu-vibration"),
    payload_scale_reading_kg:
      numberValue("builder-payload-kg") + numberValue("builder-payload-bias"),
    payload_reference_kg: numberValue("builder-payload-kg"),
    fleet_context: {
      nearby_robots: numberValue("builder-nearby-robots"),
      corridor_occupied: checkedValue("builder-corridor-occupied"),
      elevator_queue: numberValue("builder-elevator-queue"),
    },
  };

  const currentZone = textValue("builder-current-zone");
  const privacyZones = listValue("builder-privacy-zones");
  if (currentZone) {
    observation.current_zone = currentZone;
  }
  if (privacyZones.length) {
    observation.privacy_zones = privacyZones;
  }

  const expected = {
    final_move: textValue("builder-final-move"),
    seom_passed: checkedValue("builder-seom-passed"),
    audit_valid: true,
  };
  const stumGate = textValue("builder-stum-gate");
  const routeStrategy = textValue("builder-route-strategy");
  const violations = listValue("builder-violations");
  if (stumGate) {
    expected.stum_gate = stumGate;
  }
  if (routeStrategy) {
    expected.route_strategy = routeStrategy;
  }
  if (violations.length) {
    expected.expected_violations = violations;
  } else {
    expected.required_absent_violations = ["C01_person_stop_300mm", "C07_battery_return_15pct"];
  }

  return {
    id: textValue("builder-id"),
    name: textValue("builder-name"),
    description: textValue("builder-description"),
    tags: listValue("builder-tags"),
    observation,
    expected,
    overwrite: checkedValue("builder-overwrite"),
  };
}

async function refreshArtifacts() {
  setActionBusy(true);
  setActionStatus("Refreshing artifacts", "info");

  try {
    await loadDashboard();
    setActionStatus(`Artifacts refreshed at ${new Date().toLocaleTimeString()}`, "pass");
  } catch (error) {
    setActionStatus(`Refresh failed: ${error.message}`, "fail");
  } finally {
    setActionBusy(false);
  }
}

function setActionBusy(isBusy) {
  ACTION_BUTTON_IDS.forEach((id) => {
    document.getElementById(id).disabled = isBusy;
  });
}

function setActionStatus(message, kind) {
  const node = document.getElementById("action-status");
  node.textContent = message;
  node.className = kind || "";
}

function setBuilderStatus(message, kind) {
  const node = document.getElementById("builder-status");
  node.textContent = message;
  node.className = kind || "";
}

function renderDashboard(
  scenarioPayload,
  benchmarkPayload,
  eventPayload,
  auditPayload,
  historyPayload,
  scenariosPayload,
) {
  const scenarioReport = scenarioPayload.available ? scenarioPayload.data : null;
  const benchmarkReport = benchmarkPayload.available ? benchmarkPayload.data : null;

  renderSummary(scenarioPayload, benchmarkPayload, eventPayload, auditPayload);
  renderScenarioLibrary(scenariosPayload);
  renderScenarioTable(scenarioReport);
  renderLatency(benchmarkReport, scenarioReport);
  renderViolations(scenarioReport);
  renderEvents(eventPayload);
  renderAudit(auditPayload);
  renderHistory(historyPayload);
}

function renderSummary(scenarioPayload, benchmarkPayload, eventPayload, auditPayload) {
  const scenario = scenarioPayload.available ? scenarioPayload.data : null;
  const benchmark = benchmarkPayload.available ? benchmarkPayload.data : null;
  const generatedAt = scenario?.generated_at || benchmark?.generated_at;
  const eventCount = eventPayload.count || 0;
  const auditCount = auditPayload.count || 0;

  setText("generated-at", generatedAt ? `Generated ${formatTimestamp(generatedAt)}` : "No reports found");

  const overall = deriveOverallGate(scenarioPayload, benchmarkPayload, auditPayload);
  setPill("overall-gate", overall.text, overall.kind);

  setText("scenario-gate", gateText(scenario?.quality_gate_passed, scenarioPayload.available));
  setText("scenario-path", scenarioPayload.path || "artifacts/reports/scenario_report.json");
  setText("scenario-pass-rate", scenario ? formatPercent(scenario.pass_rate) : "--");
  setText("scenario-counts", scenario ? `${scenario.passed}/${scenario.total} passed` : "No scenario report");
  setText("benchmark-gate", gateText(benchmark?.quality_gate_passed, benchmarkPayload.available));
  setText(
    "benchmark-threshold",
    benchmark
      ? `p95 <= ${formatNumber(benchmark.thresholds?.max_module_p95_ms)} ms`
      : "No benchmark report",
  );
  setText("audit-event-count", `${auditCount} audit / ${eventCount} events`);
  setText("audit-event-path", auditPayload.available && eventPayload.available ? "JSONL ready" : "JSONL missing");

  setPill("scenario-total-chip", scenario ? `${scenario.total} CASES` : "NO DATA", scenario ? "info" : "warn");
}

function deriveOverallGate(scenarioPayload, benchmarkPayload, auditPayload) {
  const scenario = scenarioPayload.available ? scenarioPayload.data : null;
  const benchmark = benchmarkPayload.available ? benchmarkPayload.data : null;

  if (scenario?.quality_gate_passed === false || benchmark?.quality_gate_passed === false) {
    return { text: "FAIL", kind: "fail" };
  }
  if (!scenarioPayload.available || !benchmarkPayload.available || !auditPayload.available) {
    return { text: "MISSING", kind: "warn" };
  }
  if (scenario?.quality_gate_passed && benchmark?.quality_gate_passed) {
    return { text: "PASS", kind: "pass" };
  }
  return { text: "UNKNOWN", kind: "neutral" };
}

function renderScenarioTable(report) {
  const tableBody = document.getElementById("scenario-table-body");
  if (!report?.scenarios?.length) {
    tableBody.innerHTML = `<tr><td colspan="8" class="empty-cell">No scenario artifact</td></tr>`;
    return;
  }

  tableBody.innerHTML = report.scenarios
    .map((scenario) => {
      const actual = scenario.actual || {};
      const violations = actual.violations?.length ? actual.violations : [];
      const seomKind = actual.seom_passed ? "pass" : "fail";
      const resultKind = scenario.passed ? "pass" : "fail";
      return `
        <tr>
          <td>
            <div class="scenario-name">
              <strong>${escapeHtml(scenario.name || scenario.id)}</strong>
              <span>${escapeHtml(scenario.id)}</span>
              ${renderTags(scenario.tags)}
            </div>
          </td>
          <td><span class="status-pill ${resultKind}">${scenario.passed ? "PASS" : "FAIL"}</span></td>
          <td>${escapeHtml(actual.final_move || "--")}</td>
          <td>${escapeHtml(actual.stum_gate || "--")}</td>
          <td>${escapeHtml(actual.route_strategy || "--")}</td>
          <td><span class="status-pill ${seomKind}">${actual.seom_passed ? "PASS" : "BLOCK"}</span></td>
          <td>${escapeHtml(actual.fleet_adjustment || "--")}</td>
          <td>${renderViolationTokens(violations)}</td>
        </tr>
      `;
    })
    .join("");
}

function renderScenarioLibrary(payload) {
  const scenarios = payload?.scenarios || [];
  const container = document.getElementById("scenario-library-list");
  setPill("scenario-library-chip", `${payload?.count || 0} YAML`, payload?.available ? "info" : "warn");

  if (!scenarios.length) {
    container.innerHTML = `<span class="token">No scenario YAML files</span>`;
    return;
  }

  container.innerHTML = scenarios
    .slice(-12)
    .map((scenario) => `<span class="token info">${escapeHtml(scenario.id)}</span>`)
    .join("");
}

function renderLatency(benchmarkReport, scenarioReport) {
  const benchmarkMetrics = benchmarkReport?.module_latency_ms;
  const scenarioMetrics = scenarioReport?.summary?.module_latency_ms;
  const metrics = benchmarkMetrics || scenarioMetrics || {};
  const source = benchmarkMetrics ? "BENCHMARK" : scenarioMetrics ? "SCENARIO" : "NO DATA";
  const threshold = benchmarkReport?.thresholds?.max_module_p95_ms;
  const modules = Object.entries(metrics);
  const maxP95 = Math.max(1, ...modules.map(([, item]) => numberOrZero(item.p95)));

  setPill("latency-source", source, modules.length ? "info" : "warn");

  const container = document.getElementById("latency-bars");
  if (!modules.length) {
    container.innerHTML = `<div class="notice">No latency artifact</div>`;
    return;
  }

  container.innerHTML = modules
    .map(([moduleName, item]) => {
      const p95 = numberOrZero(item.p95);
      const width = Math.max(4, Math.min(100, (p95 / maxP95) * 100));
      const kind = latencyKind(p95, threshold);
      return `
        <div class="bar-row">
          <div class="bar-row-header">
            <strong>${escapeHtml(moduleName)}</strong>
            <span class="muted">avg ${formatNumber(item.avg)} ms / p95 ${formatNumber(p95)} ms / max ${formatNumber(item.max)} ms</span>
          </div>
          <div class="bar-track" aria-label="${escapeHtml(moduleName)} p95 latency">
            <div class="bar-fill ${kind}" style="width: ${width}%"></div>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderViolations(report) {
  const counts = report?.summary?.violation_counts || {};
  const entries = Object.entries(counts);
  const container = document.getElementById("violation-list");

  setPill("violation-chip", entries.length ? `${entries.length} TYPES` : "CLEAR", entries.length ? "warn" : "pass");

  if (!entries.length) {
    container.innerHTML = `<span class="token good">No violations in latest scenario report</span>`;
    return;
  }

  container.innerHTML = entries
    .map(([name, count]) => `<span class="token danger">${escapeHtml(name)} x ${count}</span>`)
    .join("");
}

function renderEvents(eventPayload) {
  const records = eventPayload.records || [];
  const counts = countBy(records, "module");
  const entries = Object.entries(counts).sort(([left], [right]) => left.localeCompare(right));
  const container = document.getElementById("event-modules");

  setPill("event-chip", `${eventPayload.count || 0} EVENTS`, eventPayload.available ? "info" : "warn");

  if (!entries.length) {
    container.innerHTML = `<div class="notice">No event records</div>`;
    return;
  }

  container.innerHTML = entries
    .map(
      ([moduleName, count]) => `
        <div class="module-tile">
          <strong>${escapeHtml(moduleName)}</strong>
          <span>${count} records</span>
        </div>
      `,
    )
    .join("");
}

function renderAudit(auditPayload) {
  const records = (auditPayload.records || []).slice(-6).reverse();
  const container = document.getElementById("audit-records");

  setPill("audit-chip", `${auditPayload.count || 0} RECORDS`, auditPayload.available ? "info" : "warn");

  if (!records.length) {
    container.innerHTML = `<div class="notice">No audit records</div>`;
    return;
  }

  container.innerHTML = records
    .map((record) => {
      const metadata = record.metadata || {};
      return `
        <div class="audit-record">
          <strong>${escapeHtml(record.scenario_id || record.run_id || "unknown")}</strong>
          <div class="audit-meta">
            <span>STUM ${escapeHtml(metadata.stum_gate || "--")}</span>
            <span>SEOM ${metadata.seom_passed ? "PASS" : "BLOCK"}</span>
            <span>${formatUnixTimestamp(record.timestamp)}</span>
          </div>
          <code>${escapeHtml(shortHash(record.hash))}</code>
        </div>
      `;
    })
    .join("");
}

function renderHistory(historyPayload) {
  const records = historyPayload.records || [];
  const tableBody = document.getElementById("history-table-body");

  setPill("history-chip", `${historyPayload.count || 0} RUNS`, historyPayload.available ? "info" : "warn");

  if (!records.length) {
    tableBody.innerHTML = `<tr><td colspan="7" class="empty-cell">No dashboard-triggered runs yet</td></tr>`;
    return;
  }

  tableBody.innerHTML = records
    .map((record) => {
      const resultKind = record.quality_gate_passed ? "pass" : "fail";
      return `
        <tr>
          <td>
            <div class="history-run">
              <strong>${formatTimestamp(record.generated_at || record.recorded_at)}</strong>
              <span>${escapeHtml(record.id)}</span>
            </div>
          </td>
          <td>${escapeHtml(record.type || "--")}</td>
          <td><span class="status-pill ${resultKind}">${record.quality_gate_passed ? "PASS" : "FAIL"}</span></td>
          <td>${escapeHtml(historyScope(record))}</td>
          <td>${formatNumber(record.max_module_p95_ms)} ms</td>
          <td>${historyViolationCell(record)}</td>
          <td><span class="tag">${escapeHtml(shortPath(record.artifact_path))}</span></td>
        </tr>
      `;
    })
    .join("");
}

function renderFatalError(error) {
  setPill("overall-gate", "ERROR", "fail");
  setText("generated-at", error.message);
  document.getElementById("scenario-table-body").innerHTML =
    `<tr><td colspan="8" class="empty-cell">Dashboard API error</td></tr>`;
  document.getElementById("history-table-body").innerHTML =
    `<tr><td colspan="7" class="empty-cell">Dashboard API error</td></tr>`;
}

function renderTags(tags) {
  if (!tags?.length) {
    return "";
  }
  return `<div class="tag-row">${tags
    .map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`)
    .join("")}</div>`;
}

function renderViolationTokens(violations) {
  if (!violations.length) {
    return `<span class="token good">clear</span>`;
  }
  return violations.map((violation) => `<span class="token danger">${escapeHtml(violation)}</span>`).join(" ");
}

function historyScope(record) {
  if (record.type === "scenario") {
    return `${record.passed}/${record.total} scenarios`;
  }
  if (record.type === "benchmark") {
    return `${record.steps || 0} benchmark steps`;
  }
  return "--";
}

function historyViolationCell(record) {
  if (record.type !== "scenario") {
    return `<span class="token info">n/a</span>`;
  }
  if (!record.violation_total) {
    return `<span class="token good">clear</span>`;
  }
  return `<span class="token danger">${record.violation_total} total</span>`;
}

function countBy(records, key) {
  return records.reduce((accumulator, record) => {
    const value = record[key] || "unknown";
    accumulator[value] = (accumulator[value] || 0) + 1;
    return accumulator;
  }, {});
}

function gateText(value, available) {
  if (!available) {
    return "MISSING";
  }
  if (value === true) {
    return "PASS";
  }
  if (value === false) {
    return "FAIL";
  }
  return "UNKNOWN";
}

function latencyKind(value, threshold) {
  if (!threshold) {
    return "";
  }
  if (value > threshold) {
    return "fail";
  }
  if (value > threshold * 0.75) {
    return "warn";
  }
  return "";
}

function textValue(id) {
  return document.getElementById(id).value.trim();
}

function numberValue(id) {
  const value = Number(document.getElementById(id).value);
  return Number.isFinite(value) ? value : 0;
}

function checkedValue(id) {
  return document.getElementById(id).checked;
}

function listValue(id) {
  return textValue(id)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function setPill(id, text, kind) {
  const node = document.getElementById(id);
  node.textContent = text;
  node.className = `status-pill ${kind}`;
}

function setText(id, text) {
  document.getElementById(id).textContent = text;
}

function formatPercent(value) {
  if (typeof value !== "number") {
    return "--";
  }
  return `${Math.round(value * 100)}%`;
}

function formatNumber(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "--";
  }
  return value.toFixed(value >= 10 ? 1 : 4).replace(/0+$/, "").replace(/\.$/, "");
}

function numberOrZero(value) {
  return typeof value === "number" && !Number.isNaN(value) ? value : 0;
}

function formatTimestamp(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function formatUnixTimestamp(value) {
  if (typeof value !== "number") {
    return "--";
  }
  return new Date(value * 1000).toLocaleString();
}

function shortHash(value) {
  if (!value) {
    return "--";
  }
  return `${value.slice(0, 12)}...${value.slice(-8)}`;
}

function shortPath(value) {
  if (!value) {
    return "--";
  }
  const parts = String(value).split("/");
  return parts.slice(-3).join("/");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
