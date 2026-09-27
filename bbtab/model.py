"""Data model for a guitar tablature document.

The model is deliberately UI-agnostic: the fretboard view and the staff view
both read and mutate these objects, and the whole thing serialises to plain
JSON. Nothing in here imports GTK.

String indexing convention (shared everywhere in the app):
    index 0 == highest-pitched string (the top line in tab, high "e")
    index 5 == lowest-pitched string  (the bottom line, low "E")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List

# Standard tuning, ordered high -> low to match the string index convention.
STANDARD_TUNING: List[str] = ["e", "B", "G", "D", "A", "E"]

# MIDI note number of each open string in standard tuning, high -> low.
# (e4=64, B3=59, G3=55, D3=50, A2=45, E2=40) -- used for future playback/export.
STANDARD_OPEN_MIDI: List[int] = [64, 59, 55, 50, 45, 40]

NUM_STRINGS = 6


# Bend amounts, in whole tones. 0 == no bend; 1.0 == a full (whole-step) bend.
BEND_AMOUNTS = [0.0, 0.25, 0.5, 1.0, 1.5, 2.0]


def bend_label(bend: float) -> str:
    """Tab suffix for a bend amount, e.g. 0.5 -> 'b½', 1.0 -> 'b' (full)."""
    if not bend:
        return ""
    frac = {0.25: "¼", 0.5: "½", 1.0: "", 1.5: "1½", 2.0: "2"}
    amt = frac.get(bend, str(bend).rstrip("0").rstrip("."))
    return "b" + amt  # full bend (1.0) renders as a lone "b", the usual convention


@dataclass
class Note:
    """A single fretted note plus any techniques applied to it."""

    fret: int
    bend: float = 0.0     # whole tones; see BEND_AMOUNTS
    hold: int = 0         # extra beats this note sustains/bends across (0 = just its own beat)
    vibrato: bool = False   # rendered as a 'v' after the number
    slide_out: bool = False  # slide FROM this note to the next note on the string ('7/')
    slide_in: bool = False   # slide TO this note from before it ('/9')

    def to_dict(self):
        d = {"fret": self.fret}
        if self.bend:
            d["bend"] = self.bend
        if self.hold:
            d["hold"] = self.hold
        if self.vibrato:
            d["vibrato"] = True
        if self.slide_out:
            d["slide_out"] = True
        if self.slide_in:
            d["slide_in"] = True
        return d

    @classmethod
    def from_any(cls, value) -> "Note":
        # Accept both the new object form and the old bare-int fret form.
        if isinstance(value, dict):
            return cls(fret=int(value.get("fret", 0)),
                       bend=float(value.get("bend", 0) or 0),
                       hold=int(value.get("hold", 0) or 0),
                       vibrato=bool(value.get("vibrato", False)),
                       # accept the older single "slide" key as slide_out
                       slide_out=bool(value.get("slide_out", value.get("slide", False))),
                       slide_in=bool(value.get("slide_in", False)))
        return cls(fret=int(value))


@dataclass
class Beat:
    """One vertical column in the tab: at most one note per string."""

    # Maps string index (0..5) -> Note.
    notes: Dict[int, Note] = field(default_factory=dict)

    def set_note(self, string: int, fret: int) -> None:
        # Re-fretting an existing string keeps its techniques (e.g. the bend).
        if string in self.notes:
            self.notes[string].fret = fret
        else:
            self.notes[string] = Note(fret)

    def set_bend(self, string: int, bend: float) -> None:
        if string in self.notes:
            self.notes[string].bend = bend

    def clear_string(self, string: int) -> None:
        self.notes.pop(string, None)

    def is_empty(self) -> bool:
        return not self.notes

    def to_dict(self) -> dict:
        return {"notes": {str(s): n.to_dict() for s, n in sorted(self.notes.items())}}

    @classmethod
    def from_dict(cls, data: dict) -> "Beat":
        notes = {int(s): Note.from_any(v) for s, v in data.get("notes", {}).items()}
        return cls(notes=notes)


@dataclass
class Song:
    """A whole tablature document."""

    title: str = "Untitled"
    artist: str = ""
    tuning: List[str] = field(default_factory=lambda: list(STANDARD_TUNING))
    beats_per_measure: int = 4
    beats: List[Beat] = field(default_factory=lambda: [Beat()])

    # ---- editing helpers -------------------------------------------------

    def ensure_beat(self, index: int) -> None:
        """Grow the beat list so that `index` is a valid position."""
        while len(self.beats) <= index:
            self.beats.append(Beat())

    def append_beat(self) -> int:
        self.beats.append(Beat())
        return len(self.beats) - 1

    # ---- serialisation ---------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "format": "bbtab",
            "version": 1,
            "title": self.title,
            "artist": self.artist,
            "tuning": self.tuning,
            "beats_per_measure": self.beats_per_measure,
            "beats": [b.to_dict() for b in self.beats],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Song":
        beats = [Beat.from_dict(b) for b in data.get("beats", [])] or [Beat()]
        return cls(
            title=data.get("title", "Untitled"),
            artist=data.get("artist", ""),
            tuning=list(data.get("tuning", STANDARD_TUNING)),
            beats_per_measure=int(data.get("beats_per_measure", 4)),
            beats=beats,
        )

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @classmethod
    def load(cls, path: str) -> "Song":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))
