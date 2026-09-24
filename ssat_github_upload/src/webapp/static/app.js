const state = {
  systems: [],
  currentKey: null,
  currentResult: null,
  pollTimer: null,
  editingKey: null, // set while the Add/Edit System modal is in edit mode
  envFilter: null, // null = show all environments on the home view
  dashboardView: localStorage.getItem("ssat_dashboard_view") || "descriptive", // "descriptive" | "visual" | "logs" | "history" | "ai"
  view: "home", // "home" | "dashboard" | "system" -- which top-level area of the app is showing
  viewingRunName: null, // set while browsing a historical run (via the History tab) instead of the latest one
  historyRuns: null, // cached /api/systems/<key>/runs response for the currently open system
  compareSelected: [], // up to 2 run_names checked in the History tab for comparison
  aiInsights: null, // cached /api/runs/<name>/ai/insights response for the currently viewed run (null = not generated yet)
  aiQaHistory: [], // [{question, answer}, ...] for the currently viewed run, this browser session only
};

const ENV_ORDER = ["Sandbox", "Development", "Quality", "Production"];

function envPill(environment) {
  const label = environment || "Unassigned";
  const cls = environment ? `env-${environment.toLowerCase()}` : "env-sandbox";
  return el("span", { class: `env-pill ${cls}`, text: label });
}

const app = document.getElementById("app");
const breadcrumb = document.getElementById("breadcrumb");

// ---------------------------------------------------------------- shell chrome

const sidenavEl = document.getElementById("sidenav");
sidenavEl.classList.toggle("collapsed", localStorage.getItem("ssat_sidenav_collapsed") === "1");
document.getElementById("sidenavToggleBtn").addEventListener("click", () => {
  const collapsed = !sidenavEl.classList.contains("collapsed");
  sidenavEl.classList.toggle("collapsed", collapsed);
  localStorage.setItem("ssat_sidenav_collapsed", collapsed ? "1" : "0");
});

// ---------------------------------------------------------------- theme (dark mode)

const MOON_ICON = '<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.4 5.4 0 0 1-7.54-7.54A9 9 0 0 0 12 3Z"/></svg>';
const SUN_ICON =
  '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">' +
  '<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>' +
  '<path d="M12 2v2m0 16v2m10-10h-2M4 12H2m16.66-6.66-1.42 1.42M6.76 17.24l-1.42 1.42M18.24 18.66l-1.42-1.42M6.76 6.76 5.34 5.34"/>' +
  "</svg>";
const themeToggleBtn = document.getElementById("themeToggleBtn");

function systemPrefersDark() {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyTheme(theme) {
  // theme: "light" | "dark" | null (null = follow the OS setting, handled by CSS media query)
  if (theme) document.documentElement.setAttribute("data-theme", theme);
  else document.documentElement.removeAttribute("data-theme");
  themeToggleBtn.innerHTML = (theme ? theme === "dark" : systemPrefersDark()) ? SUN_ICON : MOON_ICON;
}

applyTheme(localStorage.getItem("ssat_theme"));
themeToggleBtn.addEventListener("click", () => {
  const active = document.documentElement.getAttribute("data-theme") || (systemPrefersDark() ? "dark" : "light");
  const next = active === "dark" ? "light" : "dark";
  localStorage.setItem("ssat_theme", next);
  applyTheme(next);
});

// ---------------------------------------------------------------- utilities

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed (${res.status})`);
  }
  return res.status === 204 ? null : res.json();
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) if (c) node.appendChild(c);
  return node;
}

function setBreadcrumb(systemLabel) {
  breadcrumb.innerHTML = "";
  if (!systemLabel) return;
  breadcrumb.appendChild(el("span", { class: "sep", text: "/" }));
  breadcrumb.appendChild(el("span", { class: "crumb", text: "Home", onclick: goHome }));
  breadcrumb.appendChild(el("span", { class: "sep", text: "/" }));
  breadcrumb.appendChild(el("span", { text: systemLabel }));
}

function goHome(push = true) {
  state.currentKey = null;
  state.envFilter = null;
  state.view = "home";
  stopPolling();
  setBreadcrumb(null);
  renderSidenav();
  renderHome();
  if (push) history.pushState({ view: "home" }, "", "#home");
}

function selectEnvFilter(env, push = true) {
  state.currentKey = null;
  state.envFilter = env;
  state.view = "home";
  stopPolling();
  setBreadcrumb(null);
  renderSidenav();
  renderHome();
  if (push) history.pushState({ view: "env", env }, "", `#env/${encodeURIComponent(env)}`);
}

function goDashboard(push = true) {
  state.currentKey = null;
  state.envFilter = null;
  state.view = "dashboard";
  stopPolling();
  setBreadcrumb(null);
  renderSidenav();
  renderDashboard();
  if (push) history.pushState({ view: "dashboard" }, "", "#dashboard");
}

// Browser back/forward moves through in-app views instead of leaving the page.
window.addEventListener("popstate", (e) => {
  const s = e.state;
  if (!s || s.view === "home") goHome(false);
  else if (s.view === "env") selectEnvFilter(s.env, false);
  else if (s.view === "dashboard") goDashboard(false);
  else if (s.view === "system") openSystem(s.key, false);
  else goHome(false);
});

// ---------------------------------------------------------------- side navigation

function renderSidenav() {
  const nav = document.getElementById("sidenav");
  nav.innerHTML = "";

  const counts = { Sandbox: 0, Development: 0, Quality: 0, Production: 0 };
  let unassignedCount = 0;
  for (const sys of state.systems) {
    if (sys.environment && counts[sys.environment] !== undefined) counts[sys.environment]++;
    else unassignedCount++;
  }

  const onHome = state.view === "home";

  const homeSection = el("div", { class: "sidenav-section" });
  homeSection.appendChild(
    el("div", { class: `sidenav-item ${onHome && !state.envFilter ? "active" : ""}`, onclick: goHome }, [
      el("span", { class: "nav-label" }, [homeIcon(), el("span", { text: "Home" })]),
      el("span", { class: "nav-count", text: String(state.systems.length) }),
    ])
  );
  homeSection.appendChild(
    el("div", { class: `sidenav-item ${state.view === "dashboard" ? "active" : ""}`, onclick: goDashboard }, [
      el("span", { class: "nav-label" }, [dashboardIcon(), el("span", { text: "Dashboard" })]),
    ])
  );
  nav.appendChild(homeSection);

  // Collapsed by default (space-saving "dropdown" behaviour) -- auto-expanded whenever an
  // environment filter is actually active, so the active item is never hidden from view.
  const envFilterActive = onHome && state.envFilter;
  const envExpanded = envFilterActive || localStorage.getItem("ssat_env_nav_expanded") === "1";

  const envSection = el("div", { class: "sidenav-section" });
  const envHeading = el(
    "div",
    {
      class: "sidenav-heading sidenav-dropdown-heading",
      onclick: () => {
        const next = !envSection.classList.contains("expanded");
        envSection.classList.toggle("expanded", next);
        localStorage.setItem("ssat_env_nav_expanded", next ? "1" : "0");
      },
    },
    [el("span", { text: "Environments" }), el("span", { class: "sidenav-dropdown-caret", html: "&#9662;" })]
  );
  envSection.appendChild(envHeading);
  envSection.classList.toggle("expanded", Boolean(envExpanded));

  const envItems = el("div", { class: "sidenav-dropdown-items" });
  for (const env of ENV_ORDER) {
    const active = onHome && state.envFilter === env;
    envItems.appendChild(
      el("div", { class: `sidenav-item ${active ? "active" : ""}`, onclick: () => selectEnvFilter(env) }, [
        el("span", { class: "nav-label" }, [el("span", { class: `dot dot-${env.toLowerCase()}` }), el("span", { text: env })]),
        el("span", { class: "nav-count", text: String(counts[env]) }),
      ])
    );
  }
  if (unassignedCount > 0) {
    const active = onHome && state.envFilter === "__unassigned__";
    envItems.appendChild(
      el("div", { class: `sidenav-item ${active ? "active" : ""}`, onclick: () => selectEnvFilter("__unassigned__") }, [
        el("span", { class: "nav-label" }, [el("span", { class: "dot", style: "background:#c8ccd0;" }), el("span", { text: "Unassigned" })]),
        el("span", { class: "nav-count", text: String(unassignedCount) }),
      ])
    );
  }
  envSection.appendChild(envItems);
  nav.appendChild(envSection);
}

function homeIcon() {
  const span = el("span", { style: "display:flex;" });
  span.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24"><path fill="currentColor" d="M12 3 2 12h3v8h6v-6h2v6h6v-8h3L12 3Z"/></svg>';
  return span;
}

function dashboardIcon() {
  const span = el("span", { style: "display:flex;" });
  span.innerHTML =
    '<svg width="15" height="15" viewBox="0 0 24 24"><path fill="currentColor" d="M3 13h4v8H3v-8Zm7-8h4v16h-4V5Zm7 5h4v11h-4V10Z"/></svg>';
  return span;
}

