"""Thin client for a local Ollama server. Nothing here talks to the internet."""
import json
import re

import httpx

from . import config

_chosen: str | None = None


class LLMUnavailable(RuntimeError):
    pass


def installed_models() -> list[str]:
    try:
        r = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception as e:  # noqa: BLE001
        raise LLMUnavailable(f"Ollama is not reachable at {config.OLLAMA_URL}: {e}") from e


def model_name() -> str:
    """Explicit DVA_MODEL wins; otherwise prefer an installed Gemma, then anything installed."""
    global _chosen
    if config.OLLAMA_MODEL:
        return config.OLLAMA_MODEL
    if _chosen:
        return _chosen
    names = installed_models()
    if not names:
        raise LLMUnavailable("Ollama is running but has no models. Try: ollama pull gemma3:4b")
    gemmas = [n for n in names if n.lower().startswith("gemma") and "embed" not in n.lower()]
    _chosen = (gemmas or names)[0]
    return _chosen


def chat(system: str, user: str, *, json_mode: bool = False, temperature: float = 0.3) -> str:
    body = {
        "model": model_name(),
        "stream": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {"temperature": temperature, "num_ctx": 8192},
    }
    if json_mode:
        body["format"] = "json"
    try:
        r = httpx.post(f"{config.OLLAMA_URL}/api/chat", json=body, timeout=600)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise LLMUnavailable(str(e)) from e
    return r.json()["message"]["content"].strip()


def chat_json(system: str, user: str) -> dict:
    raw = chat(system, user, json_mode=True)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)  # small models sometimes wrap JSON in prose
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}
