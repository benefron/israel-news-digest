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
חפש בג'ימייל הודעה עם הנושא המכיל "{config.PREFERENCE_EMAIL_SUBJECT_TAG}",
מהשולח/ת: {sender_clause}, שהתקבלה אחרי {since_iso},
וללא התווית "{config.GMAIL_PROCESSED_LABEL}".

אם לא נמצאה הודעה כזו — החזר {{"found": false}}.

אם נמצאה הודעה — קח את החדשה ביותר, קרא אותה, וחלץ את בלוק ה-JSON
(בתוך ```json ... ```) מגוף ההודעה. תייג את ההודעה בתווית
"{config.GMAIL_PROCESSED_LABEL}" והסר אותה מהתיבה הנכנסת (ארכוב), כדי שלא
תעובד שוב. החזר {{"found": true, "message_id": "...", "diff": <ה-JSON שחילצת>}}.
""".strip()


def sync_from_gmail(since_iso: str) -> dict | None:
    """Non-fatal by design: any failure here should be logged and the run
    should continue with existing preferences, never block the daily digest."""
    schema = (config.PROMPTS_DIR / "gmail_sync_schema.json").read_text()
    try:
        result = subprocess.run(
            [
                "claude", "-p", _build_prompt(since_iso),
                "--allowedTools",
                "mcp__gmail__search_threads,mcp__gmail__get_message,mcp__gmail__label_message",
                "--output-format", "json",
                "--json-schema", schema,
            ],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude exited {result.returncode}: {result.stderr[:500]}")

        envelope = json.loads(result.stdout)
        if envelope.get("is_error"):
            raise RuntimeError(f"claude reported an error: {envelope}")

        structured = envelope["structured_output"]
        if not structured.get("found"):
            return None
        return structured

    except Exception as exc:  # noqa: BLE001
        log.warning("gmail preference sync failed, continuing with existing preferences: %s", exc)
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
