// World Intelligence dashboard — vanilla JS (port of the React version).
// Served as a static asset; not processed by any templating engine.

"use strict";

const CATEGORIES = ["news", "conflict", "disaster", "weather", "markets", "energy", "tech", "supplychain", "health"];
const CATEGORY_META = {
  news: { label: "News", color: "#4f8cff" },
  conflict: { label: "Conflict", color: "#ff4d4f" },
  disaster: { label: "Disasters", color: "#ff7a45" },
  weather: { label: "Weather", color: "#13c2c2" },
  markets: { label: "Markets", color: "#b37feb" },
  energy: { label: "Energy", color: "#faad14" },
  tech: { label: "Tech & Cyber", color: "#40c057" },
  supplychain: { label: "Supply Chain", color: "#f06595" },
  health: { label: "Health", color: "#36cfc9" },
};
const SEVERITY_COLORS = ["#5cdbd3", "#8b93a7", "#95de64", "#ffc53d", "#ff7a45", "#ff4d4f"];

// Used to auto-classify watchlist terms as country vs keyword.
const COUNTRY_TERMS = new Set(["afghanistan","algeria","argentina","australia","austria","bangladesh","belarus","belgium","bolivia","brazil","bulgaria","cambodia","cameroon","canada","chile","china","colombia","congo","croatia","cuba","cyprus","denmark","ecuador","egypt","ethiopia","finland","france","germany","ghana","greece","hungary","iceland","india","indonesia","iran","iraq","ireland","israel","italy","japan","jordan","kazakhstan","kenya","kuwait","laos","lebanon","libya","malaysia","mali","mexico","moldova","mongolia","morocco","myanmar","nepal","netherlands","new zealand","nicaragua","niger","nigeria","north korea","norway","oman","pakistan","panama","paraguay","peru","philippines","poland","portugal","qatar","romania","russia","rwanda","saudi arabia","serbia","singapore","slovakia","slovenia","somalia","south africa","south korea","spain","sri lanka","sudan","sweden","switzerland","syria","taiwan","thailand","tunisia","turkey","uganda","ukraine","united states","america","venezuela","vietnam","yemen","zambia","zimbabwe"]);

const TABS = [
  { id: "briefing", label: "AI Briefing" },
  { id: "live", label: "Live Feed" },
  { id: "map", label: "World Map" },
  { id: "disasters", label: "Disasters" },
  { id: "supplychain", label: "Supply Chain" },
  { id: "markets", label: "Markets" },
  { id: "watch", label: "Watch Live" },
  { id: "search", label: "Search" },
];

const state = {
  tab: "live",
  stats: null,
  statsFailed: false,
  feed: { events: [], total: 0, offset: 0, cats: new Set(), majorOnly: false, trends: { words: [], bigrams: [] }, spikes: [], trendQuery: null, updated: null, loading: true, error: false },
  briefing: { briefing: null, summary: null, stories: [], watch: null, activity: null, wl: { countries: [], keywords: [], min_severity: 3 }, updated: null, wlSaved: null },
  notify: { enabled: false, firstRun: localStorage.getItem("wiSeen") === null, seenIds: new Set(JSON.parse(localStorage.getItem("wiSeen") || "[]")) },
  map: { events: [], hidden: new Set(), map: null, layer: null, built: false, updated: null },
  disasters: { events: [], updated: null },
  supply: { indicators: [], events: [], updated: null },
  markets: { indicators: [], events: [], updated: null },
  stress: null,
  streams: [],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const $ = (sel) => document.querySelector(sel);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") node.className = v;
    else if (k === "style") node.style.cssText = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2).toLowerCase(), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function highlightHtml(text, q) {
  const t = escapeHtml(text);
  const qq = String(q || "").toLowerCase();
  const idx = t.toLowerCase().indexOf(qq);
  if (!qq || idx < 0) return t;
  const len = escapeHtml(q).length;
  return t.slice(0, idx) + "<mark>" + t.slice(idx, idx + len) + "</mark>" + t.slice(idx + len);
}

function relativeTime(ts) {
  if (!ts) return "—";
  const diff = Date.now() - ts;
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return m + "m ago";
  const h = Math.floor(m / 60);
  if (h < 24) return h + "h ago";
  return Math.floor(h / 24) + "d ago";
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(res.status + " for " + path);
  return res.json();
}

