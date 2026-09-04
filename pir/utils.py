"""Utility functions used across the UI."""

from .consts import ACCENT, DIM


def esc_markup(text: str) -> str:
    """Escape a string so Textual renders it literally instead of as markup.

    Song and album metadata arrives from the server and can contain square
    brackets (looking at you, YAYAYI); without escaping, Textual would try
    to parse them as markup tags and raise a MarkupError.
    """
    return text.replace("\\", "\\\\").replace("[", "\\[")


def fmt_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def progress_bar(pos: float, duration: float, width: int = 28) -> str:
    if duration <= 0:
        return f"[{DIM}]{'─' * width}[/]"
    frac = min(1.0, max(0.0, pos / duration))
    knob = min(width - 1, int(frac * width))
    left = "─" * knob
    right = "─" * (width - knob - 1)
    return f"[{ACCENT}]{left}●[/][{DIM}]{right}[/]"
