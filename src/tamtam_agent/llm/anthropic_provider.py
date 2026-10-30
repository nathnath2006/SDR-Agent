"""Fournisseur Anthropic (SDK officiel `anthropic`)."""

from __future__ import annotations

import json

import anthropic

from . import LLMClient, LLMError, ResearchResult, extract_json

# Modèles qui acceptent le repli serveur en cas de refus (`fallbacks="default"`).
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_MAX_PAUSE_RESUMES = 3


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def __init__(self, model, cache_dir=None, api_key=None) -> None:
        super().__init__(model, cache_dir)
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=4) if api_key else anthropic.Anthropic(max_retries=4)

    def _create(self, **params):
        if self.model in _FALLBACK_MODELS:
            params |= {"betas": [_FALLBACK_BETA], "fallbacks": "default"}
        try:
            response = self.client.beta.messages.create(model=self.model, max_tokens=16000, **params)
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic {exc.status_code} : {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"Anthropic injoignable : {exc}") from exc
        if response.stop_reason == "refusal":
            raise LLMError("Requête refusée par le modèle")
        return response

    def _json(self, system, prompt, schema, effort):
        response = self._create(
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        )
        if response.stop_reason == "max_tokens":
            raise LLMError("Réponse tronquée (max_tokens)")
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"JSON invalide : {text[:200]!r}") from exc

    def _research(self, system, prompt):
        messages = [{"role": "user", "content": prompt}]
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}]
        response = self._create(system=system, messages=messages, tools=tools,
                                output_config={"effort": "medium"})
        # La boucle serveur peut se mettre en pause : on renvoie le tour tel quel pour reprendre.
        for _ in range(_MAX_PAUSE_RESUMES):
            if response.stop_reason != "pause_turn":
                break
            messages = [*messages, {"role": "assistant", "content": response.content}]
            response = self._create(system=system, messages=messages, tools=tools,
                                    output_config={"effort": "medium"})

        texts, sources, seen = [], [], set()
        for block in response.content:
            if block.type == "text":
                texts.append(block.text)
                for cit in getattr(block, "citations", None) or []:
                    url = getattr(cit, "url", None)
                    if url and url not in seen:
                        seen.add(url)
                        sources.append({"url": url, "titre": getattr(cit, "title", "") or ""})
            elif block.type == "web_search_tool_result" and isinstance(block.content, list):
                for res in block.content:
                    if res.url not in seen:
                        seen.add(res.url)
                        sources.append({"url": res.url, "titre": res.title or ""})
        text = "".join(texts)
        extract_json(text)   # échoue tôt si la réponse n'a pas le format attendu
        return ResearchResult(text=text, sources=sources)
