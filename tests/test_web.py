import json
from pathlib import Path

from fastapi.testclient import TestClient

from jev_subtitle_translator import web

FIXTURES = Path(__file__).parent / "fixtures"


def test_qc_endpoint_reviews_an_existing_srt_pair(monkeypatch):
    class FakeClient:
        def __init__(self, api_key, *, base_url):
            self.api_key = api_key
            self.base_url = base_url

        def decisions(self, **kwargs):
            return {pair["id"]: pair["id"] == "0" for pair in kwargs["pairs"]}

    monkeypatch.setattr(web, "OpenRouterClient", FakeClient)
    source = (FIXTURES / "english.srt").read_bytes()
    translation = (FIXTURES / "german-errors.srt").read_bytes()

    with TestClient(web.create_app()) as client:
        response = client.post(
            "/api/qc",
            files={
                "source_file": ("source.srt", source, "application/x-subrip"),
                "translation_file": ("translated.srt", translation, "application/x-subrip"),
            },
            data={
                "source_language": "en",
                "target_language": "de",
                "api_key": "test-key",
                "jev_model": "typesafe/jev-1.13",
            },
        )

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    result = next(event for event in events if event["type"] == "result")
    assert result["mode"] == "qc"
    assert result["report"]["translation_model"] == "external"
    assert result["report"]["flagged_count"] == 1
    assert result["translations"]["0"] == "Ich sagte ihm, er solle kommen."


def test_translate_endpoint_with_qc_off_needs_no_openrouter_key(monkeypatch):
    from jev_subtitle_translator.translator import TranslationResult

    def fake_translate(client, cues, **kwargs):
        assert not client.is_openrouter
        return TranslationResult(translations={cue.id: "x" for cue in cues})

    monkeypatch.setattr(web, "translate_cues", fake_translate)
    source = (FIXTURES / "english.srt").read_bytes()

    with TestClient(web.create_app()) as client:
        response = client.post(
            "/api/translate",
            files={"file": ("source.srt", source, "application/x-subrip")},
            data={
                "source_language": "en",
                "target_language": "de",
                "model": "qwen2.5:7b",
                "base_url": "http://localhost:11434/v1",
                "jev_model": "off",
            },
        )

    assert response.status_code == 200
    result = json.loads(response.text.splitlines()[-1])
    assert result["report"]["qc_status"] == "skipped"
    assert result["report"]["qc_method"] == "off"
    assert result["report"]["jev_model"] is None