// ---------------------------------------------------------------- home view

async function loadSystems() {
  state.systems = await api("/api/systems");
}

function systemTile(sys) {
  const editBtn = el("button", {
    class: "tile-edit-btn",
    title: "Edit system",
    onclick: (e) => {
      e.stopPropagation();
      openEditSystemModal(sys.key);
    },
    html: '<svg width="14" height="14" viewBox="0 0 24 24"><path fill="currentColor" d="m3 17.25 11.06-11.06 3.75 3.75L6.75 21H3v-3.75Zm14.85-12.02 1.92-1.92c.39-.39 1.02-.39 1.41 0l2.34 2.34c.39.39.39 1.02 0 1.41l-1.92 1.92-3.75-3.75Z"/></svg>',
  });
  return el("div", { class: "tile", onclick: () => openSystem(sys.key) }, [
    editBtn,
    el("div", { class: "tile-icon" }, [shieldIcon()]),
    el("div", {}, [
      el("div", { class: "tile-label", text: sys.label }),
      el("div", { class: "tile-sub", text: `${sys.system_id} · Client ${sys.client}` }),
      el("div", { style: "margin-top:6px;" }, [envPill(sys.environment)]),
    ]),
  ]);
}

function addTile(presetEnv) {
  return el("div", { class: "tile add-tile", onclick: () => openAddSystemModal(presetEnv) }, [
    el("div", { class: "plus", text: "+" }),
    el("div", { class: "tile-sub", text: "Add System" }),
  ]);
}

function renderHome() {
  app.innerHTML = "";
  app.appendChild(el("h1", { class: "section-title", text: state.envFilter ? `Systems · ${state.envFilter === "__unassigned__" ? "Unassigned" : state.envFilter}` : "Systems" }));

  const grouped = {};
  for (const env of ENV_ORDER) grouped[env] = [];
  const unassigned = [];
  for (const sys of state.systems) {
    if (sys.environment && grouped[sys.environment]) grouped[sys.environment].push(sys);
    else unassigned.push(sys);
  }

  if (state.envFilter) {
    // Single-environment view: that environment's systems plus an Add tile pre-filled to it.
    const isUnassigned = state.envFilter === "__unassigned__";
    const systems = isUnassigned ? unassigned : grouped[state.envFilter] || [];
    if (!systems.length) {
      app.appendChild(el("p", { class: "empty-state", text: "No systems in this environment yet." }));
    }
    const grid = el("div", { class: "tile-grid" });
    for (const sys of systems) grid.appendChild(systemTile(sys));
    grid.appendChild(addTile(isUnassigned ? null : state.envFilter));
    app.appendChild(grid);
    return;
  }

  const sectionsWithSystems = ENV_ORDER.filter((env) => grouped[env].length > 0);
  for (const env of sectionsWithSystems) {
    app.appendChild(el("div", { class: "env-section-title", text: env }));
    const grid = el("div", { class: "tile-grid" });
    for (const sys of grouped[env]) grid.appendChild(systemTile(sys));
    app.appendChild(grid);
  }

  if (unassigned.length) {
    app.appendChild(el("div", { class: "env-section-title", text: "Unassigned" }));
    const grid = el("div", { class: "tile-grid" });
    for (const sys of unassigned) grid.appendChild(systemTile(sys));
    app.appendChild(grid);
  }

  app.appendChild(el("div", { class: "env-section-title", text: sectionsWithSystems.length || unassigned.length ? "Add" : "Get Started" }));
  const addGrid = el("div", { class: "tile-grid" });
  addGrid.appendChild(addTile(null));
  app.appendChild(addGrid);
}

function shieldIcon() {
  const span = el("span");
  span.innerHTML =
    '<svg width="28" height="28" viewBox="0 0 24 24"><path fill="currentColor" d="M12 1 2 5v6c0 5.5 3.8 10.7 10 12 6.2-1.3 10-6.5 10-12V5l-10-4Zm0 2.2 8 3.2v4.6c0 4.5-3 8.8-8 9.9-5-1.1-8-5.4-8-9.9V6.4l8-3.2Z"/><path fill="currentColor" d="m10.9 14.9-2.4-2.4-1.4 1.4 3.8 3.8 6.6-6.6-1.4-1.4z"/></svg>';
  return span;
}

// ---------------------------------------------------------------- dashboard (cross-system analytics)

function posturePills(posture) {
  const wrap = el("div", { class: "posture-counts" });
  if (posture.critical) {
    wrap.appendChild(
      el("span", { class: "posture-chip crit" }, [el("span", { class: "dot" }), el("span", { text: `${posture.critical} Critical` })])
    );
  }
  if (posture.warning) {
    wrap.appendChild(
      el("span", { class: "posture-chip warn" }, [el("span", { class: "dot" }), el("span", { text: `${posture.warning} Warning` })])
    );
  }
  if (!posture.critical && !posture.warning) {
    wrap.appendChild(el("span", { class: "posture-chip good" }, [el("span", { class: "dot" }), el("span", { text: "Clean" })]));
  }
  return wrap;
}

async function renderDashboard() {
  app.innerHTML = "";
  app.appendChild(el("h1", { class: "section-title", text: "Dashboard" }));
  const status = el("p", { class: "empty-state", text: "Loading dashboard..." });
  app.appendChild(status);

  let data;
  try {
    data = await api("/api/dashboard");
  } catch (err) {
    status.className = "error-banner";
    status.textContent = `Could not load dashboard: ${err.message}`;
    return;
  }
  if (state.view !== "dashboard") return; // user navigated elsewhere while this was loading

  app.innerHTML = "";
  app.appendChild(el("h1", { class: "section-title", text: "Dashboard" }));

  const kpis = [
    { value: data.systems_total, label: "Total Systems", cls: "" },
    { value: data.systems_with_critical, label: "Systems with Critical Findings", cls: "crit" },
    { value: data.totals.critical, label: "Critical Findings (latest runs)", cls: "crit" },
    { value: data.totals.warning, label: "Warning Findings (latest runs)", cls: "warn" },
    { value: data.systems_never_run, label: "Never Assessed", cls: "warn" },
  ];
  const kpiGrid = el("div", { class: "dash-kpi-grid" });
  kpis.forEach((k, i) => {
    const valueNode = el("div", { class: "dash-kpi-value", text: "0" });
    kpiGrid.appendChild(
      el("div", { class: `dash-kpi-card ${k.cls}`, style: `animation-delay:${i * 50}ms` }, [
        valueNode,
        el("div", { class: "dash-kpi-label", text: k.label }),
      ])
    );
    requestAnimationFrame(() => animateNumber(valueNode, k.value, 700));
  });
  app.appendChild(kpiGrid);

  app.appendChild(el("h3", { class: "viz-section-title", text: "Systems by Risk" }));
  app.appendChild(
    el("p", {
      class: "viz-section-sub",
      text: "Every saved system, ranked by its most recent assessment -- highest risk first. Click a row to open that system.",
    })
  );

  if (!data.systems.length) {
    app.appendChild(el("p", { class: "empty-state", text: "No systems saved yet -- add one from Home to get started." }));
    return;
  }

  const table = el("table", { class: "dash-table fade-in-up" });
  table.appendChild(
    el("tr", {}, [
      el("th", { text: "System" }),
      el("th", { text: "Environment" }),
      el("th", { text: "Last Run" }),
      el("th", { text: "Posture" }),
    ])
  );
  for (const sys of data.systems) {
    table.appendChild(
      el("tr", { class: "clickable", onclick: () => openSystem(sys.key) }, [
        el("td", {}, [
          el("div", { style: "font-weight:600;", text: sys.label }),
          el("div", { style: "font-size:11px;color:var(--text-secondary);", text: sys.system_id || "" }),
        ]),
        el("td", {}, [envPill(sys.environment)]),
        el("td", { text: sys.run_at ? formatRunTime(sys.run_at) : "—" }),
        el("td", {}, [sys.posture ? posturePills(sys.posture) : el("span", { class: "no-run-tag", text: "Not assessed yet" })]),
      ])
    );
  }
  app.appendChild(table);
}

// ---------------------------------------------------------------- system view

async function openSystem(key, push = true) {
  const sys = state.systems.find((s) => s.key === key);
  if (!sys) {
    goHome(push);
    return;
  }
  const switchingSystem = state.currentKey !== key;
  state.currentKey = key;
  state.view = "system";
  if (switchingSystem) {
    state.viewingRunName = null;
    state.historyRuns = null;
    state.compareSelected = [];
    state.aiInsights = null;
    state.aiQaHistory = [];
  }
  setBreadcrumb(sys.label);
  renderSidenav();
  let loadError = null;
  try {
    state.currentResult = await api(`/api/systems/${key}/latest`);
  } catch (err) {
    state.currentResult = null;
    loadError = err.message;
  }
  renderSystemView(loadError);
  if (push) history.pushState({ view: "system", key }, "", `#system/${encodeURIComponent(key)}`);
}

