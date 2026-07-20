from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
ARCHIVE_DIR = DATA_DIR / "archive"
STATE_DIR = Path(__file__).resolve().parent / "state"
LOGS_DIR = Path(__file__).resolve().parent / "logs"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

LATEST_JSON = DATA_DIR / "latest.json"
PREFERENCES_JSON = DATA_DIR / "preferences.json"
TOPIC_CATALOG_JSON = DATA_DIR / "topic_catalog.json"

LAST_RUN_STATE = STATE_DIR / "last_run.json"
SUMMARIZE_INPUT_SCRATCH = STATE_DIR / "summarize_input.json"
RUN_LOCK = STATE_DIR / "run.lock"

# Fill in once known — see plan §"Preference sync from email".
PREFERENCE_EMAIL_SENDER_ALLOWLIST: list[str] = []
PREFERENCE_EMAIL_SUBJECT_TAG = "[NewsDigestUpdate]"
GMAIL_PROCESSED_LABEL = "NewsDigest/Processed"

# Cheap-model summarization: headless Claude Code CLI, --safe-mode (NOT --bare,
# which forces API-key auth and bypasses the logged-in subscription).
SUMMARIZE_MODEL = "claude-haiku-4-5-20251001"
SUMMARIZE_MAX_BUDGET_USD = "0.50"

# Local curation pass via Ollama, before any cloud call.
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_CURATION_MODEL = "qwen3.5:9b"
OLLAMA_BATCH_SIZE = 40

HEADLINE_LOOKBACK_HOURS = 26
MAX_HEADLINES_TO_LLM = 150

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "he-IL,he;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
REQUEST_TIMEOUT_SECONDS = 15

# RSS feeds verified live during planning (2026-07-20). See plan doc for notes
# on sources that need a browser-confirmed URL (Israel Hayom, Mako category
# slugs) before relying on them unattended.
SOURCES = {
    "haaretz": {
        "label_he": "הארץ",
        "rss": [
            "https://www.haaretz.co.il/srv/rss---feedly",
            "https://www.haaretz.co.il/srv/htz---all-articles",
        ],
        "scrape_fallback_url": "https://www.haaretz.co.il/",
    },
    "ynet": {
        "label_he": "Ynet",
        "rss": [
            "https://www.ynet.co.il/Integration/StoryRss2.xml",
            "https://www.ynet.co.il/Integration/StoryRss3082.xml",
            "https://www.ynet.co.il/Integration/StoryRss3254.xml",
        ],
        "scrape_fallback_url": "https://www.ynet.co.il/",
    },
    "israel_hayom": {
        "label_he": "ישראל היום",
        # Index at israelhayom.co.il/rss-feed returned HTTP 403 without a
        # browser-like UA during planning; REQUEST_HEADERS should fix it, but
        # verify with scripts/verify_feeds.py before relying on it unattended.
        "rss": [],
        "scrape_fallback_url": "https://www.israelhayom.co.il/",
    },
    "kan": {
        "label_he": "כאן 11",
        "rss": [
            "https://www.kan.org.il/rss/landingPage.ashx?landingPageId=1009&section=1",
        ],
        "scrape_fallback_url": "https://www.kan.org.il/",
    },
    "mako": {
        "label_he": "N12",
        # Category slugs beyond these are opaque hex/GUIDs — open
        # mako.co.il/rss in a real browser to confirm the general/security
        # feed links before depending on more than this set.
        "rss": [
            "https://rcs.mako.co.il/rss/news-world.xml",
            "https://rcs.mako.co.il/rss/news-military.xml",
            "https://rcs.mako.co.il/rss/news-law.xml",
            "https://rcs.mako.co.il/rss/news-money.xml",
        ],
        "scrape_fallback_url": "https://www.mako.co.il/news",
    },
    "walla": {
        "label_he": "וואלה",
        "rss": [
            "https://rss.walla.co.il/feed/1?type=main",
            "https://rss.walla.co.il/feed/22",
            "https://rss.walla.co.il/feed/2689",
        ],
        "scrape_fallback_url": "https://news.walla.co.il/",
    },
}
