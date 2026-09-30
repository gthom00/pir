"""Main application class for pir."""

import asyncio
import threading

from textual.app import App

from .appearance import prefers_dark
from .config import Config
from .players import MpvPlayer
from .services import SubsonicClient
from .ui.screens import MainScreen, SetupScreen

THEME_POLL_SECONDS = 2.0


class PirApp(App):
    DEFAULT_CSS = """
    Screen {
        background: ansi_default;
        color: ansi_default;
    }
    """

    def __init__(self, client: SubsonicClient | None = None) -> None:
        super().__init__(ansi_color=True)
        # the ansi themes keep every widget on the terminal's own default
        # fg/bg — without them, list/input text is painted in dark-theme
        # RGB greys that wash out on light terminals. light vs dark swaps
        # the cursor/selection colors, so pick the one matching the OS
        # and keep following it as it changes its mind
        self.theme = "ansi-dark" if prefers_dark() else "ansi-light"
        self.client = client
        self.player = MpvPlayer(on_track_end=self._on_track_end)

    def on_mount(self) -> None:
        self.set_interval(THEME_POLL_SECONDS, self._sync_theme)
        if self.client is None:
            config = Config.load()
            password = config.password() if config else None
            if config and password:
                self.client = SubsonicClient(config.server, config.username, password)
                # set before start() so mpv boots with the configured mode
                self.player.replaygain = config.replaygain
        try:
            self.player.start()
        except (FileNotFoundError, RuntimeError):
            self.exit(
                message=(
                    "☂ mpv is needed for playback — brew install mpv, then come back!"
                )
            )
            return
        if self.client is not None:
            self.push_screen(MainScreen())
        else:
            self.push_screen(SetupScreen())

    async def _sync_theme(self) -> None:
        """Follow the OS into light or dark mode without blocking the UI.

        The theme reactive only repaints when the name actually changes,
        so re-setting it on every poll is a no-op most of the time.
        """
        dark = await asyncio.to_thread(prefers_dark)
        self.theme = "ansi-dark" if dark else "ansi-light"

    def finish_setup(self, client: SubsonicClient) -> None:
        self.client = client
        self.pop_screen()
        self.push_screen(MainScreen())

    def _on_track_end(self) -> None:
        # called from the mpv reader thread
        if self._thread_id != threading.get_ident():
            self.call_from_thread(self._advance_if_main)
        else:
            self._advance_if_main()

    def _advance_if_main(self) -> None:
        screen = self.screen
        if isinstance(screen, MainScreen):
            screen.advance()

    def on_unmount(self) -> None:
        self.player.shutdown()


def main() -> None:
    PirApp().run(mouse=False)
