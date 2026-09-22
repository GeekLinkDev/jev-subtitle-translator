import json
from pathlib import Path

from fastapi.testclient import TestClient

from jev_subtitle_translator import web

FIXTURES = Path(__file__).parent / "fixtures"


def test_qc_endpoint_reviews_an_existing_srt_pair(monkeypatch):
    class FakeClient:
        def __init__(self, api_key):
            self.api_key = api_key

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
