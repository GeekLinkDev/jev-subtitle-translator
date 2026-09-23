"""Minimal, loss-aware SRT parsing and rendering for the first release."""

import re
from pathlib import Path

from .models import Cue


class SRTError(ValueError):
    """Raised when an SRT document cannot be parsed safely."""


def parse_srt(text: str) -> list[Cue]:
    """Parse an SRT document without changing cue text or timing."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").rstrip()
    # Split on any run of blank lines: a cue with empty text is rendered as
    # "N\ntiming\n\n\n", and an exact "\n\n" split would glue the extra newline
    # onto the next cue and hide its number line.
    blocks = [block for block in re.split(r"\n[ \t]*(?:\n[ \t]*)+", normalized) if block.strip()]
    cues: list[Cue] = []

    for index, block in enumerate(blocks):
        lines = block.split("\n")
        if len(lines) < 2:
            raise SRTError(f"Cue {index + 1} is incomplete")

        timing_index = 1 if "-->" in lines[1] else 0
        if timing_index >= len(lines) or "-->" not in lines[timing_index]:
            raise SRTError(f"Cue {index + 1} has no timing line")

        number = lines[0].strip() if timing_index == 1 else str(index + 1)
        timing = lines[timing_index].strip()
        start, end = _split_timing(timing, index)
        cue_text = "\n".join(lines[timing_index + 1 :])
        cues.append(Cue(index=index, number=number, start=start, end=end, text=cue_text))

    if not cues:
        raise SRTError("The SRT document contains no cues")
    return cues


def _split_timing(timing: str, index: int) -> tuple[str, str]:
    parts = timing.split("-->", 1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise SRTError(f"Cue {index + 1} has an invalid timing line")
    return parts[0].strip(), parts[1].strip()


def read_srt(path: str | Path) -> list[Cue]:
    """Read an UTF-8 SRT file."""

    return parse_srt(Path(path).read_text(encoding="utf-8-sig"))


def render_srt(cues: list[Cue], translations: dict[str, str] | None = None) -> str:
    """Render cues with original numbers and timings and optional translated text."""

    rendered: list[str] = []
    for cue in cues:
        body = cue.text if translations is None else translations.get(cue.id, "")
        rendered.append(f"{cue.number}\n{cue.timing}\n{body}")
    return "\n\n".join(rendered) + "\n"


def write_srt(path: str | Path, cues: list[Cue], translations: dict[str, str]) -> None:
    """Write a translated SRT while keeping the source structure."""

    Path(path).write_text(render_srt(cues, translations), encoding="utf-8")
