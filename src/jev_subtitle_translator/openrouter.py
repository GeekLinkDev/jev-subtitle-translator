"""Small dependency-free OpenRouter client used by the CLI."""

import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter cannot provide a valid response."""

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
    """Call OpenRouter chat completions and the Jev Decisions endpoint."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://openrouter.ai",
        timeout: float = 120.0,
        attempts: int = 3,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OPENROUTER_API_KEY is required")
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.attempts = max(1, attempts)
        self.last_generation_metadata: dict[str, Any] | None = None

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
            # Keep OpenRouter from routing to an endpoint that ignores response_format.
            "provider": {"require_parameters": True},
        }
        if model not in NO_TEMPERATURE_MODELS:
            body["temperature"] = temperature
        if model in REASONING_BY_MODEL:
            body["reasoning"] = REASONING_BY_MODEL[model]
        payload = self._request_json("/api/v1/chat/completions", body)
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise OpenRouterError("chat response contains no choices")
        message = choices[0].get("message") or {}
        refusal = message.get("refusal")
        if refusal:
            raise OpenRouterError(f"model refusal: {refusal}")
        content = _message_content(message.get("content"))
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OpenRouterError("chat response is not valid JSON") from exc
        if not isinstance(result, dict):
            raise OpenRouterError("chat response JSON root is not an object")
        return result

    def decisions(
        self,
        *,
        model: str,
        pairs: list[dict[str, str]],
        guidelines: str,
    ) -> dict[str, bool]:
        """Ask a Jev Decisions model for one review verdict per subtitle ID."""

        self.last_generation_metadata = None
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
            questions[subtitle_id] = {
                "type": "noul",
                "instructions": (
                    f'Judge ONLY the subtitle whose id is "{subtitle_id}". '
                    "Does this translation need human review?"
                ),
                "criteria": {
                    "true": "There is a genuine meaning, omission, number, entity, or fluency defect.",
                    "false": "The translation preserves the source meaning.",
                },
            }

        if not subtitles:
            return {}

        payload = self._request_json(
            "/api/alpha/decisions",
            {
                "model": model,
                "state": {"guidelines": guidelines, "subtitles": subtitles},
                "questions": questions,
            },
        )
        generation_id = payload.get("id") or payload.get("generation_id")
        if isinstance(generation_id, str) and generation_id.strip():
            self.last_generation_metadata = self._get_generation_metadata(generation_id.strip())
        answers = payload.get("answers")
        if not isinstance(answers, dict):
            raise OpenRouterError("Jev response contains no answers object")
        return {
            subtitle_id: _coerce_boolean(answers[subtitle_id])
            for subtitle_id in questions
            if subtitle_id in answers
        }

    def _get_generation_metadata(self, generation_id: str) -> dict[str, Any]:
        last_error = ""
        for attempt in range(4):
            request = urllib.request.Request(
                f"{self.base_url}/api/v1/generation?{urlencode({'id': generation_id})}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                method="GET",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                data = payload.get("data")
                if not isinstance(data, dict):
                    return {
                        "generation_id": generation_id,
                        "metadata_error": "generation metadata contains no data object",
                    }
                provider_responses = data.get("provider_responses")
                provider_latencies = []
                if isinstance(provider_responses, list):
                    provider_latencies = [
                        item.get("latency")
                        for item in provider_responses
                        if isinstance(item, dict)
                        and isinstance(item.get("latency"), (int, float))
                    ]
                return {
                    "generation_id": data.get("id") or generation_id,
                    "model": data.get("model"),
                    "provider": data.get("provider_name"),
                    "api_type": data.get("api_type"),
                    "generation_time_ms": data.get("generation_time"),
                    "latency_ms": data.get("latency"),
                    "provider_latencies_ms": provider_latencies,
                }
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                last_error = f"OpenRouter HTTP {exc.code}: {detail}"
                if exc.code != 404 or attempt == 3:
                    break
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                last_error = f"generation metadata request failed: {exc}"
                if attempt == 3:
                    break
            time.sleep(0.25 * (2**attempt))
        return {"generation_id": generation_id, "metadata_error": last_error}

    def _request_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/GeekLinkDev/jev-subtitle-translator",
                "X-Title": "GeekLink Jev Subtitle Translator",
                "X-OpenRouter-Metadata": "enabled",
            },
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
                        f"OpenRouter HTTP {exc.code}: {detail}", status=exc.code
                    ) from exc
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                if attempt == self.attempts - 1:
                    raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc
            time.sleep(2**attempt)

        raise OpenRouterError("OpenRouter request failed after retries")


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
