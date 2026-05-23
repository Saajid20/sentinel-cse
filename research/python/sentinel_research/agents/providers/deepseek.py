from __future__ import annotations

import os

from openai import OpenAI

from sentinel_research.agents.providers.base import BaseLLMProvider

_DEFAULT_BASE_URL = "https://api.deepseek.com"
_DEFAULT_MODEL = "deepseek-chat"


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek-backed LLM provider for R10 context/risk intelligence.

    Sends documents to the DeepSeek chat completions API and returns raw
    text output. JSON parsing and schema validation are handled externally.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        resolved_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not resolved_key:
            raise ValueError(
                "No DeepSeek API key provided. Set DEEPSEEK_API_KEY or pass api_key."
            )

        self._base_url = (
            base_url
            or os.environ.get("DEEPSEEK_BASE_URL", "").strip()
            or _DEFAULT_BASE_URL
        )
        self._model = model or os.environ.get("DEEPSEEK_MODEL", "").strip() or _DEFAULT_MODEL

        self._client = OpenAI(
            api_key=resolved_key,
            base_url=self._base_url,
            timeout=timeout,
        )

    def analyze_context(self, document: str, prompt: str) -> str:
        if not document.strip():
            raise ValueError("document must not be empty")
        if not prompt.strip():
            raise ValueError("prompt must not be empty")

        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        "Analyze the following CSE-related document and return JSON only.\n\n"
                        f"{document}"
                    ),
                },
            ],
        )

        choices = response.choices
        if not choices:
            raise RuntimeError("DeepSeek response contained no choices")

        content = choices[0].message.content
        if not content or not content.strip():
            raise ValueError("DeepSeek response content was empty")

        return content.strip()
