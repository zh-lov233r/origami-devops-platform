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
  historyDetail: (recordId) => `/api/history/runs/${encodeURIComponent(recordId)}`,
  scenarios: "/api/scenarios",
  scenarioDetail: (scenarioId) => `/api/scenarios/${encodeURIComponent(scenarioId)}`,
  saveScenario: "/api/scenarios",
  runScenario: "/runs/scenario",
  runScenarioById: (scenarioId) => `/runs/scenario/${encodeURIComponent(scenarioId)}`,
  runBenchmark: "/runs/benchmark",
};
const GRAFANA_DASHBOARD_PATH = "/d/origami-overview?orgId=1";

const ACTION_BUTTON_IDS = [
  "run-scenario-button",
  "run-benchmark-button",
  "refresh-button",
  "test-run-selected-scenario-button",
  "save-scenario-button",
  "save-run-scenario-button",
  "new-scenario-button",
  "select-all-scenarios-button",
  "clear-scenario-selection-button",
  "duplicate-scenario-button",
  "delete-scenario-button",
  "run-selected-scenario-button",
  "clear-history-filters-button",
];

const TAB_IDS = ["dashboard", "scenario-builder", "test-lab", "run-history"];
const DEFAULT_SCENARIO_FORM = {
  id: "custom_carry_go",
  name: "Custom Carry & Go",
  description: "Dashboard-generated Carry & Go scenario.",
  tags: ["custom", "carry_go"],
  observation: {
    mission_type: "carry_go_delivery",
    position: [0, 0],
    target: [1, 1],
    payload_kg: 2,
    payload_locked: true,
    battery_pct: 80,
    nearest_human_distance_m: 2,
    state_age_s: 0,
    floor_mu_observed: 0.52,
    camera_lux_current: 480,
    imu_vibration_rms: 0.08,
    payload_scale_reading_kg: 2,
    payload_reference_kg: 2,
    fleet_context: {
      nearby_robots: 0,
      corridor_occupied: false,
      elevator_queue: 0,
    },
  },
  expected: {
    final_move: "east",
    seom_passed: true,
    audit_valid: true,
  },
};
let selectedHistoryRunId = null;
let selectedHistoryDetailPayload = null;
let selectedScenarioId = null;
let selectedScenarioSnapshot = null;
let selectedScenarioIds = new Set();
let scenarioDraftBaseSnapshot = null;
let scenarioLibraryRecords = [];
let scenarioSearchTerm = "";
let scenarioTagFilter = "";
let activeBuilderFormTab = "common";
let latestScenarioPreview = null;
let testLabSelectedScenarioId = null;
let latestTestLabResult = null;
let testRunQueue = [];
let nextTestRunQueueId = 1;
let historyRecords = [];
let historySearchTerm = "";
let historyTypeFilter = "";
let historyGateFilter = "";
let historyCompareIds = [];
const historyDetailCache = new Map();

document.addEventListener("DOMContentLoaded", () => {
  registerObservabilityLinks();
  registerTabs();
  registerActionButtons();
  registerTestLab();
  registerScenarioBuilder();
  registerHistoryDetails();
  activateBuilderFormTab(activeBuilderFormTab);
  renderScenarioDraftAssist();
  loadDashboard();
});

function registerObservabilityLinks() {
  const button = document.getElementById("observability-button");
  if (!button) {
    return;
  }
  button.href = `${window.location.protocol}//${window.location.hostname}:3000${GRAFANA_DASHBOARD_PATH}`;
}

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
  return requestJson("POST", url, payload);
}

async function requestJson(method, url, payload = null) {
  const options = { method };
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
  document.getElementById("refresh-button").addEventListener("click", () => {
    refreshArtifacts();
  });
}

function registerTestLab() {
  document.getElementById("run-scenario-button").addEventListener("click", () => {
    runTestLabAction("Scenario suite", ENDPOINTS.runScenario, "scenario");
  });
  document.getElementById("run-benchmark-button").addEventListener("click", () => {
    runTestLabAction("Benchmark", ENDPOINTS.runBenchmark, "benchmark");
  });
  document.getElementById("test-run-selected-scenario-button").addEventListener("click", () => {
    if (!testLabSelectedScenarioId) {
      setActionStatus("Select a scenario before running a targeted test", "fail");
      return;
    }
    runTestLabAction(
      `Scenario ${testLabSelectedScenarioId}`,
      ENDPOINTS.runScenarioById(testLabSelectedScenarioId),
      "scenario",
    );
  });
  document.getElementById("test-scenario-select").addEventListener("change", (event) => {
    testLabSelectedScenarioId = event.target.value;
    renderTestLabSelectedScenario();
    setActionBusy(false);
  });
}

function registerTabs() {
  document.querySelectorAll("[data-tab-target]").forEach((button) => {
    button.addEventListener("click", () => {
      activateTab(button.dataset.tabTarget);
    });
  });

  window.addEventListener("hashchange", () => {
    activateTab(tabFromHash(), { updateHash: false });
  });

  activateTab(tabFromHash(), { updateHash: false });
}

function activateTab(tabId, options = {}) {
  const selectedTab = TAB_IDS.includes(tabId) ? tabId : "dashboard";
  const shouldUpdateHash = options.updateHash !== false;

  document.querySelectorAll("[data-tab-target]").forEach((button) => {
    const isActive = button.dataset.tabTarget === selectedTab;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });

  document.querySelectorAll("[data-tab-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.tabPanel !== selectedTab;
  });

  if (shouldUpdateHash && window.location.hash !== `#${selectedTab}`) {
    window.history.replaceState(null, "", `#${selectedTab}`);
  }
}

function tabFromHash() {
  return window.location.hash.replace("#", "");
}

function registerScenarioBuilder() {
  document.getElementById("scenario-builder-form").addEventListener("submit", (event) => {
    event.preventDefault();
    saveScenarioFromBuilder(false);
  });
  document.getElementById("save-run-scenario-button").addEventListener("click", () => {
    saveScenarioFromBuilder(true);
  });
  document.getElementById("new-scenario-button").addEventListener("click", () => {
    resetScenarioManagerForm();
  });
  document.getElementById("select-all-scenarios-button").addEventListener("click", () => {
    selectAllScenarios();
  });
  document.getElementById("clear-scenario-selection-button").addEventListener("click", () => {
    clearScenarioSelection();
  });
  document.getElementById("scenario-search-input").addEventListener("input", (event) => {
    scenarioSearchTerm = event.target.value.trim().toLowerCase();
    renderScenarioLibraryItems();
    updateScenarioSelectionControls();
  });
  document.getElementById("scenario-tag-filter").addEventListener("change", (event) => {
    scenarioTagFilter = event.target.value;
    renderScenarioLibraryItems();
    updateScenarioSelectionControls();
  });
  document.querySelectorAll("[data-builder-form-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      activateBuilderFormTab(button.dataset.builderFormTab);
    });
  });
  document.getElementById("duplicate-scenario-button").addEventListener("click", () => {
    duplicateSelectedScenario();
  });
  document.getElementById("delete-scenario-button").addEventListener("click", () => {
    deleteSelectedScenario();
  });
  document.getElementById("run-selected-scenario-button").addEventListener("click", () => {
    runSelectedScenario();
  });
  document.getElementById("scenario-library-list").addEventListener("change", (event) => {
    const selector = closestFromEvent(event, "[data-scenario-selector]");
    if (!selector) {
      return;
    }
    toggleScenarioSelection(selector.dataset.scenarioSelector, selector.checked);
  });
  document.getElementById("scenario-library-list").addEventListener("click", (event) => {
    if (closestFromEvent(event, "[data-scenario-select-control]")) {
      return;
    }

    const item = closestFromEvent(event, "[data-scenario-id]");
    if (!item) {
      return;
    }
    loadScenarioForEdit(item.dataset.scenarioId);
  });
  document.getElementById("scenario-library-list").addEventListener("keydown", (event) => {
    const item = closestFromEvent(event, "[data-scenario-id]");
    if (!item) {
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      loadScenarioForEdit(item.dataset.scenarioId);
    }
    if (event.key === " ") {
      event.preventDefault();
      toggleScenarioSelection(item.dataset.scenarioId);
    }
  });
  document.getElementById("scenario-builder-form").addEventListener("input", () => {
    renderScenarioDraftAssist();
  });
  document.getElementById("scenario-builder-form").addEventListener("change", () => {
    renderScenarioDraftAssist();
  });
}

