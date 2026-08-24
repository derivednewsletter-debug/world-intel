"""World Intelligence configuration — loads backend/.env (keys) and source lists."""
import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_env() -> None:
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env()

PORT = int(os.environ.get("PORT", "4173"))
HOST = os.environ.get("HOST", "0.0.0.0")
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "data" / "world-intel.db"))
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "7"))
USER_AGENT = "WorldIntel/0.2 (personal dashboard)"

FRED_API_KEY = os.environ.get("FRED_API_KEY", "PASTE_YOUR_FRED_KEY_HERE")
FIRMS_API_KEY = os.environ.get("FIRMS_API_KEY", "PASTE_YOUR_FIRMS_KEY_HERE")

APNS = {
    "enabled": os.environ.get("APNS_ENABLED", "0") == "1",
    "auth_key_path": os.environ.get("APNS_AUTH_KEY_PATH", ""),
    "team_id": os.environ.get("APNS_TEAM_ID", ""),
    "key_id": os.environ.get("APNS_KEY_ID", ""),
    "bundle_id": os.environ.get("APNS_BUNDLE_ID", "com.worldintel.app"),
}

WATCHLIST_DEFAULTS = {
    "countries": ["iran", "ukraine", "russia", "israel", "taiwan", "china", "north korea", "sudan", "myanmar", "venezuela"],
    "keywords": ["port congestion", "earthquake", "wildfire", "cyberattack", "ransomware", "oil price", "chip"],
    "min_severity": 3,
}

SCHEDULE = {
    "rss": "*/3 * * * *",
    "gdelt_doc": "*/15 * * * *",
    "gdelt_points": "*/15 * * * *",
    "disasters": "*/10 * * * *",
    "firms": "0 * * * *",
    "fred": "0 * * * *",  # hourly
    "weather": "*/10 * * * *",  # NOAA NWS alerts
    "spaceweather": "*/15 * * * *",  # NOAA SWPC solar/geomagnetic alerts
    "watch": "*/5 * * * *",  # dynamic Google News feed from your watchlist
    "money": "*/10 * * * *",  # FX + crypto
}


def _gn(q: str) -> str:
    from urllib.parse import quote
    return f"https://news.google.com/rss/search?q={quote(q)}&hl=en-US&gl=US&ceid=US:en"


# Reddit RSS — subreddits that tolerate automation (many 429 datacenter IPs).
REDDIT_FEEDS = [
    {"name": "reddit-worldnews", "url": "https://www.reddit.com/r/worldnews/.rss", "category": "news"},
    {"name": "reddit-logistics", "url": "https://www.reddit.com/r/logistics/.rss", "category": "supplychain"},
]

