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


def test_rendered_srt_with_empty_translations_parses_back():
    cues = read_srt(FIXTURES / "english.srt")

    reparsed = parse_srt(render_srt(cues, {"0": "Eins", "1": "", "2": "Drei", "3": ""}))

    assert [cue.text for cue in reparsed] == ["Eins", "", "Drei", ""]
    assert [(c.number, c.start, c.end) for c in reparsed] == [(c.number, c.start, c.end) for c in cues]


def test_blank_separator_lines_may_contain_whitespace_or_repeat():
    cues = parse_srt(
        "1\n00:00:00,000 --> 00:00:01,000\nHello\n \t\n\n2\n00:00:02,000 --> 00:00:03,000\nWorld\n"
    )

    assert [(cue.number, cue.text) for cue in cues] == [("1", "Hello"), ("2", "World")]