function apiPut(path, body) {
  return api(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function apiDel(path) {
  return api(path, { method: "DELETE" });
}

function sevColor(s) {
  return SEVERITY_COLORS[Math.max(0, Math.min(5, s))] || "#8b93a7";
}

function fmtValue(v) {
  const n = Number(v);
  if (!isFinite(n)) return "—";
  if (n >= 1000) return n.toFixed(0);
  if (n >= 10) return n.toFixed(2);
  return String(n.toFixed(4)).replace(/0+$/, "").replace(/\.$/, "");
}

// ---------------------------------------------------------------------------
// Event cards
// ---------------------------------------------------------------------------

function eventCard(e, highlight) {
  const meta = CATEGORY_META[e.category] || { label: e.category, color: "#8b93a7" };
  const card = el("div", { class: "card", title: "Click for details" });
  card.addEventListener("click", (ev) => { if (!ev.target.closest("a")) openEventModal(e); });
  card.appendChild(el("div", { class: "sev", style: "background:" + sevColor(e.severity) }));
  if (e.image) {
    const img = el("img", { class: "thumb", src: e.image, alt: "", loading: "lazy" });
    img.addEventListener("error", () => { img.style.display = "none"; });
    card.appendChild(img);
  }
  const body = el("div", { style: "flex:1;min-width:0" });
  const metaRow = el("div", { class: "meta" });
  metaRow.appendChild(el("span", { class: "cat", style: "background:" + meta.color + "22;color:" + meta.color }, meta.label));
  metaRow.appendChild(el("span", { class: "src" }, e.source));
  if (e.geo && e.geo.place) metaRow.appendChild(el("span", { class: "place" }, "📍 " + e.geo.place));
  metaRow.appendChild(el("span", { class: "time" }, relativeTime(e.published)));
  body.appendChild(metaRow);
  const titleDiv = el("div", { class: "title" });
  if (e.url) {
    titleDiv.appendChild(el("a", { href: e.url, target: "_blank", rel: "noreferrer" }));
    titleDiv.firstChild.innerHTML = highlight ? highlightHtml(e.title, highlight) : escapeHtml(e.title);
  } else {
    titleDiv.innerHTML = highlight ? highlightHtml(e.title, highlight) : escapeHtml(e.title);
  }
  body.appendChild(titleDiv);
  if (e.summary) body.appendChild(el("div", { class: "summary" }, e.summary));
  card.appendChild(body);
  return card;
}

function feedCards(events, highlight) {
  const wrap = el("div", { class: "feed" });
  for (const e of events) wrap.appendChild(eventCard(e, highlight));
  return wrap;
}

function statCard(label, key) {
  const c = el("div", { class: "stat-card", "data-key": key });
  c.appendChild(el("div", { class: "n", id: "stat-" + key }, "—"));
  c.appendChild(el("div", { class: "l" }, label));
  return c;
}

/// Refreshes the Live-tab KPI values in place (called after stats/feed load).
function updateStatCards() {
  const set = (key, val, color) => {
    const n = document.getElementById("stat-" + key);
    if (n) { n.textContent = val; if (color) n.style.color = color; }
  };
  if (state.stats) {
    set("total", state.stats.total.toLocaleString());
    const srcs = state.stats.sources || [];
    const ok = srcs.filter((x) => x.last_ok).length;
    set("sources", ok + "/" + srcs.length, ok === srcs.length ? "var(--ok)" : ok > 0 ? "var(--warn)" : "var(--err)");
  }
  const breaking = state.feed.events.filter((e) => e.severity >= 4).length;
  set("breaking", String(breaking), breaking ? "var(--err)" : "");
  if (state.stress) {
    const s = state.stress;
    const color = s.level === "severe" ? "var(--err)" : s.level === "high" ? "#ff7a45" : s.level === "elevated" ? "var(--warn)" : "var(--ok)";
    set("stress", s.score + "/100", color);
  }
}

// ---------------------------------------------------------------------------
// Sparkline
// ---------------------------------------------------------------------------

function sparkline(data, color) {
  if (!data || data.length < 2) return null;
  const w = 280, h = 48;
  const vals = data.map((d) => d.value);
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  const step = w / (data.length - 1);
  let dpath = "", lastX = 0, lastY = 0;
  data.forEach((d, i) => {
    const x = i * step;
    const y = h - 4 - ((d.value - min) / span) * (h - 8);
    dpath += (i === 0 ? "M" : "L") + x.toFixed(1) + "," + y.toFixed(1) + " ";
    lastX = x; lastY = y;
  });
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "spark");
  svg.setAttribute("width", w);
  svg.setAttribute("height", h);
  svg.setAttribute("viewBox", "0 0 " + w + " " + h);
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", dpath.trim());
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", color);
  path.setAttribute("stroke-width", "1.8");
  svg.appendChild(path);
  const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  dot.setAttribute("cx", lastX.toFixed(1));
  dot.setAttribute("cy", lastY.toFixed(1));
  dot.setAttribute("r", "2.6");
  dot.setAttribute("fill", color);
  svg.appendChild(dot);
  return svg;
}

// ---------------------------------------------------------------------------
// Tab switching
// ---------------------------------------------------------------------------

function buildTabs() {
  const nav = $("#tabs");
  nav.innerHTML = "";
  for (const t of TABS) {
    const btn = el("button", { "data-tab": t.id }, t.label);
    btn.addEventListener("click", () => switchTab(t.id));
    nav.appendChild(btn);
  }
}

function switchTab(id) {
  state.tab = id;
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === id));
  if (location.hash !== "#" + id) history.replaceState(null, "", "#" + id);
  // destroy map when leaving so the DOM doesn't hold a stale instance
  if (state.map.built && id !== "map") {
    try { state.map.map.remove(); } catch (e) {}
    state.map.map = null;
    state.map.layer = null;
    state.map.built = false;
  }
  $("#main").innerHTML = "";
  refreshTab(id);
}

function refreshTab(id) {
  if (id === "briefing") loadBriefing();
  else if (id === "live") loadFeed();
  else if (id === "map") { if (state.map.built) loadMap(); else renderMapShell(); }
  else if (id === "disasters") loadDisasters();
  else if (id === "supplychain") loadSupply();
  else if (id === "markets") loadMarkets();
  else if (id === "watch") loadWatch();
  else if (id === "search") renderSearch();
}

// ---------------------------------------------------------------------------
// Stats footer + health modal
// ---------------------------------------------------------------------------

async function loadStats() {
  try {
    state.stats = await api("/api/stats");
    state.statsFailed = false;
  } catch (e) {
    state.stats = null;
    state.statsFailed = true;
  }
  renderFooter();
  try {
    state.stress = await api("/api/stress?hours=24");
  } catch (e) {}
  renderStressChip();
  updateStatCards();
}

function renderStressChip() {
  let chip = document.getElementById("stressChip");
  if (!chip) {
    chip = el("button", { id: "stressChip", class: "chip", title: "World Stress Index — click to open the AI Briefing" });
    document.querySelector("header").appendChild(chip);
  }
  const s = state.stress;
  if (!s) { chip.textContent = "🌡 —"; chip.style.background = ""; chip.style.color = ""; return; }
  chip.textContent = "🌡 " + s.score + "/100 · " + s.level;
  chip.style.background = s.level === "severe" ? "#ff4d4f" : s.level === "high" ? "#ff7a45" : s.level === "elevated" ? "#faad14" : "#40c057";
  chip.style.color = "#fff";
  chip.onclick = () => switchTab("briefing");
}

function renderFooter() {
  const footer = $("#footer");
  footer.innerHTML = "";
  footer.appendChild(el("span", {}, "World Intelligence · personal dashboard"));
  if (state.statsFailed) {
    footer.appendChild(el("span", { class: "err" }, "⚠ server unreachable — start it with ./start.sh (or start.bat) and refresh"));
    return;
  }
  const st = state.stats;
  if (!st) return;
  const errs = (st.sources || []).filter((s) => !s.last_ok);
  const last = (st.sources || []).reduce((a, s) => Math.max(a, s.last_run || 0), 0);
  const btn = el("button", { class: "status-link" },
    el("span", { class: errs.length ? "err" : "ok" }, errs.length ? errs.length + " source(s) down" : "all sources healthy"),
    el("span", {}, st.total.toLocaleString() + " events"),
    el("span", {}, "updated " + (last ? relativeTime(last) : "—")));
  btn.addEventListener("click", () => {
    $("#healthBackdrop").style.display = "flex";
    renderHealthTable();
  });
  footer.appendChild(btn);
}

