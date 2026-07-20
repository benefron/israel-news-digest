"""Direct Gmail IMAP access — used as fallback when Claude's Gmail MCP tools
are unavailable (e.g. session limit hit).

Setup: add these two fields to automation/secrets.local.json:
  "gmail_address": "your-address@gmail.com"
  "gmail_app_password": "xxxx xxxx xxxx xxxx"

To create an App Password:
  https://myaccount.google.com/apppasswords
  (requires 2-step verification; choose "Mail" + device name)
"""
import email as _email_module
import imaplib
import json
import logging
import re
from datetime import datetime, timezone

log = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

_JSON_BLOCK_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL)
_PLAIN_JSON_RE = re.compile(r"(\{[^}]*\"changes\"[^}]*\}.*)", re.DOTALL)


def _extract_json_from_body(body: str) -> dict | None:
    m = _JSON_BLOCK_RE.search(body)
    if m:
        return json.loads(m.group(1))
    m = _PLAIN_JSON_RE.search(body)
    if m:
        return json.loads(m.group(1).strip())
    return None


def _get_text_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    payload = msg.get_payload(decode=True)
    if payload:
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    return ""


def fetch_latest_update_email(
    gmail_address: str,
    app_password: str,
    subject_tag: str,
    sender_allowlist: list[str],
    since_iso: str,
) -> dict | None:
    """Connects to Gmail IMAP and looks for the most recent unread email
    with ``subject_tag`` in the subject from a sender in ``sender_allowlist``
    received after ``since_iso``.

    Returns the parsed JSON diff dict, or None if no matching email is found.
    Raises on connection/auth errors so the caller can log and continue.
    """
    since_dt = datetime.fromisoformat(since_iso).astimezone(timezone.utc)
    # IMAP SINCE uses day granularity — go back one day to be safe
    since_str = since_dt.strftime("%d-%b-%Y")

    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
        imap.login(gmail_address, app_password)
        imap.select("INBOX")

        # Build IMAP search: SINCE + SUBJECT + (FROM1 OR FROM2 ...)
        # IMAP search is AND-based; OR needs nesting
        if len(sender_allowlist) == 1:
            from_criteria = f'FROM "{sender_allowlist[0]}"'
        elif len(sender_allowlist) > 1:
            # Nest OR: (OR FROM a FROM b) OR ... 
            from_criteria = f'FROM "{sender_allowlist[0]}"'
            for addr in sender_allowlist[1:]:
                from_criteria = f'(OR FROM "{addr}" {from_criteria})'
        else:
            from_criteria = None

        parts = [f'SINCE "{since_str}"', f'SUBJECT "{subject_tag}"']
        if from_criteria:
            parts.append(from_criteria)
        search_str = " ".join(parts)

        _, data = imap.search(None, search_str)
        msg_ids = data[0].split() if data[0] else []
        if not msg_ids:
            log.info("gmail_client: no matching emails found (IMAP search)")
            return None

        # Fetch the most recent matching message
        _, msg_data = imap.fetch(msg_ids[-1], "(RFC822)")
        raw = msg_data[0][1] if msg_data and msg_data[0] else None
        if not raw:
            return None

        msg = _email_module.message_from_bytes(raw)
        body = _get_text_body(msg)
        subject = msg.get("Subject", "")
        sender = msg.get("From", "")
        log.info("gmail_client: found email — from=%s subject=%s", sender, subject[:60])

        diff = _extract_json_from_body(body)
        if diff is None:
            log.warning("gmail_client: could not extract JSON from email body")
        return diff
