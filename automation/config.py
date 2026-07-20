import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_LOCAL_JSON = Path(__file__).resolve().parent / "secrets.local.json"
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

# Wife's email is PII and this repo is public — kept out of git entirely in
# automation/secrets.local.json (gitignored), loaded here at runtime only.
def _load_secrets() -> dict:
    if SECRETS_LOCAL_JSON.exists():
        return json.loads(SECRETS_LOCAL_JSON.read_text())
    return {}


_secrets = _load_secrets()
_wife_email = _secrets.get("wife_email")
PREFERENCE_EMAIL_SENDER_ALLOWLIST: list[str] = [_wife_email] if _wife_email else []
PREFERENCE_EMAIL_SUBJECT_TAG = "[NewsDigestUpdate]"
GMAIL_PROCESSED_LABEL = "NewsDigest/Processed"

# Gmail IMAP credentials for direct Python access (fallback when Claude MCP
# is unavailable). Add to automation/secrets.local.json:
#   "gmail_address": "your-address@gmail.com"
#   "gmail_app_password": "xxxx xxxx xxxx xxxx"  (App Password from Google)
GMAIL_ADDRESS: str | None = _secrets.get("gmail_address")
GMAIL_APP_PASSWORD: str | None = _secrets.get("gmail_app_password") or _secrets.get("gmail_password")

# Cheap-model summarization: headless Claude Code CLI, --safe-mode (NOT --bare,
# which forces API-key auth and bypasses the logged-in subscription).
SUMMARIZE_MODEL = "claude-haiku-4-5-20251001"
SUMMARIZE_MAX_BUDGET_USD = "0.50"

# Haiku writes the summaries; Sonnet does one pass afterward to check Hebrew
# spelling/grammar/sense only (never touches headlines/urls, so it can't
# introduce a hallucinated link). Non-fatal — Haiku's text is used as-is if
# this fails.
VERIFY_MODEL = "claude-sonnet-5"
VERIFY_MAX_BUDGET_USD = "0.30"

# When the Claude CLI is unavailable (credit exhausted, auth failure, timeout),
# fall back to the GitHub Copilot chat completions API. Auth uses `gh auth token`
# (the gh CLI must be authenticated). claude-sonnet-5 is available on the Copilot
# subscription and speaks fluent Hebrew.
COPILOT_API_BASE = "https://api.githubcopilot.com"
COPILOT_INTEGRATION_ID = "vscode-chat"
COPILOT_FALLBACK_SUMMARIZE_MODEL = "claude-sonnet-5"
COPILOT_FALLBACK_VERIFY_MODEL = "claude-sonnet-5"

# Incremental update: if fewer than this many new headlines have appeared
# since the last successful digest, do a lightweight incremental pass
# (adjust existing summaries) rather than regenerating from scratch.
MIN_NEW_HEADLINES_FOR_FULL_REGEN = 12

# Local curation pass via Ollama, before any cloud call.
# qwen3.5:9b (reasoning model) was tried first but doesn't reliably honor
# structured JSON output even in simple "json" mode, and its default
# chain-of-thought makes schema-constrained calls time out. qwen2.5-coder:7b
# is not a reasoning model and empirically follows the JSON schema format
# correctly and quickly — verified live during setup.
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_CURATION_MODEL = "qwen2.5-coder:7b"
OLLAMA_BATCH_SIZE = 40

HEADLINE_LOOKBACK_HOURS = 26
MAX_HEADLINES_TO_LLM = 150

# Runs up to 7x/day (07:00, 10:00, 12:00, 15:00, 17:00, 19:00, 21:00 — see
# scripts/install_launchd.sh), each slot catching up on next wake if the Mac
# was asleep/off. The smallest gap between consecutive slots is 2h (e.g. 10→12);
# 1.5h keeps legitimate slots from blocking each other while still absorbing
# near-duplicate wake-catchup fires.
MIN_HOURS_BETWEEN_RUNS = 1.5

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

# World/Belgium sources — verified live 2026-07-20.
# These produce English-language output (LLM reads Dutch and summarises in English).
WORLD_SOURCES = {
    "vrt": {
        "label_en": "VRT NWS",
        # VRT's RSS feeds return text/html (bot-blocked). Scrape the homepage instead.
        "rss": [],
        "scrape_fallback_url": "https://www.vrt.be/vrtnws/nl/",
    },
    "de_morgen": {
        "label_en": "De Morgen",
        "rss": ["https://www.demorgen.be/rss.xml"],
        "scrape_fallback_url": "https://www.demorgen.be/",
    },
    "hln": {
        "label_en": "HLN",
        "rss": ["https://www.hln.be/rss.xml"],
        "scrape_fallback_url": "https://www.hln.be/",
    },
    "bbc_world": {
        "label_en": "BBC World",
        "rss": ["https://feeds.bbci.co.uk/news/world/rss.xml"],
        "scrape_fallback_url": "https://www.bbc.com/news/world",
    },
    "guardian_world": {
        "label_en": "The Guardian",
        "rss": ["https://www.theguardian.com/world/rss"],
        "scrape_fallback_url": "https://www.theguardian.com/world",
    },
    "politico_eu": {
        "label_en": "Politico Europe",
        "rss": ["https://www.politico.eu/feed/"],
        "scrape_fallback_url": "https://www.politico.eu/",
    },
    "times_of_israel": {
        "label_en": "Times of Israel",
        "rss": ["https://www.timesofisrael.com/feed/"],
        "scrape_fallback_url": "https://www.timesofisrael.com/",
    },
    "jta": {
        "label_en": "JTA",
        "rss": ["https://www.jta.org/feed"],
        "scrape_fallback_url": "https://www.jta.org/",
    },
}
