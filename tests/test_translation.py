from jev_subtitle_translator.models import Cue
from jev_subtitle_translator.translator import parse_translation_response, translate_cues


def _cue(index: int, text: str) -> Cue:
    return Cue(index=index, number=str(index + 1), start="00:00:00,000", end="00:00:01,000", text=text)


def test_parse_translation_response_ignores_unknown_duplicate_and_empty_ids():
    response = {
        "items": [
            {"id": "0", "translation": "Hallo"},
            {"id": "0", "translation": "Duplicate"},
            {"id": "4", "translation": "Unknown"},
            {"id": "1", "translation": ""},
        ]
    }

    assert parse_translation_response(response, {"0", "1"}) == {"0": "Hallo"}


def test_translate_retries_only_missing_ids():
    class FakeClient:
        def __init__(self):
            self.calls = []

        def chat_json(self, **kwargs):
            self.calls.append(kwargs["messages"][1]["content"])
            if len(self.calls) == 1:
                return {"items": [{"id": "0", "translation": "Hallo"}]}
            return {"items": [{"id": "1", "translation": "Welt"}]}

    client = FakeClient()
    result = translate_cues(
        client,
        [_cue(0, "Hello"), _cue(1, "World")],
        model="test/model",
        source_language="English",
        target_language="German",
        batch_size=2,
    )

    assert result.translations == {"0": "Hallo", "1": "Welt"}
    assert result.failures == {}
    assert '"id":"0"' in client.calls[0]
    assert '"id":"1"' in client.calls[0]
    assert '"id":"1"' in client.calls[1]
    assert '"id":"0"' not in client.calls[1]


def test_translate_reports_progress_after_each_batch():
    class FakeClient:
        def chat_json(self, **kwargs):
            return {"items": [{"id": "0", "translation": "A"}, {"id": "1", "translation": "B"}]}

    progress = []
    translate_cues(
        FakeClient(),
        [_cue(0, "a"), _cue(1, "b"), _cue(2, "c")],
        model="test/model",
        source_language="English",
        target_language="German",
        batch_size=2,
        missing_retries=0,
        on_progress=lambda done, total: progress.append((done, total)),
    )

    assert progress == [(2, 3), (3, 3)]


def test_language_codes_become_names_in_prompt():
    from jev_subtitle_translator.translator import build_translation_messages

    system = build_translation_messages(
        [_cue(0, "hi")], source_language="en", target_language="zh-CN"
    )[0]["content"]

    assert "from English to Chinese" in system
