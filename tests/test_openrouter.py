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


def _capture_request(client, content='{"items": []}', **kwargs):
    sent = {}

    def fake_request(url, body):
        sent["url"] = url
        sent["body"] = body
        return {"choices": [{"message": {"content": content}}]}

    client._request_json = fake_request
    result = client.chat_json(model="qwen2.5:7b", messages=[{"role": "user", "content": "x"}], **kwargs)
    return sent, result


def test_local_endpoint_needs_no_key_and_gets_no_openrouter_fields():
    import pytest

    client = OpenRouterClient(base_url="http://localhost:11434/v1/")
    sent, _ = _capture_request(client)

    assert not client.is_openrouter
    assert sent["url"] == "http://localhost:11434/v1/chat/completions"
    assert "provider" not in sent["body"]
    assert "reasoning" not in sent["body"]
    assert sent["body"]["response_format"]["type"] == "json_schema"
    with pytest.raises(Exception, match="only available on OpenRouter"):
        client.decisions(model="typesafe/jev-1.13", pairs=[{"id": "0"}], guidelines="g")


def test_openrouter_still_requires_a_key():
    import pytest

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        OpenRouterClient("")


def test_local_model_json_wrapped_in_markdown_is_accepted():
    client = OpenRouterClient(base_url="http://localhost:1234/v1")
    _, result = _capture_request(
        client, content='Sure!\n```json\n{"items": [{"id": "0", "translation": "Hallo"}]}\n```'
    )

    assert result == {"items": [{"id": "0", "translation": "Hallo"}]}
