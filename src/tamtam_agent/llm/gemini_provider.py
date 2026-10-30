"""Fournisseur Google Gemini (SDK `google-genai`).

La clé est lue dans GEMINI_API_KEY (ou GOOGLE_API_KEY) par le SDK.
"""

from __future__ import annotations

import json

from google import genai
from google.genai import errors, types

from . import LLMClient, LLMError, ResearchResult, extract_json


class GeminiClient(LLMClient):
    provider = "gemini"

    def __init__(self, model, cache_dir=None, api_key=None) -> None:
        super().__init__(model, cache_dir)
        self.client = genai.Client(api_key=api_key) if api_key else genai.Client()

    def _generate(self, prompt: str, config: types.GenerateContentConfig):
        try:
            return self.client.models.generate_content(model=self.model, contents=prompt, config=config)
        except errors.APIError as exc:
            raise LLMError(f"Gemini {exc.code} : {exc.message}") from exc

    def _json(self, system, prompt, schema, effort):
        response = self._generate(prompt, types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
        ))
        text = response.text or ""
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"JSON invalide : {text[:200]!r}") from exc

    def _research(self, system, prompt):
        response = self._generate(prompt, types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ))
        text = response.text or ""
        sources, seen = [], set()
        for cand in response.candidates or []:
            meta = cand.grounding_metadata
            for chunk in (meta.grounding_chunks or []) if meta else []:
                web = chunk.web
                if web and web.uri and web.uri not in seen:
                    seen.add(web.uri)
                    # Les URI Gemini sont des redirections : on garde aussi le domaine.
                    sources.append({"url": web.uri, "titre": web.title or web.domain or ""})
        extract_json(text)
        return ResearchResult(text=text, sources=sources)
