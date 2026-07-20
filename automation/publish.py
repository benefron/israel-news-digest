import json
import logging
import subprocess
from datetime import datetime, timezone

import config

log = logging.getLogger(__name__)


def write_latest(
    digest: dict, date_str: str, run_id: str, sources_fetched: list[str], sources_failed: list[str],
    world_digest: dict | None = None,
) -> dict:
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
    if world_digest is not None:
        payload["world"] = world_digest
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    config.LATEST_JSON.write_text(json_text)

    # Mirror into site/data/ so the PWA (served from site/) can fetch it at
    # the expected relative path "data/latest.json".
    site_data_dir = config.REPO_ROOT / "site" / "data"
    site_data_dir.mkdir(parents=True, exist_ok=True)
    (site_data_dir / "latest.json").write_text(json_text)

    # run_id (not just date_str) since this can run several times a day —
    # each slot keeps its own archive snapshot instead of clobbering the last.
    config.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = config.ARCHIVE_DIR / f"{run_id}.json"
    archive_path.write_text(json_text)

    return payload


def _run_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=config.REPO_ROOT, capture_output=True, text=True, check=True
    )


def commit_and_push(run_id: str) -> bool:
    """Returns True if a commit was made and pushed, False if there was
    nothing to commit."""
    archive_path = config.ARCHIVE_DIR / f"{run_id}.json"
    site_latest = config.REPO_ROOT / "site" / "data" / "latest.json"
    paths = [str(config.LATEST_JSON), str(archive_path), str(config.PREFERENCES_JSON), str(site_latest)]

    _run_git("add", *paths)

    status = _run_git("status", "--porcelain", "--", *paths)
    if not status.stdout.strip():
        log.info("nothing to commit for %s", run_id)
        return False

    _run_git("commit", "-m", f"עדכון חדשות — {run_id}")
    _run_git("push", "origin", "main")
    log.info("pushed digest for %s", run_id)
    return True
