"""Textual widgets used in the pir UI."""

from rich.style import Style
from textual import events
from textual.strip import Strip
from textual.widgets import Input, OptionList, Static


class PaneTitle(Static):
    DEFAULT_CSS = """
    PaneTitle {
        height: 1;
        padding: 0 2;
        text-style: bold;
    }
    """


class CozyList(OptionList):
    DEFAULT_CSS = """
    CozyList {
        border: none;
        padding: 0 1;
        color: ansi_default;
        background: transparent;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
    }
    CozyList:focus {
        border: none;
        background: transparent;
    }
    CozyList > .option-list--option-highlighted {
        color: ansi_default;
        text-style: bold;
        background: transparent;
    }
    /* palette slots 0/7 aren't actually black/white in every theme (Xcode
       Light paints slot 0 robin's-egg blue), so render_line inverts the
       terminal's own default fg/bg instead */
    CozyList:focus > .option-list--option-highlighted {
        color: ansi_default;
        background: ansi_default;
        text-style: bold;
    }
    """

    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)
        if not self.has_focus:
            return strip
        try:
            index, _ = self._lines[self.scroll_offset.y + y]
        except (IndexError, KeyError):
            return strip
        if index == self.highlighted:
            return strip.apply_style(Style(reverse=True))
        return strip


class SearchInput(Input):
    """Search box where tab flips the search target instead of moving focus."""

    def on_key(self, event: events.Key) -> None:
        if event.key == "tab":
            event.stop()
            event.prevent_default()
            self.screen.action_toggle_search_mode()


class NowPlaying(Static):
    DEFAULT_CSS = """
    NowPlaying {
        height: 3;
        padding: 1 2 0 2;
    }
    """