function renderSystemView(loadError) {
  const sys = state.systems.find((s) => s.key === state.currentKey);
  app.innerHTML = "";
  app.appendChild(el("h1", { class: "section-title", text: sys.label }));

  if (loadError) {
    app.appendChild(el("p", { class: "error-banner", text: `Could not load the latest run: ${loadError}` }));
  }

  const info = el("div", { class: "info-bar" }, [
    infoItem("Environment", null, envPill(sys.environment)),
    infoItem("SID", sys.system_id),
    infoItem("Client", sys.client),
    infoItem("Host", sys.ashost),
    infoItem("RFC User", sys.user),
    el("div", { class: "spacer" }),
  ]);
  if (state.currentResult) {
    info.appendChild(infoItem("Last Run", formatRunTime(state.currentResult.meta.run_at)));
  }
  info.appendChild(el("button", { class: "btn btn-ghost", onclick: () => openEditSystemModal(sys.key), text: "Edit" }));
  info.appendChild(el("button", { class: "btn btn-primary", onclick: openRunModal, text: "Run Assessment" }));
  app.appendChild(info);

  if (!state.currentResult) {
    app.appendChild(el("p", { class: "empty-state", text: "No runs yet for this system. Click “Run Assessment” to start one." }));
    return;
  }

  app.appendChild(viewTiles());
  renderResults(state.currentResult);
}

function infoItem(k, v, node) {
  const valueEl = node ? el("div", { class: "v" }, [node]) : el("div", { class: "v", text: v });
  return el("div", { class: "info-item" }, [el("div", { class: "k", text: k }), valueEl]);
}

function formatRunTime(iso) {
  if (!iso) return "";
  return iso.replace("T", " ");
}

// ---------------------------------------------------------------- results rendering

// KPI tiles are computed server-side from each check's own `risk_tiles` declaration (see
// checks/base.py's RiskTile) and arrive on `result.kpi_tiles` -- this file has no per-check
// knowledge of what counts as a risk, so a new check with a risk_tiles entry shows up here
// automatically, with nothing to update in this file.

const VIEW_MODE_LABELS = { descriptive: "Descriptive", visual: "Visual", logs: "Logs", history: "History", ai: "AI Insights" };

const VIEW_MODE_ICONS = {
  descriptive: '<svg width="20" height="20" viewBox="0 0 24 24"><path fill="currentColor" d="M4 5h16v2H4V5Zm0 6h16v2H4v-2Zm0 6h10v2H4v-2Z"/></svg>',
  visual: '<svg width="20" height="20" viewBox="0 0 24 24"><path fill="currentColor" d="M4 19V9h3v10H4Zm6.5 0V4h3v15h-3ZM17 19v-7h3v7h-3Z"/></svg>',
  logs: '<svg width="20" height="20" viewBox="0 0 24 24"><path fill="currentColor" d="M4 4h16v16H4V4Zm2 4v2h2V8H6Zm4 0v2h8V8h-8ZM6 12v2h2v-2H6Zm4 0v2h8v-2h-8Zm-4 4v2h2v-2H6Zm4 0v2h5v-2h-5Z"/></svg>',
  history: '<svg width="20" height="20" viewBox="0 0 24 24"><path fill="currentColor" d="M13 3a9 9 0 1 0 8.94 10H19.9A7 7 0 1 1 13 5c1.66 0 3.14.57 4.34 1.5L14 9.5V3h7L17.5 8A8.96 8.96 0 0 0 13 3Zm-1 5h1.5v4.7l3.6 2.1-.75 1.3L12 13.5V8Z"/></svg>',
  ai: '<svg width="20" height="20" viewBox="0 0 24 24"><path fill="currentColor" d="M12 2 9.9 8.1 4 10l5.9 1.9L12 18l2.1-6.1L20 10l-5.9-1.9L12 2ZM5 15l-1 2.5L1.5 18.5 4 19.5 5 22l1-2.5 2.5-1L6 17.5 5 15Zm14-1-1.2 3-3 1.2 3 1.2L19 22l1.2-3 3-1.2-3-1.2L19 14Z"/></svg>',
};

// The system page's primary navigation -- Descriptive/Visual/Logs/History/AI Insights are
// clickable tiles, not a small top-right toggle, so they read as first-class destinations
// inside a system rather than a secondary control (see renderSystemView's placement, right
// under the info bar).
function viewTiles() {
  const wrap = el("div", { class: "view-tile-row" });
  for (const mode of Object.keys(VIEW_MODE_LABELS)) {
    const iconSpan = el("span", { class: "view-tile-icon" });
    iconSpan.innerHTML = VIEW_MODE_ICONS[mode];
    wrap.appendChild(
      el(
        "div",
        {
          class: `view-tile ${state.dashboardView === mode ? "active" : ""}`,
          onclick: () => {
            if (state.dashboardView === mode) return;
            state.dashboardView = mode;
            localStorage.setItem("ssat_dashboard_view", mode);
            renderSystemView(); // cheap re-render -- state.currentResult is already cached, no re-fetch
          },
        },
        [iconSpan, el("span", { text: VIEW_MODE_LABELS[mode] })]
      )
    );
  }
  return wrap;
}

function backToLatestRun() {
  state.viewingRunName = null;
  openSystem(state.currentKey, false);
}

function renderViewingRunBanner() {
  if (!state.viewingRunName) return;
  const runMeta = state.historyRuns && state.historyRuns.find((r) => r.run_name === state.viewingRunName);
  app.appendChild(
    el("div", { class: "viewing-run-banner" }, [
      el("span", { text: `Browsing a historical run${runMeta ? ` from ${formatRunTime(runMeta.run_at)}` : ""}, not the latest.` }),
      el("button", { class: "link-btn", text: "Back to latest run", onclick: backToLatestRun }),
    ])
  );
}

function renderResults(result) {
  renderViewingRunBanner();

  app.appendChild(
    el("div", { class: "findings-intro" }, [
      el("h2", {
        class: "findings-title",
        text: state.dashboardView === "history" ? "Run History" : state.dashboardView === "ai" ? "AI Insights" : "Major Findings",
      }),
      el("p", {
        class: "findings-subtitle",
        text:
          state.dashboardView === "history"
            ? "Every completed assessment run recorded for this system. Select two runs to compare what changed between them."
            : state.dashboardView === "ai"
            ? "An executive summary, remediation guidance, and free-form Q&A generated by AI from this run's aggregate results. " +
              "No individual usernames or record-level data are ever sent -- only counts, categories, and the narrative findings " +
              "already shown in the Descriptive tab."
            : "The headline risk indicators from this assessment -- each figure below points to a specific, actionable gap. " +
              "This is a summary, not the full picture: every check performed is broken out by domain further down this page, " +
              "and in the downloadable Excel report.",
      }),
    ])
  );

  if (state.dashboardView === "history") {
    renderHistoryBody();
    return;
  }
  if (state.dashboardView === "ai") {
    renderAiInsightsBody(result);
    return;
  }

  // Already computed and severity-sorted server-side (see server.py's _kpi_tiles).
  const tiles = result.kpi_tiles || [];

  if (state.dashboardView === "visual") {
    renderVisualBody(result, tiles);
  } else if (state.dashboardView === "logs") {
    renderLogsBody(result, tiles);
  } else {
    renderDescriptiveBody(result, tiles);
  }

  const downloadRow = el("div", { class: "download-row" });
  downloadRow.appendChild(
    el("button", {
      class: "btn btn-ghost",
      text: "Download Excel Report",
      onclick: () => window.open(`/api/runs/${result.run_name}/download`, "_blank"),
    })
  );
  downloadRow.appendChild(
    el("button", {
      class: "btn btn-ghost",
      text: "Download Assessment Criteria",
      title: "What each check verifies, explained for a consultant and for the business -- same for every system, not tied to this run",
      onclick: () => window.open("/api/criteria/download", "_blank"),
    })
  );
  app.appendChild(downloadRow);
}

function renderDescriptiveBody(result, tiles) {
  if (tiles.length) {
    const kpiRow = el("div", { class: "kpi-row fade-in-up" });
    tiles.forEach((t, i) => {
      const check = result.checks.find((c) => c.check_id === t.check_id);
      kpiRow.appendChild(buildRiskCard(t, check, i));
    });
    app.appendChild(kpiRow);
  } else {
    app.appendChild(el("p", { class: "empty-state", text: "No checks in this run crossed a risk threshold worth flagging here -- see the full results by domain below." }));
  }

  const domains = [...new Set(result.checks.map((c) => c.domain))];
  for (const domain of domains) {
    app.appendChild(el("div", { class: "domain-heading fade-in-up", text: domain }));
    const table = el("table", { class: "checks-table fade-in-up" });
    table.appendChild(
      el("tr", {}, [
        el("th", { text: "Check" }),
        el("th", { text: "Question" }),
        el("th", { text: "Scope" }),
        el("th", { text: "Key Finding" }),
        el("th", { text: "Records" }),
      ])
    );
    for (const c of result.checks.filter((c) => c.domain === domain)) {
      table.appendChild(
        el("tr", {}, [
          el("td", {}, [statusIcon(c.error_count === 0), el("span", { class: "check-id", text: c.check_id })]),
          el("td", { text: c.question }),
          el("td", {}, [el("span", { class: "scope-tag", text: c.scope || "" })]),
          el("td", { text: c.key_finding }),
          el("td", { text: String(c.record_count) }),
        ])
      );
    }
    app.appendChild(table);
  }
}

