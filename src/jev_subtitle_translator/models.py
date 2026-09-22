"""Small data models shared by the parser, translator, and QC reporter."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Cue:
    """One SRT cue with an internal stable ID and the original display number."""

    index: int
    number: str
    start: str
    end: str
    text: str

    @property
    def id(self) -> str:
        """Return a unique ID that is independent of the SRT display number."""

        return str(self.index)

    @property
    def timing(self) -> str:
        """Return the original SRT timing line."""

        return f"{self.start} --> {self.end}"
