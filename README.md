# 🌍 World Intelligence

A personal world-intelligence dashboard: live global news, conflicts, natural disasters, severe weather, markets, energy, tech/cyber and supply-chain disruptions — all from **free APIs**. One data core, two clients:

- **Website** — dashboard rendered by the Python backend (FastAPI + Jinja2 + vanilla JS)
- **iOS app** — fully standalone SwiftUI app that fetches the same free sources directly from your phone (no laptop dependency, ~zero battery cost when idle)

The whole backend is **Python** (FastAPI, SQLite, APScheduler). The only non-Python piece is the iOS app, because a native iPhone app can only be written in Swift — but it shares the same logic: the from-scratch AI engine is ported 1:1 between `backend/app/ai/engine.py` and `ios/WorldIntel/AIEngine.swift`.

## Repo layout

```
start.sh / start.bat   one-command desktop launch (Windows / macOS / Linux / Git Bash)
scripts/build_ios.sh   one-command iOS build + install + launch (on a Mac with Xcode)
backend/               Python: collectors, SQLite store, FastAPI REST API, scheduler, AI engine, Jinja2 dashboard
ios/                   SwiftUI app
```

## Data sources (all free)

| Category | Sources |
|---|---|
| Breaking news | Google News RSS, BBC, Al Jazeera, Guardian, DW, Sky, France 24, NHK, Reddit r/worldnews |
| Real news (no RSS) | Site feeds for Reuters, AP, CNN, Bloomberg, FT via Google News |
| Communities | Reddit r/worldnews + r/logistics (supply-chain chatter) |
| Space weather | NOAA SWPC solar flares & geomagnetic storms (keyless) |
| Conflicts / events | GDELT (article search + geo point data) |
| Natural disasters | NASA EONET, USGS earthquakes, GDACS alerts, NASA FIRMS fire hotspots (free key) |
| Severe weather | NOAA NWS live alerts (api.weather.gov, keyless) + EONET storm categories |
| Markets / economy | Google News business feeds + FRED API (free key) |
| Money | FX rates (open.er-api.com, keyless) + crypto prices (CoinGecko, keyless) |
| Energy | Oil/gas/OPEC + agriculture/food feeds + FRED series (WTI + Brent) |
| Supply chain | Port congestion / freight / chokepoint news feeds + FRED freight index |
| Tech & cyber | Cyberattack, ransomware, semiconductors, outage feeds |
| Health | Outbreak / epidemic / vaccine feeds |
| Live TV | Free official streams: Al Jazeera, DW, France 24, Sky, Reuters, ABC, CNBC |

Two optional free keys: **FRED** (markets/energy indicators) and **NASA FIRMS** (satellite fire detection) — everything else is keyless.

---

## Website — one command

Requires **Python 3.11+** (built and tested on 3.14) on your PATH.

```bash
# Windows: double-click start.bat  (or run it from any terminal)
# macOS / Linux / Git Bash:
./start.sh
```

The first run creates the Python environment and installs dependencies automatically (one time);
after that it boots instantly. The dashboard is at `http://localhost:4173`, and the server prints
your LAN address so you can open it from any device on the same Wi-Fi. `Ctrl+C` stops it.

The Live tab opens on a KPI row (events tracked · sources healthy · breaking now · world stress)
that updates in place every 60s, with a pulsing **live** indicator in the header. A **🚨 Surge
banner** appears when a term spikes 2.5×+ above its hourly baseline (click a term to filter).
The **▶ Present** button in the header auto-cycles the main tabs with a progress bar — handy for
demos.

Other endpoints: `GET /api/ai/trends` (surge terms), `GET /api/stress?hours=24` (World Stress Index),
`GET /api/event/{id}` (one event + its story-cluster timeline), `GET /api/export?hours=24` (CSV).

Optional keys (FRED / FIRMS / APNs) go in `backend/.env` — copy from `backend/.env.example`.

Useful extras:

```bash
backend/.venv/Scripts/python -m app.collect                # run every collector once (diagnostics)
backend/.venv/Scripts/python -m unittest discover -s tests  # run the unit tests (55 tests)
./status.sh                                                    # source health at a glance in the terminal
```



### World Stress Index

A single 0–100 **"how bad is the world right now"** gauge in the header (and a full panel on the
AI Briefing tab) — a transparent weighted composite of event pressure, breaking-news volume,
active disasters, market volatility, and your watchlist activity, with a 24-hour trend sparkline.
Computed locally from data the dashboard already collects — no external service.

### Story timelines & event details

- **Click any story cluster** on the AI Briefing tab to expand its chronological timeline
  (first report → updates → where it stands now).
