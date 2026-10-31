"""Accès LLM, indépendant du fournisseur (Anthropic ou Gemini).

Deux opérations suffisent à l'agent :
- `json` : réponse JSON contrainte par un schéma (classification, rédaction) ;
- `research` : recherche web avec sources (vérification marketplace, D5).

Chaque appel est mis en cache sur disque (relance reproductible et gratuite)
et journalisé (entrée, sortie, fournisseur, modèle).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MODELS = {"anthropic": "claude-opus-5-5", "gemini": "gemini-3.5-flash"}


class LLMError(RuntimeError):
    """Réponse inexploitable (refus, JSON invalide, erreur API)."""


@dataclass
class ResearchResult:
    text: str
    sources: list[dict] = field(default_factory=list)   # [{"url", "titre"}] renvoyées par l'outil de recherche

    def to_dict(self) -> dict:
        return {"text": self.text, "sources": self.sources}


class LLMClient(ABC):
    provider: str = ""

    def __init__(self, model: str, cache_dir: Path | None = None) -> None:
        self.model = model
        self.cache_dir = cache_dir
        self.log_path: Path | None = None

    # --- API publique ---------------------------------------------------------
    def json(self, system: str, prompt: str, schema: dict, task: str, effort: str = "medium") -> dict:
        key = self._key("json", system, prompt, json.dumps(schema, sort_keys=True))
        cached = self._cache_get(key)
        if cached is not None:
            self._log(task, prompt, cached, cached=True)
            return cached
        result = self._json(system, prompt, schema, effort)
        self._cache_put(key, result)
        self._log(task, prompt, result, cached=False)
        return result

    def research(self, system: str, prompt: str, task: str) -> ResearchResult:
        key = self._key("research", system, prompt)
        cached = self._cache_get(key)
        if cached is not None:
            self._log(task, prompt, cached, cached=True)
            return ResearchResult(**cached)
        result = self._research(system, prompt)
        self._cache_put(key, result.to_dict())
        self._log(task, prompt, result.to_dict(), cached=False)
        return result

    # --- À implémenter par fournisseur ---------------------------------------
    @abstractmethod
    def _json(self, system: str, prompt: str, schema: dict, effort: str) -> dict: ...

    @abstractmethod
    def _research(self, system: str, prompt: str) -> ResearchResult: ...

    # --- Cache et journal -----------------------------------------------------
    def _key(self, *parts: str) -> str:
        h = hashlib.sha256("\x1f".join((self.provider, self.model, *parts)).encode())
        return h.hexdigest()[:32]

    def _cache_get(self, key: str) -> dict | None:
        if not self.cache_dir:
            return None
        path = self.cache_dir / f"{key}.json"
        return json.loads(path.read_text()) if path.exists() else None

    def _cache_put(self, key: str, value: dict) -> None:
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{key}.json").write_text(json.dumps(value, ensure_ascii=False, indent=1))

    def _log(self, task: str, prompt: str, output: dict, cached: bool) -> None:
        if not self.log_path:
            return
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "task": task,
                 "provider": self.provider, "model": self.model, "cached": cached,
                 "prompt": prompt, "output": output}
        with self.log_path.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def extract_json(text: str) -> dict:
    """JSON d'une réponse libre (recherche web) : bloc ```json``` ou premier objet."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text[text.find("{"): text.rfind("}") + 1]
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMError(f"JSON introuvable dans la réponse : {text[:200]!r}") from exc


def get_llm(provider: str = "auto", cache_dir: Path | None = None, api_key: str | None = None,
            model: str | None = None) -> LLMClient | None:
    """Choisit le fournisseur. 'auto' : celui des réglages, sinon celui dont la clé existe,
    sinon None (décisions calculées, aucun texte rédigé). `api_key` et `model` remplacent l'environnement."""
    provider = (provider or "auto").lower()
    if provider == "none":
        return None
    if provider == "auto":
        from ..settings import active_provider   # réglage TAMTAM_LLM_PROVIDER, sinon la clé disponible
        provider = active_provider()
        if provider is None:
            return None
    if provider == "anthropic":
        from .anthropic_provider import AnthropicClient
        return AnthropicClient(model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODELS["anthropic"]), cache_dir, api_key)
    if provider == "gemini":
        from .gemini_provider import GeminiClient
        return GeminiClient(model or os.getenv("GEMINI_MODEL", DEFAULT_MODELS["gemini"]), cache_dir, api_key)
    raise ValueError(f"Fournisseur LLM inconnu : {provider} (anthropic, gemini, auto, none)")