// ---------------------------------------------------------------- visual dashboard

// Counts up from 0 to `target` over `duration`ms (ease-out cubic). Non-numeric targets
// (e.g. "Open", "Disabled" from the string-valued KPI tiles) are just set directly --
// there's nothing to animate. Respects prefers-reduced-motion by jumping straight to the
// end value, matching the CSS-side reduced-motion guard in style.css.
const _REDUCE_MOTION = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function animateNumber(node, target, duration = 800) {
  if (typeof target !== "number" || !isFinite(target) || _REDUCE_MOTION) {
    node.textContent = typeof target === "number" ? target.toLocaleString() : String(target);
    return;
  }
  const startTime = performance.now();
  function tick(now) {
    const progress = Math.min(1, (now - startTime) / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    node.textContent = Math.round(target * eased).toLocaleString();
    if (progress < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// A bar "chart" built from plain HTML/CSS (no chart library, no SVG path math) -- consistent
// with the rest of this app's zero-dependency approach. Every bar carries a direct text label
// (name + value), so identity is never conveyed by color alone. Bars grow in from 0 and their
// value counts up on mount, rather than appearing instantly at full width.
function vizBarSection(title, subtitle, items, defaultColor, emptyText) {
  const section = el("div", { class: "viz-section" });
  section.appendChild(el("h3", { class: "viz-section-title", text: title }));
  if (subtitle) section.appendChild(el("p", { class: "viz-section-sub", text: subtitle }));
  if (!items.length) {
    section.appendChild(el("p", { class: "empty-state", text: emptyText || "No data available for this chart." }));
    return section;
  }
  const maxValue = Math.max(1, ...items.map((i) => i.value));
  const pending = [];
  for (const item of items) {
    const pct = Math.max(2, Math.round((item.value / maxValue) * 100));
    const fill = el("div", {
      class: "viz-bar-fill",
      style: `width:0%; background:${item.color || defaultColor}`,
      title: `${item.label}: ${item.value}`,
    });
    const valueNode = el("div", { class: "viz-bar-value", text: "0" });
    pending.push({ fill, pct, valueNode, value: item.value });
    section.appendChild(
      el("div", { class: "viz-bar-row" }, [
        el("div", { class: "viz-bar-label", text: item.label, title: item.label }),
        el("div", { class: "viz-bar-track" }, [fill]),
        valueNode,
      ])
    );
  }
  requestAnimationFrame(() => {
    for (const p of pending) {
      p.fill.style.width = `${p.pct}%`;
      animateNumber(p.valueNode, p.value, 700);
    }
  });
  return section;
}

// Builds a multi-segment donut ring as raw SVG markup (circle strokes with dasharray/
// dashoffset -- the standard technique). Only numbers we compute go into the markup; no
// system/user-supplied text is ever interpolated into it, so string-building it directly
// (rather than via the DOM) carries no injection risk here.
function _donutSvg(segments, total) {
  const size = 148, r = 52, sw = 17, cx = 74, cy = 74, gap = 3;
  const c = 2 * Math.PI * r;
  let acc = 0;
  let circles = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--border)" stroke-width="${sw}"></circle>`;
  for (const seg of segments) {
    if (!seg.value) continue;
    const frac = seg.value / total;
    const len = Math.max(0, frac * c - gap);
    circles +=
      `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${seg.color}" stroke-width="${sw}" ` +
      `stroke-linecap="round" stroke-dasharray="${len.toFixed(2)} ${(c - len).toFixed(2)}" ` +
      `stroke-dashoffset="${(-acc).toFixed(2)}" transform="rotate(-90 ${cx} ${cy})"></circle>`;
    acc += frac * c;
  }
  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">${circles}</svg>`;
}

function vizDonutCard(title, subtitle, segments, centerLabel) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  const card = el("div", { class: "viz-donut-card" });
  card.appendChild(el("h3", { class: "viz-section-title", text: title }));
  if (subtitle) card.appendChild(el("p", { class: "viz-section-sub", text: subtitle }));

  const wrap = el("div", { class: "viz-donut-wrap", html: _donutSvg(segments, total || 1) });
  const centerValue = el("div", { class: "viz-donut-value", text: "0" });
  wrap.appendChild(el("div", { class: "viz-donut-center" }, [centerValue, el("div", { class: "viz-donut-label", text: centerLabel })]));
  requestAnimationFrame(() => animateNumber(centerValue, total, 800));

  const legend = el("div", { class: "viz-legend" });
  for (const seg of segments) {
    legend.appendChild(
      el("div", { class: "viz-legend-item" }, [
        el("span", { class: "viz-legend-swatch", style: `background:${seg.color}` }),
        el("span", { text: seg.label }),
        el("span", { class: "n", text: String(seg.value) }),
      ])
    );
  }

  const row = el("div", { class: "viz-donut-row" }, [wrap, legend]);
  card.appendChild(row);
  return card;
}

function severityIcon(cls) {
  const span = el("span", { class: "viz-stat-icon" });
  const paths = {
    crit: '<path fill="currentColor" d="M12 2 1 21h22L12 2Zm-1 6h2v7h-2V8Zm0 9h2v2h-2v-2Z"/>',
    warn: '<path fill="currentColor" d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm-1 5h2v6h-2V7Zm0 8h2v2h-2v-2Z"/>',
    good: '<path fill="currentColor" d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm-1.2 14.6-4-4 1.4-1.4 2.6 2.6 5.6-5.6 1.4 1.4-7 7Z"/>',
  };
  span.innerHTML = `<svg viewBox="0 0 24 24" width="24" height="24">${paths[cls] || paths.good}</svg>`;
  return span;
}

// Whether a check's own RFC/HTTP collection succeeded (not whether it found a clean result --
// see severityIcon for that axis). A checkmark for "ran cleanly", a cross for "hit a collection
// error" -- replaces a bare color dot so status doesn't rely on color alone.
function statusIcon(ok) {
  const span = el("span", { class: `status-icon ${ok ? "ok" : "err"}` });
  const check = '<path fill="currentColor" d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm-1.2 14.6-4-4 1.4-1.4 2.6 2.6 5.6-5.6 1.4 1.4-7 7Z"/>';
  const cross =
    '<path fill="currentColor" d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm3.5 13.1-1.4 1.4L12 13.4l-2.1 2.1-1.4-1.4L10.6 12 8.5 9.9l1.4-1.4L12 10.6l2.1-2.1 1.4 1.4L13.4 12l2.1 2.1Z"/>';
  span.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16">${ok ? check : cross}</svg>`;
  return span;
}

// Populates and opens the shared risk-indicator detail popup (#riskDetailBackdrop in
// index.html) for one KPI tile -- the check it came from, its full assessment question, and
// the same narrative key-finding sentence shown in the Descriptive view's domain tables.
function openRiskDetail(tile, check) {
  document.getElementById("riskDetailTitle").textContent = `${tile.label}: ${tile.value}`;
  const body = document.getElementById("riskDetailBody");
  body.innerHTML = "";
  if (check) {
    body.appendChild(el("dt", { text: "Check" }));
    body.appendChild(el("dd", { text: `${check.check_id} -- ${check.question}` }));
    body.appendChild(el("dt", { text: "Key finding" }));
    body.appendChild(el("dd", { text: check.key_finding }));
    body.appendChild(el("dt", { text: "Domain" }));
    body.appendChild(el("dd", { text: check.scope ? `${check.domain} (${check.scope})` : check.domain }));
  } else {
    body.appendChild(el("dd", { text: "No further detail available for this check." }));
  }
  openModal("riskDetailBackdrop");
}

// One risk-indicator tile, shared verbatim by the Descriptive KPI row and the Visual tab's Top
// Risk Indicators grid -- same fixed 176x176 Fiori-tile footprint as the Home page's .tile (so
// every card in a row lines up regardless of label length), same priority rank badge (`rank` is
// 0-based; the server already sorts `tiles` by severity then magnitude -- see server.py's
// _kpi_tiles), same animated count-up, and clicking (or Enter/Space when focused) opens the same
// popup with the underlying check's question, domain, and full narrative key finding.
function buildRiskCard(tile, check, rank) {
  const valueNode = el("div", { class: "viz-stat-value", text: "0" });
  const card = el(
    "div",
    {
      class: `viz-stat-card ${tile.cls}`,
      style: `animation-delay:${rank * 50}ms`,
      tabindex: "0",
      role: "button",
      "aria-label": `${tile.label}: ${tile.value}. Click for details.`,
    },
    [
      el("span", { class: "viz-stat-rank", text: `#${rank + 1}` }),
      severityIcon(tile.cls),
      el("div", {}, [valueNode, el("div", { class: "viz-stat-label", text: tile.label })]),
    ]
  );
  card.addEventListener("click", () => openRiskDetail(tile, check));
  card.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openRiskDetail(tile, check);
    }
  });
  requestAnimationFrame(() => animateNumber(valueNode, tile.value, 800));
  return card;
}