RSS_FEEDS = [
    {"name": "bbc-world", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "category": "news"},
    {"name": "bbc-business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "category": "markets"},
    {"name": "aljazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "category": "news"},
    {"name": "guardian-world", "url": "https://www.theguardian.com/world/rss", "category": "news"},
    {"name": "guardian-business", "url": "https://www.theguardian.com/business/rss", "category": "markets"},
    {"name": "dw-world", "url": "https://rss.dw.com/rdf/rss-en-world", "category": "news"},
    {"name": "sky-news", "url": "https://feeds.skynews.com/feeds/rss/world.xml", "category": "news"},
    {"name": "france24", "url": "https://www.france24.com/en/rss", "category": "news"},
    {"name": "nhk-world", "url": "https://www3.nhk.or.jp/rss/news/cat0.xml", "category": "news"},
]

GOOGLE_NEWS_FEEDS = [
    {"name": "gn-top", "url": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en", "category": "news"},
    {"name": "gn-world", "url": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en", "category": "news"},
    {"name": "gn-business", "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en", "category": "markets"},
    {"name": "gn-tech", "url": "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-US&gl=US&ceid=US:en", "category": "tech"},
    {"name": "gn-science", "url": "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=en-US&gl=US&ceid=US:en", "category": "tech"},
    {"name": "gn-health", "url": "https://news.google.com/rss/headlines/section/topic/HEALTH?hl=en-US&gl=US&ceid=US:en", "category": "health"},
]

SITE_FEEDS = [
    {"name": "gn-reuters", "url": _gn("site:reuters.com"), "category": "news"},
    {"name": "gn-ap", "url": _gn("site:apnews.com"), "category": "news"},
    {"name": "gn-cnn", "url": _gn("site:cnn.com"), "category": "news"},
    {"name": "gn-bloomberg", "url": _gn("site:bloomberg.com"), "category": "markets"},
    {"name": "gn-ft", "url": _gn("site:ft.com"), "category": "markets"},
]

SEARCH_FEEDS = [
    {"name": "gn-sc", "url": _gn('port congestion OR container shipping OR freight rates OR "supply chain" disruption'), "category": "supplychain"},
    {"name": "gn-energy", "url": _gn("oil price OR natural gas OR energy crisis OR OPEC"), "category": "energy"},
    {"name": "gn-markets", "url": _gn('stock market OR inflation OR "interest rate" OR recession'), "category": "markets"},
    {"name": "gn-conflict", "url": _gn("war OR conflict OR ceasefire OR missile OR invasion"), "category": "conflict"},
    {"name": "gn-disaster", "url": _gn("earthquake OR wildfire OR flood OR cyclone OR hurricane OR volcano"), "category": "disaster"},
    {"name": "gn-cyber", "url": _gn("cyberattack OR ransomware OR data breach OR outage"), "category": "tech"},
    {"name": "gn-agri", "url": _gn("food prices OR crop failure OR harvest OR agriculture exports"), "category": "energy"},
    {"name": "gn-chips", "url": _gn("semiconductors OR chip shortage OR microchips"), "category": "tech"},
    {"name": "gn-outbreak", "url": _gn("outbreak OR epidemic OR pandemic OR disease"), "category": "health"},
]

ALL_RSS_SOURCES = RSS_FEEDS + REDDIT_FEEDS + GOOGLE_NEWS_FEEDS + SITE_FEEDS + SEARCH_FEEDS

GDELT_DOC_QUERIES = [
    {"name": "gdelt-conflict", "query": "conflict OR war OR attack OR protest", "category": "conflict"},
    {"name": "gdelt-disaster", "query": "earthquake OR wildfire OR flood OR hurricane OR cyclone OR volcano", "category": "disaster"},
    {"name": "gdelt-supplychain", "query": '"supply chain" OR shipping OR "port congestion" OR freight', "category": "supplychain"},
    {"name": "gdelt-markets", "query": 'inflation OR markets OR economy OR "interest rate"', "category": "markets"},
    {"name": "gdelt-energy", "query": "oil OR gas OR energy OR OPEC", "category": "energy"},
    {"name": "gdelt-tech", "query": 'cyberattack OR ransomware OR "artificial intelligence" OR outage', "category": "tech"},
]

GDELT_EVENT_QUERY = "conflict OR protest OR riot OR strike OR disaster OR earthquake OR flood"

FRED_SERIES = [
    {"series_id": "CPIAUCSL", "name": "US CPI", "category": "markets", "unit": "index"},
    {"series_id": "UNRATE", "name": "US Unemployment", "category": "markets", "unit": "%"},
    {"series_id": "DFF", "name": "US Fed Funds Rate", "category": "markets", "unit": "%"},
    {"series_id": "DGS10", "name": "US 10Y Treasury", "category": "markets", "unit": "%"},
    {"series_id": "DCOILWTICO", "name": "WTI Crude Oil", "category": "energy", "unit": "USD/bbl"},
    {"series_id": "DCOILBRENTEU", "name": "Brent Crude Oil", "category": "energy", "unit": "USD/bbl"},
    {"series_id": "TSIFRGHTC", "name": "Freight Transportation Services Index", "category": "supplychain", "unit": "% chg"},
    {"series_id": "VIXCLS", "name": "CBOE Volatility Index (VIX)", "category": "markets", "unit": "index"},
]

# Keyless money sources (open.er-api.com FX + CoinGecko crypto).
FX_CURRENCIES = ["EUR", "GBP", "JPY", "CNY", "CHF", "AUD", "CAD", "INR"]
CRYPTO_COINS = ["bitcoin", "ethereum", "solana"]

LIVE_STREAMS = [
    {"name": "Al Jazeera English", "url": "https://www.youtube.com/embed/live_stream?channel=UCNye-wNBqNL5ZzHSJj3l8Bg", "note": "24/7 international news"},
    {"name": "DW News", "url": "https://www.youtube.com/embed/live_stream?channel=UCknLrEdhRCp1aegoMqRaCZg", "note": "24/7 news from Germany"},
    {"name": "France 24 English", "url": "https://www.youtube.com/embed/live_stream?channel=UCQfwfsi5VrQ8yKZ-UWmAEFg", "note": "24/7 international news"},
    {"name": "Sky News", "url": "https://www.youtube.com/embed/live_stream?channel=UCoMdktPbSTixAyNGwb-UYkQ", "note": "24/7 UK news"},
    {"name": "Reuters", "url": "https://www.youtube.com/embed/live_stream?channel=UChqUTb7kYRX8-EiaN3XFrSQ", "note": "Breaking coverage"},
    {"name": "ABC News Live", "url": "https://www.youtube.com/embed/live_stream?channel=UCBi2mrWuNuyYy4gbM6fU18Q", "note": "24/7 US news"},
    {"name": "CNBC", "url": "https://www.youtube.com/embed/live_stream?channel=UCrp_UI8XtuYfpiqluWLD7Lw", "note": "24/7 business & markets"},
]

CATEGORIES = ["news", "conflict", "disaster", "weather", "markets", "energy", "tech", "supplychain", "health"]

CATEGORY_META = {
    "news": {"label": "News", "color": "#4f8cff"},
    "conflict": {"label": "Conflict", "color": "#ff4d4f"},
    "disaster": {"label": "Disasters", "color": "#ff7a45"},
    "weather": {"label": "Weather", "color": "#13c2c2"},
    "markets": {"label": "Markets", "color": "#b37feb"},
    "energy": {"label": "Energy", "color": "#faad14"},
    "tech": {"label": "Tech & Cyber", "color": "#40c057"},
    "supplychain": {"label": "Supply Chain", "color": "#f06595"},
    "health": {"label": "Health", "color": "#36cfc9"},
}

SEVERITY_COLORS = ["#5cdbd3", "#8b93a7", "#95de64", "#ffc53d", "#ff7a45", "#ff4d4f"]
