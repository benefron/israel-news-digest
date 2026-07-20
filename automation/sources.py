import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

import feedparser
import httpx
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


def _fetch_rss(feed_url: str) -> list[dict]:
    resp = httpx.get(
        feed_url,
        headers=config.REQUEST_HEADERS,
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
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


def _fetch_scrape_fallback(source_key: str, page_url: str) -> list[dict]:
    resp = httpx.get(
        page_url,
        headers=config.REQUEST_HEADERS,
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    seen_urls = set()
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if not text or len(text) < 8:
            continue
        url = urljoin(page_url, a["href"])
        if not url.startswith("http"):
            continue
        canon = canonicalize_url(url)
        if canon in seen_urls:
            continue
        seen_urls.add(canon)

        img_el = a.find("img") or (a.parent.find("img") if a.parent else None)
        image_url = urljoin(page_url, img_el["src"]) if img_el and img_el.get("src") else None

        items.append({"title": text, "url": url, "published_at": None, "image_url": image_url})
        if len(items) >= 30:
            break
    return items


def fetch_source(source_key: str) -> tuple[list[dict], bool]:
    """Returns (items, ok). ok=False means every RSS candidate and the
    scrape fallback failed for this source."""
    source = config.SOURCES[source_key]

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


def _security_keywords():
    from security_keywords import SECURITY_WAR_KEYWORDS
    return SECURITY_WAR_KEYWORDS
