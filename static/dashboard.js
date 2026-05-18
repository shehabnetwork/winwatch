/**
 * dashboard.js — Filter, sort, chart, and CSV export logic.
 *
 * No external dependencies beyond Chart.js (loaded via CDN in the HTML).
 */

"use strict";

// ── Utilities ──────────────────────────────────────────────────────────────

/**
 * Format whole seconds into a human-readable string: "2h 14m 35s".
 * @param {number|null} secs
 * @returns {string}
 */
function fmtDuration(secs) {
  if (secs == null || secs < 0) return "—";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

/**
 * Format an ISO 8601 string into a locale-aware short datetime.
 * @param {string|null} iso
 * @returns {string}
 */
function fmtDatetime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch {
    return iso;
  }
}

/** Build a query string from a plain object, omitting null/empty values. */
function buildQuery(params) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "") q.set(k, String(v));
  }
  return q.toString();
}

// ── Sorting state ─────────────────────────────────────────────────────────

/** @type {{ col: string, dir: 1|-1 }} */
const appSort   = { col: "start_time", dir: -1 };
const loginSort = { col: "login_time", dir: -1 };

function sortRows(rows, sortState) {
  const { col, dir } = sortState;
  return [...rows].sort((a, b) => {
    const av = a[col] ?? "";
    const bv = b[col] ?? "";
    if (av < bv) return -1 * dir;
    if (av > bv) return  1 * dir;
    return 0;
  });
}

function updateSortHeaders(tableId, sortState) {
  const table = document.getElementById(tableId);
  table.querySelectorAll("th.sortable").forEach(th => {
    th.classList.remove("sort-asc", "sort-desc");
    if (th.dataset.col === sortState.col) {
      th.classList.add(sortState.dir === 1 ? "sort-asc" : "sort-desc");
    }
  });
}

// ── Chart ─────────────────────────────────────────────────────────────────

let appChartInstance = null;

/**
 * Render (or update) the horizontal bar chart showing the top-10 apps
 * by total duration from the currently filtered rows.
 * @param {Array<object>} rows
 */
