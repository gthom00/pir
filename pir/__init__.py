"""pir — a cozy little Navidrome client for your terminal.

No borders, gentle padding, a few cute symbols, and no colors at all —
just your terminal's default foreground with bold and dim, plus a solid
black-on-white block for the cursor row.
Playback is handled by mpv; your password lives in the system keychain.
"""

# Re-export all public symbols so existing imports still work:
#   from pir import PirApp, MainScreen, SetupScreen, SubsonicClient, ...
#   from pir import Album, Song, Scrobbler, fmt_time, progress_bar

from .app import PirApp
from .config import Config
from .consts import (
    ACCENT,
    API_VERSION,
    APP_NAME,
    CONFIG_DIR,
    CONFIG_FILE,
    DIM,
    REPLAYGAIN_DEFAULT,
    REPLAYGAIN_MODES,
)
from .models import Album, Song
from .players import MpvPlayer
from .scrobbler import Scrobbler
from .services import SubsonicClient, SubsonicError
from .ui.screens import MainScreen, SetupScreen
from .ui.widgets import CozyList, NowPlaying, PaneTitle, SearchInput
from .utils import esc_markup, fmt_time, progress_bar

__all__ = [
    # app
    "PirApp",
    # screens
    "MainScreen",
    "SetupScreen",
    # models
    "Album",
    "Song",
    "SubsonicError",
    "SubsonicClient",
    # player
    "MpvPlayer",
    # scrobbler
    "Scrobbler",
    # config
    "Config",
    # widgets
    "PaneTitle",
    "CozyList",
    "SearchInput",
    "NowPlaying",
    # utils
    "esc_markup",
    "fmt_time",
    "progress_bar",
    # consts
    "APP_NAME",
    "API_VERSION",
    "CONFIG_DIR",
    "CONFIG_FILE",
    "ACCENT",
    "DIM",
    "REPLAYGAIN_MODES",
    "REPLAYGAIN_DEFAULT",
]