function renderHealthTable() {
  const st = state.stats;
  const box = $("#healthTable");
  box.innerHTML = "";
  if (!st) return;
  const rows = (st.sources || []).slice().sort((a, b) => Number(a.last_ok) - Number(b.last_ok));
  const table = el("table", { class: "health-table" });
  const thead = el("thead");
  const trh = el("tr");
  for (const h of ["Source", "Status", "Last run", "Events", "Error"]) trh.appendChild(el("th", {}, h));
  thead.appendChild(trh);
  table.appendChild(thead);
  const tbody = el("tbody");
  for (const s of rows) {
    const status = s.last_ok ? "ok" : s.stale ? "stale" : "down";
    const tr = el("tr");
    tr.appendChild(el("td", {}, s.source));
    tr.appendChild(el("td", {}, el("span", { class: s.last_ok ? "ok" : "err" }, status)));
    tr.appendChild(el("td", {}, s.last_run ? relativeTime(s.last_run) : "never"));
    tr.appendChild(el("td", {}, String(s.count || 0)));
    tr.appendChild(el("td", { class: "muted" }, s.last_error || ""));
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  box.appendChild(table);
}

// ---------------------------------------------------------------------------
// Live Feed tab
// ---------------------------------------------------------------------------

async function loadFeed() {
  const s = state.feed;
  try {
    const params = new URLSearchParams();
    params.set("limit", "100");
    params.set("offset", "0");
    if (s.majorOnly) params.set("minSeverity", "3");
    const d = await api("/api/events?" + params);
    s.events = d.events;
    s.total = d.total;
    s.offset = d.events.length;
    s.updated = Date.now();
    s.loading = false;
    s.error = false;
    seedSeenIds(s.events);
    scanForAlerts(s.events);
    renderFeed();
  } catch (e) {
    s.loading = false;
    s.error = true;
    renderFeed();
  }
}

function loadMoreFeed() {
  const s = state.feed;
  const params = new URLSearchParams();
  params.set("limit", "100");
  params.set("offset", String(s.offset));
  if (s.majorOnly) params.set("minSeverity", "3");
  api("/api/events?" + params).then((d) => {
    const seen = new Set(s.events.map((e) => e.id));
    const fresh = d.events.filter((e) => !seen.has(e.id));
    s.events = s.events.concat(fresh);
    s.offset += fresh.length;
    renderFeed();
  }).catch(() => {});
}

async function loadTrends() {
  try {
    state.feed.trends = await api("/api/trends");
    renderFeed();
  } catch (e) {}
  // Surge detection — terms spiking 2.5×+ above their hourly baseline.
  try {
    const d = await api("/api/ai/trends");
    state.feed.spikes = d.spikes || [];
    renderFeed();
  } catch (e) {}
}

function renderFeed() {
  if (state.tab !== "live") return; // don't clobber another tab's content
  const s = state.feed;
  const main = $("#main");
  main.innerHTML = "";

  // KPI row — updated in place by updateStatCards() (no re-render needed).
  main.appendChild(el("div", { class: "stat-cards" },
    statCard("Events tracked", "total"),
    statCard("Sources healthy", "sources"),
    statCard("Breaking now", "breaking"),
    statCard("World stress", "stress")));
  updateStatCards();

  const breaking = s.events.filter((e) => e.severity >= 4).slice(0, 6);
  if (breaking.length) {
    const b = el("div", { class: "breaking" },
      el("span", { class: "breaking-label" }, "⚠ Breaking"),
      el("div", { class: "breaking-list" }, breaking.map((e) =>
        el("span", { class: "breaking-item" }, e.url ? el("a", { href: e.url, target: "_blank", rel: "noreferrer" }, e.title) : e.title))));
    main.appendChild(b);
  }

  const controls = el("div", { class: "controls" });
  const chips = el("div", { class: "chips" });
  const allBtn = el("button", { class: "chip" + (s.cats.size === 0 ? " on" : "") }, "All");
  allBtn.addEventListener("click", () => { s.cats = new Set(); renderFeed(); });
  chips.appendChild(allBtn);
  for (const c of CATEGORIES) {
    const on = s.cats.has(c);
    const btn = el("button", {
      class: "chip" + (on ? " on" : ""),
      style: on ? "background:" + CATEGORY_META[c].color : "",
    }, CATEGORY_META[c].label);
    btn.addEventListener("click", () => {
      const next = new Set(s.cats);
      if (next.has(c)) next.delete(c); else next.add(c);
      s.cats = next;
      renderFeed();
    });
    chips.appendChild(btn);
  }
  controls.appendChild(chips);
  const majBtn = el("button", {
    class: "chip" + (s.majorOnly ? " on" : ""),
    style: s.majorOnly ? "background:#ff4d4f" : "",
  }, "🔥 Major only");
  majBtn.addEventListener("click", () => { s.majorOnly = !s.majorOnly; s.loading = true; loadFeed(); });
  controls.appendChild(majBtn);
  if (s.updated) controls.appendChild(el("span", { class: "status" }, "updated " + relativeTime(s.updated)));
  if (s.error && s.events.length > 0) {
    controls.appendChild(el("span", { class: "status err" }, "⚠ server unreachable — showing last loaded data"));
  }
  main.appendChild(controls);

  const spikes = (s.spikes || []).filter((x) => x.count >= 4).slice(0, 4);
  if (spikes.length) {
    const sur = el("div", { class: "surge" },
      el("span", { class: "surge-label" }, "🚨 Surge"),
      el("span", { class: "surge-note" }, "terms spiking right now — click to filter"));
    const list = el("div", { class: "surge-list" });
    for (const x of spikes) {
      const btn = el("button", {
        class: "chip" + (s.trendQuery === x.term ? " on" : ""),
        title: x.count + " mentions this hour vs " + Math.round(x.baseline) + " baseline",
      }, x.term + " ×" + Math.round(x.ratio));
      btn.addEventListener("click", () => {
        s.trendQuery = s.trendQuery === x.term ? null : x.term;
        renderFeed();
      });
      list.appendChild(btn);
    }
    sur.appendChild(list);
    main.appendChild(sur);
  }

  if (s.trends.words && s.trends.words.length) {
    const t = el("div", { class: "trends" }, el("span", { class: "trends-label" }, "Trending"));
    for (const tr of s.trends.words.slice(0, 10)) {
      const btn = el("button", { class: "chip" + (s.trendQuery === tr.term ? " on" : "") }, tr.term);
      btn.addEventListener("click", () => {
        s.trendQuery = s.trendQuery === tr.term ? null : tr.term;
        renderFeed();
      });
      t.appendChild(btn);
    }
    main.appendChild(t);
  }

  if (s.loading) main.appendChild(el("div", { class: "empty" }, "Loading…"));

  let list = s.cats.size === 0 ? s.events : s.events.filter((e) => s.cats.has(e.category));
  if (s.trendQuery) {
    const q = s.trendQuery.toLowerCase();
    list = list.filter((e) => e.title.toLowerCase().includes(q));
  }
  main.appendChild(feedCards(list));
  if (!s.loading && list.length === 0) {
    main.appendChild(el("div", { class: "empty" },
      s.error ? "Can't reach the server — start it with ./start.sh (or start.bat), then refresh." : "No events match — try clearing filters."));
  }

  if (list.length < s.total) {
    const btn = el("button", { class: "chip", style: "padding:8px 18px" }, "Load more (" + (s.total - list.length) + " remaining)");
    btn.addEventListener("click", loadMoreFeed);
    main.appendChild(el("div", { style: "text-align:center;margin-top:14px" }, btn));
  }
}

// ---------------------------------------------------------------------------
// AI Briefing tab
// ---------------------------------------------------------------------------

async function loadBriefing() {
  const b = state.briefing;
  try {
    const [br, su, st, wa, act, wl, stress] = await Promise.all([
      api("/api/ai/briefing"),
      api("/api/ai/summary"),
      api("/api/ai/stories?limit=12"),
      api("/api/ai/watch"),
      api("/api/activity?hours=24"),
      api("/api/watchlist"),
      api("/api/stress?hours=24"),
    ]);
    b.briefing = br;
    b.summary = su;
    b.stories = st.stories;
    b.watch = wa;
    b.activity = act;
    b.wl = wl;
    b.stress = stress;
    b.updated = Date.now();
    renderBriefing();
  } catch (e) {}
}

function renderBriefing() {
  if (state.tab !== "briefing") return;
  const b = state.briefing;
  const main = $("#main");
  main.innerHTML = "";
  if (!b.briefing) {
    main.appendChild(el("div", { class: "empty" }, "The AI is reading the news…"));
    return;
  }

  const controls = el("div", { class: "controls" },
    el("span", { class: "status" }, "AI briefing · generated " + relativeTime(b.briefing.generated) + " · runs locally on your machine"),
    b.updated ? el("span", { class: "status" }, "refreshed " + relativeTime(b.updated)) : null);
  main.appendChild(controls);

  const head = el("div", { class: "panel", style: "margin-bottom:14px;border-color:#33415c" });
  head.appendChild(el("div", { class: "meta" }, el("span", { class: "cat", style: "background:#4f8cff22;color:#4f8cff" }, "AI Headline")));
  head.appendChild(el("h2", { style: "margin:8px 0 0" }, b.briefing.headline));
  main.appendChild(head);
  main.appendChild(renderStressPanel());

  if (b.summary) {
    const panel = el("div", { class: "panel", style: "margin-bottom:14px" });
    panel.appendChild(el("div", { class: "meta" }, el("span", { class: "cat", style: "background:#40c05722;color:#40c057" }, "World Summary")));
    panel.appendChild(el("p", { style: "line-height:1.55;margin:10px 0" }, b.summary.opening));
    const grid = el("div", { class: "grid2" });
    for (const r of b.summary.regions) {
      const box = el("div", { class: "indicator" });
      const top = el("div", { class: "top" });
      top.appendChild(el("span", { class: "name" }, "🌍 " + r.name));
      top.appendChild(el("span", { class: "val" }, String(r.count)));
      box.appendChild(top);
      for (const t of r.top) {
        box.appendChild(el("div", { class: "summary", style: "margin-top:3px" },
          t.url ? el("a", { href: t.url, target: "_blank", rel: "noreferrer" }, t.title) : t.title));
      }
      grid.appendChild(box);
    }
    panel.appendChild(grid);
    const cats = el("div", { class: "controls", style: "margin-top:12px;margin-bottom:0" });
    for (const c of b.summary.categories) {
      cats.appendChild(el("span", {
        class: "chip on",
        style: "background:" + (CATEGORY_META[c.category] ? CATEGORY_META[c.category].color : "#8b93a7") + ";cursor:default",
      }, (CATEGORY_META[c.category] ? CATEGORY_META[c.category].label : c.category) + ": " + c.count));
    }
    panel.appendChild(cats);
    main.appendChild(panel);
  }

  main.appendChild(renderActivity());
  main.appendChild(renderWatchlistPanel());

  for (const sec of b.briefing.sections) {
    const wrap = el("div", { style: "margin-bottom:14px" });
    wrap.appendChild(el("h3", { style: "margin:4px 0 8px;color:#8b93a7;font-size:13px;text-transform:uppercase;letter-spacing:0.6px" }, sec.title));
    const feed = el("div", { class: "feed" });
    sec.items.forEach((it, i) => {
      const card = el("div", { class: "card" });
      card.appendChild(el("div", { class: "sev", style: "background:" + sevColor(it.severity) }));
      const body = el("div", { style: "flex:1" });
      const td = el("div", { class: "title" });
      if (it.url) td.appendChild(el("a", { href: it.url, target: "_blank", rel: "noreferrer" }, it.title));
      else td.appendChild(el("span", {}, it.title));
      body.appendChild(td);
      if (it.detail) body.appendChild(el("div", { class: "summary" }, it.detail));
      card.appendChild(body);
      feed.appendChild(card);
    });
    wrap.appendChild(feed);
    main.appendChild(wrap);
  }

  if (b.watch && b.watch.alerts && b.watch.alerts.length) {
    const wrap = el("div", { style: "margin-bottom:14px" });
    wrap.appendChild(el("h3", { style: "margin:4px 0 8px;color:#8b93a7;font-size:13px;text-transform:uppercase;letter-spacing:0.6px" }, "🎯 Watchlist hits (your interests)"));
    const feed = el("div", { class: "feed" });
    for (const a of b.watch.alerts) {
      const card = el("div", { class: "card" });
      card.appendChild(el("div", { class: "sev", style: "background:" + sevColor(a.event.severity) }));
      const body = el("div", { style: "flex:1" });
      const metaRow = el("div", { class: "meta" }, el("span", { class: "src" }, a.event.source));
      for (const m of a.matched) metaRow.appendChild(el("span", { class: "cat", style: "background:#faad1422;color:#faad14" }, m));
      body.appendChild(metaRow);
      const td = el("div", { class: "title" });
      if (a.event.url) td.appendChild(el("a", { href: a.event.url, target: "_blank", rel: "noreferrer" }, a.event.title));
      else td.appendChild(el("span", {}, a.event.title));
      body.appendChild(td);
      card.appendChild(body);
      feed.appendChild(card);
    }
    wrap.appendChild(feed);
    main.appendChild(wrap);
  }

  if (b.stories && b.stories.length) {
    const wrap = el("div", {});
    wrap.appendChild(el("h3", { style: "margin:4px 0 8px;color:#8b93a7;font-size:13px;text-transform:uppercase;letter-spacing:0.6px" }, "Story clusters (" + b.stories.length + ")"));
    const grid = el("div", { class: "grid2" });
    for (const s of b.stories) {
      const box = el("div", { class: "indicator", style: "cursor:pointer" });
      box.appendChild(el("div", { class: "top" }, el("span", { class: "name" }, s.title)));
      box.appendChild(el("div", { class: "summary", style: "margin-top:4px" },
        s.count + " update(s) · " + s.sources.length + " source(s) · severity " + s.severity + "/5" + (s.momentum > 0.3 ? " · 📈 accelerating" : "") + " · click for timeline"));
      box.appendChild(el("div", { class: "summary", style: "color:#8b93a7;font-size:11px" }, s.sources.slice(0, 6).join(", ")));
      const tl = el("div", { style: "display:none;margin-top:8px;border-top:1px solid var(--border);padding-top:6px" });
      for (const t of (s.timeline || [])) {
        tl.appendChild(el("div", { style: "margin-top:4px;font-size:12px" },
          el("span", { class: "status", style: "margin-right:6px" }, relativeTime(t.published)),
          t.url ? el("a", { href: t.url, target: "_blank", rel: "noreferrer" }, t.title) : el("span", {}, t.title),
          el("span", { class: "status", style: "margin-left:6px" }, "· " + t.source)));
      }
      box.appendChild(tl);
      box.addEventListener("click", () => { tl.style.display = tl.style.display === "none" ? "block" : "none"; });
      grid.appendChild(box);
    }
    wrap.appendChild(grid);
    main.appendChild(wrap);
  }
}

// ---------------------------------------------------------------------------
// World Map tab
// ---------------------------------------------------------------------------

function renderMapShell() {
  const main = $("#main");
  main.innerHTML = "";
  const controls = el("div", { class: "controls", id: "mapControls" });
  main.appendChild(controls);
  main.appendChild(el("div", { class: "map-wrap" }, el("div", { id: "mapEl", style: "height:100%" })));
  main.appendChild(el("div", { class: "legend", id: "mapLegend" }));
  state.map.built = true;
  initMap();
  loadMap();
}

function initMap() {
  if (state.map.map) return;
  const node = document.getElementById("mapEl");
  if (!node) return;
  const map = L.map(node, { zoomControl: true, worldCopyJump: true }).setView([20, 0], 2);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  state.map.map = map;
  state.map.layer = L.layerGroup().addTo(map);
  setTimeout(() => map.invalidateSize(), 0);
}

async function loadMap() {
  try {
    const d = await api("/api/events?geo=1&limit=500");
    state.map.events = d.events;
    state.map.updated = Date.now();
    renderMap();
  } catch (e) {}
}

function renderMap() {
  const m = state.map;
  const controls = $("#mapControls");
  if (controls) {
    controls.innerHTML = "";
    controls.appendChild(el("span", { class: "status" }, m.events.filter((e) => !m.hidden.has(e.category)).length + " geo events"));
    const all = el("button", { class: "chip" + (m.hidden.size === 0 ? " on" : ""), style: m.hidden.size === 0 ? "background:#33415c" : "" }, "All");
    all.addEventListener("click", () => { m.hidden = new Set(); renderMap(); });
    controls.appendChild(all);
    for (const c of CATEGORIES) {
      const on = !m.hidden.has(c);
      const btn = el("button", { class: "chip" + (on ? " on" : ""), style: on ? "background:" + CATEGORY_META[c].color : "" }, CATEGORY_META[c].label);
      btn.addEventListener("click", () => {
        const next = new Set(m.hidden);
        if (next.has(c)) next.delete(c); else next.add(c);
        m.hidden = next;
        renderMap();
      });
      controls.appendChild(btn);
    }
  }
  const legend = $("#mapLegend");
  if (legend) {
    legend.innerHTML = "";
    for (const c of CATEGORIES) {
      legend.appendChild(el("span", { class: "legend-item" },
        el("span", { class: "legend-dot", style: "background:" + CATEGORY_META[c].color }), CATEGORY_META[c].label));
    }
    legend.appendChild(el("span", { class: "legend-item" },
      el("span", { class: "legend-dot", style: "background:#8b93a7" }), "size = severity"));
  }
  drawMapPoints();
}

function drawMapPoints() {
  const m = state.map;
  const layer = m.layer;
  if (!layer) return;
  layer.clearLayers();
  for (const e of m.events) {
    if (m.hidden.has(e.category) || !e.geo) continue;
    const color = (CATEGORY_META[e.category] || { color: "#8b93a7" }).color;
    const radius = 5 + e.severity * 2.2;
    const circle = L.circleMarker([e.geo.lat, e.geo.lon], {
      radius: radius,
      color: "#0b0e14",
      weight: 1,
      fillColor: color,
      fillOpacity: 0.75,
    });
    let html = "<b>" + escapeHtml(e.title) + "</b><br/>";
    html += '<span style="color:#8b93a7">' + escapeHtml((CATEGORY_META[e.category] || { label: e.category }).label + " · " + e.source + " · " + relativeTime(e.published)) + "</span>";
    if (e.summary) html += "<br/>" + escapeHtml(e.summary);
    if (e.url) html += '<br/><a href="' + escapeHtml(e.url) + '" target="_blank" rel="noreferrer">Read more →</a>';
    circle.bindPopup(html);
    circle.addTo(layer);
  }
}

// ---------------------------------------------------------------------------
// Disasters tab
// ---------------------------------------------------------------------------

async function loadDisasters() {
  try {
    const [a, b] = await Promise.all([
      api("/api/events?category=disaster&limit=120"),
      api("/api/events?category=weather&limit=60"),
    ]);
    state.disasters.events = a.events.concat(b.events).sort((x, y) => y.published - x.published);
    state.disasters.updated = Date.now();
    renderDisasters();
  } catch (e) {}
}

function renderDisasters() {
  if (state.tab !== "disasters") return;
  const d = state.disasters;
  const main = $("#main");
  main.innerHTML = "";
  const active = d.events.filter((e) => ["eonet", "gdacs", "usgs"].includes(e.source));
  const counts = {};
  for (const e of d.events) counts[e.source] = (counts[e.source] || 0) + 1;
  const cards = el("div", { class: "stat-cards" },
    el("div", { class: "stat-card" }, el("div", { class: "n" }, String(active.length)), el("div", { class: "l" }, "Active alerts")),
    el("div", { class: "stat-card" }, el("div", { class: "n" }, String(counts.eonet || 0)), el("div", { class: "l" }, "NASA EONET")),
    el("div", { class: "stat-card" }, el("div", { class: "n" }, String(counts.usgs || 0)), el("div", { class: "l" }, "Earthquakes (24h)")),
    el("div", { class: "stat-card" }, el("div", { class: "n" }, String(counts.gdacs || 0)), el("div", { class: "l" }, "GDACS alerts")));
  main.appendChild(cards);
  const controls = el("div", { class: "controls" },
    el("span", { class: "status" }, "🔥 includes NASA FIRMS satellite fire detections"),
    d.updated ? el("span", { class: "status" }, "updated " + relativeTime(d.updated)) : null);
  main.appendChild(controls);
  main.appendChild(feedCards(d.events));
}

// ---------------------------------------------------------------------------
// Supply Chain tab
// ---------------------------------------------------------------------------

async function loadSupply() {
  try {
    const [i, e] = await Promise.all([
      api("/api/indicators"),
      api("/api/events?category=supplychain&limit=100"),
    ]);
    state.supply.indicators = i.indicators.filter((x) => x.category === "supplychain");
    state.supply.events = e.events;
    state.supply.updated = Date.now();
    renderSupply();
  } catch (err) {}
}

function renderSupply() {
  if (state.tab !== "supplychain") return;
  const s = state.supply;
  const main = $("#main");
  main.innerHTML = "";
  if (s.indicators.length) {
    const grid = el("div", { class: "grid2", style: "margin-bottom:14px" });
    for (const i of s.indicators) {
      const box = el("div", { class: "indicator" });
      const top = el("div", { class: "top" });
      top.appendChild(el("span", { class: "name" }, i.name));
      top.appendChild(el("span", { class: "val" }, (i.latest_value != null ? i.latest_value.toFixed(2) : "—") + " <small>" + escapeHtml(i.unit || "") + "</small>"));
      box.appendChild(top);
      box.appendChild(el("div", { class: "date" }, "as of " + (i.latest_date || "—")));
      const sp = sparkline((i.history || []).slice(-90), "#f06595");
      if (sp) box.appendChild(sp);
      grid.appendChild(box);
    }
    main.appendChild(grid);
  }
  const controls = el("div", { class: "controls" },
    s.updated ? el("span", { class: "status" }, "updated " + relativeTime(s.updated)) : null);
  main.appendChild(controls);
  main.appendChild(feedCards(s.events));
  if (!s.events.length) {
    main.appendChild(el("div", { class: "empty" },
      "No supply-chain alerts right now. This feed tracks port congestion, freight rates, shipping disruptions and trade news."));
  }
}

// ---------------------------------------------------------------------------
// Markets tab
// ---------------------------------------------------------------------------

async function loadMarkets() {
  try {
    const [i, m, en] = await Promise.all([
      api("/api/indicators"),
      api("/api/events?category=markets&limit=80"),
      api("/api/events?category=energy&limit=60"),
    ]);
    state.markets.indicators = i.indicators.filter((x) => x.category === "markets" || x.category === "energy" || x.category === "money");
    state.markets.events = m.events.concat(en.events).sort((a, b) => b.published - a.published);
    state.markets.updated = Date.now();
    renderMarkets();
  } catch (e) {}
}

function renderMarkets() {
  if (state.tab !== "markets") return;
  const s = state.markets;
  const main = $("#main");
  main.innerHTML = "";
  const grid = el("div", { class: "grid2", style: "margin-bottom:14px" });
  if (s.indicators.length) {
    for (const i of s.indicators) {
      const box = el("div", { class: "indicator" });
      const top = el("div", { class: "top" });
      top.appendChild(el("span", { class: "name" }, i.name));
      top.appendChild(el("span", { class: "val" }, (i.latest_value != null ? i.latest_value.toFixed(2) : "—") + " <small>" + escapeHtml(i.unit || "") + "</small>"));
      box.appendChild(top);
      box.appendChild(el("div", { class: "date" }, "as of " + (i.latest_date || "—")));
      grid.appendChild(box);
    }
  } else {
    grid.appendChild(el("div", { class: "panel" },
      "No FRED data yet — set FRED_API_KEY in backend/.env to get CPI, rates, unemployment and oil prices."));
  }
  main.appendChild(grid);
  const money = s.indicators.filter((x) => x.category === "money");
  if (money.length) {
    main.appendChild(el("h3", { style: "margin:0 0 8px;color:#8b93a7;font-size:13px;text-transform:uppercase;letter-spacing:0.6px" }, "Money — FX & crypto (live, keyless)"));
    const mgrid = el("div", { class: "grid2", style: "margin-bottom:14px" });
    for (const i of money) {
      const box = el("div", { class: "indicator" });
      const top = el("div", { class: "top" });
      top.appendChild(el("span", { class: "name" }, i.name));
      top.appendChild(el("span", { class: "val" }, fmtValue(i.latest_value)));
      box.appendChild(top);
      const hist = (i.history || []).map((p) => ({ value: p.value }));
      const sp = sparkline(hist, String(i.series_id || "").indexOf("CRYPTO") === 0 ? "#b37feb" : "#4f8cff");
      if (sp) box.appendChild(sp);
      box.appendChild(el("div", { class: "date" }, "as of " + (i.latest_date || "—")));
      mgrid.appendChild(box);
    }
    main.appendChild(mgrid);
  }
  const controls = el("div", { class: "controls" },
    s.updated ? el("span", { class: "status" }, "updated " + relativeTime(s.updated)) : null);
  main.appendChild(controls);
  main.appendChild(feedCards(s.events));
}

// ---------------------------------------------------------------------------
// Watch Live tab
// ---------------------------------------------------------------------------

async function loadWatch() {
  try {
    const d = await api("/api/live");
    state.streams = d.streams;
    renderWatch();
  } catch (e) {}
}

function renderWatch() {
  if (state.tab !== "watch") return;
  const main = $("#main");
  main.innerHTML = "";
  main.appendChild(el("p", { class: "status", style: "margin-top:0" },
    "Free official live news streams. Tap play on any channel — streams are embedded directly from YouTube."));
  const grid = el("div", { class: "watch-grid" });
  for (const s of state.streams) {
    const card = el("div", { class: "watch-card" });
    card.appendChild(el("iframe", { src: s.url, title: s.name, allow: "autoplay; encrypted-media; picture-in-picture", allowFullScreen: "", loading: "lazy" }));
    const info = el("div", { class: "info" });
    info.appendChild(el("h3", {}, s.name));
    info.appendChild(el("p", {}, s.note));
    card.appendChild(info);
    grid.appendChild(card);
  }
  main.appendChild(grid);
}

// ---------------------------------------------------------------------------
// Search tab
// ---------------------------------------------------------------------------

function renderSearch(initialValue = "") {
  const main = $("#main");
  main.innerHTML = "";
  const form = el("form", { class: "search-box" });
  const input = el("input", { placeholder: "Search events, headlines, indicators…", autofocus: "" });
  input.value = initialValue;
  const btn = el("button", { class: "chip", type: "submit", style: "color:#fff;background:#2b3a55" }, "Search");
  form.appendChild(input);
  form.appendChild(btn);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    main.appendChild(el("div", { class: "empty" }, "Searching…"));
    try {
      const r = await api("/api/search?q=" + encodeURIComponent(q));
      renderSearchResults(r, q);
    } catch (e) {
      main.appendChild(el("div", { class: "empty" }, "Search failed — is the server running?"));
    }
  });
  main.appendChild(form);
}

