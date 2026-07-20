import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone

import config
import curate_local
import publish
import sources
import summarize
import sync_preferences_from_email

log = logging.getLogger("run_daily")

LOCK_STALE_SECONDS = 2 * 60 * 60


def _setup_logging(date_str: str) -> None:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(config.LOGS_DIR / f"run_{date_str}.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _load_state() -> dict:
    if config.LAST_RUN_STATE.exists():
        return json.loads(config.LAST_RUN_STATE.read_text())
    return {}


def _save_state(state: dict) -> None:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    config.LAST_RUN_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def _acquire_lock() -> bool:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    if config.RUN_LOCK.exists():
        age = time.time() - config.RUN_LOCK.stat().st_mtime
        if age < LOCK_STALE_SECONDS:
            return False
        log.warning("stale lock (age=%.0fs), taking over", age)
    config.RUN_LOCK.write_text(str(time.time()))
    return True


def _release_lock() -> None:
    config.RUN_LOCK.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="ignore the once-a-day idempotency guard")
    parser.add_argument("--no-push", action="store_true", help="write data files but skip git commit/push")
    args = parser.parse_args()

    today = datetime.now(timezone.utc).astimezone().date().isoformat()
    _setup_logging(today)

    state = _load_state()
    if not args.force and state.get("last_success_date") == today:
        log.info("already ran successfully today (%s), exiting", today)
        return 0

    if not _acquire_lock():
        log.warning("another run appears to be in progress, exiting")
        return 0

    try:
        prefs = json.loads(config.PREFERENCES_JSON.read_text())

        since_iso = state.get("last_gmail_check_at", "1970-01-01T00:00:00+00:00")
        gmail_result = sync_preferences_from_email.sync_from_gmail(since_iso)
        if gmail_result:
            sync_preferences_from_email.apply_diff(gmail_result["diff"])
            prefs = json.loads(config.PREFERENCES_JSON.read_text())
        state["last_gmail_check_at"] = datetime.now(timezone.utc).isoformat()

        enabled_subjects = [s for s in prefs["subjects"] if s.get("enabled")]
        subject_keys = [s["key"] for s in enabled_subjects]

        fetched = sources.fetch_all_headlines()
        headlines = fetched["headlines"]
        if not headlines:
            log.error("no headlines fetched from any source, aborting without overwriting latest.json")
            return 1

        try:
            labels_by_id = curate_local.curate_all(headlines, subject_keys)
            reduced = curate_local.select_curated_subset(headlines, labels_by_id, subject_keys)
            log.info("local curation reduced %d headlines to %d", len(headlines), len(reduced))
        except Exception as exc:  # noqa: BLE001 - Ollama being unavailable must not block the run
            log.warning("local curation failed, falling back to raw capped headlines: %s", exc)
            reduced = headlines

        digest = summarize.summarize(reduced, enabled_subjects)

        publish.write_latest(digest, today, fetched["sources_fetched"], fetched["sources_failed"])

        if not args.no_push:
            publish.commit_and_push(today)

        state["last_success_date"] = today
        state["last_success_at"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)
        log.info("run complete for %s", today)
        return 0

    finally:
        _release_lock()


if __name__ == "__main__":
    sys.exit(main())
