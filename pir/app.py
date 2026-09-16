"""Main application class for pir."""

import threading

from textual.app import App

from .config import Config
from .players import MpvPlayer
from .services import SubsonicClient
from .ui.screens import MainScreen, SetupScreen


class PirApp(App):
    DEFAULT_CSS = """
    Screen {
        background: ansi_default;
        color: ansi_default;
    }
    """

    def __init__(self, client: SubsonicClient | None = None) -> None:
        super().__init__(ansi_color=True)
        # the ansi theme keeps every widget on the terminal's own default
        # fg/bg — without it, list/input text is painted in dark-theme RGB
        # greys that wash out on light terminals
        self.theme = "ansi-light"
        self.client = client
        self.player = MpvPlayer(on_track_end=self._on_track_end)

    def on_mount(self) -> None:
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