function renderSearchResults(r, q) {
  const main = $("#main");
  main.innerHTML = "";
  renderSearch(q); // keep the query in the box
  const box = main;
  if (r.indicators && r.indicators.length) {
    box.appendChild(el("h3", { style: "margin:6px 0" }, "Indicators"));
    const grid = el("div", { class: "grid2", style: "margin-bottom:14px" });
    for (const i of r.indicators) {
      const ind = el("div", { class: "indicator" });
      ind.appendChild(el("span", { class: "name" }, i.name));
      ind.appendChild(el("span", { class: "val", style: "margin-left:8px" }, i.latest_value != null ? i.latest_value.toFixed(2) : "—"));
      grid.appendChild(ind);
    }
    box.appendChild(grid);
  }
  box.appendChild(feedCards(r.events || [], q));
  if ((!r.events || !r.events.length) && (!r.indicators || !r.indicators.length)) {
    box.appendChild(el("div", { class: "empty" }, "No results for “" + q + "”."));
  }
}

// ---------------------------------------------------------------------------
// Activity chart + watchlist editor (Briefing tab)
// ---------------------------------------------------------------------------

function renderStressPanel() {
  const s = state.briefing.stress;
  if (!s) return null;
  const LEVEL_COLOR = { severe: "#ff4d4f", high: "#ff7a45", elevated: "#faad14", calm: "#40c057" };
  const color = LEVEL_COLOR[s.level] || "#4f8cff";
  const panel = el("div", { class: "panel", style: "margin-bottom:14px" });
  panel.appendChild(el("div", { class: "meta" },
    el("span", { class: "cat", style: "background:" + color + "22;color:" + color }, "World Stress Index"),
    el("span", { class: "src" }, "0–100 composite · computed locally from your event data")));
  const row = el("div", { style: "display:flex;align-items:center;gap:16px;margin-top:10px;flex-wrap:wrap" });
  const big = el("div", { style: "text-align:center;min-width:110px" });
  big.appendChild(el("div", { style: "font-size:44px;font-weight:700;line-height:1;color:" + color }, String(s.score)));
  big.appendChild(el("div", { class: "status", style: "text-transform:capitalize;color:" + color }, s.level));
  row.appendChild(big);
  const comps = el("div", { style: "flex:1;min-width:200px" });
  for (const [key, label] of [["pressure", "Event pressure"], ["breaking", "Breaking now"], ["disasters", "Active disasters"], ["volatility", "Market volatility"], ["watchlist", "Watchlist activity"]]) {
    const v = Math.max(0, Math.min(100, s.components[key] || 0));
    const bar = el("div", { style: "display:flex;align-items:center;gap:8px;margin-top:4px" });
    bar.appendChild(el("span", { class: "status", style: "width:130px" }, label));
    const track = el("div", { style: "flex:1;height:6px;background:#222b3d;border-radius:3px" });
    track.appendChild(el("div", { style: "width:" + v + "%;height:100%;background:" + color + ";border-radius:3px" }));
    bar.appendChild(track);
    bar.appendChild(el("span", { class: "status", style: "width:34px;text-align:right" }, v + "%"));
    comps.appendChild(bar);
  }
  row.appendChild(comps);
  panel.appendChild(row);
  if (s.history && s.history.length >= 2) {
    const sp = sparkline(s.history.map((h) => ({ value: h.score })), color);
    const first = s.history[0].score, last = s.history[s.history.length - 1].score;
    const trend = last > first + 5 ? "rising" : last < first - 5 ? "falling" : "steady";
    panel.appendChild(el("div", { style: "margin-top:10px" },
      el("div", { class: "status", style: "margin-bottom:2px" }, "Last " + s.history.length + "h trend — " + trend),
      sp));
  }
  return panel;
}