function renderAppChart(rows) {
  // Aggregate duration by app_name.
  const totals = {};
  for (const row of rows) {
    const name = row.app_name || "unknown";
    totals[name] = (totals[name] || 0) + (row.duration_seconds || 0);
  }

  // Top 10, sorted descending.
  const sorted = Object.entries(totals)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);

  const labels = sorted.map(([name]) => name);
  const data   = sorted.map(([, secs]) => Math.round(secs / 60)); // minutes

  const ctx = document.getElementById("app-chart");
  if (!ctx) return;

  if (appChartInstance) {
    appChartInstance.data.labels = labels;
    appChartInstance.data.datasets[0].data = data;
    appChartInstance.update();
    return;
  }

  appChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Time (minutes)",
        data,
        backgroundColor: "rgba(37,99,235,0.72)",
        borderColor:     "rgba(37,99,235,1)",
        borderWidth: 1,
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.parsed.x} min`,
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: "Minutes" },
          beginAtZero: true,
          ticks: { precision: 0 },
        },
      },
    },
  });
}

// ── App sessions tab ──────────────────────────────────────────────────────

/** Collect current filter values for app-sessions. */
function getAppFilters() {
  return {
    username:     document.getElementById("app-username").value     || null,
    app_name:     document.getElementById("app-appname").value      || null,
    exe_path:     document.getElementById("app-exepath").value      || null,
    date_from:    document.getElementById("app-datefrom").value     || null,
    date_to:      document.getElementById("app-dateto").value       || null,
    min_duration: document.getElementById("app-minduration").value  || null,
  };
}

async function loadAppSessions() {
  const filters = getAppFilters();
  const qs = buildQuery(filters);
  let rows = [];
  try {
    const res = await fetch(`/api/app-sessions?${qs}`);
    rows = await res.json();
  } catch (e) {
    console.error("Failed to load app sessions:", e);
  }

  const sorted = sortRows(rows, appSort);
  renderAppTable(sorted);
  renderAppChart(sorted);
  updateSortHeaders("app-table", appSort);
  updateAppSummary(rows);
}

function updateAppSummary(rows) {
  const count = rows.length;
  const total = rows.reduce((s, r) => s + (r.duration_seconds || 0), 0);
  document.getElementById("app-count").textContent = `${count} session${count !== 1 ? "s" : ""}`;
  document.getElementById("app-total-duration").textContent = `Total: ${fmtDuration(total)}`;
}

function renderAppTable(rows) {
  const tbody = document.getElementById("app-tbody");
  const empty = document.getElementById("app-empty");

  if (rows.length === 0) {
    tbody.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  tbody.innerHTML = rows.map(r => `
    <tr>
      <td>${escHtml(r.username ?? "")}</td>
      <td>${escHtml(r.app_name ?? "")}</td>
      <td title="${escHtml(r.exe_path ?? "")}">${escHtml(r.exe_path ?? "—")}</td>
      <td title="${escHtml(r.window_title ?? "")}">${escHtml(r.window_title ?? "—")}</td>
      <td>${fmtDatetime(r.start_time)}</td>
      <td>
        ${r.end_time ? fmtDatetime(r.end_time) : '<span class="active-badge">Active</span>'}
      </td>
      <td class="duration-cell">${fmtDuration(r.duration_seconds)}</td>
    </tr>
  `).join("");
}

// ── Login sessions tab ────────────────────────────────────────────────────

function getLoginFilters() {
  return {
    username:     document.getElementById("login-username").value    || null,
    date_from:    document.getElementById("login-datefrom").value    || null,
    date_to:      document.getElementById("login-dateto").value      || null,
    min_duration: document.getElementById("login-minduration").value || null,
  };
}

async function loadLoginSessions() {
  const filters = getLoginFilters();
  const qs = buildQuery(filters);
  let rows = [];
  try {
    const res = await fetch(`/api/login-sessions?${qs}`);
    rows = await res.json();
  } catch (e) {
    console.error("Failed to load login sessions:", e);
  }

  const sorted = sortRows(rows, loginSort);
  renderLoginTable(sorted);
  updateSortHeaders("login-table", loginSort);
  updateLoginSummary(rows);
}

function updateLoginSummary(rows) {
  const count = rows.length;
  const total = rows.reduce((s, r) => s + (r.duration_seconds || 0), 0);
  document.getElementById("login-count").textContent = `${count} session${count !== 1 ? "s" : ""}`;
  document.getElementById("login-total-duration").textContent = `Total: ${fmtDuration(total)}`;
}

function renderLoginTable(rows) {
  const tbody = document.getElementById("login-tbody");
  const empty = document.getElementById("login-empty");

  if (rows.length === 0) {
    tbody.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  tbody.innerHTML = rows.map(r => `
    <tr>
      <td>${escHtml(r.username ?? "")}</td>
      <td>${fmtDatetime(r.login_time)}</td>
      <td>
        ${r.logout_time ? fmtDatetime(r.logout_time) : '<span class="active-badge">Active</span>'}
      </td>
      <td class="duration-cell">${fmtDuration(r.duration_seconds)}</td>
      <td>${escHtml(r.source ?? "—")}</td>
    </tr>
  `).join("");
}

// ── User dropdown population ──────────────────────────────────────────────

async function populateUserDropdowns() {
  let users = [];
  try {
    const res = await fetch("/api/users");
    users = await res.json();
  } catch {
    return;
  }

  const fragment = (current) => {
    const el = document.getElementById(current);
    if (!el) return;
    const existing = [...el.options].map(o => o.value);
    for (const u of users) {
      if (!existing.includes(u)) {
        const opt = document.createElement("option");
        opt.value = opt.textContent = u;
        el.appendChild(opt);
      }
    }
  };
  fragment("app-username");
  fragment("login-username");
}

// ── CSV export ────────────────────────────────────────────────────────────

function exportCSV(endpoint, getFilters) {
  const qs = buildQuery(getFilters());
  window.location.href = `${endpoint}?${qs}`;
}

// ── XSS defence: HTML entity escaping ─────────────────────────────────────

const _escEl = document.createElement("span");
function escHtml(str) {
  _escEl.textContent = str;
  return _escEl.innerHTML;
}

// ── Tab switching ─────────────────────────────────────────────────────────

function initTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    });
  });
}

// ── Sortable column headers ───────────────────────────────────────────────

function initSortableHeaders(tableId, sortState, reloadFn) {
  const table = document.getElementById(tableId);
  table.querySelectorAll("th.sortable").forEach(th => {
    th.addEventListener("click", () => {
      const col = th.dataset.col;
      if (sortState.col === col) {
        sortState.dir = sortState.dir === 1 ? -1 : 1;
      } else {
        sortState.col = col;
        sortState.dir = -1;
      }
      reloadFn();
    });
  });
}

// ── Bootstrap ─────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  initTabs();
  initSortableHeaders("app-table",   appSort,   loadAppSessions);
  initSortableHeaders("login-table", loginSort, loadLoginSessions);

  await populateUserDropdowns();

  // Apply buttons.
  document.getElementById("app-apply").addEventListener("click",   loadAppSessions);
  document.getElementById("login-apply").addEventListener("click", loadLoginSessions);

  // Reset buttons.
  document.getElementById("app-reset").addEventListener("click", () => {
    ["app-username","app-appname","app-exepath","app-datefrom","app-dateto","app-minduration"]
      .forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
    loadAppSessions();
  });
  document.getElementById("login-reset").addEventListener("click", () => {
    ["login-username","login-datefrom","login-dateto","login-minduration"]
      .forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
    loadLoginSessions();
  });

  // Export buttons.
  document.getElementById("app-export").addEventListener("click", () =>
    exportCSV("/export/app-sessions.csv", getAppFilters));
  document.getElementById("login-export").addEventListener("click", () =>
    exportCSV("/export/login-sessions.csv", getLoginFilters));

  // Initial data load.
  await Promise.all([loadAppSessions(), loadLoginSessions()]);
});