function vizRiskCards(tiles, result) {
  const section = el("div", { class: "viz-section" });
  section.appendChild(el("h3", { class: "viz-section-title", text: "Top Risk Indicators" }));
  if (!tiles.length) {
    section.appendChild(el("p", { class: "empty-state", text: "No checks in this run crossed a risk threshold worth flagging here." }));
    return section;
  }
  const grid = el("div", { class: "viz-card-grid" });
  tiles.forEach((t, i) => {
    const check = result.checks.find((c) => c.check_id === t.check_id);
    grid.appendChild(buildRiskCard(t, check, i));
  });
  section.appendChild(grid);
  return section;
}

// Two donut gauges side by side: security posture (every check bucketed into the severity
// it actually triggered) and data-collection health (did the RFC/HTTP calls behind each
// check succeed at all). Deliberately kept as two separate rings rather than one -- a
// collection error is an operational fact, not a security severity, so folding it into the
// posture ring would misstate it as a finding.
function vizPostureDonuts(result, tiles) {
  const critIds = new Set(tiles.filter((t) => t.cls === "crit").map((t) => t.check_id));
  const warnIds = new Set(tiles.filter((t) => t.cls === "warn").map((t) => t.check_id));
  let critical = 0, warning = 0, clean = 0;
  for (const c of result.checks) {
    if (critIds.has(c.check_id)) critical++;
    else if (warnIds.has(c.check_id)) warning++;
    else clean++;
  }
  const postureCard = vizDonutCard(
    "Assessment Posture",
    "Every check in this run, bucketed by the most severe finding it triggered.",
    [
      { label: "Critical", value: critical, color: "var(--critical)" },
      { label: "Warning", value: warning, color: "var(--warning)" },
      { label: "Clean", value: clean, color: "var(--good)" },
    ],
    "checks run"
  );

  const total = result.checks.length;
  const errored = result.checks.filter((c) => c.error_count > 0).length;
  const healthCard = vizDonutCard(
    "Data Collection Health",
    "Whether each check's RFC/HTTP calls actually succeeded -- separate from what they found.",
    [
      { label: "Collected cleanly", value: total - errored, color: "var(--good)" },
      { label: "Hit a collection error", value: errored, color: "var(--text-secondary)" },
    ],
    "checks total"
  );
  if (errored > 0) {
    healthCard.appendChild(
      el("p", { class: "viz-donut-note", text: `${errored} check(s) couldn't fully collect data -- see the Descriptive view for details.` })
    );
  }

  return el("div", { class: "viz-donut-grid" }, [postureCard, healthCard]);
}

function vizDomainChart(result) {
  const totals = {};
  for (const c of result.checks) {
    totals[c.domain] = (totals[c.domain] || 0) + c.record_count;
  }
  const items = Object.entries(totals)
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value);
  return vizBarSection(
    "Records Reviewed by Domain",
    "Total data points collected per assessment domain in this run -- a rough proxy for how much ground each area covers.",
    items,
    "var(--accent)"
  );
}

function vizUserTypeChart(result) {
  const lan005 = result.checks.find((c) => c.check_id === "LAN-005");
  const byType = lan005 && lan005.summary.by_user_type;
  if (!byType) return null;

  const order = ["dialog", "system", "communication", "service", "reference"];
  const palette = ["var(--viz-cat-1)", "var(--viz-cat-2)", "var(--viz-cat-3)", "var(--viz-cat-4)"];
  const keys = [...order.filter((k) => byType[k] !== undefined), ...Object.keys(byType).filter((k) => !order.includes(k))];
  const items = keys.map((k, i) => ({
    label: k.charAt(0).toUpperCase() + k.slice(1),
    value: byType[k],
    color: palette[i % palette.length],
  }));

  return vizBarSection(
    "User Accounts by Type",
    "From LAN-005 -- dialog accounts are the closest proxy to real named/human users; the rest are technical accounts.",
    items,
    "var(--viz-cat-1)"
  );
}

function renderVisualBody(result, tiles) {
  app.appendChild(vizPostureDonuts(result, tiles));
  app.appendChild(vizRiskCards(tiles, result));
  app.appendChild(vizDomainChart(result));
  const userTypeChart = vizUserTypeChart(result);
  if (userTypeChart) app.appendChild(userTypeChart);
}

// ---------------------------------------------------------------- logs tab

// Renders this run as a syslog-style execution log: `<timestamp> <host> <tag>: <LEVEL> <message>`,
// same shape as a Unix syslog/journald line. Two kinds of line:
//   - One summary line per check, in the order it actually ran (collected_at ascending). INFO =
//     ran cleanly with nothing to flag, WARN = ran cleanly but contributed a KPI tile (see
//     server.py's _kpi_tiles), ERROR = the check's own RFC/HTTP collection failed outright (a
//     data-quality fact, not a security finding).
//   - Underneath each check, a TRACE sub-line for every RFC call it actually made against the
//     backend and what came back -- exactly what the RFC user executed, for troubleshooting when
//     a check errors (see RFCConnector.trace / server.py's rfc_trace). A failed call is still
//     ERROR-colored even though it's nested under a check's line, since it's the concrete cause.
function renderLogsBody(result, tiles) {
  const section = el("div", { class: "viz-section" });
  section.appendChild(el("h3", { class: "viz-section-title", text: "Assessment Log" }));
  section.appendChild(
    el("p", {
      class: "viz-section-sub",
      text: "Raw execution log for this run: one summary line per check, plus every RFC call it made against the backend and what it returned -- for troubleshooting when a check errors.",
    })
  );

  const flaggedIds = new Set(tiles.map((t) => t.check_id));
  const host = (result.meta && result.meta.system_id) || "SYSTEM";
  const runTag = `ssat-assessment[${result.run_name || "run"}]`;
  const trace = result.rfc_trace || [];
  const sorted = [...result.checks].sort((a, b) => (a.collected_at || "").localeCompare(b.collected_at || ""));

  const traceLine = (t, tag) => ({
    ts: t.ts || "",
    tag,
    level: t.ok ? "TRACE" : "ERROR",
    msg: `    ↳ ${t.call}${t.detail ? ` -> ${t.detail}` : ""}`,
    cls: t.ok ? "trace" : "error",
  });

  const lines = [];
  lines.push({
    ts: (result.meta && result.meta.run_at) || sorted[0]?.collected_at || "",
    tag: runTag,
    level: "INFO",
    msg: `Run started -- ${sorted.length} check(s) queued`,
    cls: "meta",
  });
  // RFC calls made outside any check (e.g. connect()'s own RFC_SYSTEM_INFO lookup).
  for (const t of trace.filter((t) => !t.check_id)) {
    lines.push(traceLine(t, `ssat-assessment[connect]`));
  }
  for (const c of sorted) {
    const level = c.error_count > 0 ? "ERROR" : flaggedIds.has(c.check_id) ? "WARN" : "INFO";
    const tag = `ssat-assessment[${c.check_id}]`;
    lines.push({ ts: c.collected_at || "", tag, level, msg: c.key_finding, cls: level.toLowerCase() });
    for (const t of trace.filter((tr) => tr.check_id === c.check_id)) {
      lines.push(traceLine(t, tag));
    }
  }
  const errorCount = sorted.filter((c) => c.error_count > 0).length;
  lines.push({
    ts: sorted[sorted.length - 1]?.collected_at || (result.meta && result.meta.run_at) || "",
    tag: runTag,
    level: "INFO",
    msg: `Run completed -- ${sorted.length} check(s), ${errorCount} error(s), ${tiles.length} finding(s) flagged`,
    cls: "meta",
  });

  const term = el("div", { class: "log-terminal" });
  lines.forEach((line, i) => {
    term.appendChild(
      el("div", { class: `log-line log-${line.cls}`, style: `animation-delay:${Math.min(i, 40) * 12}ms` }, [
        el("span", { class: "log-ts", text: line.ts }),
        el("span", { text: " " }),
        el("span", { class: "log-host", text: host }),
        el("span", { text: " " }),
        el("span", { class: "log-tag", text: line.tag }),
        el("span", { text: ": " }),
        el("span", { class: "log-level", text: line.level.padEnd(6, " ") }),
        el("span", { class: "log-msg", text: line.msg || "" }),
      ])
    );
  });
  section.appendChild(term);
  app.appendChild(section);
}

// ---------------------------------------------------------------- history tab + run comparison

