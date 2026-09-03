"""pir — a cozy little Navidrome client for your terminal.

No borders, gentle padding, a few cute symbols, and no colors at all —
just your terminal's default foreground with bold, dim, and reverse.
Playback is handled by mpv; your password lives in the system keychain.
"""

# Re-export all public symbols so existing imports still work:
#   from pir import PirApp, MainScreen, SetupScreen, SubsonicClient, ...
#   from pir import Album, Song, Scrobbler, fmt_time, progress_bar

from .app import PirApp
from .consts import ACCENT, APP_NAME, CONFIG_DIR, CONFIG_FILE, DIM, API_VERSION
from .config import Config
from .models import Album, Song, SubsonicError
from .players import MpvPlayer
from .scrobbler import Scrobbler
from .services import SubsonicClient
from .ui.screens import MainScreen, SetupScreen
from .ui.widgets import CozyList, NowPlaying, PaneTitle, SearchInput
from .utils import fmt_time, progress_bar

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
    "fmt_time",
    "progress_bar",
    # consts
    "APP_NAME",
    "API_VERSION",
    "CONFIG_DIR",
    "CONFIG_FILE",
    "ACCENT",
    "DIM",
]
