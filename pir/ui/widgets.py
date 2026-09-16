"""Textual widgets used in the pir UI."""

from textual import events
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
    /* the cursor row paints an ansi_white block (palette color 7) —
       reverse video proved invisible on some terminals; black text keeps
       it readable on both light and dark palettes */
    CozyList:focus > .option-list--option-highlighted {
        color: ansi_black;
        background: ansi_white;
        text-style: bold;
    }
    """


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