- **Click any event card** anywhere in the dashboard to open a detail modal: full summary,
  source links, location (with a map link), copy-link, and the rest of its story cluster.

### Money tab

FX rates (USD/EUR, USD/JPY, …) and crypto prices (Bitcoin, Ethereum, Solana) — keyless, collected
every 10 minutes, each with a live sparkline on the Markets tab.

Dashboard features: **AI Briefing** tab, **Breaking** banner (severity ≥ 4), **Trending topics**, category filters, "Major only" toggle, article thumbnails, infinite scroll, geo map with category legend + filters, source **health panel** (click the footer status), search with highlighting, a **24h activity chart**, **browser alerts** for major events (🔔 button in the header), and an editable **watchlist** that drives the AI alerts, a dynamic watch feed, and push.

Every tab has a deep link — open `http://localhost:4173/#briefing`, `#map`, `#disasters`, … — and the dashboard is fully usable with the server stopped for the data it already fetched; it shows a clear "server unreachable" state otherwise.

### The watchlist (editable, persists in the DB)

Your watchlist (countries + keywords) drives the AI's alerts, a **dynamic Google News feed** built from those terms (collected every 5 min), and push notifications. Each term shows a **live match count** (events matched in the last 24h) right on its chip, so you can see at a glance whether a watchlist item is active. Edit it on the **AI Briefing** tab → "Your watchlist", or via the API:

```bash
curl -X PUT http://localhost:4173/api/watchlist -H "Content-Type: application/json" \
  -d '{"countries":["japan","india"],"keywords":["tsunami","semiconductor"],"min_severity":3}'
curl http://localhost:4173/api/watchlist          # read it
curl -X DELETE http://localhost:4173/api/watchlist  # back to defaults
```

### The on-device AI (built from scratch)

`backend/app/ai/engine.py` (ported 1:1 to Swift in the iOS app) is a bespoke intelligence engine — no ML libraries, no model downloads, pure algorithms that run in milliseconds:

- **Story clustering** — groups headlines about the same story (token Jaccard similarity)
- **Importance scoring** — severity × source diversity × story size × recency × momentum
- **Trend-spike detection** — terms suddenly appearing far above their baseline
- **Watchlist alerts** — your countries/keywords, high-severity hits flagged (`backend/app/config.py` → `WATCHLIST`)
- **AI Briefing** — auto-generated headline + sections (Breaking / Top stories / Natural disasters / Supply chain & energy / Emerging trends), rendered on the website and generated locally on the iPhone
- **World Summary** — the AI organizes **all** current events by region (Middle East, Europe, Asia-Pacific, Africa, Americas) and by category, then writes an opening brief: activity levels, fastest-rising topics, and the single most important story right now (`/api/ai/summary`, same logic on iOS)

Because it's just fast algorithms, it costs nothing on battery or CPU on either device.

**Collector schedule** (edit `SCHEDULE` in `backend/app/config.py`): RSS feeds every 3 min, disasters every 10 min, GDELT every 15 min (rate-limited to 1 req / 5 s), FIRMS hourly, FRED hourly. Events are pruned after 7 days.

### Keys live in `backend/.env`

The backend auto-loads `backend/.env` (copy from `.env.example`). Fill in any of:

| Var | What it unlocks | Where to get it |
|---|---|---|
| `FRED_API_KEY` | CPI, unemployment, rates, WTI + Brent oil, freight index | https://fred.stlouisfed.org/docs/api/api_key.html (free, instant) |
| `FIRMS_API_KEY` | NASA satellite fire detection on map + Disasters (MODIS + VIIRS) | https://firms.modaps.eosdis.nasa.gov (free Earthdata login) |
| `APNS_ENABLED` / `APNS_AUTH_KEY_PATH` / `APNS_TEAM_ID` / `APNS_KEY_ID` / `APNS_BUNDLE_ID` | Real push notifications | Paid Apple Developer account + .p8 key |

Set the keys, restart the server, and the Markets / Supply Chain tabs show live CPI, unemployment, rates, WTI + Brent oil and the Freight Transportation Services Index, while the Disasters tab and map pick up satellite fire clusters every hour.

## iOS app — one command (on a Mac)

The app builds and launches with a single command on any Mac with Xcode installed:

```bash
./scripts/build_ios.sh
```

- **iPhone plugged in** → it builds, installs and launches on your phone.
- **No iPhone** → it boots a simulator and runs the app there — no Apple ID, no signing, zero setup.

