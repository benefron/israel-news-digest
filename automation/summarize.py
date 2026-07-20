import json
import logging
import subprocess

import config

log = logging.getLogger(__name__)

PLACEHOLDER_SUMMARY = "לא הצלחנו להפיק סיכום אוטומטי הפעם — הנה הכותרות הגולמיות."


def _degraded_result(headlines: list[dict], subjects: list[dict]) -> dict:
    by_id = {h["id"]: h for h in headlines}
    top = headlines[:8]
    return {
        "top_general": {"summary_he": PLACEHOLDER_SUMMARY, "headlines": top},
        "security_war": {"summary_he": PLACEHOLDER_SUMMARY, "headlines": []},
        "subjects": [],
        "degraded": True,
    }


def _resolve_ids(ids: list[str], by_id: dict[str, dict]) -> list[dict]:
    # Unresolvable ids (the LLM referencing something it wasn't given) are
    # silently dropped rather than surfaced — this is the hallucination
    # guard: an invented id just resolves to nothing, never a fake URL.
    return [by_id[i] for i in ids if i in by_id]


def summarize(headlines: list[dict], enabled_subjects: list[dict]) -> dict:
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
    schema = (config.PROMPTS_DIR / "summarize_schema.json").read_text()
    prompt = f"{instructions}\n\nקרא את הקובץ הזה: {config.SUMMARIZE_INPUT_SCRATCH}"

    try:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--model", config.SUMMARIZE_MODEL,
                "--safe-mode",
                "--allowedTools", "Read",
                "--output-format", "json",
                "--json-schema", schema,
                "--max-budget-usd", config.SUMMARIZE_MAX_BUDGET_USD,
            ],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude exited {result.returncode}: {result.stderr[:500]}")

        envelope = json.loads(result.stdout)
        if envelope.get("is_error"):
            raise RuntimeError(f"claude reported an error: {envelope}")

        structured = envelope["structured_output"]

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

    except Exception as exc:  # noqa: BLE001 - any failure here must degrade, never crash the run
        log.error("summarize step failed, degrading: %s", exc)
        return _degraded_result(headlines, enabled_subjects)
