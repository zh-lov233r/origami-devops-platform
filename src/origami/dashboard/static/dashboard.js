/*
中文：Artifact Dashboard 前端逻辑，从 FastAPI artifact API 拉取报告并渲染表格、延迟和审计摘要。
English: Artifact Dashboard frontend logic fetching FastAPI artifact APIs and rendering tables, latency, and audit summaries.
*/

const ENDPOINTS = {
  scenario: "/api/reports/scenario",
  benchmark: "/api/reports/benchmark",
  events: "/api/events/scenario?limit=500",
  audit: "/api/audit/scenario?limit=100",
};

document.addEventListener("DOMContentLoaded", () => {
  loadDashboard();
});

async function loadDashboard() {
  try {
    const [scenarioPayload, benchmarkPayload, eventPayload, auditPayload] = await Promise.all([
      fetchJson(ENDPOINTS.scenario),
      fetchJson(ENDPOINTS.benchmark),
      fetchJson(ENDPOINTS.events),
      fetchJson(ENDPOINTS.audit),
    ]);

    renderDashboard(scenarioPayload, benchmarkPayload, eventPayload, auditPayload);
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

function renderDashboard(scenarioPayload, benchmarkPayload, eventPayload, auditPayload) {
  const scenarioReport = scenarioPayload.available ? scenarioPayload.data : null;
  const benchmarkReport = benchmarkPayload.available ? benchmarkPayload.data : null;

  renderSummary(scenarioPayload, benchmarkPayload, eventPayload, auditPayload);
  renderScenarioTable(scenarioReport);
  renderLatency(benchmarkReport, scenarioReport);
  renderViolations(scenarioReport);
  renderEvents(eventPayload);
  renderAudit(auditPayload);
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

function renderFatalError(error) {
  setPill("overall-gate", "ERROR", "fail");
  setText("generated-at", error.message);
  document.getElementById("scenario-table-body").innerHTML =
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

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
