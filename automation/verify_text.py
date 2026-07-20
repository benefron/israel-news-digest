import json
import logging

import config
import llm_runner

log = logging.getLogger(__name__)

_VERIFY_SCHEMA = json.loads((config.PROMPTS_DIR / "verify_schema.json").read_text())


def verify_summaries(digest: dict) -> dict:
    """Proofreading pass only — corrects Hebrew spelling/grammar/sense in the
    Haiku-written summary text. Never sees headlines/urls, so it has no way
    to introduce a hallucinated link. Non-fatal: any failure returns the
    original digest unchanged, since Haiku's text is already publishable."""
    if digest.get("degraded"):
        return digest

    scratch_input = {
        "top_general_summary": digest["top_general"]["summary_he"],
        "security_war_summary": digest["security_war"]["summary_he"],
        "subjects": [{"key": s["key"], "summary": s["summary_he"]} for s in digest["subjects"]],
    }

    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    scratch_path = config.STATE_DIR / "verify_input.json"
    scratch_path.write_text(json.dumps(scratch_input, ensure_ascii=False, indent=2))

    instructions = (config.PROMPTS_DIR / "verify_instructions.txt").read_text()
    schema = _VERIFY_SCHEMA

    try:
        structured = llm_runner.run_with_schema(
            instructions=instructions,
            input_path=scratch_path,
            schema=schema,
            claude_model=config.VERIFY_MODEL,
            claude_max_budget=config.VERIFY_MAX_BUDGET_USD,
            copilot_fallback_model=config.COPILOT_FALLBACK_VERIFY_MODEL,
        )

        digest["top_general"]["summary_he"] = structured["top_general_summary"]
        digest["security_war"]["summary_he"] = structured["security_war_summary"]
        corrected_by_key = {s["key"]: s["summary"] for s in structured["subjects"]}
        for subject in digest["subjects"]:
            if subject["key"] in corrected_by_key:
                subject["summary_he"] = corrected_by_key[subject["key"]]

        log.info("verification pass applied")
        return digest

    except Exception as exc:  # noqa: BLE001 - Haiku's text is already good enough to publish
        log.warning("verification pass failed, keeping text as-is: %s", exc)
        return digest
