import logging

import httpx

import config

log = logging.getLogger(__name__)

CURATION_SCHEMA = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "labels"],
            },
        }
    },
    "required": ["classifications"],
}


def _prompt_for_batch(batch: list[dict], subject_keys: list[str]) -> str:
    lines = [
        "סווג כל כותרת חדשות (בעברית) לאחת או יותר מהתוויות הבאות, או תווית ריקה אם אף אחת לא רלוונטית:",
        "- security_war: ביטחון, מלחמה, צה\"ל, פיגועים, איראן, חיזבאללה, חמאס וכדומה",
        "- top_general: כותרת כללית וחשובה, לא בהכרח ביטחונית",
        "- " + ", ".join(subject_keys) + ": התאמה לאחד מתחומי העניין האלה, לפי מפתח (key) בלבד",
        "",
        "כותרות (id ואחריו הכותרת):",
    ]
    for h in batch:
        lines.append(f'{h["id"]}: {h["title"]}')
    return "\n".join(lines)


def curate_batch(batch: list[dict], subject_keys: list[str]) -> dict[str, list[str]]:
    """Returns {headline_id: [labels]}. Raises on any failure — caller
    decides whether to fall back to sending raw headlines to Haiku instead."""
    resp = httpx.post(
        f"{config.OLLAMA_BASE_URL}/api/chat",
        json={
            "model": config.OLLAMA_CURATION_MODEL,
            "messages": [{"role": "user", "content": _prompt_for_batch(batch, subject_keys)}],
            "format": CURATION_SCHEMA,
            "stream": False,
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]

    import json
    parsed = json.loads(content)
    return {c["id"]: c.get("labels", []) for c in parsed.get("classifications", [])}


def curate_all(headlines: list[dict], subject_keys: list[str]) -> dict[str, list[str]]:
    """Batches headlines to stay well within a small local model's comfort
    zone, rather than relying on a huge single-shot context window."""
    result: dict[str, list[str]] = {}
    for i in range(0, len(headlines), config.OLLAMA_BATCH_SIZE):
        batch = headlines[i : i + config.OLLAMA_BATCH_SIZE]
        result.update(curate_batch(batch, subject_keys))
    return result


def select_curated_subset(
    headlines: list[dict], labels_by_id: dict[str, list[str]], subject_keys: list[str],
    top_general_cap: int = 8, security_cap: int = 8, per_subject_cap: int = 5,
) -> list[dict]:
    """Shrinks ~150 raw headlines down to the ones actually worth spending a
    Haiku call on, using the cheap local classification as a filter."""
    by_id = {h["id"]: h for h in headlines}
    selected: dict[str, dict] = {}

    def take(label: str, cap: int):
        count = 0
        for hid, labels in labels_by_id.items():
            if count >= cap:
                break
            if label in labels and hid in by_id:
                selected[hid] = by_id[hid]
                count += 1

    take("top_general", top_general_cap)
    take("security_war", security_cap)
    for key in subject_keys:
        take(key, per_subject_cap)

    return list(selected.values())
