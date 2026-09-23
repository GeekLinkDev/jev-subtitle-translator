"""Small dependency-free client for OpenRouter and OpenAI-compatible endpoints."""

import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LOCAL_BASE_URL = "http://localhost:11434/v1"


def is_openrouter_url(base_url: str) -> bool:
    """Return True when an API root points at OpenRouter."""

    return urlsplit((base_url or OPENROUTER_BASE_URL).strip()).hostname == "openrouter.ai"


class OpenRouterError(RuntimeError):
    """Raised when the model endpoint cannot provide a valid response."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


TRANSLATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "translation": {"type": "string"},
                },
                "required": ["id", "translation"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

# Reasoning models think by default, which makes a 40-cue JSON batch slow and
# far more expensive than the list price suggests. Translation does not need
# chain-of-thought, so pin it off. Gemini 3.6 Flash cannot disable thinking and
# only accepts "minimal".
REASONING_BY_MODEL: dict[str, dict[str, Any]] = {
    "openai/gpt-5.6-luna": {"effort": "none", "exclude": True},
    "openai/gpt-5.6-terra": {"effort": "none", "exclude": True},
    "google/gemini-3.6-flash": {"effort": "minimal", "exclude": True},
    "anthropic/claude-sonnet-5": {"enabled": False},
    "deepseek/deepseek-v4-flash-0731": {"enabled": False},
    "deepseek/deepseek-v4-pro": {"enabled": False},
}

# These reject the legacy temperature parameter outright.
NO_TEMPERATURE_MODELS = frozenset(
    {"openai/gpt-5.6-luna", "openai/gpt-5.6-terra", "anthropic/claude-sonnet-5"}
)


class OpenRouterClient:
    """Call chat completions on OpenRouter or any OpenAI-compatible server.

    ``base_url`` is the OpenAI-style API root (``.../v1``). OpenRouter-only
    features — the Jev Decisions endpoint, provider routing, and reasoning
    controls — are used only when the host is openrouter.ai, because local
    servers such as Ollama, LM Studio, or vLLM may reject unknown fields.
    """

    def __init__(
        self,
        api_key: str = "",
        *,
        base_url: str = OPENROUTER_BASE_URL,
        timeout: float = 120.0,
        attempts: int = 3,
    ) -> None:
        self.base_url = (base_url or OPENROUTER_BASE_URL).strip().rstrip("/")
        parts = urlsplit(self.base_url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError(f"invalid base URL: {base_url!r}")
        self.is_openrouter = is_openrouter_url(self.base_url)
        self.api_key = api_key.strip()
        if self.is_openrouter and not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is required")
        self._origin = f"{parts.scheme}://{parts.netloc}"
        self.label = "OpenRouter" if self.is_openrouter else self._origin
        self.timeout = timeout
        self.attempts = max(1, attempts)

    def chat_json(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        schema_name: str = "subtitle_translations",
        schema: Mapping[str, Any] | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Request a strict JSON Schema response from a chat model."""

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema or TRANSLATION_SCHEMA,
                },
            },
        }
        if model not in NO_TEMPERATURE_MODELS:
            body["temperature"] = temperature
        if self.is_openrouter:
            # Keep OpenRouter from routing to an endpoint that ignores response_format.
            body["provider"] = {"require_parameters": True}
            if model in REASONING_BY_MODEL:
                body["reasoning"] = REASONING_BY_MODEL[model]
        payload = self._request_json(f"{self.base_url}/chat/completions", body)
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise OpenRouterError("chat response contains no choices")
        message = choices[0].get("message") or {}
        refusal = message.get("refusal")
        if refusal:
            raise OpenRouterError(f"model refusal: {refusal}")
        return _parse_json_object(_message_content(message.get("content")))

    def decisions(
        self,
        *,
        model: str,
        pairs: list[dict[str, str]],
        guidelines: str,
    ) -> dict[str, bool]:
        """Ask a Jev Decisions model for one review verdict per subtitle ID."""

        if not self.is_openrouter:
            raise OpenRouterError("the Jev Decisions endpoint is only available on OpenRouter")
        subtitles = []
        questions: dict[str, Any] = {}
        for pair in pairs:
            subtitle_id = str(pair.get("id", "")).strip()
            if not subtitle_id:
                continue
            subtitles.append(
                {
                    "id": subtitle_id,
                    "source": str(pair.get("source", "")),
                    "translation": str(pair.get("translation", "")),
                }
            )
            # Question wording mirrors GeekLink's worker (callJevDecisions); keep in sync.
            questions[subtitle_id] = {
                "type": "noul",
                "instructions": (
                    f'Judge ONLY the item in state.subtitles whose id is "{subtitle_id}". '
                    "Following state.guidelines, does that translation need human review?"
                ),
                "criteria": {
                    "true": (
                        "The translation has a genuine defect: omission, flipped negation, "
                        "changed numbers/dates/units, changed names, opposite meaning, "
                        "unsupported additions, or truncation/repetition."
                    ),
                    "false": (
                        "The translation preserves the source meaning; wording or style "
                        "differences are acceptable."
                    ),
                },
            }

        if not subtitles:
            return {}

        payload = self._request_json(
            f"{self._origin}/api/alpha/decisions",
            {
                "model": model,
                "state": {"guidelines": guidelines, "subtitles": subtitles},
                "questions": questions,
            },
        )
        answers = payload.get("answers")
        if not isinstance(answers, dict):
            raise OpenRouterError("Jev response contains no answers object")
        return {
            subtitle_id: _coerce_boolean(answers[subtitle_id])
            for subtitle_id in questions
            if subtitle_id in answers
        }

    def _request_json(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.is_openrouter:
            headers.update(
                {
                    "HTTP-Referer": "https://github.com/GeekLinkDev/jev-subtitle-translator",
                    "X-Title": "GeekLink Jev Subtitle Translator",
                    "X-OpenRouter-Metadata": "enabled",
                }
            )
        request = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        for attempt in range(self.attempts):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise OpenRouterError("API response root is not an object")
                return result
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:1000]
                retryable = exc.code == 429 or exc.code >= 500
                if not retryable or attempt == self.attempts - 1:
                    raise OpenRouterError(
                        f"{self.label} HTTP {exc.code}: {detail}", status=exc.code
                    ) from exc
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                if attempt == self.attempts - 1:
                    raise OpenRouterError(f"{self.label} request failed: {exc}") from exc
            time.sleep(2**attempt)

        raise OpenRouterError(f"{self.label} request failed after retries")


def _message_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts).strip()
    raise OpenRouterError("chat response content is missing")


def _parse_json_object(content: str) -> dict[str, Any]:
    """Parse the model's JSON object, tolerating code fences or surrounding prose.

    Hosted models honour strict JSON Schema, but many local models wrap the
    object in markdown or add a sentence before it.
    """

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end <= start:
            raise OpenRouterError("chat response is not valid JSON") from None
        try:
            result = json.loads(content[start : end + 1])
        except json.JSONDecodeError as exc:
            raise OpenRouterError("chat response is not valid JSON") from exc
    if not isinstance(result, dict):
        raise OpenRouterError("chat response JSON root is not an object")
    return result


def _coerce_boolean(value: Any) -> bool:
    """Convert the observed Jev answer shapes into a review boolean."""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value >= 0.5
    if isinstance(value, str):
        return value.strip().lower() == "true"
    if isinstance(value, dict):
        if "noul" in value:
            return _coerce_boolean(value["noul"])
        for key in ("value", "answer", "result", "decision", "label"):
            if key in value:
                return _coerce_boolean(value[key])
        if "true" in value or "false" in value:
            return float(value.get("true", 0)) >= float(value.get("false", 0))
    return False
