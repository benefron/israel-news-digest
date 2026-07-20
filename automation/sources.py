import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

import feedparser
import httpx
import tls_client
from bs4 import BeautifulSoup

import config

log = logging.getLogger(__name__)

IMG_TAG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
SIZED_FIELD_RE = re.compile(r"image(\d+)x(\d+)")


def _extract_image(entry: dict) -> str | None:
    """Every source here exposes article images differently — Media RSS,
    a plain enclosure, custom sized fields, or just an <img> buried in the
    HTML summary — so try each in turn rather than assume one convention."""
    media_content = entry.get("media_content")
    if media_content:
        best = max(media_content, key=lambda m: int(m.get("width") or 0))
        if best.get("url"):
            return best["url"]

    for enc in entry.get("enclosures", []):
        href = enc.get("href") or enc.get("url")
        if href and enc.get("type", "").startswith("image"):
            return href

    sized = []
    for key, value in entry.items():
        m = SIZED_FIELD_RE.fullmatch(key)
        if m and value:
            sized.append((int(m.group(1)) * int(m.group(2)), value))
    if sized:
        sized.sort(key=lambda t: t[0], reverse=True)
        return sized[0][1]

    html = entry.get("summary") or entry.get("description") or ""
    match = IMG_TAG_RE.search(html)
    if match:
        return match.group(1)

    return None


def _upgrade_image_size(source_key: str, image_url: str) -> str | None:
    # Haaretz CDN URLs (img.haarets.co.il/bs/…) consistently return 404 for
    # unauthenticated requests. Suppress rather than expose a broken image.
    if source_key == "haaretz":
        return None
    return image_url


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    # drop utm_* and other tracking params, keep everything else
    query = [(k, v) for k, v in parse_qsl(parsed.query) if not k.lower().startswith("utm_")]
    return urlunparse(parsed._replace(query=urlencode(query), fragment=""))


def headline_id(url: str) -> str:
    return hashlib.sha1(canonicalize_url(url).encode("utf-8")).hexdigest()[:10]


def _fetch_via_tls_client(url: str) -> bytes:
    """Some sites (Cloudflare/Akamai-fronted) 403 plain httpx requests
    because its TLS handshake doesn't look like a real browser, even with
    browser-like headers. tls_client spoofs an actual Chrome TLS/JA3
    fingerprint, which clears that check without needing a full headless
    browser. Only worth the overhead as a fallback after httpx's 403."""
    session = tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
    resp = session.get(url, headers=config.REQUEST_HEADERS, timeout_seconds=config.REQUEST_TIMEOUT_SECONDS)
    if resp.status_code >= 400:
        raise ValueError(f"tls_client fallback got HTTP {resp.status_code} for {url}")
    return resp.content