function openEventModal(ev) {
  const backdrop = $("#eventBackdrop");
  const modal = $("#eventModal");
  const meta = CATEGORY_META[ev.category] || { label: ev.category, color: "#8b93a7" };
  modal.innerHTML = "";
  const head = el("div", { class: "modal-head" },
    el("h3", {}, meta.label + " · severity " + ev.severity + "/5"),
    el("button", { class: "chip", id: "eventClose" }, "Close"));
  modal.appendChild(head);
  const metaRow = el("div", { class: "meta" });
  metaRow.appendChild(el("span", { class: "src" }, ev.source));
  if (ev.geo && ev.geo.place) metaRow.appendChild(el("span", { class: "place" }, "📍 " + ev.geo.place));
  metaRow.appendChild(el("span", { class: "time" }, new Date(ev.published).toLocaleString()));
  modal.appendChild(metaRow);
  const titleDiv = el("div", { class: "title", style: "font-size:17px;margin:8px 0" });
  if (ev.url) titleDiv.appendChild(el("a", { href: ev.url, target: "_blank", rel: "noreferrer" }, ev.title));
  else titleDiv.appendChild(el("span", {}, ev.title));
  modal.appendChild(titleDiv);
  if (ev.summary) modal.appendChild(el("p", { style: "line-height:1.55" }, ev.summary));
  if (ev.image) modal.appendChild(el("img", { src: ev.image, style: "max-width:100%;border-radius:8px;margin-top:8px" }));
  const actions = el("div", { class: "controls", style: "margin-top:12px" });
  if (ev.geo && ev.geo.lat != null && ev.geo.lon != null) {
    actions.appendChild(el("a", { class: "chip", href: "https://maps.google.com/?q=" + ev.geo.lat + "," + ev.geo.lon, target: "_blank", rel: "noreferrer" }, "🗺 View on map"));
  }
  const copyBtn = el("button", { class: "chip" }, "🔗 Copy link");
  copyBtn.addEventListener("click", async () => {
    const url = ev.url || (location.origin + "/#search");
    try {
      await navigator.clipboard.writeText(url);
      copyBtn.textContent = "✓ copied";
    } catch (e) { copyBtn.textContent = "✗ copy failed"; }
    setTimeout(() => { copyBtn.textContent = "🔗 Copy link"; }, 1500);
  });
  actions.appendChild(copyBtn);
  modal.appendChild(actions);
  const relBox = el("div", { id: "relatedBox", style: "margin-top:12px" });
  relBox.appendChild(el("div", { class: "empty" }, "Loading related coverage…"));
  modal.appendChild(relBox);
  backdrop.style.display = "flex";
  api("/api/event/" + encodeURIComponent(ev.id)).then((d) => {
    const box = $("#relatedBox");
    if (!box) return;
    box.innerHTML = "";
    if (!d.cluster || !d.cluster.timeline || !d.cluster.timeline.length) {
      box.appendChild(el("div", { class: "status" }, "No other reports in this story cluster yet."));
      return;
    }
    box.appendChild(el("h4", { style: "margin:0 0 6px;color:#8b93a7;font-size:12px;text-transform:uppercase;letter-spacing:0.5px" }, "Story timeline"));
    for (const t of d.cluster.timeline) {
      box.appendChild(el("div", { style: "margin-top:4px;font-size:12.5px" },
        el("span", { class: "status", style: "margin-right:6px" }, relativeTime(t.published)),
        t.url ? el("a", { href: t.url, target: "_blank", rel: "noreferrer" }, t.title) : el("span", {}, t.title),
        el("span", { class: "status", style: "margin-left:6px" }, "· " + t.source)));
    }
  }).catch(() => {
    const box = $("#relatedBox");
    if (box) { box.innerHTML = ""; box.appendChild(el("div", { class: "status" }, "Couldn't load related coverage.")); }
  });
}

