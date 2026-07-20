import json
import logging

import config
import llm_runner

log = logging.getLogger(__name__)

PLACEHOLDER_SUMMARY = "לא הצלחנו להפיק סיכום אוטומטי הפעם — הנה הכותרות הגולמיות."
PLACEHOLDER_SUMMARY_EN = "Automatic summary unavailable — raw headlines shown below."

_SUMMARIZE_SCHEMA_PATH = config.PROMPTS_DIR / "summarize_schema.json"
_UPDATE_SCHEMA_PATH = config.PROMPTS_DIR / "update_schema.json"
_SUMMARIZE_WORLD_SCHEMA_PATH = config.PROMPTS_DIR / "summarize_world_schema.json"
_UPDATE_WORLD_SCHEMA_PATH = config.PROMPTS_DIR / "update_world_schema.json"


def _degraded_result(headlines: list[dict], subjects: list[dict]) -> dict:
    top = headlines[:8]
    return {
        "top_general": {"summary_he": PLACEHOLDER_SUMMARY, "headlines": top},
        "security_war": {"summary_he": PLACEHOLDER_SUMMARY, "headlines": []},
        "subjects": [],
        "degraded": True,
    }


def _resolve_ids(ids: list[str], by_id: dict[str, dict]) -> list[dict]:
    # Unresolvable ids (the LLM referencing something it wasn't given) are
    # silently dropped — invented ids resolve to nothing, never a fake URL.
    return [by_id[i] for i in ids if i in by_id]


def _structured_to_digest(structured: dict, by_id: dict, enabled_subjects: list[dict]) -> dict:
    top_general = {
        "summary_he": structured["top_general"]["summary_he"],
        "headlines": _resolve_ids(structured["top_general"]["headline_ids"], by_id),
    }
    security_war = {
        "summary_he": structured["security_war"]["summary_he"],
        "headlines": _resolve_ids(structured["security_war"]["headline_ids"], by_id),
    }
    subjects = []
    for s in structured.get("subjects", []):
        resolved = _resolve_ids(s["headline_ids"], by_id)
        if not resolved:
            continue
        label = next((es["label_he"] for es in enabled_subjects if es["key"] == s["key"]), s["key"])
        subjects.append({"key": s["key"], "label_he": label, "summary_he": s["summary_he"], "headlines": resolved})
    return {"top_general": top_general, "security_war": security_war, "subjects": subjects, "degraded": False}


def summarize(headlines: list[dict], enabled_subjects: list[dict]) -> dict:
    """Full regeneration from scratch."""
    by_id = {h["id"]: h for h in headlines}

    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    scratch_input = {
        "headlines": [
            {"id": h["id"], "source": h["source_label_he"], "title": h["title"], "published_at": h["published_at"]}
            for h in headlines
        ],
        "subjects": [{"key": s["key"], "label_he": s["label_he"]} for s in enabled_subjects],
    }
    config.SUMMARIZE_INPUT_SCRATCH.write_text(json.dumps(scratch_input, ensure_ascii=False, indent=2))

    instructions = (config.PROMPTS_DIR / "summarize_instructions.txt").read_text()
    schema = json.loads(_SUMMARIZE_SCHEMA_PATH.read_text())

    try:
        structured = llm_runner.run_with_schema(
            instructions=instructions,
            input_path=config.SUMMARIZE_INPUT_SCRATCH,
            schema=schema,
            claude_model=config.SUMMARIZE_MODEL,
            claude_max_budget=config.SUMMARIZE_MAX_BUDGET_USD,
            copilot_fallback_model=config.COPILOT_FALLBACK_SUMMARIZE_MODEL,
        )
        return _structured_to_digest(structured, by_id, enabled_subjects)
    except Exception as exc:  # noqa: BLE001
        log.error("summarize step failed, degrading: %s", exc)
        return _degraded_result(headlines, enabled_subjects)


def update_incrementally(
    existing_digest: dict,
    new_headlines: list[dict],
    all_headlines: list[dict],
    enabled_subjects: list[dict],
) -> dict:
    """Lightweight update: adjusts existing summaries to incorporate new headlines.

    Used when only a small number of new headlines have arrived since the last
    digest — cheaper than a full regeneration and still keeps the digest fresh.
    Falls back to returning the existing digest unchanged on any failure.
    """
    by_id = {h["id"]: h for h in all_headlines}

    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    scratch_path = config.STATE_DIR / "update_input.json"

    # Provide the existing summaries (text only, not raw headline objects) and
    # the new headlines so the model can decide what to adjust.
    existing_for_prompt = {
        "top_general": {
            "summary_he": existing_digest["top_general"]["summary_he"],
            "headline_ids": [h["id"] for h in existing_digest["top_general"].get("headlines", [])],
        },
        "security_war": {
            "summary_he": existing_digest["security_war"]["summary_he"],
            "headline_ids": [h["id"] for h in existing_digest["security_war"].get("headlines", [])],
        },
        "subjects": [
            {
                "key": s["key"],
                "label_he": s["label_he"],
                "summary_he": s["summary_he"],
                "headline_ids": [h["id"] for h in s.get("headlines", [])],
            }
            for s in existing_digest.get("subjects", [])
        ],
    }
    scratch_input = {
        "existing_digest": existing_for_prompt,
        "new_headlines": [
            {"id": h["id"], "source": h["source_label_he"], "title": h["title"], "published_at": h["published_at"]}
            for h in new_headlines
        ],
        "subjects": [{"key": s["key"], "label_he": s["label_he"]} for s in enabled_subjects],
    }
    scratch_path.write_text(json.dumps(scratch_input, ensure_ascii=False, indent=2))

    instructions = (config.PROMPTS_DIR / "update_instructions.txt").read_text()
    schema = json.loads(_UPDATE_SCHEMA_PATH.read_text())

    try:
        structured = llm_runner.run_with_schema(
            instructions=instructions,
            input_path=scratch_path,
            schema=schema,
            claude_model=config.SUMMARIZE_MODEL,
            claude_max_budget=config.SUMMARIZE_MAX_BUDGET_USD,
            copilot_fallback_model=config.COPILOT_FALLBACK_SUMMARIZE_MODEL,
        )
        updated = _structured_to_digest(structured, by_id, enabled_subjects)
        log.info("incremental update applied (%d new headlines)", len(new_headlines))
        return updated
    except Exception as exc:  # noqa: BLE001
        log.warning("incremental update failed, keeping existing digest: %s", exc)
        return existing_digest