async function viewHistoricalRun(runName) {
  try {
    const summary = await api(`/api/runs/${runName}/summary`);
    state.currentResult = summary;
    state.viewingRunName = runName;
    state.aiInsights = null;
    state.aiQaHistory = [];
    state.dashboardView = "descriptive";
    localStorage.setItem("ssat_dashboard_view", "descriptive");
    renderSystemView();
  } catch (err) {
    alert(err.message);
  }
}

async function renderHistoryBody() {
  const container = el("div", { class: "viz-section", id: "historyContainer" });
  container.appendChild(el("p", { class: "empty-state", text: "Loading run history..." }));
  app.appendChild(container);

  const key = state.currentKey;
  let runs;
  try {
    runs = await api(`/api/systems/${key}/runs`);
  } catch (err) {
    container.innerHTML = "";
    container.appendChild(el("p", { class: "error-banner", text: `Could not load run history: ${err.message}` }));
    return;
  }
  if (state.currentKey !== key || state.dashboardView !== "history") return; // navigated away while loading

  state.historyRuns = runs;
  container.innerHTML = "";

  if (!runs.length) {
    container.appendChild(el("p", { class: "empty-state", text: "No completed runs recorded for this system yet." }));
    return;
  }

  const latestRunName = runs[0].run_name;
  const compareBtn = el("button", {
    class: "btn btn-primary",
    text: "Compare Selected",
    onclick: () => renderComparison(),
  });
  compareBtn.disabled = state.compareSelected.length !== 2; // property, not attribute -- setAttribute("disabled", false) would still disable it
  container.appendChild(
    el("div", { class: "history-toolbar" }, [
      el("p", { class: "hint", text: "Check two runs below to compare what changed between them." }),
      compareBtn,
    ])
  );

  const table = el("table", { class: "history-table" });
  table.appendChild(
    el("tr", {}, [
      el("th", { text: "Compare" }),
      el("th", { text: "Run Date" }),
      el("th", { text: "Critical" }),
      el("th", { text: "Warning" }),
      el("th", { text: "Clean" }),
      el("th", { text: "Errors" }),
      el("th", { text: "Actions" }),
    ])
  );
  for (const run of runs) {
    const isCurrent = state.viewingRunName ? run.run_name === state.viewingRunName : run.run_name === latestRunName;
    const checkbox = el("input", {
      type: "checkbox",
      onchange: (e) => {
        state.compareSelected = state.compareSelected.filter((n) => n !== run.run_name);
        if (e.target.checked) {
          if (state.compareSelected.length >= 2) {
            e.target.checked = false;
            return;
          }
          state.compareSelected.push(run.run_name);
        }
        compareBtn.disabled = state.compareSelected.length !== 2;
        const existingPanel = document.getElementById("comparePanel");
        if (existingPanel) existingPanel.remove();
      },
    });
    checkbox.checked = state.compareSelected.includes(run.run_name);
    table.appendChild(
      el("tr", { class: isCurrent ? "is-current" : "" }, [
        el("td", {}, [checkbox]),
        el("td", { text: formatRunTime(run.run_at) + (isCurrent ? " (viewing)" : "") }),
        el("td", { text: String(run.posture.critical) }),
        el("td", { text: String(run.posture.warning) }),
        el("td", { text: String(run.posture.clean) }),
        el("td", { text: String(run.posture.errored) }),
        el(
          "td",
          {},
          [
            el("div", { class: "history-actions" }, [
              el("button", { class: "btn btn-ghost", text: "View", onclick: () => viewHistoricalRun(run.run_name) }),
              el("button", {
                class: "btn btn-ghost",
                text: "Download",
                onclick: () => window.open(`/api/runs/${run.run_name}/download`, "_blank"),
              }),
            ]),
          ]
        ),
      ])
    );
  }
  container.appendChild(table);

  if (state.compareSelected.length === 2) renderComparison();
}

function deltaCell(a, b, higherIsBad) {
  if (a === null || a === undefined) return el("td", {}, [el("span", { class: "delta-new", text: "New this run" })]);
  if (b === null || b === undefined) return el("td", {}, [el("span", { class: "delta-resolved", text: "Resolved" })]);
  if (typeof a !== "number" || typeof b !== "number") {
    return el("td", { text: a === b ? "No change" : `${a} -> ${b}` });
  }
  const diff = b - a;
  if (diff === 0) return el("td", {}, [el("span", { class: "delta-same", text: "No change" })]);
  const bad = higherIsBad ? diff > 0 : diff < 0;
  const arrow = diff > 0 ? "▲" : "▼";
  return el("td", {}, [el("span", { class: bad ? "delta-up" : "delta-down", text: `${arrow} ${Math.abs(diff)}` })]);
}

function compareRow(label, a, b, higherIsBad) {
  return el("tr", {}, [el("td", { text: label }), el("td", { text: String(a) }), el("td", { text: String(b) }), deltaCell(a, b, higherIsBad)]);
}

async function renderComparison() {
  const existing = document.getElementById("comparePanel");
  if (existing) existing.remove();
  if (state.compareSelected.length !== 2) return;

  // Chronological order (earlier run first) for a natural "before -> after" read.
  const runsMeta = state.compareSelected
    .map((name) => state.historyRuns.find((r) => r.run_name === name))
    .filter(Boolean)
    .sort((a, b) => (a.run_at || "").localeCompare(b.run_at || ""));
  if (runsMeta.length !== 2) return;
  const [runA, runB] = runsMeta;

  let summaryA, summaryB;
  try {
    [summaryA, summaryB] = await Promise.all([
      api(`/api/runs/${runA.run_name}/summary`),
      api(`/api/runs/${runB.run_name}/summary`),
    ]);
  } catch (err) {
    alert(err.message);
    return;
  }
  const container = document.getElementById("historyContainer");
  if (!container) return; // user left the History tab while this was loading

  const panel = el("div", { class: "compare-panel fade-in-up", id: "comparePanel" });
  panel.appendChild(
    el("div", { class: "compare-head" }, [
      el("div", { class: "compare-head-col" }, [el("b", { text: "Run A (earlier)" }), el("span", { text: formatRunTime(runA.run_at) })]),
      el("div", { class: "compare-head-col" }, [el("b", { text: "Run B (later)" }), el("span", { text: formatRunTime(runB.run_at) })]),
    ])
  );

  const postureTable = el("table", { class: "compare-table" });
  postureTable.appendChild(
    el("tr", {}, [el("th", { text: "Posture" }), el("th", { text: "Run A" }), el("th", { text: "Run B" }), el("th", { text: "Change" })])
  );
  for (const [k, label, higherIsBad] of [
    ["critical", "Critical checks", true],
    ["warning", "Warning checks", true],
    ["clean", "Clean checks", false],
    ["errored", "Collection errors", true],
  ]) {
    postureTable.appendChild(compareRow(label, runA.posture[k], runB.posture[k], higherIsBad));
  }
  panel.appendChild(postureTable);

  // Per-indicator comparison, matched by check_id + label (a check can surface more than one tile).
  const indicators = new Map();
  for (const t of summaryA.kpi_tiles || []) indicators.set(`${t.check_id}|${t.label}`, { checkId: t.check_id, label: t.label, a: t.value, b: null });
  for (const t of summaryB.kpi_tiles || []) {
    const k = `${t.check_id}|${t.label}`;
    if (indicators.has(k)) indicators.get(k).b = t.value;
    else indicators.set(k, { checkId: t.check_id, label: t.label, a: null, b: t.value });
  }
  if (indicators.size) {
    panel.appendChild(el("h4", { class: "domain-heading", style: "margin-top:18px;", text: "Risk Indicators" }));
    const indicatorTable = el("table", { class: "compare-table" });
    indicatorTable.appendChild(
      el("tr", {}, [el("th", { text: "Indicator" }), el("th", { text: "Run A" }), el("th", { text: "Run B" }), el("th", { text: "Change" })])
    );
    for (const ind of indicators.values()) {
      indicatorTable.appendChild(
        el("tr", {}, [
          el("td", { text: `${ind.checkId} — ${ind.label}` }),
          el("td", { text: ind.a === null ? "—" : String(ind.a) }),
          el("td", { text: ind.b === null ? "—" : String(ind.b) }),
          deltaCell(ind.a, ind.b, true),
        ])
      );
    }
    panel.appendChild(indicatorTable);
  }

  container.appendChild(panel);
}

// ---------------------------------------------------------------- AI insights tab

// Sends this run's sanitized results (see server.py's ai/ routes -> ai.sanitize
// on the Python side -- no username or record-level data ever crosses this
// boundary) to whichever LLM provider is configured, to produce an executive
// summary, remediation guidance, and answer free-form questions.

async function renderAiInsightsBody(result) {
  const container = el("div", { class: "viz-section", id: "aiInsightsContainer" });
  app.appendChild(container);

  if (state.aiInsights === null) {
    container.appendChild(el("p", { class: "empty-state", text: "Checking for previously generated insights..." }));
    let cached = null;
    try {
      cached = await api(`/api/runs/${result.run_name}/ai/insights`);
    } catch (err) {
      cached = null;
    }
    if (state.dashboardView !== "ai" || !document.getElementById("aiInsightsContainer")) return; // navigated away
    state.aiInsights = cached; // still null if nothing cached yet -- that's a valid "not generated" state
    container.innerHTML = "";
  }

  renderAiSummarySection(container, result.run_name);
  renderAiQaSection(container, result.run_name);
}