function activateBuilderFormTab(tabId) {
  const selectedTab = tabId || "common";
  activeBuilderFormTab = selectedTab;
  document.querySelectorAll("[data-builder-form-tab]").forEach((button) => {
    const isActive = button.dataset.builderFormTab === selectedTab;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
  document.querySelectorAll("[data-builder-form-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.builderFormPanel !== selectedTab;
  });
}

function registerHistoryDetails() {
  const tableBody = document.getElementById("history-table-body");
  document.getElementById("history-search-input").addEventListener("input", (event) => {
    historySearchTerm = event.target.value.trim().toLowerCase();
    renderHistory({ records: historyRecords, count: historyRecords.length, available: true });
  });
  document.getElementById("history-type-filter").addEventListener("change", (event) => {
    historyTypeFilter = event.target.value;
    renderHistory({ records: historyRecords, count: historyRecords.length, available: true });
  });
  document.getElementById("history-gate-filter").addEventListener("change", (event) => {
    historyGateFilter = event.target.value;
    renderHistory({ records: historyRecords, count: historyRecords.length, available: true });
  });
  document.getElementById("clear-history-filters-button").addEventListener("click", () => {
    historySearchTerm = "";
    historyTypeFilter = "";
    historyGateFilter = "";
    document.getElementById("history-search-input").value = "";
    document.getElementById("history-type-filter").value = "";
    document.getElementById("history-gate-filter").value = "";
    renderHistory({ records: historyRecords, count: historyRecords.length, available: true });
  });
  tableBody.addEventListener("change", (event) => {
    const selector = closestFromEvent(event, "[data-history-compare-selector]");
    if (!selector) {
      return;
    }
    toggleHistoryCompare(selector.dataset.historyCompareSelector, selector.checked);
  });
  tableBody.addEventListener("click", (event) => {
    if (closestFromEvent(event, "[data-history-compare-control]")) {
      return;
    }
    const moreButton = closestFromEvent(event, "[data-history-more-button]");
    if (moreButton) {
      toggleHistoryMore(moreButton);
      return;
    }

    const row = closestFromEvent(event, "[data-history-row-id]");
    if (!row) {
      return;
    }
    toggleHistoryDetail(row.dataset.historyRowId);
  });
  tableBody.addEventListener("keydown", (event) => {
    if (!["Enter", " "].includes(event.key)) {
      return;
    }
    const row = closestFromEvent(event, "[data-history-row-id]");
    if (!row) {
      return;
    }
    event.preventDefault();
    toggleHistoryDetail(row.dataset.historyRowId);
  });
}

async function runTestLabAction(label, url, resultType) {
  const queueId = enqueueTestRun(label, resultType);
  setActionBusy(true);
  setActionStatus(`${label} running`, "info");
  renderTestLabResultLoading(label);

  try {
    updateTestRunQueueItem(queueId, { status: "running", progress: 35 });
    const report = await postJson(url);
    updateTestRunQueueItem(queueId, {
      status: report.quality_gate_passed ? "pass" : "fail",
      progress: 100,
      completedAt: new Date().toISOString(),
      report,
      steps: testRunQueueSteps(report, resultType),
    });
    latestTestLabResult = { label, report, resultType };
    await loadDashboard();
    renderTestLabResult(label, report, resultType);
    setActionStatus(`${label} complete at ${new Date().toLocaleTimeString()}`, "pass");
  } catch (error) {
    updateTestRunQueueItem(queueId, {
      status: "fail",
      progress: 100,
      completedAt: new Date().toISOString(),
      error: error.message,
    });
    latestTestLabResult = null;
    renderTestLabResultError(label, error);
    setActionStatus(`${label} failed: ${error.message}`, "fail");
  } finally {
    setActionBusy(false);
  }
}

function enqueueTestRun(label, resultType) {
  const queueItem = {
    id: nextTestRunQueueId,
    label,
    resultType,
    status: "queued",
    progress: 8,
    startedAt: new Date().toISOString(),
    steps: [],
  };
  nextTestRunQueueId += 1;
  testRunQueue = [queueItem, ...testRunQueue].slice(0, 8);
  renderTestRunQueue();
  return queueItem.id;
}

function updateTestRunQueueItem(queueId, patch) {
  testRunQueue = testRunQueue.map((item) =>
    item.id === queueId ? { ...item, ...patch } : item,
  );
  renderTestRunQueue();
}

function testRunQueueSteps(report, resultType) {
  if (resultType === "benchmark") {
    return Object.entries(report.module_latency_ms || {}).map(([name, metrics]) => ({
      name,
      status: "pass",
      detail: `p95 ${formatNumber(metrics.p95)} ms`,
    }));
  }

  return (report.scenarios || (report.scenario ? [report.scenario] : [])).map((scenario) => ({
    name: scenario.id || scenario.name || "scenario",
    status: scenario.passed ? "pass" : "fail",
    detail: scenario.actual?.final_move || "--",
  }));
}

function renderTestRunQueue() {
  const container = document.getElementById("test-run-queue-body");
  const activeCount = testRunQueue.filter((item) => ["queued", "running"].includes(item.status)).length;
  setPill(
    "test-run-queue-chip",
    activeCount ? `${activeCount} ACTIVE` : testRunQueue.length ? `${testRunQueue.length} RECENT` : "IDLE",
    activeCount ? "info" : testRunQueue.length ? "neutral" : "neutral",
  );

  if (!testRunQueue.length) {
    container.innerHTML = `<div class="notice">Triggered Test Lab runs will appear here.</div>`;
    return;
  }

  container.innerHTML = `
    <div class="queue-list">
      ${testRunQueue.map(renderTestRunQueueItem).join("")}
    </div>
  `;
}

function renderTestRunQueueItem(item) {
  const kind = item.status === "pass" ? "pass" : item.status === "fail" ? "fail" : "info";
  const progress = Math.max(0, Math.min(100, Number(item.progress || 0)));
  const steps = (item.steps || []).slice(0, 8);
  return `
    <div class="queue-item">
      <div class="queue-item-heading">
        <div>
          <strong>${escapeHtml(item.label)}</strong>
          <span>${escapeHtml(formatTimestamp(item.startedAt))}</span>
        </div>
        <span class="status-pill ${kind}">${escapeHtml(item.status.toUpperCase())}</span>
      </div>
      <div class="queue-progress" aria-label="${escapeHtml(item.label)} progress">
        <div class="queue-progress-fill ${kind}" style="width: ${progress}%"></div>
      </div>
      ${
        item.error
          ? `<div class="queue-error">${escapeHtml(item.error)}</div>`
          : steps.length
            ? `<div class="queue-steps">${steps.map(renderQueueStep).join("")}</div>`
            : `<div class="queue-steps"><span class="queue-step info">Waiting for result</span></div>`
      }
    </div>
  `;
}

function renderQueueStep(step) {
  const kind = step.status === "pass" ? "pass" : step.status === "fail" ? "fail" : "info";
  return `
    <span class="queue-step ${kind}">
      ${escapeHtml(step.name)} ${step.detail ? `<small>${escapeHtml(step.detail)}</small>` : ""}
    </span>
  `;
}

async function saveScenarioFromBuilder(runAfterSave) {
  setActionBusy(true);
  const editingScenarioId = selectedScenarioId;
  setBuilderStatus(editingScenarioId ? "Updating scenario" : "Creating scenario", "info");

  try {
    const payload = buildScenarioPayload();
    const saved = editingScenarioId
      ? await requestJson("PUT", ENDPOINTS.scenarioDetail(editingScenarioId), payload)
      : await postJson(ENDPOINTS.saveScenario, payload);
    selectedScenarioId = saved.scenario.id;
    selectedScenarioSnapshot = clonePlainObject({ ...payload, id: saved.scenario.id });
    scenarioDraftBaseSnapshot = clonePlainObject(selectedScenarioSnapshot);
    await loadDashboard();
    setScenarioManagerMode("edit", saved.scenario.id);
    renderScenarioDraftAssist();
    setBuilderStatus(`${editingScenarioId ? "Updated" : "Created"} ${saved.scenario.id}`, "pass");

    if (runAfterSave) {
      await runScenarioPreview(saved.scenario.id);
    }
  } catch (error) {
    setBuilderStatus(error.message, "fail");
  } finally {
    setActionBusy(false);
  }
}

async function loadScenarioForEdit(scenarioId) {
  setActionBusy(true);
  setBuilderStatus(`Loading ${scenarioId}`, "info");

  try {
    const payload = await fetchJson(ENDPOINTS.scenarioDetail(scenarioId));
    selectedScenarioId = payload.scenario.id;
    selectedScenarioSnapshot = clonePlainObject(payload.scenario);
    scenarioDraftBaseSnapshot = clonePlainObject(payload.scenario);
    testLabSelectedScenarioId = payload.scenario.id;
    populateScenarioForm(payload.scenario);
    setScenarioManagerMode("edit", payload.scenario.id);
    renderScenarioLibrary({
      scenarios: scenarioLibraryRecords,
      count: scenarioLibraryRecords.length,
      available: true,
    });
    renderScenarioPreviewEmpty();
    renderScenarioDraftAssist();
    setBuilderStatus(`Editing ${payload.scenario.id}`, "pass");
  } catch (error) {
    setBuilderStatus(`Load failed: ${error.message}`, "fail");
  } finally {
    setActionBusy(false);
  }
}

async function runSelectedScenario() {
  const scenarioIds = selectedScenarioOperationIds();
  if (!scenarioIds.length) {
    setBuilderStatus("Select one or more scenarios to run", "fail");
    return;
  }

  if (scenarioIds.length === 1) {
    await runScenarioPreview(scenarioIds[0]);
    return;
  }

  await runScenarioBatchPreview(scenarioIds);
}

function duplicateSelectedScenario() {
  if (!selectedScenarioSnapshot) {
    setBuilderStatus("Select a scenario to duplicate", "fail");
    return;
  }

  const source = clonePlainObject(selectedScenarioSnapshot);
  const duplicateId = uniqueScenarioCopyId(source.id || "custom_scenario");
  const duplicate = {
    ...source,
    id: duplicateId,
    name: `${source.name || source.id || "Scenario"} Copy`,
    tags: normalizeTagList(source.tags),
  };

  selectedScenarioId = null;
  selectedScenarioSnapshot = clonePlainObject(source);
  scenarioDraftBaseSnapshot = clonePlainObject(source);
  latestScenarioPreview = null;
  populateScenarioForm(duplicate);
  setScenarioManagerMode("duplicate", source.id || null);
  renderScenarioLibrary({
    scenarios: scenarioLibraryRecords,
    count: scenarioLibraryRecords.length,
    available: true,
  });
  renderScenarioPreviewEmpty();
  renderScenarioDraftAssist();
  setBuilderStatus(`Duplicated ${source.id}; edit the draft and save`, "info");
}

async function runScenarioPreview(scenarioId) {
  setActionBusy(true);
  setBuilderStatus(`Running ${scenarioId}`, "info");
  renderScenarioPreviewLoading(scenarioId);

  try {
    const report = await postJson(ENDPOINTS.runScenarioById(scenarioId));
    latestScenarioPreview = report;
    renderScenarioPreview(report);
    setBuilderStatus(`Ran ${scenarioId}`, report.quality_gate_passed ? "pass" : "fail");
    setActionStatus(`Scenario ${scenarioId} complete at ${new Date().toLocaleTimeString()}`, "pass");
  } catch (error) {
    latestScenarioPreview = null;
    renderScenarioPreviewError(scenarioId, error);
    setBuilderStatus(`Run failed: ${error.message}`, "fail");
  } finally {
    setActionBusy(false);
  }
}

async function runScenarioBatchPreview(scenarioIds) {
  setActionBusy(true);
  setBuilderStatus(`Running ${scenarioIds.length} scenarios`, "info");
  renderScenarioBatchPreviewLoading(scenarioIds);

  try {
    const reports = [];
    for (const scenarioId of scenarioIds) {
      reports.push(await postJson(ENDPOINTS.runScenarioById(scenarioId)));
    }
    latestScenarioPreview = { reports };
    renderScenarioBatchPreview(reports);
    await loadDashboard();
    setBuilderStatus(`Ran ${scenarioIds.length} scenarios`, reports.every((report) => report.quality_gate_passed) ? "pass" : "fail");
    setActionStatus(`${scenarioIds.length} scenarios complete at ${new Date().toLocaleTimeString()}`, "pass");
  } catch (error) {
    latestScenarioPreview = null;
    renderScenarioPreviewError("batch", error);
    setBuilderStatus(`Batch run failed: ${error.message}`, "fail");
  } finally {
    setActionBusy(false);
  }
}

async function deleteSelectedScenario() {
  const scenarioIds = selectedScenarioOperationIds();
  if (!scenarioIds.length) {
    setBuilderStatus("Select one or more scenarios to delete", "fail");
    return;
  }

  const label = scenarioIds.length === 1 ? `"${scenarioIds[0]}"` : `${scenarioIds.length} scenarios`;
  if (!window.confirm(`Delete ${label}?`)) {
    return;
  }

  setActionBusy(true);
  setBuilderStatus(`Deleting ${label}`, "info");

  try {
    for (const scenarioId of scenarioIds) {
      await requestJson("DELETE", ENDPOINTS.scenarioDetail(scenarioId));
    }
    if (scenarioIds.includes(selectedScenarioId)) {
      resetScenarioManagerForm();
    }
    selectedScenarioIds = new Set([...selectedScenarioIds].filter((scenarioId) => !scenarioIds.includes(scenarioId)));
    renderScenarioPreviewEmpty();
    await loadDashboard();
    setBuilderStatus(`Deleted ${label}`, "pass");
  } catch (error) {
    setBuilderStatus(`Delete failed: ${error.message}`, "fail");
  } finally {
    setActionBusy(false);
  }
}

async function loadHistoryDetail(recordId) {
  selectedHistoryRunId = recordId;
  selectedHistoryDetailPayload = null;
  markSelectedHistoryRow(recordId);
  renderHistoryDetailLoading(recordId);

  try {
    const payload = await fetchJson(ENDPOINTS.historyDetail(recordId));
    selectedHistoryDetailPayload = payload;
    renderHistoryDetail(payload);
    markSelectedHistoryRow(recordId);
  } catch (error) {
    selectedHistoryDetailPayload = null;
    renderHistoryDetailError(recordId, error);
  }
}

function toggleHistoryDetail(recordId) {
  if (selectedHistoryRunId === recordId && findHistoryDetailRow(recordId)) {
    renderHistoryDetailEmpty();
    markSelectedHistoryRow(null);
    return;
  }

  loadHistoryDetail(recordId);
}

function buildScenarioPayload() {
  const baseScenario = selectedScenarioSnapshot ? clonePlainObject(selectedScenarioSnapshot) : {};
  const baseObservation = baseScenario.observation || {};
  const baseExpected = baseScenario.expected || {};
  const payloadKg = numberValue("builder-payload-kg");

  const observation = {
    ...baseObservation,
    mission_type: "carry_go_delivery",
    position: [numberValue("builder-position-x"), numberValue("builder-position-y")],
    target: [numberValue("builder-target-x"), numberValue("builder-target-y")],
    sensor_bias: numberOrFallback(baseObservation.sensor_bias, 0.01),
    payload_kg: payloadKg,
    payload_locked: checkedValue("builder-payload-locked"),
    battery_pct: numberValue("builder-battery-pct"),
    nearest_human_distance_m: numberValue("builder-human-distance"),
    state_age_s: numberValue("builder-state-age"),
    sensor_blackout: checkedValue("builder-sensor-blackout"),
    floor_mu_observed: numberValue("builder-floor-mu"),
    camera_lux_reference: numberOrFallback(baseObservation.camera_lux_reference, 500),
    camera_lux_current: numberValue("builder-camera-lux"),
    camera_sharpness: numberOrFallback(baseObservation.camera_sharpness, 0.96),
    imu_vibration_rms: numberValue("builder-imu-vibration"),
    payload_scale_reading_kg: payloadKg + numberValue("builder-payload-bias"),
    payload_reference_kg: numberOrFallback(baseObservation.payload_reference_kg, payloadKg),
    fleet_context: {
      ...(baseObservation.fleet_context || {}),
      nearby_robots: numberValue("builder-nearby-robots"),
      corridor_occupied: checkedValue("builder-corridor-occupied"),
      elevator_queue: numberValue("builder-elevator-queue"),
    },
  };

  const currentZone = textValue("builder-current-zone");
  const privacyZones = listValue("builder-privacy-zones");
  if (currentZone) {
    observation.current_zone = currentZone;
  } else {
    delete observation.current_zone;
  }
  if (privacyZones.length) {
    observation.privacy_zones = privacyZones;
  } else {
    delete observation.privacy_zones;
  }

  const expected = {
    ...baseExpected,
    final_move: textValue("builder-final-move"),
    seom_passed: checkedValue("builder-seom-passed"),
    audit_valid: true,
  };
  const stumGate = textValue("builder-stum-gate");
  const routeStrategy = textValue("builder-route-strategy");
  const violations = listValue("builder-violations");
  if (stumGate) {
    expected.stum_gate = stumGate;
  } else {
    delete expected.stum_gate;
  }
  if (routeStrategy) {
    expected.route_strategy = routeStrategy;
  } else {
    delete expected.route_strategy;
  }
  if (violations.length) {
    expected.expected_violations = violations;
    delete expected.required_absent_violations;
  } else {
    expected.required_absent_violations = ["C01_person_stop_300mm", "C07_battery_return_15pct"];
    delete expected.expected_violations;
  }

  return {
    id: textValue("builder-id"),
    name: textValue("builder-name"),
    description: textValue("builder-description"),
    tags: listValue("builder-tags"),
    observation,
    expected,
    overwrite: selectedScenarioId !== null,
  };
}

function resetScenarioManagerForm() {
  selectedScenarioId = null;
  selectedScenarioSnapshot = null;
  scenarioDraftBaseSnapshot = null;
  latestScenarioPreview = null;
  populateScenarioForm(DEFAULT_SCENARIO_FORM);
  setScenarioManagerMode("create");
  renderScenarioLibrary({
    scenarios: scenarioLibraryRecords,
    count: scenarioLibraryRecords.length,
    available: true,
  });
  renderScenarioPreviewEmpty();
  renderScenarioDraftAssist();
  setBuilderStatus("Create a new scenario or select one to edit", "");
}

function populateScenarioForm(scenario) {
  const observation = scenario.observation || {};
  const expected = scenario.expected || {};
  const fleetContext = observation.fleet_context || {};
  const position = Array.isArray(observation.position) ? observation.position : [0, 0];
  const target = Array.isArray(observation.target) ? observation.target : [1, 1];
  const payloadKg = numberOrFallback(observation.payload_kg, 2);
  const payloadScale = numberOrFallback(observation.payload_scale_reading_kg, payloadKg);

  setInputValue("builder-id", scenario.id || "custom_carry_go");
  setInputValue("builder-name", scenario.name || "Custom Carry & Go");
  setInputValue("builder-tags", (scenario.tags || ["custom", "carry_go"]).join(","));
  setInputValue("builder-description", scenario.description || "");
  setInputValue("builder-position-x", numberOrFallback(position[0], 0));
  setInputValue("builder-position-y", numberOrFallback(position[1], 0));
  setInputValue("builder-target-x", numberOrFallback(target[0], 1));
  setInputValue("builder-target-y", numberOrFallback(target[1], 1));
  setInputValue("builder-payload-kg", payloadKg);
  setInputValue("builder-battery-pct", numberOrFallback(observation.battery_pct, 80));
  setInputValue(
    "builder-human-distance",
    numberOrFallback(observation.nearest_human_distance_m, 2),
  );
  setInputValue("builder-final-move", expected.final_move || "east");
  setCheckedValue("builder-payload-locked", observation.payload_locked !== false);
  setCheckedValue("builder-seom-passed", expected.seom_passed !== false);
  setInputValue("builder-state-age", numberOrFallback(observation.state_age_s, 0));
  setInputValue("builder-floor-mu", numberOrFallback(observation.floor_mu_observed, 0.52));
  setInputValue("builder-camera-lux", numberOrFallback(observation.camera_lux_current, 480));
  setInputValue("builder-imu-vibration", numberOrFallback(observation.imu_vibration_rms, 0.08));
  setInputValue("builder-payload-bias", payloadScale - payloadKg);
  setInputValue("builder-current-zone", observation.current_zone || "");
  setInputValue("builder-privacy-zones", (observation.privacy_zones || []).join(","));
  setInputValue("builder-nearby-robots", numberOrFallback(fleetContext.nearby_robots, 0));
  setInputValue("builder-elevator-queue", numberOrFallback(fleetContext.elevator_queue, 0));
  setInputValue("builder-stum-gate", expected.stum_gate || "");
  setInputValue("builder-route-strategy", expected.route_strategy || "");
  setInputValue("builder-violations", (expected.expected_violations || []).join(","));
  setCheckedValue("builder-sensor-blackout", Boolean(observation.sensor_blackout));
  setCheckedValue("builder-corridor-occupied", Boolean(fleetContext.corridor_occupied));
}

function renderScenarioDraftAssist() {
  const draft = buildScenarioPayload();
  renderScenarioValidation(draft);
  renderScenarioDiff(draft);
}

function renderScenarioValidation(draft) {
  const findings = scenarioValidationFindings(draft);
  const errors = findings.filter((finding) => finding.kind === "fail");
  const warnings = findings.filter((finding) => finding.kind === "warn");
  const chipKind = errors.length ? "fail" : warnings.length ? "warn" : "pass";
  const chipText = errors.length ? `${errors.length} ERRORS` : warnings.length ? `${warnings.length} WARNINGS` : "READY";
  const container = document.getElementById("scenario-validation-list");

  setPill("scenario-validation-chip", chipText, chipKind);
  container.innerHTML = findings.length
    ? findings
      .map(
        (finding) => `
          <div class="assist-row ${finding.kind}">
            <strong>${escapeHtml(finding.title)}</strong>
            <span>${escapeHtml(finding.detail)}</span>
          </div>
        `,
      )
      .join("")
    : `<div class="assist-row pass"><strong>Ready to save</strong><span>Required fields and expected checks look consistent.</span></div>`;
}

function scenarioValidationFindings(draft) {
  const findings = [];
  const expected = draft.expected || {};
  const observation = draft.observation || {};

  if (!draft.id) {
    findings.push({ kind: "fail", title: "Missing id", detail: "Scenario id is required." });
  }
  if (!draft.name) {
    findings.push({ kind: "fail", title: "Missing name", detail: "Scenario name is required." });
  }
  if (!expected.final_move) {
    findings.push({ kind: "fail", title: "Missing final move", detail: "expected.final_move is required." });
  }
  if (!Array.isArray(observation.position) || observation.position.length !== 2) {
    findings.push({ kind: "fail", title: "Invalid position", detail: "observation.position must contain two coordinates." });
  }
  if (!Array.isArray(observation.target) || observation.target.length !== 2) {
    findings.push({ kind: "fail", title: "Invalid target", detail: "observation.target must contain two coordinates." });
  }
  if (expected.seom_passed === false && !expected.expected_violations?.length) {
    findings.push({
      kind: "warn",
      title: "Blocked SEOM without violations",
      detail: "Add expected violations when SEOM is expected to block.",
    });
  }
  if (expected.expected_violations?.length && expected.required_absent_violations?.length) {
    findings.push({
      kind: "warn",
      title: "Conflicting violation expectations",
      detail: "Use either expected violations or required absent violations for this form.",
    });
  }
  if (observation.nearest_human_distance_m < 0.3 && expected.final_move !== "hold") {
    findings.push({
      kind: "warn",
      title: "Human proximity risk",
      detail: "A human distance below 0.3 m usually expects a hold action.",
    });
  }
  if (observation.battery_pct < 15 && !["hold", "return_to_dock"].includes(expected.final_move)) {
    findings.push({
      kind: "warn",
      title: "Low battery action",
      detail: "Low battery scenarios usually hold or return to dock.",
    });
  }
  if (!draft.tags?.length) {
    findings.push({ kind: "warn", title: "No tags", detail: "Tags make scenario filtering and review easier." });
  }
  return findings;
}

function renderScenarioDiff(draft) {
  const container = document.getElementById("scenario-diff-list");
  if (!scenarioDraftBaseSnapshot) {
    setPill("scenario-diff-chip", "NEW", "neutral");
    container.innerHTML = `<div class="notice">This is a new scenario draft.</div>`;
    return;
  }

  const changes = scenarioDiffRows(scenarioComparable(scenarioDraftBaseSnapshot), scenarioComparable(draft));
  setPill("scenario-diff-chip", changes.length ? `${changes.length} CHANGES` : "CLEAN", changes.length ? "info" : "pass");

  if (!changes.length) {
    container.innerHTML = `<div class="assist-row pass"><strong>No changes</strong><span>The draft matches the loaded scenario.</span></div>`;
    return;
  }

  container.innerHTML = changes
    .slice(0, 24)
    .map(
      (change) => `
        <div class="diff-row">
          <strong>${escapeHtml(change.path)}</strong>
          <div class="diff-values">
            <code>${escapeHtml(formatDetailValue(change.before))}</code>
            <code>${escapeHtml(formatDetailValue(change.after))}</code>
          </div>
        </div>
      `,
    )
    .join("");
}

function scenarioComparable(scenario) {
  return {
    id: scenario.id,
    name: scenario.name,
    description: scenario.description,
    tags: scenario.tags || [],
    observation: scenario.observation || {},
    expected: scenario.expected || {},
  };
}

function scenarioDiffRows(before, after) {
  const beforeFlat = flattenObject(before);
  const afterFlat = flattenObject(after);
  const keys = [...new Set([...Object.keys(beforeFlat), ...Object.keys(afterFlat)])].sort();
  return keys
    .filter((key) => stableStringify(beforeFlat[key]) !== stableStringify(afterFlat[key]))
    .map((key) => ({ path: key, before: beforeFlat[key], after: afterFlat[key] }));
}

function flattenObject(value, prefix = "") {
  if (Array.isArray(value) || value === null || typeof value !== "object") {
    return prefix ? { [prefix]: value } : {};
  }

  return Object.entries(value).reduce((accumulator, [key, item]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (item !== null && typeof item === "object" && !Array.isArray(item)) {
      return { ...accumulator, ...flattenObject(item, path) };
    }
    accumulator[path] = item;
    return accumulator;
  }, {});
}

function uniqueScenarioCopyId(sourceId) {
  const base = `${sourceId}_copy`;
  const existingIds = new Set(scenarioLibraryRecords.map((scenario) => scenario.id));
  if (!existingIds.has(base)) {
    return base;
  }
  let index = 2;
  while (existingIds.has(`${base}_${index}`)) {
    index += 1;
  }
  return `${base}_${index}`;
}

function normalizeTagList(tags) {
  const normalized = Array.isArray(tags) ? [...tags] : [];
  if (!normalized.includes("custom")) {
    normalized.unshift("custom");
  }
  if (!normalized.includes("duplicate")) {
    normalized.push("duplicate");
  }
  return normalized;
}

function setScenarioManagerMode(mode, scenarioId = null) {
  const isEdit = mode === "edit";
  const isDuplicate = mode === "duplicate";
  const label = isEdit ? "EDIT" : isDuplicate ? "DUPLICATE" : "CREATE";
  const kind = isEdit || isDuplicate ? "info" : "neutral";
  setPill("scenario-manager-mode-chip", label, kind);
  setText(
    "scenario-manager-title",
    isEdit ? `Editing ${scenarioId}` : isDuplicate ? `Duplicating ${scenarioId}` : "New Scenario",
  );
  document.getElementById("duplicate-scenario-button").disabled = !selectedScenarioSnapshot;
  updateScenarioSelectionControls();
}

function renderScenarioPreview(report) {
  const scenario = report.scenario || {};
  const actual = scenario.actual || {};
  const checks = scenario.checks || [];
  const latency = report.summary?.module_latency_ms || {};
  const resultKind = report.quality_gate_passed ? "pass" : "fail";

  setText("scenario-preview-title", scenario.id ? `Run ${scenario.id}` : "Scenario Run");
  setPill("scenario-preview-chip", report.quality_gate_passed ? "PASS" : "FAIL", resultKind);

  document.getElementById("scenario-preview-body").innerHTML = `
    <div class="detail-stat-grid compact">
      ${renderDetailStat("Move", actual.final_move || "--")}
      ${renderDetailStat("STUM", actual.stum_gate || "--")}
      ${renderDetailStat("Route", actual.route_strategy || "--")}
      ${renderDetailStat("SEOM", actual.seom_passed ? "pass" : "block")}
      ${renderDetailStat("Fleet", actual.fleet_adjustment || "--")}
      ${renderDetailStat("Violations", String((actual.violations || []).length))}
      ${renderDetailStat("Checks", `${checks.filter((check) => check.passed).length}/${checks.length}`)}
      ${renderDetailStat("Generated", formatTimestamp(report.generated_at))}
    </div>
    ${renderDetailLatency(latency)}
    ${renderScenarioPreviewChecks(checks)}
    <details class="raw-snapshot">
      <summary>Run JSON</summary>
      <pre>${escapeHtml(JSON.stringify(report, null, 2))}</pre>
    </details>
  `;
}

function renderScenarioBatchPreview(reports) {
  const scenarios = reports.map((report) => report.scenario).filter(Boolean);
  const passed = reports.filter((report) => report.quality_gate_passed).length;
  const failed = reports.length - passed;
  const maxP95 = Math.max(
    0,
    ...reports.map((report) => maxModuleP95(report.summary?.module_latency_ms || {})),
  );

  setText("scenario-preview-title", `Batch Run: ${reports.length} scenarios`);
  setPill("scenario-preview-chip", failed ? "FAIL" : "PASS", failed ? "fail" : "pass");
  document.getElementById("scenario-preview-body").innerHTML = `
    <div class="detail-stat-grid compact">
      ${renderDetailStat("Scenarios", String(reports.length))}
      ${renderDetailStat("Passed", String(passed))}
      ${renderDetailStat("Failed", String(failed))}
      ${renderDetailStat("Max P95", `${formatNumber(maxP95)} ms`)}
      ${renderDetailStat("History Records", String(reports.filter((report) => report.history_record).length))}
      ${renderDetailStat("Generated", reports.at(-1)?.generated_at ? formatTimestamp(reports.at(-1).generated_at) : "--")}
    </div>
    ${renderTestLabScenarioRows(scenarios)}
    <details class="raw-snapshot">
      <summary>Batch JSON</summary>
      <pre>${escapeHtml(JSON.stringify(reports, null, 2))}</pre>
    </details>
  `;
}

function renderScenarioPreviewChecks(checks) {
  if (!checks.length) {
    return `<div class="notice">No expected checks in scenario</div>`;
  }

  return `
    <div class="detail-table-wrap">
      <table class="detail-table check-detail-table">
        <thead>
          <tr>
            <th>Check</th>
            <th>Result</th>
            <th>Expected</th>
            <th>Actual</th>
          </tr>
        </thead>
        <tbody>
          ${checks
            .map(
              (check) => `
                <tr>
                  <td>${escapeHtml(check.name || "--")}</td>
                  <td>
                    <span class="status-pill ${check.passed ? "pass" : "fail"}">
                      ${check.passed ? "PASS" : "FAIL"}
                    </span>
                  </td>
                  <td><code>${escapeHtml(formatDetailValue(check.expected))}</code></td>
                  <td><code>${escapeHtml(formatDetailValue(check.actual))}</code></td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderScenarioPreviewLoading(scenarioId) {
  setText("scenario-preview-title", `Running ${scenarioId}`);
  setPill("scenario-preview-chip", "RUNNING", "info");
  document.getElementById("scenario-preview-body").innerHTML =
    `<div class="notice">Running selected scenario</div>`;
}

function renderScenarioBatchPreviewLoading(scenarioIds) {
  setText("scenario-preview-title", `Running ${scenarioIds.length} scenarios`);
  setPill("scenario-preview-chip", "RUNNING", "info");
  document.getElementById("scenario-preview-body").innerHTML =
    `<div class="notice">Running ${escapeHtml(scenarioIds.join(", "))}</div>`;
}

function renderScenarioPreviewError(scenarioId, error) {
  setText("scenario-preview-title", `Run ${scenarioId}`);
  setPill("scenario-preview-chip", "ERROR", "fail");
  document.getElementById("scenario-preview-body").innerHTML =
    `<div class="notice">${escapeHtml(error.message)}</div>`;
}

function renderScenarioPreviewEmpty() {
  setText("scenario-preview-title", "No Run Selected");
  setPill("scenario-preview-chip", "IDLE", "neutral");
  document.getElementById("scenario-preview-body").innerHTML =
    `<div class="notice">Select a scenario and run it to preview actual signals and checks.</div>`;
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
  if (!isBusy) {
    updateScenarioSelectionControls();
    document.getElementById("duplicate-scenario-button").disabled = !selectedScenarioSnapshot;
    document.getElementById("test-run-selected-scenario-button").disabled =
      !scenarioLibraryRecords.some((scenario) => scenario.id === testLabSelectedScenarioId);
  }
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
  renderVisualOverview(scenarioReport, historyPayload);
  renderScenarioLibrary(scenariosPayload);
  renderTestLab(scenarioReport, benchmarkReport, scenariosPayload);
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

function renderVisualOverview(scenarioReport, historyPayload) {
  renderOutcomeVisual(scenarioReport);
  renderHistoryTrendVisual(historyPayload);
  renderViolationVisual(scenarioReport);
}

function renderOutcomeVisual(report) {
  const container = document.getElementById("outcome-visual");
  if (!report?.scenarios?.length) {
    setPill("outcome-chip", "NO DATA", "warn");
    container.innerHTML = `<div class="notice">No scenario report available</div>`;
    return;
  }

  const passed = Number(report.passed || 0);
  const failed = Number(report.failed || 0);
  const total = Math.max(1, Number(report.total || report.scenarios.length));
  const passedWidth = Math.max(0, Math.min(100, (passed / total) * 100));
  const failedWidth = Math.max(0, 100 - passedWidth);
  const rows = report.scenarios
    .slice(0, 8)
    .map((scenario) => {
      const kind = scenario.passed ? "pass" : "fail";
      const width = scenario.passed ? 100 : 45;
      return `
        <div class="scenario-mini-row">
          <div class="scenario-mini-header">
            <span>${escapeHtml(scenario.id)}</span>
            <span>${scenario.passed ? "PASS" : "FAIL"}</span>
          </div>
          <div class="mini-track">
            <div class="mini-fill ${kind}" style="width: ${width}%"></div>
          </div>
        </div>
      `;
    })
    .join("");

  setPill("outcome-chip", `${passed}/${total} PASS`, failed ? "fail" : "pass");
  container.innerHTML = `
    <div class="stacked-bar" aria-label="Scenario pass fail split">
      <div class="stacked-segment pass" style="width: ${passedWidth}%"></div>
      <div class="stacked-segment fail" style="width: ${failedWidth}%"></div>
    </div>
    <div class="outcome-legend">
      <span class="legend-item"><span class="legend-dot pass"></span>${passed} passed</span>
      <span class="legend-item"><span class="legend-dot fail"></span>${failed} failed</span>
      <span class="legend-item">${formatPercent(report.pass_rate)} pass rate</span>
    </div>
    <div class="scenario-mini-list">${rows}</div>
  `;
}

function renderHistoryTrendVisual(historyPayload) {
  const container = document.getElementById("history-trend-visual");
  const records = (historyPayload?.records || [])
    .slice()
    .reverse()
    .filter((record) => typeof record.max_module_p95_ms === "number")
    .slice(-18);

  setPill("trend-chip", `${records.length} POINTS`, records.length >= 2 ? "info" : "warn");

  if (records.length < 2) {
    container.innerHTML = `<div class="notice">Run scenario or benchmark a few times to draw a trend</div>`;
    return;
  }

  const values = records.map((record) => numberOrZero(record.max_module_p95_ms));
  const maxValue = Math.max(...values, 1);
  const latest = records[records.length - 1];
  const failedCount = records.filter((record) => record.quality_gate_passed === false).length;
  const points = values
    .map((value, index) => {
      const x = 12 + (index / Math.max(1, records.length - 1)) * 276;
      const y = 128 - (value / maxValue) * 104;
      return `${roundForSvg(x)},${roundForSvg(y)}`;
    })
    .join(" ");
  const circles = records
    .map((record, index) => {
      const value = numberOrZero(record.max_module_p95_ms);
      const x = 12 + (index / Math.max(1, records.length - 1)) * 276;
      const y = 128 - (value / maxValue) * 104;
      const kind = record.quality_gate_passed === false ? "fail" : "";
      return `<circle class="trend-point ${kind}" cx="${roundForSvg(x)}" cy="${roundForSvg(y)}" r="3.8"></circle>`;
    })
    .join("");

  container.innerHTML = `
    <svg class="trend-svg" viewBox="0 0 300 150" role="img" aria-label="Max module p95 latency trend">
      <line class="trend-axis" x1="12" y1="128" x2="288" y2="128"></line>
      <line class="trend-axis" x1="12" y1="24" x2="12" y2="128"></line>
      <text class="trend-label" x="14" y="20">${formatNumber(maxValue)} ms</text>
      <text class="trend-label" x="222" y="144">latest</text>
      <polyline class="trend-line" points="${points}"></polyline>
      ${circles}
    </svg>
    <div class="trend-metrics">
      <span class="trend-metric">latest ${formatNumber(latest.max_module_p95_ms)} ms</span>
      <span class="trend-metric">max ${formatNumber(maxValue)} ms</span>
      <span class="trend-metric">${failedCount} failed gates</span>
    </div>
  `;
}

function renderViolationVisual(report) {
  const container = document.getElementById("violation-visual");
  const counts = report?.summary?.violation_counts || {};
  const entries = Object.entries(counts).sort((left, right) => Number(right[1]) - Number(left[1]));

  setPill("violation-visual-chip", entries.length ? `${entries.length} TYPES` : "CLEAR", entries.length ? "warn" : "pass");

  if (!entries.length) {
    container.innerHTML = `<span class="token good">No violations in latest scenario report</span>`;
    return;
  }

  const maxCount = Math.max(...entries.map(([, count]) => Number(count)), 1);
  container.innerHTML = `
    <div class="violation-visual-list">
      ${entries
        .map(([name, count]) => {
          const width = Math.max(6, (Number(count) / maxCount) * 100);
          return `
            <div class="violation-visual-row">
              <div class="violation-visual-header">
                <span>${escapeHtml(name)}</span>
                <span>${count}</span>
              </div>
              <div class="violation-track">
                <div class="violation-fill" style="width: ${width}%"></div>
              </div>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
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
    tableBody.innerHTML = `<tr><td colspan="9" class="empty-cell">No scenario artifact</td></tr>`;
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
          <td>${renderViolationStatus(scenario.violation_analysis)}</td>
          <td>${renderViolationTokens(violations)}</td>
        </tr>
      `;
    })
    .join("");
}

function renderScenarioLibrary(payload) {
  const scenarios = payload?.scenarios || [];
  scenarioLibraryRecords = scenarios;
  const availableIds = new Set(scenarios.map((scenario) => scenario.id));
  selectedScenarioIds = new Set([...selectedScenarioIds].filter((scenarioId) => availableIds.has(scenarioId)));
  if (selectedScenarioId && !scenarios.some((scenario) => scenario.id === selectedScenarioId)) {
    selectedScenarioId = null;
    selectedScenarioSnapshot = null;
    setScenarioManagerMode("create");
  }
  setPill("scenario-library-chip", `${payload?.count || 0} YAML`, payload?.available ? "info" : "warn");
  renderScenarioTagFilterOptions();
  renderScenarioLibraryItems();
  updateScenarioSelectionControls();
}

function renderScenarioLibraryItems() {
  const container = document.getElementById("scenario-library-list");
  const scenarios = filteredScenarioRecords();

  if (!scenarioLibraryRecords.length) {
    container.innerHTML = `<div class="notice">No scenario YAML files</div>`;
    return;
  }

  if (!scenarios.length) {
    container.innerHTML = `<div class="notice">No scenarios match the current filters</div>`;
    return;
  }

  container.innerHTML = scenarios
    .map((scenario) => {
      const selectedClass = scenario.id === selectedScenarioId ? "selected" : "";
      const multiSelected = selectedScenarioIds.has(scenario.id);
      const multiSelectedClass = multiSelected ? "multi-selected" : "";
      return `
        <div
          class="scenario-item ${selectedClass} ${multiSelectedClass}"
          data-scenario-id="${escapeHtml(scenario.id)}"
          role="button"
          tabindex="0"
          aria-pressed="${selectedClass ? "true" : "false"}"
        >
          <label class="scenario-select-control" data-scenario-select-control>
            <input
              type="checkbox"
              data-scenario-selector="${escapeHtml(scenario.id)}"
              ${multiSelected ? "checked" : ""}
              aria-label="Select ${escapeHtml(scenario.name || scenario.id)}"
            />
            <span>Select</span>
          </label>
          <div class="scenario-item-copy">
            <strong>${escapeHtml(scenario.name || scenario.id)}</strong>
            <small>${escapeHtml(scenario.id)}</small>
          </div>
          ${renderTags(scenario.tags)}
        </div>
      `;
    })
    .join("");
  syncScenarioSelectionClasses();
}

function renderScenarioTagFilterOptions() {
  const select = document.getElementById("scenario-tag-filter");
  const tags = [
    ...new Set(scenarioLibraryRecords.flatMap((scenario) => scenario.tags || [])),
  ].sort((left, right) => left.localeCompare(right));
  if (scenarioTagFilter && !tags.includes(scenarioTagFilter)) {
    scenarioTagFilter = "";
  }
  select.innerHTML = [
    `<option value="">All tags</option>`,
    ...tags.map((tag) => `<option value="${escapeHtml(tag)}">${escapeHtml(tag)}</option>`),
  ].join("");
  select.value = scenarioTagFilter;
}

function filteredScenarioRecords() {
  return scenarioLibraryRecords.filter((scenario) => {
    const searchable = [
      scenario.id,
      scenario.name,
      scenario.description,
      ...(scenario.tags || []),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    const matchesSearch = !scenarioSearchTerm || searchable.includes(scenarioSearchTerm);
    const matchesTag = !scenarioTagFilter || (scenario.tags || []).includes(scenarioTagFilter);
    return matchesSearch && matchesTag;
  });
}

function toggleScenarioSelection(scenarioId, checked = null) {
  if (!scenarioId) {
    return;
  }

  const shouldSelect = checked === null ? !selectedScenarioIds.has(scenarioId) : Boolean(checked);
  if (shouldSelect) {
    selectedScenarioIds.add(scenarioId);
  } else {
    selectedScenarioIds.delete(scenarioId);
  }
  syncScenarioSelectionClasses();
  updateScenarioSelectionControls();
}

function selectAllScenarios() {
  filteredScenarioRecords().forEach((scenario) => {
    selectedScenarioIds.add(scenario.id);
  });
  syncScenarioSelectionClasses();
  updateScenarioSelectionControls();
  setBuilderStatus(`Selected ${selectedScenarioIds.size} scenarios`, "info");
}

function clearScenarioSelection() {
  selectedScenarioIds.clear();
  syncScenarioSelectionClasses();
  updateScenarioSelectionControls();
  setBuilderStatus("Scenario selection cleared", "");
}

function selectedScenarioOperationIds() {
  if (selectedScenarioIds.size) {
    return [...selectedScenarioIds];
  }
  return selectedScenarioId ? [selectedScenarioId] : [];
}

function updateScenarioSelectionControls() {
  const selectedCount = selectedScenarioIds.size;
  const operationCount = selectedScenarioOperationIds().length;
  const visibleScenarios = filteredScenarioRecords();
  const allVisibleSelected =
    visibleScenarios.length > 0 && visibleScenarios.every((scenario) => selectedScenarioIds.has(scenario.id));
  setPill(
    "scenario-selection-chip",
    selectedCount ? `${selectedCount} SELECTED` : "0 SELECTED",
    selectedCount ? "info" : "neutral",
  );
  document.getElementById("manager-bulk-bar").hidden = selectedCount === 0;
  document.getElementById("clear-scenario-selection-button").disabled = selectedCount === 0;
  document.getElementById("select-all-scenarios-button").disabled =
    !visibleScenarios.length || allVisibleSelected;
  document.getElementById("run-selected-scenario-button").disabled = operationCount === 0;
  document.getElementById("delete-scenario-button").disabled = operationCount === 0;
  document.getElementById("run-selected-scenario-button").textContent =
    selectedCount > 1 ? `Run ${selectedCount} Selected` : "Run Selected";
  document.getElementById("delete-scenario-button").textContent =
    selectedCount > 1 ? `Delete ${selectedCount} Selected` : selectedCount === 1 ? "Delete Selected" : "Delete Scenario";
}

function syncScenarioSelectionClasses() {
  document.querySelectorAll("[data-scenario-id]").forEach((item) => {
    const scenarioId = item.dataset.scenarioId;
    const isMultiSelected = selectedScenarioIds.has(scenarioId);
    item.classList.toggle("multi-selected", isMultiSelected);
    const checkbox = item.querySelector("[data-scenario-selector]");
    if (checkbox) {
      checkbox.checked = isMultiSelected;
    }
  });
}

function renderTestLab(scenarioReport, benchmarkReport, scenariosPayload) {
  setPill("test-lab-chip", latestTestLabResult ? "RESULT READY" : "READY", latestTestLabResult ? "info" : "neutral");
  renderTestLabSuiteSummary(scenarioReport);
  renderTestLabBenchmarkSummary(benchmarkReport);
  renderTestLabScenarioSelector(scenariosPayload?.scenarios || []);
  renderTestRunQueue();
  if (latestTestLabResult) {
    renderTestLabResult(
      latestTestLabResult.label,
      latestTestLabResult.report,
      latestTestLabResult.resultType,
    );
  }
}

function renderTestLabSuiteSummary(report) {
  const container = document.getElementById("test-suite-summary");
  if (!report) {
    setPill("test-suite-chip", "NO DATA", "warn");
    container.innerHTML = `<div class="notice">No scenario suite report yet</div>`;
    return;
  }

  setPill("test-suite-chip", `${report.passed || 0}/${report.total || 0} PASS`, report.quality_gate_passed ? "pass" : "fail");
  container.innerHTML = `
    <div class="detail-stat-grid compact">
      ${renderDetailStat("Cases", String(report.total || 0))}
      ${renderDetailStat("Pass Rate", formatPercent(report.pass_rate))}
      ${renderDetailStat("Failed", String(report.failed || 0))}
      ${renderDetailStat("Generated", formatTimestamp(report.generated_at))}
    </div>
  `;
}

function renderTestLabBenchmarkSummary(report) {
  const container = document.getElementById("test-benchmark-summary");
  if (!report) {
    setPill("test-benchmark-chip", "NO DATA", "warn");
    container.innerHTML = `<div class="notice">No benchmark report yet</div>`;
    return;
  }

  const maxP95 = maxModuleP95(report.module_latency_ms || {});
  setPill("test-benchmark-chip", report.quality_gate_passed ? "PASS" : "FAIL", report.quality_gate_passed ? "pass" : "fail");
  container.innerHTML = `
    <div class="detail-stat-grid compact">
      ${renderDetailStat("Steps", String(report.steps || 0))}
      ${renderDetailStat("Max P95", `${formatNumber(maxP95)} ms`)}
      ${renderDetailStat("Threshold", `${formatNumber(report.thresholds?.max_module_p95_ms)} ms`)}
      ${renderDetailStat("Audit", report.audit_valid ? "valid" : "invalid")}
    </div>
  `;
}

function renderTestLabScenarioSelector(scenarios) {
  const select = document.getElementById("test-scenario-select");
  if (!scenarios.length) {
    testLabSelectedScenarioId = null;
    select.innerHTML = `<option value="">No scenarios available</option>`;
    setPill("test-single-chip", "NO YAML", "warn");
    renderTestLabSelectedScenario();
    return;
  }

  const preferredId = testLabSelectedScenarioId || selectedScenarioId || select.value || scenarios[0].id;
  testLabSelectedScenarioId = scenarios.some((scenario) => scenario.id === preferredId)
    ? preferredId
    : scenarios[0].id;
  select.innerHTML = scenarios
    .map(
      (scenario) => `
        <option value="${escapeHtml(scenario.id)}">${escapeHtml(scenario.name || scenario.id)}</option>
      `,
    )
    .join("");
  select.value = testLabSelectedScenarioId;
  setPill("test-single-chip", "READY", "info");
  renderTestLabSelectedScenario();
}

function renderTestLabSelectedScenario() {
  const scenario = scenarioLibraryRecords.find((item) => item.id === testLabSelectedScenarioId);
  const container = document.getElementById("test-selected-scenario-meta");
  document.getElementById("test-run-selected-scenario-button").disabled = !scenario;

  if (!scenario) {
    container.innerHTML = `<div class="notice">Select a scenario to run a targeted test.</div>`;
    return;
  }

  container.innerHTML = `
    <div class="test-selected-scenario-card">
      <strong>${escapeHtml(scenario.name || scenario.id)}</strong>
      <span>${escapeHtml(scenario.id)}</span>
      ${renderTags(scenario.tags)}
    </div>
  `;
}

function renderTestLabResultLoading(label) {
  setText("test-lab-result-title", label);
  setPill("test-lab-result-chip", "RUNNING", "info");
  setPill("test-lab-chip", "RUNNING", "info");
  document.getElementById("test-lab-result-body").innerHTML =
    `<div class="notice">${escapeHtml(label)} is running</div>`;
}

function renderTestLabResultError(label, error) {
  setText("test-lab-result-title", label);
  setPill("test-lab-result-chip", "ERROR", "fail");
  setPill("test-lab-chip", "ERROR", "fail");
  document.getElementById("test-lab-result-body").innerHTML =
    `<div class="notice">${escapeHtml(error.message)}</div>`;
}

function renderTestLabResult(label, report, resultType) {
  const passed = report?.quality_gate_passed === true;
  const failed = report?.quality_gate_passed === false;
  const chipKind = passed ? "pass" : failed ? "fail" : "neutral";
  const chipText = passed ? "PASS" : failed ? "FAIL" : "UNKNOWN";

  setText("test-lab-result-title", label);
  setPill("test-lab-result-chip", chipText, chipKind);
  setPill("test-lab-chip", chipText, chipKind);
  document.getElementById("test-lab-result-body").innerHTML =
    resultType === "benchmark"
      ? renderTestLabBenchmarkResult(report)
      : renderTestLabScenarioResult(report);
}

function renderTestLabScenarioResult(report) {
  const scenarios = report.scenarios || (report.scenario ? [report.scenario] : []);
  const latency = report.summary?.module_latency_ms || {};
  const maxP95 = maxModuleP95(latency);
  const historyId = report.history_record?.id || "--";

  return `
    <div class="detail-stat-grid compact">
      ${renderDetailStat("Cases", String(report.total || scenarios.length || 0))}
      ${renderDetailStat("Passed", String(report.passed || 0))}
      ${renderDetailStat("Failed", String(report.failed || 0))}
      ${renderDetailStat("Max P95", `${formatNumber(maxP95)} ms`)}
      ${renderDetailStat("Pass Rate", formatPercent(report.pass_rate))}
      ${renderDetailStat("Generated", formatTimestamp(report.generated_at))}
      ${renderDetailStat("History", shortHash(historyId))}
      ${renderDetailStat("Suite", report.suite || "carry_go")}
    </div>
    ${renderTestLabScenarioRows(scenarios)}
    ${renderDetailLatency(latency)}
  `;
}

function renderTestLabBenchmarkResult(report) {
  const latency = report.module_latency_ms || {};
  const maxP95 = maxModuleP95(latency);
  const historyId = report.history_record?.id || "--";

  return `
    <div class="detail-stat-grid compact">
      ${renderDetailStat("Steps", String(report.steps || 0))}
      ${renderDetailStat("Max P95", `${formatNumber(maxP95)} ms`)}
      ${renderDetailStat("Threshold", `${formatNumber(report.thresholds?.max_module_p95_ms)} ms`)}
      ${renderDetailStat("Audit", report.audit_valid ? "valid" : "invalid")}
      ${renderDetailStat("Gate", report.quality_gate_passed ? "pass" : "fail")}
      ${renderDetailStat("Generated", formatTimestamp(report.generated_at))}
      ${renderDetailStat("History", shortHash(historyId))}
      ${renderDetailStat("Runner", "latency")}
    </div>
    ${renderDetailLatency(latency)}
  `;
}

function renderTestLabScenarioRows(scenarios) {
  if (!scenarios.length) {
    return `<div class="notice">No scenario rows returned</div>`;
  }

  return `
    <div class="detail-table-wrap">
      <table class="detail-table">
        <thead>
          <tr>
            <th>Scenario</th>
            <th>Result</th>
            <th>Move</th>
            <th>STUM</th>
            <th>Route</th>
            <th>Safety</th>
            <th>Violations</th>
          </tr>
        </thead>
        <tbody>
          ${scenarios
            .slice(0, 12)
            .map((scenario) => {
              const actual = scenario.actual || {};
              return `
                <tr>
                  <td>
                    <div class="history-run">
                      <strong>${escapeHtml(scenario.name || scenario.id)}</strong>
                      <span>${escapeHtml(scenario.id || "--")}</span>
                    </div>
                  </td>
                  <td>
                    <span class="status-pill ${scenario.passed ? "pass" : "fail"}">
                      ${scenario.passed ? "PASS" : "FAIL"}
                    </span>
                  </td>
                  <td>${escapeHtml(actual.final_move || "--")}</td>
                  <td>${escapeHtml(actual.stum_gate || "--")}</td>
                  <td>${escapeHtml(actual.route_strategy || "--")}</td>
                  <td>${renderViolationStatus(scenario.violation_analysis)}</td>
                  <td>${renderViolationTokens(actual.violations || [])}</td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
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
  historyRecords = historyPayload.records || [];
  historyCompareIds = historyCompareIds.filter((id) =>
    historyRecords.some((record) => record.id === id),
  );
  const records = filteredHistoryRecords();
  const tableBody = document.getElementById("history-table-body");

  setPill(
    "history-chip",
    records.length === historyRecords.length
      ? `${historyPayload.count || 0} RUNS`
      : `${records.length}/${historyRecords.length} RUNS`,
    historyPayload.available ? "info" : "warn",
  );
  renderHistoryComparePanel();

  if (!historyRecords.length) {
    tableBody.innerHTML = `<tr><td colspan="8" class="empty-cell">No dashboard-triggered runs yet</td></tr>`;
    renderHistoryDetailEmpty();
    return;
  }

  if (!records.length) {
    tableBody.innerHTML = `<tr><td colspan="8" class="empty-cell">No runs match the current filters</td></tr>`;
    renderHistoryDetailEmpty();
    return;
  }

  tableBody.innerHTML = records
    .map((record) => {
      const resultKind = record.quality_gate_passed ? "pass" : "fail";
      const selectedClass = record.id === selectedHistoryRunId ? "selected" : "";
      return `
        <tr
          class="history-click-row ${selectedClass}"
          data-history-row-id="${escapeHtml(record.id)}"
          tabindex="0"
          role="button"
          aria-label="View run details for ${escapeHtml(record.id)}"
        >
          <td data-history-compare-control>
            <label class="history-compare-control">
              <input
                type="checkbox"
                data-history-compare-selector="${escapeHtml(record.id)}"
                ${historyCompareIds.includes(record.id) ? "checked" : ""}
                aria-label="Compare ${escapeHtml(record.id)}"
              />
              <span>Compare</span>
            </label>
          </td>
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

  if (selectedHistoryRunId && !records.some((record) => record.id === selectedHistoryRunId)) {
    renderHistoryDetailEmpty();
  } else if (selectedHistoryDetailPayload?.id === selectedHistoryRunId) {
    renderHistoryDetail(selectedHistoryDetailPayload);
  } else {
    markSelectedHistoryRow(selectedHistoryRunId);
  }
}

function filteredHistoryRecords() {
  return historyRecords.filter((record) => {
    const gate = record.quality_gate_passed ? "pass" : "fail";
    const searchable = [
      record.id,
      record.type,
      record.artifact_path,
      record.generated_at,
      record.recorded_at,
      historyScope(record),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    const matchesSearch = !historySearchTerm || searchable.includes(historySearchTerm);
    const matchesType = !historyTypeFilter || record.type === historyTypeFilter;
    const matchesGate = !historyGateFilter || gate === historyGateFilter;
    return matchesSearch && matchesType && matchesGate;
  });
}

function toggleHistoryCompare(recordId, checked) {
  if (!recordId) {
    return;
  }
  if (checked) {
    historyCompareIds = historyCompareIds.filter((id) => id !== recordId);
    historyCompareIds.push(recordId);
    historyCompareIds = historyCompareIds.slice(-2);
  } else {
    historyCompareIds = historyCompareIds.filter((id) => id !== recordId);
  }
  syncHistoryCompareControls();
  renderHistoryComparePanel();
}

function syncHistoryCompareControls() {
  document.querySelectorAll("[data-history-compare-selector]").forEach((checkbox) => {
    checkbox.checked = historyCompareIds.includes(checkbox.dataset.historyCompareSelector);
  });
}

function renderHistoryComparePanel() {
  const selectedCount = historyCompareIds.length;
  setPill(
    "history-compare-chip",
    `${selectedCount} SELECTED`,
    selectedCount === 2 ? "info" : "neutral",
  );
  setText("history-compare-title", selectedCount === 2 ? "Run Delta" : "Select Two Runs");

  if (selectedCount < 2) {
    document.getElementById("history-compare-body").innerHTML =
      `<div class="notice">Check two runs in the table to compare gate, scope, latency, and violations.</div>`;
    return;
  }

  document.getElementById("history-compare-body").innerHTML =
    `<div class="notice">Loading comparison</div>`;
  loadHistoryCompare(historyCompareIds);
}

async function loadHistoryCompare(compareIds) {
  try {
    const details = await Promise.all(compareIds.map(fetchHistoryDetailForCompare));
    if (compareIds.join("|") !== historyCompareIds.join("|")) {
      return;
    }
    renderHistoryComparison(details[0], details[1]);
  } catch (error) {
    document.getElementById("history-compare-body").innerHTML =
      `<div class="notice">${escapeHtml(error.message)}</div>`;
  }
}

async function fetchHistoryDetailForCompare(recordId) {
  if (historyDetailCache.has(recordId)) {
    return historyDetailCache.get(recordId);
  }
  const payload = await fetchJson(ENDPOINTS.historyDetail(recordId));
  historyDetailCache.set(recordId, payload);
  return payload;
}

function renderHistoryComparison(leftPayload, rightPayload) {
  const leftRecord = leftPayload.record || {};
  const rightRecord = rightPayload.record || {};
  const leftReport = leftPayload.data || {};
  const rightReport = rightPayload.data || {};
  const leftLatency = reportModuleLatency(leftReport);
  const rightLatency = reportModuleLatency(rightReport);
  const leftViolations = totalCount(leftReport.summary?.violation_counts || {});
  const rightViolations = totalCount(rightReport.summary?.violation_counts || {});
  const leftP95 = maxModuleP95(leftLatency);
  const rightP95 = maxModuleP95(rightLatency);

  document.getElementById("history-compare-body").innerHTML = `
    <div class="history-compare-summary">
      ${renderDetailStat("Left", shortHash(leftRecord.id || leftPayload.id))}
      ${renderDetailStat("Right", shortHash(rightRecord.id || rightPayload.id))}
      ${renderDetailStat("Gate", `${gateLabel(leftRecord)} -> ${gateLabel(rightRecord)}`)}
      ${renderDetailStat("Scope", `${historyScope(leftRecord)} -> ${historyScope(rightRecord)}`)}
      ${renderDetailStat("Max P95 Delta", deltaNumber(rightP95 - leftP95, " ms"))}
      ${renderDetailStat("Violation Delta", deltaNumber(rightViolations - leftViolations, ""))}
    </div>
    ${renderHistoryCompareLatency(leftLatency, rightLatency)}
    ${renderHistoryCompareScenarioDelta(leftReport, rightReport)}
  `;
}

function renderHistoryCompareLatency(leftLatency, rightLatency) {
  const modules = [...new Set([...Object.keys(leftLatency), ...Object.keys(rightLatency)])].sort();
  if (!modules.length) {
    return `<div class="notice">No comparable latency metrics</div>`;
  }

  return `
    <div class="detail-table-wrap">
      <table class="detail-table latency-detail-table">
        <thead>
          <tr>
            <th>Module</th>
            <th>Left P95</th>
            <th>Right P95</th>
            <th>Delta</th>
          </tr>
        </thead>
        <tbody>
          ${modules
            .map((moduleName) => {
              const left = numberOrZero(leftLatency[moduleName]?.p95);
              const right = numberOrZero(rightLatency[moduleName]?.p95);
              return `
                <tr>
                  <td><strong>${escapeHtml(moduleName)}</strong></td>
                  <td>${formatNumber(left)} ms</td>
                  <td>${formatNumber(right)} ms</td>
                  <td>${deltaNumber(right - left, " ms")}</td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderHistoryCompareScenarioDelta(leftReport, rightReport) {
  const leftScenarios = scenarioResultMap(leftReport.scenarios || []);
  const rightScenarios = scenarioResultMap(rightReport.scenarios || []);
  const scenarioIds = [...new Set([...Object.keys(leftScenarios), ...Object.keys(rightScenarios)])].sort();
  const changed = scenarioIds.filter((scenarioId) =>
    stableStringify(leftScenarios[scenarioId]) !== stableStringify(rightScenarios[scenarioId]),
  );

  if (!scenarioIds.length) {
    return "";
  }
  if (!changed.length) {
    return `<div class="notice">Scenario outcomes match across the selected runs.</div>`;
  }

  return `
    <div class="history-detail-section">
      <div class="detail-section-heading">
        <h3>Scenario Outcome Changes</h3>
        <span class="status-pill info">${changed.length} CHANGED</span>
      </div>
      <div class="detail-table-wrap">
        <table class="detail-table">
          <thead>
            <tr>
              <th>Scenario</th>
              <th>Left</th>
              <th>Right</th>
            </tr>
          </thead>
          <tbody>
            ${changed
              .slice(0, 16)
              .map((scenarioId) => `
                <tr>
                  <td><strong>${escapeHtml(scenarioId)}</strong></td>
                  <td>${scenarioOutcomeLabel(leftScenarios[scenarioId])}</td>
                  <td>${scenarioOutcomeLabel(rightScenarios[scenarioId])}</td>
                </tr>
              `)
              .join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderHistoryDetail(payload) {
  const record = payload.record || {};
  const report = payload.data || {};
  const resultKind = record.quality_gate_passed ? "pass" : "fail";
  const runLabel = `${record.type || "run"} ${formatTimestamp(record.generated_at || record.recorded_at)}`;

  if (!payload.available) {
    setHistoryDetailRow(
      record.id || payload.id,
      "Run Detail Error",
      "ERROR",
      "fail",
      `<div class="notice">${escapeHtml(payload.error || "Run snapshot unavailable")}</div>`,
    );
    return;
  }

  const detailContent =
    record.type === "scenario"
      ? renderHistoryScenarioDetail(report)
      : renderHistoryBenchmarkDetail(report);

  const body = `
    <div class="detail-stat-grid">
      ${renderDetailStat("Type", record.type || "--")}
      ${renderDetailStat("Scope", historyScope(record))}
      ${renderDetailStat("Max P95", `${formatNumber(record.max_module_p95_ms)} ms`)}
      ${renderDetailStat("Recorded", formatTimestamp(record.recorded_at))}
      ${renderDetailStat("Artifact", shortPath(payload.path || record.artifact_path))}
      ${renderDetailStat("Run ID", record.id || "--")}
    </div>
    ${detailContent}
    <div class="history-more-actions">
      <button
        class="action-button"
        type="button"
        data-history-more-button
        aria-expanded="false"
      >
        Browse More
      </button>
    </div>
    <div class="history-more-panel" data-history-more-panel hidden>
      ${renderHistoryMoreData(record, report)}
    </div>
  `;

  setHistoryDetailRow(
    record.id || payload.id,
    runLabel,
    record.quality_gate_passed ? "PASS" : "FAIL",
    resultKind,
    body,
  );
}

function renderHistoryDetailEmpty() {
  selectedHistoryRunId = null;
  selectedHistoryDetailPayload = null;
  removeHistoryDetailRow();
}

function renderHistoryDetailLoading(recordId) {
  setHistoryDetailRow(
    recordId,
    "Loading Run",
    "LOADING",
    "info",
    `<div class="notice">Loading run snapshot</div>`,
  );
}

function renderHistoryDetailError(recordId, error) {
  setHistoryDetailRow(
    recordId,
    "Run Detail Error",
    "ERROR",
    "fail",
    `<div class="notice">${escapeHtml(error.message)}</div>`,
  );
}

function setHistoryDetailRow(recordId, title, chipText, chipKind, bodyHtml) {
  removeHistoryDetailRow();
  const row = findHistoryRow(recordId);
  if (!row) {
    return;
  }

  const detailRow = document.createElement("tr");
  detailRow.className = "history-detail-row";
  detailRow.dataset.historyDetailFor = recordId;
  detailRow.innerHTML = `
    <td colspan="8">
      <div class="history-detail">
        <div class="history-detail-heading">
          <div>
            <p class="eyebrow">Run Details</p>
            <h2>${escapeHtml(title)}</h2>
          </div>
          <span class="status-pill ${chipKind}">${escapeHtml(chipText)}</span>
        </div>
        <div class="history-detail-body">
          ${bodyHtml}
        </div>
      </div>
    </td>
  `;
  row.insertAdjacentElement("afterend", detailRow);
}

function removeHistoryDetailRow() {
  document.querySelectorAll(".history-detail-row").forEach((row) => {
    row.remove();
  });
}

function findHistoryRow(recordId) {
  return [...document.querySelectorAll("[data-history-row-id]")]
    .find((row) => row.dataset.historyRowId === recordId);
}

function findHistoryDetailRow(recordId) {
  return [...document.querySelectorAll("[data-history-detail-for]")]
    .find((row) => row.dataset.historyDetailFor === recordId);
}

function toggleHistoryMore(button) {
  const detailRow = button.closest(".history-detail-row");
  const panel = detailRow?.querySelector("[data-history-more-panel]");
  const isOpen = panel && !panel.hidden;
  if (panel) {
    panel.hidden = isOpen;
  }
  button.textContent = isOpen ? "Browse More" : "Show Less";
  button.setAttribute("aria-expanded", String(!isOpen));
}

function renderHistoryScenarioDetail(report) {
  const scenarios = report.scenarios || [];
  const latency = report.summary?.module_latency_ms || {};
  const violationCounts = report.summary?.violation_counts || {};

  return `
    <div class="history-detail-section">
      <div class="detail-section-heading">
        <h3>Scenario Summary</h3>
        <span class="status-pill ${report.quality_gate_passed ? "pass" : "fail"}">
          ${report.passed || 0}/${report.total || 0} PASS
        </span>
      </div>
      <div class="detail-stat-grid compact">
        ${renderDetailStat("Suite", report.suite || "--")}
        ${renderDetailStat("Pass Rate", formatPercent(report.pass_rate))}
        ${renderDetailStat("Failed", String(report.failed || 0))}
        ${renderDetailStat("Violations", String(totalCount(violationCounts)))}
      </div>
      ${renderDetailLatency(latency)}
      ${renderHistoryScenarioRows(scenarios)}
    </div>
  `;
}

function renderHistoryBenchmarkDetail(report) {
  const latency = report.module_latency_ms || {};

  return `
    <div class="history-detail-section">
      <div class="detail-section-heading">
        <h3>Benchmark Summary</h3>
        <span class="status-pill ${report.audit_valid ? "pass" : "fail"}">
          AUDIT ${report.audit_valid ? "PASS" : "FAIL"}
        </span>
      </div>
      <div class="detail-stat-grid compact">
        ${renderDetailStat("Steps", String(report.steps || 0))}
        ${renderDetailStat("Threshold", `${formatNumber(report.thresholds?.max_module_p95_ms)} ms`)}
        ${renderDetailStat("Audit", report.audit_valid ? "valid" : "invalid")}
        ${renderDetailStat("Gate", report.quality_gate_passed ? "pass" : "fail")}
      </div>
      ${renderDetailLatency(latency)}
    </div>
  `;
}

function renderHistoryMoreData(record, report) {
  const checkDetails = record.type === "scenario" ? renderScenarioCheckDetails(report.scenarios || []) : "";

  return `
    ${checkDetails}
    <div class="raw-snapshot">
      <div class="raw-snapshot-heading">Raw Snapshot</div>
      <pre>${escapeHtml(JSON.stringify(report, null, 2))}</pre>
    </div>
  `;
}

function renderScenarioCheckDetails(scenarios) {
  const checks = scenarios.flatMap((scenario) =>
    (scenario.checks || []).map((check) => ({
      scenarioId: scenario.id,
      ...check,
    })),
  );

  if (!checks.length) {
    return `<div class="notice">No scenario check records in snapshot</div>`;
  }

  return `
    <div class="history-detail-section">
      <div class="detail-section-heading">
        <h3>Scenario Checks</h3>
        <span class="status-pill info">${checks.length} CHECKS</span>
      </div>
      <div class="detail-table-wrap">
        <table class="detail-table check-detail-table">
          <thead>
            <tr>
              <th>Scenario</th>
              <th>Check</th>
              <th>Result</th>
              <th>Expected</th>
              <th>Actual</th>
            </tr>
          </thead>
          <tbody>
            ${checks
              .map(
                (check) => `
                  <tr>
                    <td>${escapeHtml(check.scenarioId || "--")}</td>
                    <td>${escapeHtml(check.name || "--")}</td>
                    <td>
                      <span class="status-pill ${check.passed ? "pass" : "fail"}">
                        ${check.passed ? "PASS" : "FAIL"}
                      </span>
                    </td>
                    <td><code>${escapeHtml(formatDetailValue(check.expected))}</code></td>
                    <td><code>${escapeHtml(formatDetailValue(check.actual))}</code></td>
                  </tr>
                `,
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderHistoryScenarioRows(scenarios) {
  if (!scenarios.length) {
    return `<div class="notice">No scenario records in snapshot</div>`;
  }

  return `
    <div class="detail-table-wrap">
      <table class="detail-table">
        <thead>
          <tr>
            <th>Scenario</th>
            <th>Result</th>
            <th>Move</th>
            <th>STUM</th>
            <th>Route</th>
            <th>Fleet</th>
            <th>Safety</th>
            <th>Violations</th>
          </tr>
        </thead>
        <tbody>
          ${scenarios
            .map((scenario) => {
              const actual = scenario.actual || {};
              return `
                <tr>
                  <td>
                    <div class="history-run">
                      <strong>${escapeHtml(scenario.name || scenario.id)}</strong>
                      <span>${escapeHtml(scenario.id || "--")}</span>
                    </div>
                  </td>
                  <td>
                    <span class="status-pill ${scenario.passed ? "pass" : "fail"}">
                      ${scenario.passed ? "PASS" : "FAIL"}
                    </span>
                  </td>
                  <td>${escapeHtml(actual.final_move || "--")}</td>
                  <td>${escapeHtml(actual.stum_gate || "--")}</td>
                  <td>${escapeHtml(actual.route_strategy || "--")}</td>
                  <td>${escapeHtml(actual.fleet_adjustment || "--")}</td>
                  <td>${renderViolationStatus(scenario.violation_analysis)}</td>
                  <td>${renderViolationTokens(actual.violations || [])}</td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderDetailLatency(metrics) {
  const modules = Object.entries(metrics || {});
  if (!modules.length) {
    return `<div class="notice">No latency metrics in snapshot</div>`;
  }

  return `
    <div class="detail-table-wrap">
      <table class="detail-table latency-detail-table">
        <thead>
          <tr>
            <th>Module</th>
            <th>Avg ms</th>
            <th>P50 ms</th>
            <th>P95 ms</th>
            <th>Max ms</th>
          </tr>
        </thead>
        <tbody>
          ${modules
            .map(
              ([moduleName, item]) => `
                <tr>
                  <td><strong>${escapeHtml(moduleName)}</strong></td>
                  <td>${formatNumber(item.avg)}</td>
                  <td>${formatNumber(item.p50)}</td>
                  <td>${formatNumber(item.p95)}</td>
                  <td>${formatNumber(item.max)}</td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderDetailStat(label, value) {
  return `
    <div class="detail-stat">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function markSelectedHistoryRow(recordId) {
  document.querySelectorAll("[data-history-row-id]").forEach((row) => {
    row.classList.toggle("selected", row.dataset.historyRowId === recordId);
  });
}

function renderFatalError(error) {
  setPill("overall-gate", "ERROR", "fail");
  setText("generated-at", error.message);
  document.getElementById("scenario-table-body").innerHTML =
    `<tr><td colspan="9" class="empty-cell">Dashboard API error</td></tr>`;
  document.getElementById("history-table-body").innerHTML =
    `<tr><td colspan="8" class="empty-cell">Dashboard API error</td></tr>`;
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

function renderViolationStatus(analysis) {
  const status = analysis?.status || "none";
  const metadata = {
    none: ["NONE", "pass"],
    expected: ["EXPECTED", "info"],
    unexpected: ["UNEXPECTED", "fail"],
    missing: ["MISSING", "fail"],
    mixed: ["MIXED", "fail"],
  };
  const [label, kind] = metadata[status] || [status.toUpperCase(), "neutral"];
  return `<span class="status-pill ${kind}">${escapeHtml(label)}</span>`;
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

function gateLabel(record) {
  return record.quality_gate_passed ? "PASS" : "FAIL";
}

function reportModuleLatency(report) {
  if (report?.module_latency_ms) {
    return report.module_latency_ms;
  }
  return report?.summary?.module_latency_ms || {};
}

function deltaNumber(value, suffix) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value)}${suffix}`;
}

function scenarioResultMap(scenarios) {
  return scenarios.reduce((accumulator, scenario) => {
    const actual = scenario.actual || {};
    accumulator[scenario.id || scenario.name || "unknown"] = {
      passed: Boolean(scenario.passed),
      move: actual.final_move || "--",
      stum: actual.stum_gate || "--",
      route: actual.route_strategy || "--",
      violations: actual.violations || [],
    };
    return accumulator;
  }, {});
}

function scenarioOutcomeLabel(outcome) {
  if (!outcome) {
    return `<span class="status-pill neutral">MISSING</span>`;
  }
  return `
    <span class="status-pill ${outcome.passed ? "pass" : "fail"}">
      ${outcome.passed ? "PASS" : "FAIL"}
    </span>
    <span class="muted">${escapeHtml(outcome.move)} / ${escapeHtml(outcome.route)}</span>
  `;
}

function countBy(records, key) {
  return records.reduce((accumulator, record) => {
    const value = record[key] || "unknown";
    accumulator[value] = (accumulator[value] || 0) + 1;
    return accumulator;
  }, {});
}

function closestFromEvent(event, selector) {
  return event.target instanceof Element ? event.target.closest(selector) : null;
}

function clonePlainObject(value) {
  return JSON.parse(JSON.stringify(value || {}));
}

function totalCount(counts) {
  return Object.values(counts || {}).reduce((total, value) => total + Number(value || 0), 0);
}

function maxModuleP95(metrics) {
  return Math.max(
    0,
    ...Object.values(metrics || {}).map((item) => numberOrZero(item?.p95)),
  );
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

function setInputValue(id, value) {
  document.getElementById(id).value = value;
}

function numberValue(id) {
  const value = Number(document.getElementById(id).value);
  return Number.isFinite(value) ? value : 0;
}

function numberOrFallback(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function checkedValue(id) {
  return document.getElementById(id).checked;
}

function setCheckedValue(id, value) {
  document.getElementById(id).checked = Boolean(value);
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

function roundForSvg(value) {
  return Number(value).toFixed(2);
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

function formatDetailValue(value) {
  if (value === undefined || value === null) {
    return "--";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function stableStringify(value) {
  return JSON.stringify(stableNormalize(value));
}

function stableNormalize(value) {
  if (value === undefined) {
    return "__undefined__";
  }
  if (Array.isArray(value)) {
    return value.map((item) => stableNormalize(item));
  }
  if (value && typeof value === "object") {
    return Object.keys(value)
      .sort()
      .reduce((accumulator, key) => {
        accumulator[key] = stableNormalize(value[key]);
        return accumulator;
      }, {});
  }
  return value;
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