First time on a physical iPhone, Apple requires a signing team: open the project once in Xcode
(`open ios/WorldIntel.xcodeproj`), pick your team under **Signing & Capabilities**, hit Run once —
that saves the team into the project, and `./scripts/build_ios.sh` works automatically from then on
(a free Apple ID is fine; apps re-expire after 7 days and need a re-run). You can also skip Xcode
entirely by passing your team once: `TEAM_ID=XXXXXXXXXX ./scripts/build_ios.sh`.

### Optional: local server mode (richer data on your phone)

The app is **fully standalone by default** — it talks directly to the free APIs and needs nothing from your laptop. If you're on the same Wi-Fi as the dashboard, set **Settings → Local server URL** to `http://<your-machine's-LAN-IP>:4173` and the app upgrades itself: the Live feed becomes the backend's full aggregated feed, Markets shows **live FRED indicators** (CPI, rates, oil), Disasters + Map include **NASA FIRMS satellite fires** and NOAA weather, and the Briefing uses the backend's richer AI world summary. Leave it empty to stay standalone.

### Build in Xcode (manual, if you prefer)


The app is **standalone**: it calls the free APIs directly from your phone, caches everything on device, and refreshes on two tiers:

- **While open:** everything updates every **30 seconds** (a foreground tick loop, screen-on usage so battery impact is negligible).
- **In the background (best-effort):** an iOS BackgroundTasks refresh keeps data current when you're not using the app. iOS controls the schedule (typically every 15–30 min, more often on Wi-Fi/charging) — that's the platform's maximum for a free Apple ID, and the system manages it so battery stays minimal. Toggle in Settings.

Tabs: Live · Map · Disasters · Supply Chain · Markets · Watch · **Search** · Settings. Search scans everything already cached on the phone — instant and free. Every tab shows a "last updated" freshness label; Settings lists per-section cache ages. The map has a color legend, and the feed has a "Major only" severity filter. The **Markets tab shows live FX rates and crypto prices even standalone** (keyless APIs, same as the web dashboard) — no server URL needed for money data.

**Home Screen widget** — add the "World Intelligence" widget (small or medium) and it shows the top world headlines, refreshed automatically by WidgetKit. It fetches the same core news feeds the app uses, so it needs no shared container, no setup, and no extra permissions — just long-press your Home Screen → **+** → search for World Intelligence.

1. Open `ios/WorldIntel.xcodeproj` in Xcode (macOS 14+, Xcode 15+).
2. Select your team under **Signing & Capabilities** (personal free Apple ID works for a 7-day local install; a paid account removes the expiry).
3. Plug in your iPhone (or pick a simulator) and hit **Run**.

- **AI Briefing** tab — generated on-device from cached headlines (zero network, zero battery).
- **Watch** embeds free live streams; players load only when you open a channel.
- **Settings** lets you toggle live 30s refresh (default on), best-effort background refresh (default on), clear the cache, and manage notifications.

### Notifications

**Local alerts (works with a free Apple ID):** when you open the app, if a major event (severity 4–5) happened since your last visit, you get an instant notification. Fires only while the app is open — no background polling.

**Real push (optional, requires a paid Apple Developer account):**
1. Enable the Push Notifications capability in Xcode (Signing & Capabilities → + → Push Notifications).
2. Create an APNs auth key (.p8) at developer.apple.com → Certificates/Keys → APNs Key, note the **Key ID** and your **Team ID**.
3. Set the `APNS_*` vars in `backend/.env` (see table above), then start the backend.
4. In the iOS app: Settings → turn on **Real push notifications** and set **Your machine's server URL** to `http://<machine-lan-ip>:4173`.
5. Verify the whole chain: `curl -X POST http://localhost:4173/api/push/test` — your phone should ping within a second.

The push server is built from scratch (`backend/app/push/apns.py`) — HTTP/2 + ES256 JWT signing with `httpx[http2]` + `cryptography`. It scans every 5 minutes for new severity ≥ 4 or watchlist events and pushes to your phone. APNs delivery is handled by iOS itself, so it costs no battery.

## Notes & limits

- Free news sources keep ~1 day to ~1 month of history; this is a "what's happening now" dashboard by design.
- GDELT enforces 1 request / 5 s per IP; the backend staggers queries, backs off, and enters a 30-min cooldown when throttled so it never hammers a blocked IP. If GDELT shows down in the health panel, it's usually a temporary throttle — it recovers on its own.
- Stories are deduplicated by normalized title (same story from two outlets collapses into one) and generic news items are auto-classified into Conflict/Disaster/Markets/etc. by keyword rules.
- Everything is hardcoded/local by design (personal use, no accounts, no cloud).