function renderActivity() {
  const act = state.briefing.activity;
  if (!act || !act.buckets || !act.buckets.length) return null;
  const max = Math.max(1, ...act.buckets.map((b) => b.count));
  const panel = el("div", { class: "panel", style: "margin-bottom:14px" });
  panel.appendChild(el("div", { class: "meta" },
    el("span", { class: "cat", style: "background:#4f8cff22;color:#4f8cff" }, "Activity")));
  panel.appendChild(el("p", { style: "margin:8px 0 0;font-size:12.5px;color:#8b93a7" },
    "Events per hour, last " + act.hours + "h — " + act.total.toLocaleString() + " total"));
  const bars = el("div", { style: "display:flex;align-items:flex-end;gap:2px;height:64px;margin-top:10px" });
  for (const b of act.buckets) {
    const h = Math.max(2, Math.round((b.count / max) * 60));
    const bar = el("div", { title: b.count + " events", style: "flex:1;background:#4f8cff55;border-radius:2px 2px 0 0;height:" + h + "px" });
    bar.addEventListener("mouseenter", () => { bar.style.background = "#4f8cff"; });
    bar.addEventListener("mouseleave", () => { bar.style.background = "#4f8cff55"; });
    bars.appendChild(bar);
  }
  panel.appendChild(bars);
  return panel;
}