def _http_get(url: str) -> bytes:
    try:
        resp = httpx.get(
            url,
            headers=config.REQUEST_HEADERS,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.content
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 403:
            raise
        log.info("url=%s got 403 via httpx, retrying via tls_client", url)
        return _fetch_via_tls_client(url)


def _fetch_rss(feed_url: str) -> list[dict]:
    parsed = feedparser.parse(_http_get(feed_url))
    if not parsed.entries:
        raise ValueError(f"no entries in feed: {feed_url}")

    items = []
    for entry in parsed.entries:
        url = entry.get("link")
        title = entry.get("title")
        if not url or not title:
            continue
        published_at = None
        if entry.get("published_parsed"):
            published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
        items.append({
            "title": title.strip(),
            "url": url.strip(),
            "published_at": published_at,
            "image_url": _extract_image(entry),
        })
    return items


# Below this, scraped anchor text is reliably nav/menu/category/byline
# chrome (observed max ~28 chars across several sites' homepages); real
# headlines observed were all 50+ chars. There's no separating this by any
# other cheap signal, so a length floor is the whole filter.
MIN_SCRAPE_TITLE_CHARS = 30


def _fetch_scrape_fallback(source_key: str, page_url: str) -> list[dict]:
    soup = BeautifulSoup(_http_get(page_url), "html.parser")

    # A single article is often wrapped by more than one <a> to the same
    # URL — e.g. a big card anchor (badge + headline + teaser, all
    # concatenated with no whitespace in the source HTML) alongside a
    # smaller anchor around just the headline. Keep the shortest
    # (still-above-floor) candidate per URL rather than whichever anchor
    # the DOM happens to list first, since the concise one is reliably just
    # the headline.
    candidates: dict[str, dict] = {}
    order: list[str] = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if not text or len(text) < MIN_SCRAPE_TITLE_CHARS:
            continue
        url = urljoin(page_url, a["href"])
        if not url.startswith("http"):
            continue
        canon = canonicalize_url(url)

        img_el = a.find("img") or (a.parent.find("img") if a.parent else None)
        image_url = urljoin(page_url, img_el["src"]) if img_el and img_el.get("src") else None

        existing = candidates.get(canon)
        if existing is None:
            candidates[canon] = {"title": text, "url": url, "published_at": None, "image_url": image_url}
            order.append(canon)
        elif len(text) < len(existing["title"]):
            existing["title"] = text
            if image_url:
                existing["image_url"] = image_url

    return [candidates[c] for c in order[:30]]


def fetch_source(source_key: str, sources_dict: dict | None = None) -> tuple[list[dict], bool]:
    """Returns (items, ok). ok=False means every RSS candidate and the
    scrape fallback failed for this source."""
    if sources_dict is None:
        sources_dict = config.SOURCES
    source = sources_dict[source_key]

    for feed_url in source.get("rss", []):
        try:
            items = _fetch_rss(feed_url)
            log.info("source=%s feed=%s entries=%d", source_key, feed_url, len(items))
            return items, True
        except Exception as exc:  # noqa: BLE001 - try the next candidate regardless of cause
            log.warning("source=%s feed=%s failed: %s", source_key, feed_url, exc)

    fallback_url = source.get("scrape_fallback_url")
    if fallback_url:
        try:
            items = _fetch_scrape_fallback(source_key, fallback_url)
            log.info("source=%s scrape fallback entries=%d", source_key, len(items))
            return items, True
        except Exception as exc:  # noqa: BLE001
            log.warning("source=%s scrape fallback failed: %s", source_key, exc)

    return [], False


def fetch_all_headlines() -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.HEADLINE_LOOKBACK_HOURS)
    fetched, failed = [], []
    all_headlines = []
    seen_ids = set()

    for source_key, source in config.SOURCES.items():
        items, ok = fetch_source(source_key)
        if not ok:
            failed.append(source_key)
            continue
        fetched.append(source_key)

        for item in items[: config.MAX_HEADLINES_PER_SOURCE]:
            if item["published_at"]:
                published = datetime.fromisoformat(item["published_at"])
                if published < cutoff:
                    continue
            hid = headline_id(item["url"])
            if hid in seen_ids:
                continue
            seen_ids.add(hid)
            image_url = item.get("image_url")
            if image_url:
                image_url = _upgrade_image_size(source_key, image_url)
            all_headlines.append({
                "id": hid,
                "title": item["title"],
                "url": canonicalize_url(item["url"]),
                "source": source_key,
                "source_label": source["label_he"],
                "source_label_he": source["label_he"],
                "published_at": item["published_at"],
                "image_url": image_url,
            })

    def sort_key(h):
        has_security_kw = any(kw in h["title"] for kw in _security_keywords())
        return (not has_security_kw, h["published_at"] is None, h["published_at"] or "")

    all_headlines.sort(key=sort_key)
    capped = all_headlines[: config.MAX_HEADLINES_TO_LLM]

    return {"headlines": capped, "sources_fetched": fetched, "sources_failed": failed}


def fetch_world_headlines() -> dict:
    """Fetch headlines from WORLD_SOURCES. Returns same structure as
    fetch_all_headlines() but uses source_label_en (English source names)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.HEADLINE_LOOKBACK_HOURS)
    fetched, failed = [], []
    all_headlines = []
    seen_ids = set()

    for source_key, source in config.WORLD_SOURCES.items():
        items, ok = fetch_source(source_key, sources_dict=config.WORLD_SOURCES)
        if not ok:
            failed.append(source_key)
            continue
        fetched.append(source_key)

        for item in items:
            if item["published_at"]:
                published = datetime.fromisoformat(item["published_at"])
                if published < cutoff:
                    continue
            hid = headline_id(item["url"])
            if hid in seen_ids:
                continue
            seen_ids.add(hid)
            image_url = item.get("image_url")
            if image_url:
                image_url = _upgrade_image_size(source_key, image_url)
            all_headlines.append({
                "id": hid,
                "title": item["title"],
                "url": canonicalize_url(item["url"]),
                "source": source_key,
                "source_label": source["label_en"],
                "source_label_en": source["label_en"],
                "published_at": item["published_at"],
                "image_url": image_url,
            })

    # World headlines: sort by published_at, most recent first; no security priority.
    all_headlines.sort(key=lambda h: (h["published_at"] is None, h["published_at"] or ""), reverse=True)
    capped = all_headlines[: config.MAX_HEADLINES_TO_LLM]

    return {"headlines": capped, "sources_fetched": fetched, "sources_failed": failed}


def _security_keywords():
    from security_keywords import SECURITY_WAR_KEYWORDS
    return SECURITY_WAR_KEYWORDS
