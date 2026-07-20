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
        timeout=150,  # first call each day cold-loads the model into memory
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


_WORLD_CURATION_SCHEMA = {
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

_WORLD_CATEGORIES = {
    "israel_jewish": (
        "Any headline about Israel, IDF, Gaza, West Bank, Israeli politics, antisemitism, "
        "Jewish communities in Belgium/Europe/worldwide, Holocaust remembrance, or hostages"
    ),
    "belgium_top": (
        "Belgian national news, Flemish region, Brussels, Leuven, Belgian politics, "
        "Belgian climate/environment, Belgian economy"
    ),
    "europe_top": (
        "European Union, EU institutions, European countries' domestic politics, NATO, "
        "European economy, European society"
    ),
    "world_top": (
        "Major global headlines not covered by the categories above: wars, disasters, "
        "elections, international diplomacy"
    ),
}


def _world_prompt_for_batch(batch: list[dict]) -> str:
    category_lines = "\n".join(f"- {k}: {v}" for k, v in _WORLD_CATEGORIES.items())
    lines = [
        "Classify each headline into ONE of the following categories (or leave labels empty if none fits):",
        category_lines,
        "",
        "Headlines (id: title):",
    ]
    for h in batch:
        lines.append(f'{h["id"]}: {h["title"]}')
    return "\n".join(lines)


def curate_world_batch(batch: list[dict]) -> dict[str, list[str]]:
    """Classify a batch of world headlines into world curation categories."""
    import json
    resp = httpx.post(
        f"{config.OLLAMA_BASE_URL}/api/chat",
        json={
            "model": config.OLLAMA_CURATION_MODEL,
            "messages": [{"role": "user", "content": _world_prompt_for_batch(batch)}],
            "format": _WORLD_CURATION_SCHEMA,
            "stream": False,
        },
        timeout=150,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    parsed = json.loads(content)
    return {c["id"]: c.get("labels", []) for c in parsed.get("classifications", [])}


def curate_world_all(headlines: list[dict]) -> dict[str, list[str]]:
    """Batch world headlines through the local model for classification."""
    result: dict[str, list[str]] = {}
    for i in range(0, len(headlines), config.OLLAMA_BATCH_SIZE):
        batch = headlines[i : i + config.OLLAMA_BATCH_SIZE]
        result.update(curate_world_batch(batch))
    return result


def select_world_subset(
    headlines: list[dict],
    labels_by_id: dict[str, list[str]],
    israel_cap: int = 10,
    belgium_cap: int = 8,
    europe_cap: int = 6,
    world_cap: int = 6,
) -> list[dict]:
    """Pick the most relevant world headlines per category for the LLM call."""
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

    take("israel_jewish", israel_cap)
    take("belgium_top", belgium_cap)
    take("europe_top", europe_cap)
    take("world_top", world_cap)

    return list(selected.values())