function renderAiSummarySection(container, runName) {
  const existing = document.getElementById("aiSummarySection");
  if (existing) existing.remove();
  const section = el("div", { class: "ai-summary-section", id: "aiSummarySection" });

  if (!state.aiInsights) {
    section.appendChild(
      el("p", {
        class: "ai-disclosure",
        text:
          "Generating sends this run's aggregate results (check counts, categories, and existing narrative findings -- " +
          "never individual usernames or row-level data) to the configured AI provider.",
      })
    );
    const btn = el("button", { class: "btn btn-primary", text: "Generate AI Insights" });
    btn.addEventListener("click", () => generateAiInsights(runName, btn));
    section.appendChild(btn);
    container.appendChild(section);
    return;
  }

  section.appendChild(el("h3", { class: "viz-section-title", text: "Executive Summary" }));
  for (const para of state.aiInsights.executive_summary.split(/\n+/).filter(Boolean)) {
    section.appendChild(el("p", { class: "ai-summary-para", text: para }));
  }

  if (state.aiInsights.remediation && state.aiInsights.remediation.length) {
    section.appendChild(el("h3", { class: "viz-section-title", style: "margin-top:24px;", text: "Remediation Guidance" }));
    const list = el("div", { class: "ai-remediation-list" });
    for (const item of state.aiInsights.remediation) {
      const steps = el("ul", { class: "ai-remediation-steps" });
      for (const step of item.steps || []) steps.appendChild(el("li", { text: step }));
      list.appendChild(
        el("div", { class: "ai-remediation-item" }, [
          el("div", { class: "ai-remediation-head" }, [
            el("span", { class: "check-id", text: item.check_id }),
            el("span", { text: item.label }),
          ]),
          el("p", { class: "ai-remediation-recommendation", text: item.recommendation }),
          steps,
        ])
      );
    }
    section.appendChild(list);
  }

  const footer = el("div", { class: "ai-summary-footer" }, [
    el("span", {
      class: "hint",
      text: `Generated ${formatRunTime(state.aiInsights.generated_at)}${
        state.aiInsights.provider ? ` via ${state.aiInsights.provider}` : ""
      }`,
    }),
  ]);
  const regenBtn = el("button", { class: "btn btn-ghost", text: "Regenerate" });
  regenBtn.addEventListener("click", () => generateAiInsights(runName, regenBtn, true));
  footer.appendChild(regenBtn);
  footer.appendChild(
    el("button", {
      class: "btn btn-ghost",
      text: "Download PDF Report",
      title: "Cover page, executive summary, risk heat map, detailed findings, and a remediation roadmap -- an AI-assisted draft, review before sending to a client.",
      onclick: () => window.open(`/api/runs/${runName}/report/pdf`, "_blank"),
    })
  );
  section.appendChild(footer);

  container.appendChild(section);
}

async function generateAiInsights(runName, btn, force = false) {
  btn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = "Generating...";
  try {
    state.aiInsights = await api(`/api/runs/${runName}/ai/generate`, {
      method: "POST",
      body: JSON.stringify({ force }),
    });
    const container = document.getElementById("aiInsightsContainer");
    if (container) renderAiSummarySection(container, runName);
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

function renderAiQaSection(container, runName) {
  const section = el("div", { class: "ai-qa-section" });
  section.appendChild(el("h3", { class: "viz-section-title", style: "margin-top:24px;", text: "Ask a Question" }));
  section.appendChild(
    el("p", {
      class: "viz-section-sub",
      text: "Ask about this run's results in plain language. Answers are grounded only in this run's aggregate data.",
    })
  );

  const thread = el("div", { class: "ai-qa-thread" });
  for (const turn of state.aiQaHistory) {
    thread.appendChild(el("div", { class: "ai-qa-turn ai-qa-question", text: turn.question }));
    thread.appendChild(el("div", { class: "ai-qa-turn ai-qa-answer", text: turn.answer }));
  }
  section.appendChild(thread);

  const input = el("input", { type: "text", placeholder: "e.g. What are the most urgent findings to fix first?" });
  const askBtn = el("button", { class: "btn btn-primary", text: "Ask" });
  const form = el("form", { class: "ai-qa-form" }, [input, askBtn]);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    askAiQuestion(runName, question, input, askBtn, thread);
  });
  section.appendChild(form);

  container.appendChild(section);
}

async function askAiQuestion(runName, question, input, btn, thread) {
  input.disabled = true;
  btn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = "Asking...";
  try {
    const { answer } = await api(`/api/runs/${runName}/ai/ask`, {
      method: "POST",
      body: JSON.stringify({ question, history: state.aiQaHistory }),
    });
    state.aiQaHistory.push({ question, answer });
    thread.appendChild(el("div", { class: "ai-qa-turn ai-qa-question", text: question }));
    thread.appendChild(el("div", { class: "ai-qa-turn ai-qa-answer", text: answer }));
    input.value = "";
  } catch (err) {
    alert(err.message);
  } finally {
    input.disabled = false;
    btn.disabled = false;
    btn.textContent = originalText;
    input.focus();
  }
}

// ---------------------------------------------------------------- add system modal

function openModal(id) {
  const backdrop = document.getElementById(id);
  backdrop.hidden = false;
  requestAnimationFrame(() => backdrop.classList.add("open"));
}
function closeModal(id) {
  const backdrop = document.getElementById(id);
  backdrop.classList.remove("open");
  setTimeout(() => {
    backdrop.hidden = true;
  }, 160); // matches the .modal-backdrop opacity transition duration
}
document.querySelectorAll("[data-close]").forEach((btn) => {
  btn.addEventListener("click", () => closeModal(btn.dataset.close));
});
// Clicking the dimmed backdrop itself (not the modal card) closes it too, like any popup.
document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) closeModal(backdrop.id);
  });
});

function openAddSystemModal(presetEnv) {
  state.editingKey = null;
  document.getElementById("systemModalTitle").textContent = "Add System";
  const form = document.getElementById("addSystemForm");
  form.reset();
  document.getElementById("odataFields").hidden = true;
  if (presetEnv) form.environment.value = presetEnv;
  openModal("addSystemBackdrop");
}

function openEditSystemModal(key) {
  const sys = state.systems.find((s) => s.key === key);
  if (!sys) return;
  state.editingKey = key;
  document.getElementById("systemModalTitle").textContent = "Edit System";
  const form = document.getElementById("addSystemForm");
  form.reset();
  form.label.value = sys.label || "";
  form.environment.value = sys.environment || "";
  form.system_id.value = sys.system_id || "";
  form.client.value = sys.client || "";
  form.ashost.value = sys.ashost || "";
  form.sysnr.value = sys.sysnr || "";
  form.user.value = sys.user || "";
  form.lang.value = sys.lang || "EN";
  const hasOdata = !!(sys.odata && sys.odata.base_url);
  document.getElementById("odataToggle").checked = hasOdata;
  document.getElementById("odataFields").hidden = !hasOdata;
  if (hasOdata) {
    form.odata_base_url.value = sys.odata.base_url || "";
    form.odata_client.value = sys.odata.client || "";
    form.odata_verify_ssl.checked = !!sys.odata.verify_ssl;
  }
  openModal("addSystemBackdrop");
}

document.getElementById("testConnBtn").addEventListener("click", async () => {
  const form = document.getElementById("addSystemForm");
  const hint = document.getElementById("testConnHint");
  const passwordInput = document.getElementById("testConnPassword");
  const btn = document.getElementById("testConnBtn");

  const ashost = form.ashost.value.trim();
  const sysnr = form.sysnr.value.trim();
  const client = form.client.value.trim();
  const user = form.user.value.trim();
  const enteredSid = form.system_id.value.trim();
  const password = passwordInput.value;

  const missing = [];
  if (!ashost) missing.push("Application Server Host");
  if (!sysnr) missing.push("System Number");
  if (!client) missing.push("Client");
  if (!user) missing.push("RFC User");
  if (!password) missing.push("RFC password (above)");
  if (missing.length) {
    hint.className = "hint hint-error";
    hint.textContent = `Fill in first: ${missing.join(", ")}.`;
    return;
  }

  btn.disabled = true;
  btn.textContent = "Testing...";
  hint.className = "hint";
  hint.textContent = "";
  try {
    const result = await api("/api/systems/test-connection", {
      method: "POST",
      body: JSON.stringify({ ashost, sysnr, client, user, password, lang: form.lang.value || "EN" }),
    });
    const details = [result.host, result.sap_release && `SAP ${result.sap_release}`, result.db_system]
      .filter(Boolean)
      .join(" · ");
    if (!enteredSid) {
      form.system_id.value = result.system_id;
      hint.className = "hint hint-ok";
      hint.textContent = `Connected -- System ID auto-filled: ${result.system_id} (${details}).`;
    } else if (enteredSid.toUpperCase() !== (result.system_id || "").toUpperCase()) {
      hint.className = "hint hint-error";
      hint.textContent = `Connected, but the system reports SID "${result.system_id}", not "${enteredSid}" -- check System ID (${details}).`;
    } else {
      hint.className = "hint hint-ok";
      hint.textContent = `Connected -- System ID confirmed: ${result.system_id} (${details}).`;
    }
  } catch (err) {
    hint.className = "hint hint-error";
    hint.textContent = err.message;
  } finally {
    passwordInput.value = "";
    btn.disabled = false;
    btn.textContent = "Test Connection";
  }
});

