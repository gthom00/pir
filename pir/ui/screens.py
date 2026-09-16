"""Textual screens for the pir music player."""

import time

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from ..config import Config
from ..consts import ACCENT, APP_NAME, DIM, REPLAYGAIN_MODES
from ..scrobbler import Scrobbler
from ..services import SubsonicClient
from ..utils import esc_markup, fmt_time, progress_bar
from .widgets import CozyList, NowPlaying, PaneTitle, SearchInput


class SetupScreen(Screen):
    """First-run cozy questionnaire: server, username, password."""

    DEFAULT_CSS = """
    SetupScreen {
        align: center middle;
        background: ansi_default;
    }
    SetupScreen > Vertical {
        width: 60;
        height: auto;
        padding: 1 4;
    }
    SetupScreen Static {
        margin: 0 0 1 0;
    }
    SetupScreen Input {
        border: none;
        padding: 0 1;
        margin: 0 0 1 0;
        background: transparent;
    }
    SetupScreen Input:focus {
        border: none;
        background: transparent;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(
                f"[{ACCENT}]☁ welcome to {APP_NAME}[/]  ·  let's get you settled in"
            )
            yield Static(
                f"[{DIM}]your password goes straight into the system keychain,\n"
                f"never into a file.[/]"
            )
            yield Input(
                placeholder="server url  (https://music.example.com)", id="server"
            )
            yield Input(placeholder="username", id="username")
            yield Input(placeholder="password", password=True, id="password")
            yield Static("", id="setup-status")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        order = ["server", "username", "password"]
        current = event.input.id
        if current in order[:-1]:
            self.query_one(f"#{order[order.index(current) + 1]}", Input).focus()
            return
        server = self.query_one("#server", Input).value.strip().rstrip("/")
        username = self.query_one("#username", Input).value.strip()
        password = self.query_one("#password", Input).value
        if not (server and username and password):
            self._status(f"[{DIM}]☂ all three fields are needed[/]")
            return
        if not server.startswith(("http://", "https://")):
            server = "https://" + server
        self._status(f"[{DIM}]☕ knocking on the server's door…[/]")
        self._try_connect(server, username, password)

    def _status(self, markup: str) -> None:
        self.query_one("#setup-status", Static).update(markup)

    @work(thread=True, exclusive=True)
    def _try_connect(self, server: str, username: str, password: str) -> None:
        try:
            client = SubsonicClient(server, username, password)
            client.ping()
        except Exception as exc:
            self.app.call_from_thread(
                self._status, f"[{DIM}]☂ couldn't get in: {esc_markup(str(exc))}[/]"
            )
            return
        config = Config(server=server, username=username)
        config.save()
        config.store_password(password)
        self.app.call_from_thread(self.app.finish_setup, client)


class MainScreen(Screen):
    DEFAULT_CSS = """
    MainScreen {
        background: ansi_default;
    }
    #title {
        height: 2;
        padding: 1 2 0 2;
    }
    #panes {
        height: 1fr;
    }
    #albums-pane, #songs-pane {
        width: 1fr;
        padding: 0 1;
    }
    #search-row {
        display: none;
        height: 1;
        padding: 0 2;
    }
    #search-row.visible {
        display: block;
    }
    #search-mode {
        width: auto;
        padding: 0 2 0 0;
        text-style: bold;
    }
    #search {
        width: 1fr;
        border: none;
        height: 1;
        padding: 0;
        background: transparent;
    }
    #search:focus {
        border: none;
        background: transparent;
    }
    """

    BINDINGS = [
        Binding("space", "toggle_pause", "pause", priority=True),
        Binding("n", "next_song", "next"),
        Binding("b", "prev_song", "back"),
        # the search box owns the arrow keys while it has focus, so these
        # only fire when a list is focused
        Binding("right", "seek(5)", "seek", show=False),
        Binding("left", "seek(-5)", "seek", show=False),
        Binding("shift+right", "seek(30)", "seek 30s", show=False),
        Binding("shift+left", "seek(-30)", "seek 30s", show=False),
        Binding("slash", "search", "search"),
        Binding("s", "cycle_sort", "sort"),
        Binding("r", "shuffle_albums", "shuffle"),
        Binding("g", "cycle_replaygain", "gain"),
        # `=` is `+` unshifted — some folks refuse to reach for shift mid-song
        Binding("plus", "volume_up", "louder", show=False),
        Binding("equals_sign", "volume_up", "louder", show=False),
        Binding("minus", "volume_down", "quieter", show=False),
        Binding("escape", "hide_search", show=False),
        Binding("tab", "swap_pane", "swap", show=False),
        Binding("q", "app.quit", "quit"),
    ]

    # (label shown in the pane title, getAlbumList2 type)
    SORTS = [
        ("alphabetical", "alphabeticalByName"),
        ("recently added", "newest"),
        ("recently played", "recent"),
        ("random", "alphabeticalByName"),  # fetched sorted, shuffled locally
    ]

    VOLUME_STEP = 5
    VOLUME_NOTE_SECONDS = 3.0

    def __init__(self) -> None:
        super().__init__()
        self.albums: list = []
        self.songs: list = []
        self.queue: list = []
        self.queue_index: int = -1
        self.search_mode: str = "albums"
        self.sort_index: int = 0
        self.scrobbler: Scrobbler | None = None
        self._volume_note_until: float = 0.0

    # ── layout ──

    def compose(self) -> ComposeResult:
        yield Static(
            f"[{ACCENT}]{APP_NAME}[/]  "
            f"[{DIM}]· space pause · ←→ seek · n next · / search · s sort · "
            f"g gain · +/- vol · q quit[/]",
            id="title",
        )
        with Horizontal(id="search-row"):
            yield Static("albums", id="search-mode")
            yield SearchInput(
                placeholder="what are you in the mood for?  (tab switches target)",
                id="search",
            )
        with Horizontal(id="panes"):
            with Vertical(id="albums-pane"):
                yield PaneTitle("✻ albums", id="albums-title")
                yield CozyList(id="albums")
            with Vertical(id="songs-pane"):
                yield PaneTitle("✻ songs")
                yield CozyList(id="songs")
        yield NowPlaying(id="now-playing")

    def on_mount(self) -> None:
        self.scrobbler = Scrobbler(self.app.client)
        self.query_one("#albums", CozyList).focus()
        self._render_now_playing()
        self.set_interval(0.5, self._tick)
        self.load_albums()

    def _tick(self) -> None:
        player = self.app.player
        if self.scrobbler is not None and self.queue_index >= 0:
            song = self.queue[self.queue_index]
            self.scrobbler.tick(
                player.time_pos, player.duration or song.duration, player.paused
            )
        self._render_now_playing()

    # ── data loading (thread workers) ──

    @work(thread=True, exclusive=True, group="albums")
    def load_albums(self) -> None:
        label, list_type = self.SORTS[self.sort_index]
        self.app.call_from_thread(self._show_albums_note, "☕ fetching your library…")
        try:
            albums = self.app.client.album_list_all(list_type)
        except Exception as exc:
            self.app.call_from_thread(self._show_albums_error, str(exc))
            return
        if label == "random":
            import random

            random.shuffle(albums)
        self.app.call_from_thread(self._show_albums, albums)

    def _show_albums_note(self, note: str) -> None:
        lst = self.query_one("#albums", CozyList)
        lst.clear_options()
        lst.add_option(Option(f"[{DIM}]{note}[/]", disabled=True))

    def _show_albums_error(self, message: str) -> None:
        lst = self.query_one("#albums", CozyList)
        lst.clear_options()
        lst.add_option(Option(f"☂ {esc_markup(message)}", disabled=True))

    @work(thread=True, exclusive=True, group="albums")
    def run_search_albums(self, query: str) -> None:
        try:
            albums = self.app.client.search_albums(query)
        except Exception as exc:
            self.app.call_from_thread(self._show_albums_error, str(exc))
            return
        note = None if albums else f'☾ nothing found for "{esc_markup(query)}"'
        self.app.call_from_thread(self._show_albums, albums, note, "search")

    def _show_albums(
        self,
        albums: list,
        note: str | None = None,
        source: str | None = None,
    ) -> None:
        self.albums = albums
        label = source or self.SORTS[self.sort_index][0]
        count = f" · {len(albums)}" if albums else ""
        self.query_one("#albums-title", PaneTitle).update(
            f"✻ albums  [{DIM}]· {label}{count}[/]"
        )
        lst = self.query_one("#albums", CozyList)
        lst.clear_options()
        if note:
            lst.add_option(Option(note, disabled=True))
        for album in albums:
            year = f"  [{DIM}]{album.year}[/]" if album.year else ""
            lst.add_option(
                Option(
                    f"{esc_markup(album.name)}  "
                    f"[{DIM}]{esc_markup(album.artist)}[/]{year}"
                )
            )
        if albums:
            lst.highlighted = 0

    @work(thread=True, exclusive=True, group="songs")
    def load_album_songs(self, album_id: str) -> None:
        try:
            songs = self.app.client.album_songs(album_id)
        except Exception as exc:
            self.app.call_from_thread(self._show_songs, [], f"☂ {esc_markup(str(exc))}")
            return
        self.app.call_from_thread(self._show_songs, songs)

    @work(thread=True, exclusive=True, group="songs")
    def run_search(self, query: str) -> None:
        try:
            songs = self.app.client.search_songs(query)
        except Exception as exc:
            self.app.call_from_thread(self._show_songs, [], f"☂ {esc_markup(str(exc))}")
            return
        note = None if songs else f'☾ nothing found for "{esc_markup(query)}"'
        self.app.call_from_thread(self._show_songs, songs, note)

    def _show_songs(self, songs: list, note: str | None = None) -> None:
        self.songs = songs
        lst = self.query_one("#songs", CozyList)
        lst.clear_options()
        if note:
            lst.add_option(Option(note, disabled=True))
        for song in songs:
            length = f"  [{DIM}]{fmt_time(song.duration)}[/]" if song.duration else ""
            lst.add_option(
                Option(
                    f"{esc_markup(song.title)}  "
                    f"[{DIM}]{esc_markup(song.artist)}[/]{length}"
                )
            )
        if songs:
            lst.highlighted = 0

    # ── list events ──

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if event.option_list.id == "albums" and 0 <= event.option_index < len(
            self.albums
        ):
            self.load_album_songs(self.albums[event.option_index].id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "albums":
            self.query_one("#songs", CozyList).focus()
        elif event.option_list.id == "songs":
            index = event.option_index
            if self.songs and 0 <= index < len(self.songs):
                self.queue = list(self.songs)
                self.queue_index = index
                self._play_current()

    # ── playback ──

    def _play_current(self) -> None:
        if not (0 <= self.queue_index < len(self.queue)):
            return
        song = self.queue[self.queue_index]
        self.app.player.play(self.app.client.stream_url(song.id))
        if self.scrobbler is not None:
            self.scrobbler.track_started(song)
        self._render_now_playing()

    def advance(self) -> None:
        if self.queue_index + 1 < len(self.queue):
            self.queue_index += 1
            self._play_current()
        else:
            self.queue_index = -1
            if self.scrobbler is not None:
                self.scrobbler.stopped()
            self._render_now_playing()

    def action_toggle_pause(self) -> None:
        if isinstance(self.focused, Input):
            return
        self.app.player.toggle_pause()

    def action_next_song(self) -> None:
        if self.queue_index >= 0:
            self.advance()

    def action_seek(self, seconds: int) -> None:
        if self.queue_index >= 0:
            self.app.player.seek(seconds)
            self._render_now_playing()

    def action_prev_song(self) -> None:
        if self.queue_index > 0:
            self.queue_index -= 1
            self._play_current()

    # ── other actions ──

    def action_search(self) -> None:
        self.query_one("#search-row").add_class("visible")
        self.query_one("#search", Input).focus()

    def action_hide_search(self) -> None:
        self.query_one("#search-row").remove_class("visible")
        self.query_one("#albums", CozyList).focus()

    def action_toggle_search_mode(self) -> None:
        self.search_mode = "songs" if self.search_mode == "albums" else "albums"
        self.query_one("#search-mode", Static).update(self.search_mode)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search":
            query = event.value.strip()
            self.query_one("#search-row").remove_class("visible")
            if self.search_mode == "albums":
                if query:
                    self.run_search_albums(query)
                self.query_one("#albums", CozyList).focus()
            else:
                if query:
                    self.run_search(query)
                self.query_one("#songs", CozyList).focus()

    def action_cycle_sort(self) -> None:
        self.sort_index = (self.sort_index + 1) % len(self.SORTS)
        self.load_albums()

    def action_shuffle_albums(self) -> None:
        self.sort_index = next(
            i for i, (label, _) in enumerate(self.SORTS) if label == "random"
        )
        self.load_albums()

    def action_cycle_replaygain(self) -> None:
        player = self.app.player
        modes = REPLAYGAIN_MODES
        current = getattr(player, "replaygain", "off")
        if current not in modes:
            current = "off"
        player.set_replaygain(modes[(modes.index(current) + 1) % len(modes)])
        self._render_now_playing()

    def action_volume_up(self) -> None:
        self._adjust_volume(self.VOLUME_STEP)

    def action_volume_down(self) -> None:
        self._adjust_volume(-self.VOLUME_STEP)

    def _adjust_volume(self, delta: int) -> None:
        self.app.player.adjust_volume(delta)
        # flash the level in the footer for a few seconds, then let the
        # 0.5s tick sweep it away
        self._volume_note_until = time.monotonic() + self.VOLUME_NOTE_SECONDS
        self._render_now_playing()

    def action_swap_pane(self) -> None:
        albums = self.query_one("#albums", CozyList)
        songs = self.query_one("#songs", CozyList)
        (songs if self.focused is albums else albums).focus()

    # ── now playing footer ──

    def _render_now_playing(self) -> None:
        widget = self.query_one("#now-playing", NowPlaying)
        player = self.app.player
        if self.queue_index < 0 or not self.queue:
            widget.update(f"[{DIM}]☕ nothing playing — pick a song and press enter[/]")
            return
        song = self.queue[self.queue_index]
        mark = "☾" if player.paused else "♪"
        duration = player.duration or song.duration
        bar = progress_bar(player.time_pos, duration)
        times = f"[{DIM}]{fmt_time(player.time_pos)} / {fmt_time(duration)}[/]"
        notes: list[str] = []
        volume = getattr(player, "volume", None)
        if volume is not None and time.monotonic() < self._volume_note_until:
            notes.append(f"vol {int(round(volume))}")
        gain = getattr(player, "replaygain", "off")
        if gain != "off":
            notes.append(f"rg {gain}")
        note_text = "".join(f"  [{DIM}]· {note}[/]" for note in notes)
        widget.update(
            f"[{ACCENT}]{mark}[/] {esc_markup(song.title)}  "
            f"[{DIM}]{esc_markup(song.artist)}[/]\n{bar}  {times}{note_text}"
        )
