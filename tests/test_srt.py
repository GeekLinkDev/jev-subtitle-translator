from pathlib import Path

from jev_subtitle_translator.srt import parse_srt, read_srt, render_srt

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_and_render_preserve_source_structure():
    cues = read_srt(FIXTURES / "english.srt")

    assert len(cues) == 4
    assert cues[0].id == "0"
    assert cues[0].number == "1"
    assert cues[0].text == "I told him not to come."

    rendered = render_srt(cues)
    assert "00:00:01,000 --> 00:00:03,000" in rendered
    assert "I told him not to come." in rendered


def test_render_keeps_missing_translation_empty():
    cues = parse_srt("1\n00:00:00,000 --> 00:00:01,000\nHello\n")

    assert render_srt(cues, {"0": ""}) == "1\n00:00:00,000 --> 00:00:01,000\n\n"
