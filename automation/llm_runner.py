"""LLM invocation abstraction with automatic GitHub Copilot API fallback.

Primary path: Claude CLI (`claude -p ...` with structured JSON output).
Fallback path: GitHub Copilot chat completions API via httpx, authenticated
with `gh auth token`. Triggered on any Claude failure (non-zero exit, timeout,
parse error). Both paths return the same structured dict.
"""
import json
import logging
import subprocess
from pathlib import Path

import httpx

import config

log = logging.getLogger(__name__)


def _gh_token() -> str:
    result = subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh auth token failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _call_copilot(system_msg: str, user_msg: str, model: str) -> str:
    """Returns the raw text content from the first choice."""
    token = _gh_token()
    resp = httpx.post(
        f"{config.COPILOT_API_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Copilot-Integration-Id": config.COPILOT_INTEGRATION_ID,
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
        },
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _try_claude(
    prompt: str,
    schema: dict,
    model: str,
    max_budget: str,
) -> dict:
    """Runs Claude CLI and returns the structured output dict. Raises on any failure."""
    result = subprocess.run(
        [
            "claude", "-p", prompt,
            "--model", model,
            "--safe-mode",
            "--allowedTools", "Read",
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            "--max-budget-usd", max_budget,
        ],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude exited {result.returncode}: {result.stderr[:500]}")
    envelope = json.loads(result.stdout)
    if envelope.get("is_error"):
        raise RuntimeError(f"claude reported an error: {envelope}")
    return envelope["structured_output"]


def _try_copilot(
    instructions: str,
    input_path: Path,
    schema: dict,
    fallback_model: str,
) -> dict:
    """Calls the Copilot API with instructions + file content and returns parsed JSON."""
    file_content = input_path.read_text(encoding="utf-8")
    schema_text = json.dumps(schema, ensure_ascii=False, indent=2)
    system_msg = (
        f"{instructions}\n\n"
        "IMPORTANT: Return ONLY a valid JSON object matching this exact schema. "
        "Do not include any explanation, markdown, or text before or after the JSON.\n\n"
        f"Required JSON schema:\n{schema_text}"
    )
    raw = _call_copilot(system_msg, file_content, fallback_model)

    # Strip any accidental markdown fences
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()

    return json.loads(raw)


def run_with_schema(
    instructions: str,
    input_path: Path,
    schema: dict,
    claude_model: str,
    claude_max_budget: str,
    copilot_fallback_model: str,
) -> dict:
    """Returns the structured output dict. Tries Claude CLI first, then Copilot API.

    Raises only if both backends fail — callers should handle this and degrade
    gracefully (e.g. return a degraded digest or pass through unchanged text).

    Args:
        instructions: Text of the instructions prompt (loaded from prompts/*.txt).
        input_path: Path to the scratch JSON file that Claude reads via the Read
                    tool. For the Copilot path this file's content is sent inline.
        schema: Parsed JSON schema dict.
        claude_model: Model ID for the Claude CLI call.
        claude_max_budget: Budget cap string for the Claude CLI call.
        copilot_fallback_model: Model ID for the Copilot API fallback.
    """
    prompt = f"{instructions}\n\nקרא את הקובץ הזה: {input_path}"

    try:
        structured = _try_claude(prompt, schema, claude_model, claude_max_budget)
        log.info("llm_runner: used Claude CLI (%s)", claude_model)
        return structured
    except Exception as claude_exc:
        log.warning(
            "llm_runner: Claude failed (%s), trying Copilot API fallback", claude_exc
        )

    structured = _try_copilot(instructions, input_path, schema, copilot_fallback_model)
    log.info("llm_runner: used Copilot API fallback (%s)", copilot_fallback_model)
    return structured
