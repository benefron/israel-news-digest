import json
import logging
import subprocess
from datetime import datetime, timezone

import config

log = logging.getLogger(__name__)


def _build_prompt(since_iso: str) -> str:
    sender_clause = (
        " OR ".join(f"from:{addr}" for addr in config.PREFERENCE_EMAIL_SENDER_ALLOWLIST)
        if config.PREFERENCE_EMAIL_SENDER_ALLOWLIST
        else "from:anyone (no sender filter configured yet)"
    )
    return f"""
בדוק קודם (list_labels) אם קיימת תווית בשם "{config.GMAIL_PROCESSED_LABEL}"
בג'ימייל. אם לא קיימת, צור אותה (create_label) — עוד לא היה שימוש בה.

חפש בג'ימייל (search_threads) הודעה עם הנושא המכיל "{config.PREFERENCE_EMAIL_SUBJECT_TAG}",
מהשולח/ת: {sender_clause}, שהתקבלה אחרי {since_iso},
וללא התווית "{config.GMAIL_PROCESSED_LABEL}" (זכור: אופרטור label: דורש
מזהה תווית, לא שם — קבל אותו מ-list_labels).

אם לא נמצאה הודעה כזו — החזר {{"found": false}}.

אם נמצאה הודעה — קח את החדשה ביותר, קרא אותה (get_message), וחלץ את בלוק
ה-JSON (בתוך ```json ... ```) מגוף ההודעה. תייג את ההודעה (label_message)
בתווית "{config.GMAIL_PROCESSED_LABEL}", כדי שלא תעובד שוב. החזר
{{"found": true, "message_id": "...", "diff": <ה-JSON שחילצת>}}.
""".strip()


def _sync_via_claude(since_iso: str) -> dict | None:
    """Try to fetch preference update using Claude's Gmail MCP tools."""
    schema = json.loads((config.PROMPTS_DIR / "gmail_sync_schema.json").read_text())
    result = subprocess.run(
        [
            "claude", "-p", _build_prompt(since_iso),
            "--allowedTools",
            "mcp__claude_ai_Gmail__search_threads,mcp__claude_ai_Gmail__get_message,"
            "mcp__claude_ai_Gmail__label_message,mcp__claude_ai_Gmail__list_labels,"
            "mcp__claude_ai_Gmail__create_label",
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
        ],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude exited {result.returncode}: {result.stderr[:300]}")
    envelope = json.loads(result.stdout)
    if envelope.get("is_error"):
        raise RuntimeError(f"claude reported an error: {envelope.get('result','')[:200]}")
    structured = envelope["structured_output"]
    if not structured.get("found"):
        return None
    return structured


def _sync_via_imap(since_iso: str) -> dict | None:
    """Fallback: read Gmail directly via IMAP with an App Password."""
    if not config.GMAIL_ADDRESS or not config.GMAIL_APP_PASSWORD:
        log.warning(
            "gmail_client: no gmail_address/gmail_app_password in secrets.local.json "
            "— cannot use IMAP fallback. See automation/gmail_client.py for setup."
        )
        return None
    if not config.PREFERENCE_EMAIL_SENDER_ALLOWLIST:
        log.warning("gmail_client: no sender allowlist configured, skipping IMAP search")
        return None

    import gmail_client
    diff = gmail_client.fetch_latest_update_email(
        gmail_address=config.GMAIL_ADDRESS,
        app_password=config.GMAIL_APP_PASSWORD,
        subject_tag=config.PREFERENCE_EMAIL_SUBJECT_TAG,
        sender_allowlist=config.PREFERENCE_EMAIL_SENDER_ALLOWLIST,
        since_iso=since_iso,
    )
    if diff is None:
        return None
    return {"found": True, "diff": diff}


def sync_from_gmail(since_iso: str) -> dict | None:
    """Non-fatal by design: any failure here should be logged and the run
    should continue with existing preferences, never block the daily digest.

    Tries Claude MCP first (rich tool access, labels messages as processed).
    Falls back to direct IMAP if Claude is unavailable.
    """
    try:
        result = _sync_via_claude(since_iso)
        if result is not None:
            log.info("gmail sync: found update via Claude MCP")
        return result
    except Exception as claude_exc:
        log.warning("gmail sync via Claude failed (%s), trying IMAP fallback", claude_exc)

    try:
        result = _sync_via_imap(since_iso)
        if result is not None:
            log.info("gmail sync: found update via IMAP fallback")
        return result
    except Exception as imap_exc:
        log.warning("gmail sync via IMAP also failed: %s", imap_exc)
        return None


def apply_diff(diff: dict) -> None:
    prefs = json.loads(config.PREFERENCES_JSON.read_text())
    subjects = {s["key"]: s for s in prefs["subjects"]}
    changes = diff["changes"]

    for added in changes.get("add_subjects", []):
        subjects[added["key"]] = {
            "key": added["key"], "label_he": added["label_he"],
            "enabled": True, "source": "user_added",
        }
    for key in changes.get("remove_subject_keys", []):
        subjects.pop(key, None)
    for key in changes.get("enable_subject_keys", []):
        if key in subjects:
            subjects[key]["enabled"] = True
    for key in changes.get("disable_subject_keys", []):
        if key in subjects:
            subjects[key]["enabled"] = False

    prefs["subjects"] = list(subjects.values())
    prefs["updated_at"] = datetime.now(timezone.utc).isoformat()
    config.PREFERENCES_JSON.write_text(json.dumps(prefs, ensure_ascii=False, indent=2))
    log.info("applied preference update from email")