document.getElementById("odataToggle").addEventListener("change", (e) => {
  document.getElementById("odataFields").hidden = !e.target.checked;
});

document.getElementById("detectGatewayBtn").addEventListener("click", async () => {
  const form = document.getElementById("addSystemForm");
  const hint = document.getElementById("detectGatewayHint");
  const passwordInput = document.getElementById("detectGatewayPassword");
  const btn = document.getElementById("detectGatewayBtn");

  const ashost = form.ashost.value.trim();
  const sysnr = form.sysnr.value.trim();
  const client = form.client.value.trim();
  const user = form.user.value.trim();
  const password = passwordInput.value;

  const missing = [];
  if (!ashost) missing.push("Application Server Host");
  if (!sysnr) missing.push("System Number");
  if (!client) missing.push("Client");
  if (!user) missing.push("RFC User");
  if (!password) missing.push("RFC password (above)");
  if (missing.length) {
    hint.className = "hint hint-error";
    hint.textContent = `Fill in first: ${missing.join(", ")}.`;
    return;
  }

  btn.disabled = true;
  btn.textContent = "Detecting...";
  hint.className = "hint";
  hint.textContent = "";
  try {
    const result = await api("/api/systems/detect-gateway", {
      method: "POST",
      body: JSON.stringify({ ashost, sysnr, client, user, password, lang: form.lang.value || "EN" }),
    });
    form.odata_base_url.value = result.base_url;
    hint.className = "hint";
    hint.textContent = `Detected ${result.base_url} (from ${result.detected_from}). Still editable if this system sits behind a web dispatcher or load balancer.`;
  } catch (err) {
    hint.className = "hint hint-error";
    hint.textContent = err.message;
  } finally {
    passwordInput.value = "";
    btn.disabled = false;
    btn.textContent = "Detect from System";
  }
});

document.getElementById("addSystemForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {
    label: fd.get("label"),
    environment: fd.get("environment"),
    system_id: fd.get("system_id"),
    client: fd.get("client"),
    ashost: fd.get("ashost"),
    sysnr: fd.get("sysnr"),
    user: fd.get("user"),
    lang: fd.get("lang") || "EN",
  };
  if (document.getElementById("odataToggle").checked) {
    body.odata = {
      base_url: fd.get("odata_base_url"),
      client: fd.get("odata_client") || body.client,
      user: body.user,
      verify_ssl: fd.get("odata_verify_ssl") === "on",
    };
  }
  try {
    if (state.editingKey) {
      await api(`/api/systems/${state.editingKey}`, { method: "PUT", body: JSON.stringify(body) });
    } else {
      await api("/api/systems", { method: "POST", body: JSON.stringify(body) });
    }
    closeModal("addSystemBackdrop");
    await loadSystems();
    renderSidenav();
    if (state.currentKey) {
      renderSystemView();
    } else {
      renderHome();
    }
  } catch (err) {
    alert(err.message);
  }
});

// ---------------------------------------------------------------- run modal + polling

function openRunModal() {
  const sys = state.systems.find((s) => s.key === state.currentKey);
  document.getElementById("runTargetLabel").textContent = `${sys.label} (${sys.system_id}, client ${sys.client}) as ${sys.user}`;
  document.getElementById("runForm").reset();
  document.getElementById("runForm").querySelector("button[type=submit]").disabled = false;
  openModal("runBackdrop");
}

document.getElementById("runForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const password = new FormData(e.target).get("password");
  const submitBtn = e.target.querySelector("button[type=submit]");
  submitBtn.disabled = true;
  const targetKey = state.currentKey;
  try {
    const { job_id } = await api(`/api/systems/${targetKey}/run`, {
      method: "POST",
      body: JSON.stringify({ password }),
    });
    closeModal("runBackdrop");
    submitBtn.disabled = false;
    showRunBanner();
    startPolling(job_id, targetKey);
  } catch (err) {
    alert(err.message);
    submitBtn.disabled = false;
  }
});

// The assessment runs as a non-blocking strip pinned under the shell bar (instead of a
// blocking modal) so the consultant can keep browsing other systems while it runs.
function showRunBanner() {
  const banner = document.getElementById("runBanner");
  banner.hidden = false;
  banner.classList.remove("is-error", "is-warning");
  document.getElementById("runBannerSpinner").hidden = false;
  document.getElementById("runBannerDismiss").hidden = true;
  document.getElementById("runBannerFill").style.width = "0%";
  document.getElementById("runBannerPct").textContent = "0%";
  document.getElementById("runBannerText").textContent = "Starting assessment...";
}

function hideRunBanner() {
  document.getElementById("runBanner").hidden = true;
}

document.getElementById("runBannerDismiss").addEventListener("click", hideRunBanner);

function startPolling(jobId, targetKey) {
  stopPolling();
  state.pollTimer = setInterval(() => pollJob(jobId, targetKey), 1200);
  pollJob(jobId, targetKey);
}

function stopPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
}

async function pollJob(jobId, targetKey) {
  let job;
  try {
    job = await api(`/api/jobs/${jobId}`);
  } catch (err) {
    stopPolling();
    return;
  }
  renderProgress(job);
  if (job.status === "done") {
    stopPolling();
    // The spinner only means "still working" -- once the job is done (with or without an
    // ai_error) it must stop, or a banner reading "complete" next to a still-spinning icon
    // reads as hung/stuck rather than finished.
    document.getElementById("runBannerSpinner").hidden = true;
    document.getElementById("runBanner").classList.toggle("is-warning", Boolean(job.ai_error));
    document.getElementById("runBannerText").textContent = job.ai_error
      ? `${job.system_label} — Assessment complete (AI insights/report couldn't auto-generate: ${job.ai_error})`
      : `${job.system_label} — Assessment complete`;
    document.getElementById("runBannerFill").style.width = "100%";
    document.getElementById("runBannerPct").textContent = "100%";
    if (state.currentKey === targetKey) {
      state.currentResult = job.result_summary;
      state.viewingRunName = null; // a fresh run just landed -- snap back to viewing the latest
      state.historyRuns = null; // stale now that a new run exists; History tab will refetch on next visit
      state.compareSelected = [];
      state.aiInsights = null;
      state.aiQaHistory = [];
      renderSystemView();
    }
    document.getElementById("runBannerDismiss").hidden = false;
    // Self-cleans either way -- the ai_error case just gets more time to be read before it does,
    // rather than sitting there indefinitely waiting for a manual dismiss.
    setTimeout(hideRunBanner, job.ai_error ? 6000 : 1500);
  } else if (job.status === "error") {
    stopPolling();
    const banner = document.getElementById("runBanner");
    document.getElementById("runBannerSpinner").hidden = true;
    banner.classList.add("is-error");
    document.getElementById("runBannerText").textContent = job.error || "Assessment failed.";
    document.getElementById("runBannerFill").style.width = "100%";
    document.getElementById("runBannerPct").textContent = "";
    document.getElementById("runBannerDismiss").hidden = false;
  }
}

function renderProgress(job) {
  const entries = Object.entries(job.progress);
  const total = entries.length;
  const doneCount = entries.filter(([, status]) => status === "done").length;
  const running = entries.find(([, status]) => status === "running");
  const pct = total ? Math.round((doneCount / total) * 100) : 0;
  // job.phase covers the post-check step (AI insights + PDF report generation, see
  // job_runner.py) -- all checks are already done at that point, so the "(n/total)" count
  // no longer applies.
  if (job.phase) {
    document.getElementById("runBannerText").textContent = `${job.system_label} — ${job.phase}`;
    document.getElementById("runBannerFill").style.width = "100%";
    document.getElementById("runBannerPct").textContent = "100%";
    return;
  }
  const label = running ? `Running ${running[0]}` : doneCount >= total && total > 0 ? "Finalizing report" : "Preparing";
  document.getElementById("runBannerText").textContent = `${job.system_label} — ${label} (${doneCount}/${total})`;
  document.getElementById("runBannerFill").style.width = `${pct}%`;
  document.getElementById("runBannerPct").textContent = `${pct}%`;
}

// ---------------------------------------------------------------- boot

(async function init() {
  await loadSystems();
  history.replaceState({ view: "home" }, "", "#home");
  renderSidenav();
  renderHome();
})();
