"""Réglages LLM enregistrés dans le .env local (jamais versionné)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .llm import DEFAULT_MODELS

PROVIDER_VAR = "TAMTAM_LLM_PROVIDER"
KEY_VARS = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
MODEL_VARS = {"gemini": "GEMINI_MODEL", "anthropic": "ANTHROPIC_MODEL"}


def key_for(provider: str) -> str:
    if provider == "gemini":
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
    return os.getenv(KEY_VARS.get(provider, ""), "")


def active_provider() -> str | None:
    """Fournisseur choisi dans les réglages, sinon le premier dont la clé existe."""
    chosen = os.getenv(PROVIDER_VAR, "").lower()
    if chosen in KEY_VARS and key_for(chosen):
        return chosen
    return next((p for p in ("anthropic", "gemini") if key_for(p)), None)


def describe() -> dict:
    def hint(key: str) -> str:
        return f"{key[:4]}…{key[-4:]}" if len(key) > 12 else ("défini" if key else "")
    return {
        "provider": active_provider(),
        "providers": {p: {"key_set": bool(key_for(p)), "key_hint": hint(key_for(p)),
                          "model": os.getenv(MODEL_VARS[p], DEFAULT_MODELS[p])} for p in KEY_VARS},
    }


def save(env_path: Path, provider: str, api_key: str | None = None, model: str | None = None) -> None:
    """Écrit les valeurs dans .env (en conservant les autres lignes) et dans l'environnement courant."""
    if provider not in KEY_VARS:
        raise ValueError(f"fournisseur inconnu : {provider}")
    values = {PROVIDER_VAR: provider}
    if api_key:
        values[KEY_VARS[provider]] = api_key.strip()
    if model:
        values[MODEL_VARS[provider]] = model.strip()

    lines = env_path.read_text().splitlines() if env_path.exists() else []
    for name, value in values.items():
        pattern = re.compile(rf"^\s*#?\s*{name}\s*=")
        line = f"{name}={value}"
        for i, existing in enumerate(lines):
            if pattern.match(existing):
                lines[i] = line
                break
        else:
            lines.append(line)
        os.environ[name] = value
    env_path.write_text("\n".join(lines) + "\n")
    env_path.chmod(0o600)