# ── World / Belgium / Europe pipeline ─────────────────────────────────────────

def _degraded_world_result(headlines: list[dict]) -> dict:
    top = headlines[:6]
    return {
        "israel_jewish": {"summary_en": PLACEHOLDER_SUMMARY_EN, "headlines": top},
        "belgium":       {"summary_en": PLACEHOLDER_SUMMARY_EN, "headlines": []},
        "europe":        {"summary_en": PLACEHOLDER_SUMMARY_EN, "headlines": []},
        "world_top":     {"summary_en": PLACEHOLDER_SUMMARY_EN, "headlines": []},
        "degraded": True,
    }


def _structured_to_world_digest(structured: dict, by_id: dict) -> dict:
    sections = {}
    for key in ("israel_jewish", "belgium", "europe", "world_top"):
        sec = structured.get(key, {})
        resolved = []
        for item in sec.get("headlines", []):
            if isinstance(item, dict):
                hid = item.get("id")
                if hid and hid in by_id:
                    h = dict(by_id[hid])
                    title_en = (item.get("title_en") or "").strip()
                    if title_en:
                        h["title"] = title_en  # replace original (possibly Dutch) title
                    resolved.append(h)
            elif isinstance(item, str) and item in by_id:
                resolved.append(by_id[item])
        sections[key] = {
            "summary_en": sec.get("summary_en", PLACEHOLDER_SUMMARY_EN),
            "headlines": resolved,
        }
    return {**sections, "degraded": False}


def summarize_world(headlines: list[dict]) -> dict:
    """Full world digest from scratch."""
    by_id = {h["id"]: h for h in headlines}

    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    scratch_input = {
        "headlines": [
            {"id": h["id"], "source": h.get("source_label_en", h.get("source_label", "")),
             "title": h["title"], "published_at": h["published_at"]}
            for h in headlines
        ],
    }
    scratch_path = config.STATE_DIR / "summarize_world_input.json"
    scratch_path.write_text(json.dumps(scratch_input, ensure_ascii=False, indent=2))

    instructions = (config.PROMPTS_DIR / "summarize_world_instructions.txt").read_text()
    schema = json.loads(_SUMMARIZE_WORLD_SCHEMA_PATH.read_text())

    try:
        structured = llm_runner.run_with_schema(
            instructions=instructions,
            input_path=scratch_path,
            schema=schema,
            claude_model=config.SUMMARIZE_MODEL,
            claude_max_budget=config.SUMMARIZE_MAX_BUDGET_USD,
            copilot_fallback_model=config.COPILOT_FALLBACK_SUMMARIZE_MODEL,
        )
        return _structured_to_world_digest(structured, by_id)
    except Exception as exc:  # noqa: BLE001
        log.error("summarize_world failed, degrading: %s", exc)
        return _degraded_world_result(headlines)


def update_world_incrementally(
    existing_world: dict,
    new_headlines: list[dict],
    all_headlines: list[dict],
) -> dict:
    """Lightweight world update for small batches of new headlines."""
    by_id = {h["id"]: h for h in all_headlines}

    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    scratch_path = config.STATE_DIR / "update_world_input.json"

    existing_for_prompt = {}
    for key in ("israel_jewish", "belgium", "europe", "world_top"):
        sec = existing_world.get(key, {})
        existing_for_prompt[key] = {
            "summary_en": sec.get("summary_en", ""),
            # Include title so the LLM can re-emit it in title_en without needing to re-translate
            "headlines": [{"id": h["id"], "title_en": h["title"]} for h in sec.get("headlines", [])],
        }

    scratch_input = {
        "existing_world": existing_for_prompt,
        "new_headlines": [
            {"id": h["id"], "source": h.get("source_label_en", h.get("source_label", "")),
             "title": h["title"], "published_at": h["published_at"]}
            for h in new_headlines
        ],
    }
    scratch_path.write_text(json.dumps(scratch_input, ensure_ascii=False, indent=2))

    instructions = (config.PROMPTS_DIR / "update_world_instructions.txt").read_text()
    schema = json.loads(_UPDATE_WORLD_SCHEMA_PATH.read_text())

    try:
        structured = llm_runner.run_with_schema(
            instructions=instructions,
            input_path=scratch_path,
            schema=schema,
            claude_model=config.SUMMARIZE_MODEL,
            claude_max_budget=config.SUMMARIZE_MAX_BUDGET_USD,
            copilot_fallback_model=config.COPILOT_FALLBACK_SUMMARIZE_MODEL,
        )
        updated = _structured_to_world_digest(structured, by_id)
        log.info("world incremental update applied (%d new headlines)", len(new_headlines))
        return updated
    except Exception as exc:  # noqa: BLE001
        log.warning("world incremental update failed, keeping existing: %s", exc)
        return existing_world
