import json
import logging
import subprocess
from datetime import datetime, timezone

import config

log = logging.getLogger(__name__)


def write_latest(digest: dict, date_str: str, sources_fetched: list[str], sources_failed: list[str]) -> dict:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date": date_str,
        "degraded": digest.get("degraded", False),
        "top_general": digest["top_general"],
        "security_war": digest["security_war"],
        "subjects": digest["subjects"],
        "sources_fetched": sources_fetched,
        "sources_failed": sources_failed,
    }
    config.LATEST_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    config.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = config.ARCHIVE_DIR / f"{date_str}.json"
    archive_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    return payload


def _run_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=config.REPO_ROOT, capture_output=True, text=True, check=True
    )


def commit_and_push(date_str: str) -> bool:
    """Returns True if a commit was made and pushed, False if there was
    nothing to commit."""
    archive_path = config.ARCHIVE_DIR / f"{date_str}.json"
    paths = [str(config.LATEST_JSON), str(archive_path), str(config.PREFERENCES_JSON)]

    _run_git("add", *paths)

    status = _run_git("status", "--porcelain", "--", *paths)
    if not status.stdout.strip():
        log.info("nothing to commit for %s", date_str)
        return False

    _run_git("commit", "-m", f"עדכון חדשות יומי — {date_str}")
    _run_git("push", "origin", "main")
    log.info("pushed digest for %s", date_str)
    return True
