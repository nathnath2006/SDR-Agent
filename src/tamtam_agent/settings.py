"""Réglages LLM de la ligne de commande, lus dans .env (jamais versionné).

L'interface web ne s'en sert pas : chaque utilisateur y apporte sa clé."""

from __future__ import annotations

import os

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