function renderWatchlistPanel() {
  const b = state.briefing;
  const wl = b.wl;
  const panel = el("div", { class: "panel", style: "margin-bottom:14px" });
  panel.appendChild(el("div", { class: "meta" },
    el("span", { class: "cat", style: "background:#faad1422;color:#faad14" }, "Your watchlist"),
    el("span", { class: "src" }, "drives AI alerts, the watch feed, and push")));

  const termStats = {};
  for (const s of (b.watch && b.watch.term_stats) || []) termStats[s.term] = s.count;
  const row = (label, list, onRemove) => {
    const wrap = el("div", { style: "margin-top:8px" });
    wrap.appendChild(el("span", { class: "trends-label" }, label));
    const chips = el("div", { class: "chips", style: "margin-top:4px" });
    for (const term of list) {
      const n = termStats[term] || 0;
      const chip = el("button", {
        class: "chip on" + (n ? " hot" : ""),
        style: "background:#33415c" + (n ? ";border-color:#ff7a45" : ""),
        title: n ? n + " matching event(s) in the last 24h" : "no matches in the last 24h",
      }, term + " ✕" + (n ? " (" + n + ")" : ""));
      chip.addEventListener("click", () => onRemove(term));
      chips.appendChild(chip);
    }
    if (!list.length) chips.appendChild(el("span", { class: "status" }, "none"));
    wrap.appendChild(chips);
    return wrap;
  };

  panel.appendChild(row("Countries", wl.countries, (t) => { wl.countries = wl.countries.filter((x) => x !== t); renderBriefing(); }));
  panel.appendChild(row("Keywords", wl.keywords, (t) => { wl.keywords = wl.keywords.filter((x) => x !== t); renderBriefing(); }));

  const addForm = el("form", { class: "search-box", style: "margin-top:10px" });
  const input = el("input", { placeholder: "Add a country or keyword (e.g. japan, chip shortage)…" });
  const addBtn = el("button", { class: "chip", type: "submit", style: "color:#fff;background:#2b3a55" }, "Add");
  addForm.appendChild(input);
  addForm.appendChild(addBtn);
  addForm.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const v = input.value.trim().toLowerCase();
    if (!v) return;
    if (COUNTRY_TERMS.has(v)) { if (!wl.countries.includes(v)) wl.countries.push(v); }
    else if (!wl.keywords.includes(v)) wl.keywords.push(v);
    input.value = "";
    renderBriefing();
  });
  panel.appendChild(addForm);

  const sevRow = el("div", { class: "controls", style: "margin-top:8px;margin-bottom:0" });
  sevRow.appendChild(el("span", { class: "trends-label" }, "Alert threshold:"));
  for (const s of [3, 4, 5]) {
    const btn = el("button", { class: "chip" + (wl.min_severity === s ? " on" : ""), style: wl.min_severity === s ? "background:#faad14" : "" }, s + "+");
    btn.addEventListener("click", () => { wl.min_severity = s; renderBriefing(); });
    sevRow.appendChild(btn);
  }
  const saveBtn = el("button", { class: "chip", style: "color:#fff;background:#40c057" }, "Save");
  saveBtn.addEventListener("click", async () => {
    b.wlSaved = "saving…";
    renderBriefing();
    try {
      await apiPut("/api/watchlist", wl);
      b.wlSaved = "✓ saved — the AI and watch feed pick it up on the next run";
    } catch (e) {
      b.wlSaved = "✗ save failed — is the server running?";
    }
    renderBriefing();
  });
  const resetBtn = el("button", { class: "chip" }, "Reset to defaults");
  resetBtn.addEventListener("click", async () => {
    try {
      b.wl = await apiDel("/api/watchlist");
      b.wlSaved = "✓ reset to defaults";
    } catch (e) {}
    renderBriefing();
  });
  sevRow.appendChild(saveBtn);
  sevRow.appendChild(resetBtn);
  if (b.wlSaved) sevRow.appendChild(el("span", { class: "status" }, b.wlSaved));
  panel.appendChild(sevRow);
  return panel;
}

