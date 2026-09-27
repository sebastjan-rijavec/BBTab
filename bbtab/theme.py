"""Palette derived from the current light/dark preference.

Custom Cairo drawing doesn't get theme colours for free, so we build a small
palette from libadwaita's dark flag and recompute it each draw (cheap).
"""

from __future__ import annotations

from gi.repository import Adw


def palette() -> dict:
    dark = Adw.StyleManager.get_default().get_dark()
    if dark:
        return {
            "bg": (0.13, 0.13, 0.14),
            "fg": (0.90, 0.90, 0.92),
            "line": (0.45, 0.45, 0.48),
            "muted": (0.55, 0.55, 0.58),
            "accent": (0.30, 0.60, 0.95),
            "cursor": (0.30, 0.60, 0.95, 0.22),
            "hover": (0.90, 0.90, 0.92, 0.12),
            "dot": (0.35, 0.35, 0.38),
        }
    return {
        "bg": (0.99, 0.99, 0.99),
        "fg": (0.12, 0.12, 0.14),
        "line": (0.55, 0.55, 0.58),
        "muted": (0.45, 0.45, 0.48),
        "accent": (0.16, 0.44, 0.85),
        "cursor": (0.16, 0.44, 0.85, 0.16),
        "hover": (0.12, 0.12, 0.14, 0.08),
        "dot": (0.82, 0.82, 0.84),
    }
