from jev_subtitle_translator.openrouter import OpenRouterClient


def _capture_body(model: str, **kwargs) -> dict:
    client = OpenRouterClient("key")
    sent = {}

    def fake_request(path, body):
        sent.update(body)
        return {"choices": [{"message": {"content": '{"items": []}'}}]}

    client._request_json = fake_request
    client.chat_json(model=model, messages=[{"role": "user", "content": "x"}], **kwargs)
    return sent


def test_reasoning_models_have_thinking_pinned_off():
    body = _capture_body("deepseek/deepseek-v4-flash-0731")

    assert body["reasoning"] == {"enabled": False}
    assert body["temperature"] == 0
    assert body["provider"] == {"require_parameters": True}


def test_gpt56_omits_temperature_and_uses_effort_none():
    body = _capture_body("openai/gpt-5.6-luna")

    assert "temperature" not in body
    assert body["reasoning"] == {"effort": "none", "exclude": True}


def test_legacy_model_gets_plain_body():
    body = _capture_body("openai/gpt-4o")

    assert body["temperature"] == 0
    assert "reasoning" not in body


def test_custom_temperature_is_forwarded_except_where_rejected():
    assert _capture_body("openai/gpt-4o", temperature=0.7)["temperature"] == 0.7
    assert "temperature" not in _capture_body("anthropic/claude-sonnet-5", temperature=0.7)