// ---------------------------------------------------------------------------
// Browser alerts for major events
// ---------------------------------------------------------------------------

function initNotifications() {
  const bell = el("button", { class: "chip", title: "Browser alerts for major events" }, "🔔 Alerts");
  const update = () => {
    bell.textContent = state.notify.enabled ? "🔔 On" : "🔔 Alerts";
    bell.style.background = state.notify.enabled ? "#40c057" : "";
  };
  bell.addEventListener("click", async () => {
    if (!("Notification" in window)) { bell.textContent = "🔕 unsupported"; return; }
    if (Notification.permission === "granted") {
      state.notify.enabled = !state.notify.enabled;
      update();
    } else {
      const p = await Notification.requestPermission();
      if (p === "granted") { state.notify.enabled = true; update(); }
    }
  });
  document.querySelector("header").appendChild(bell);
}

function seedSeenIds(events) {
  // First-ever visit: don't alert for everything already in the feed.
  const n = state.notify;
  if (!n.firstRun) return;
  for (const e of events) { if (e.severity >= 4) n.seenIds.add(e.id); }
  n.firstRun = false;
  localStorage.setItem("wiSeen", JSON.stringify([...n.seenIds]));
}

function scanForAlerts(events) {
  const n = state.notify;
  if (!("Notification" in window) || Notification.permission !== "granted" || !n.enabled) return;
  let changed = false;
  for (const e of events) {
    if (e.severity < 4 || n.seenIds.has(e.id)) continue;
    n.seenIds.add(e.id);
    changed = true;
    const label = (CATEGORY_META[e.category] || { label: e.category }).label.toUpperCase();
    const note = new Notification("🌍 " + label, { body: e.title, tag: e.id });
    note.onclick = () => { if (e.url) window.open(e.url, "_blank"); };
  }
  if (changed) {
    const list = [...n.seenIds];
    if (list.length > 300) n.seenIds = new Set(list.slice(-300));
    localStorage.setItem("wiSeen", JSON.stringify([...n.seenIds]));
  }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

let demoTimer = null;
const DEMO_ORDER = ["briefing", "live", "map", "disasters", "markets", "supplychain"];

function initDemoMode() {
  const btn = el("button", { id: "demoBtn", class: "chip", title: "Auto-cycle through the main tabs for presentations" }, "▶ Present");
  const bar = el("div", { id: "demoBar" });
  document.body.appendChild(bar);
  btn.addEventListener("click", () => {
    if (demoTimer) {
      clearInterval(demoTimer);
      demoTimer = null;
      document.body.classList.remove("demo");
      btn.textContent = "▶ Present";
      return;
    }
    document.body.classList.add("demo");
    btn.textContent = "⏹ Stop";
    let i = DEMO_ORDER.indexOf(state.tab);
    if (i < 0) i = 0;
    demoTimer = setInterval(() => {
      i = (i + 1) % DEMO_ORDER.length;
      switchTab(DEMO_ORDER[i]);
    }, 8000);
  });
  document.querySelector("header").appendChild(btn);
}

function init() {
  buildTabs();
  initNotifications();
  renderStressChip();
  initDemoMode();
  renderFooter();
  $("#healthClose").addEventListener("click", () => { $("#healthBackdrop").style.display = "none"; });
  $("#healthBackdrop").addEventListener("click", (e) => {
    if (e.target === $("#healthBackdrop")) $("#healthBackdrop").style.display = "none";
  });
  $("#eventBackdrop").addEventListener("click", (e) => {
    if (e.target === $("#eventBackdrop") || e.target.closest("#eventClose")) $("#eventBackdrop").style.display = "none";
  });
  loadStats();
  loadTrends();
  const initial = (location.hash || "").replace("#", "");
  switchTab(TABS.some((t) => t.id === initial) ? initial : "live");
  window.addEventListener("hashchange", () => {
    const id = (location.hash || "").replace("#", "");
    if (TABS.some((t) => t.id === id) && id !== state.tab) switchTab(id);
  });

  // Foreground refresh: active tab refreshes every 30s, stats every 60s.
  setInterval(() => { refreshTab(state.tab); }, 30000);
  setInterval(loadStats, 60000);
}

document.addEventListener("DOMContentLoaded", init);
