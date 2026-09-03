#!/usr/bin/env python3
"""pir — a cozy little Navidrome client for your terminal.

No borders, gentle padding, a few cute symbols, and no colors at all —
just your terminal's default foreground with bold, dim, and reverse.
Playback is handled by mpv; your password lives in the system keychain.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import random
import secrets
import socket
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import keyring
import requests

from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

APP_NAME = "pir"
API_VERSION = "1.16.1"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.toml"

ACCENT = "bold"
DIM = "dim"


# ──────────────────────────── config & credentials ────────────────────────────


@dataclass
class Config:
    server: str = ""
    username: str = ""

    @classmethod
    def load(cls) -> "Config | None":
        try:
            import tomllib

            with open(CONFIG_FILE, "rb") as f:
                data = tomllib.load(f)
            server = data.get("server", "").rstrip("/")
            username = data.get("username", "")
            if server and username:
                return cls(server=server, username=username)
        except FileNotFoundError:
            pass
        return None

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        body = f'server = "{self.server}"\nusername = "{self.username}"\n'
        CONFIG_FILE.write_text(body, encoding="utf-8")
        CONFIG_FILE.chmod(0o600)

    def password(self) -> str | None:
        return keyring.get_password(APP_NAME, self.username)

    def store_password(self, password: str) -> None:
        keyring.set_password(APP_NAME, self.username, password)


# ──────────────────────────── subsonic api client ─────────────────────────────


class SubsonicError(Exception):
    pass


@dataclass
class Album:
    id: str
    name: str
    artist: str
    year: int | None = None
    song_count: int = 0


@dataclass
class Song:
    id: str
    title: str
    artist: str
    album: str
    duration: int = 0
    track: int | None = None


class SubsonicClient:
    """Tiny Subsonic REST client using salted-token auth.

    The raw password is only used to derive per-request tokens
    (md5(password + salt)); it is never placed in a URL.
    """

    def __init__(self, server: str, username: str, password: str) -> None:
        self.server = server.rstrip("/")
        self.username = username
        self._password = password
        self._session = requests.Session()

    def _auth_params(self) -> dict[str, str]:
        salt = secrets.token_hex(8)
        token = hashlib.md5((self._password + salt).encode()).hexdigest()
        return {
            "u": self.username,
            "t": token,
            "s": salt,
            "v": API_VERSION,
            "c": APP_NAME,
            "f": "json",
        }

    def _get(self, endpoint: str, **params: str) -> dict:
        url = f"{self.server}/rest/{endpoint}"
        resp = self._session.get(
            url, params={**self._auth_params(), **params}, timeout=15
        )
        resp.raise_for_status()
        body = resp.json()["subsonic-response"]
        if body.get("status") != "ok":
            err = body.get("error", {})
            raise SubsonicError(err.get("message", "unknown server error"))
        return body

    def ping(self) -> None:
        self._get("ping")

    def album_list_all(self, list_type: str = "alphabeticalByName") -> list[Album]:
        """Every album in the library, paged through getAlbumList2."""
        albums: list[Album] = []
        offset = 0
        while True:
            body = self._get(
                "getAlbumList2", type=list_type, size="500", offset=str(offset)
            )
            batch = [
                self._album(a) for a in body.get("albumList2", {}).get("album", [])
            ]
            albums.extend(batch)
            if len(batch) < 500:
                return albums
            offset += 500

    def search_albums(self, query: str, count: int = 50) -> list[Album]:
        body = self._get(
            "search3",
            query=query,
            albumCount=str(count),
            songCount="0",
            artistCount="0",
        )
        albums = body.get("searchResult3", {}).get("album", [])
        return [self._album(a) for a in albums]

    def album_songs(self, album_id: str) -> list[Song]:
        body = self._get("getAlbum", id=album_id)
        songs = body.get("album", {}).get("song", [])
        return [self._song(s) for s in songs]

    def search_songs(self, query: str, count: int = 50) -> list[Song]:
        body = self._get(
            "search3",
            query=query,
            songCount=str(count),
            albumCount="0",
            artistCount="0",
        )
        songs = body.get("searchResult3", {}).get("song", [])
        return [self._song(s) for s in songs]

    def scrobble(
        self, song_id: str, submission: bool, timestamp_ms: int | None = None
    ) -> None:
        """Tell the server what's playing.

        submission=False is a "now playing" heartbeat that Navidrome shows
        in its web UI and forwards to Last.fm; submission=True records the
        play in the listening history.
        """
        params = {"id": song_id, "submission": "true" if submission else "false"}
        if timestamp_ms is not None:
            params["time"] = str(timestamp_ms)
        self._get("scrobble", **params)

    def stream_url(self, song_id: str) -> str:
        params = {**self._auth_params(), "id": song_id}
        query = "&".join(
            f"{k}={requests.utils.quote(str(v))}" for k, v in params.items()
        )
        return f"{self.server}/rest/stream?{query}"

    @staticmethod
    def _album(a: dict) -> Album:
        return Album(
            id=a["id"],
            name=a.get("name", "untitled"),
            artist=a.get("artist", "unknown artist"),
            year=a.get("year"),
            song_count=a.get("songCount", 0),
        )

    @staticmethod
    def _song(s: dict) -> Song:
        return Song(
            id=s["id"],
            title=s.get("title", "untitled"),
            artist=s.get("artist", "unknown artist"),
            album=s.get("album", ""),
            duration=s.get("duration", 0),
            track=s.get("track"),
        )


# ─────────────────────────────── mpv playback ─────────────────────────────────


class MpvPlayer:
    """Drives an mpv subprocess over its JSON IPC socket."""

    def __init__(self, on_track_end=None) -> None:
        self.on_track_end = on_track_end
        self.time_pos: float = 0.0
        self.duration: float = 0.0
        self.paused: bool = False
        self._sock: socket.socket | None = None
        self._proc: subprocess.Popen | None = None
        self._sock_path = os.path.join(
            tempfile.gettempdir(), f"{APP_NAME}-mpv-{os.getpid()}.sock"
        )
        self._lock = threading.Lock()

    def start(self) -> None:
        self._proc = subprocess.Popen(
            [
                "mpv",
                "--idle=yes",
                "--no-video",
                "--no-terminal",
                f"--input-ipc-server={self._sock_path}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(50):  # wait up to 5s for the socket
            if os.path.exists(self._sock_path):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("mpv did not create its IPC socket")
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.connect(self._sock_path)
        threading.Thread(target=self._reader, daemon=True).start()
        for prop_id, prop in ((1, "time-pos"), (2, "duration"), (3, "pause")):
            self._send({"command": ["observe_property", prop_id, prop]})

    def _send(self, payload: dict) -> None:
        with self._lock:
            if self._sock is not None:
                try:
                    self._sock.sendall(json.dumps(payload).encode() + b"\n")
                except OSError:
                    pass

    def _reader(self) -> None:
        buf = b""
        while self._sock is not None:
            try:
                chunk = self._sock.recv(4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._handle(msg)

    def _handle(self, msg: dict) -> None:
        event = msg.get("event")
        if event == "property-change":
            name, data = msg.get("name"), msg.get("data")
            if name == "time-pos" and isinstance(data, (int, float)):
                self.time_pos = float(data)
            elif name == "duration" and isinstance(data, (int, float)):
                self.duration = float(data)
            elif name == "pause" and isinstance(data, bool):
                self.paused = data
        elif event == "end-file" and msg.get("reason") == "eof":
            if self.on_track_end is not None:
                self.on_track_end()

    def play(self, url: str) -> None:
        self.time_pos = 0.0
        self.duration = 0.0
        self._send({"command": ["loadfile", url, "replace"]})
        self._send({"command": ["set_property", "pause", False]})

    def toggle_pause(self) -> None:
        self._send({"command": ["cycle", "pause"]})

    def seek(self, seconds: float) -> None:
        """Jump `seconds` forwards (or backwards, if negative)."""
        self._send({"command": ["seek", seconds, "relative"]})
        # move the clock now so the bar answers the keypress; mpv's own
        # time-pos will overwrite this within a tick
        limit = self.duration if self.duration > 0 else self.time_pos + seconds
        self.time_pos = min(max(0.0, self.time_pos + seconds), limit)

    def stop(self) -> None:
        self._send({"command": ["stop"]})
        self.time_pos = 0.0
        self.duration = 0.0

    def shutdown(self) -> None:
        self._send({"command": ["quit"]})
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if self._proc is not None:
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        try:
            os.unlink(self._sock_path)
        except OSError:
            pass


# ──────────────────────────────── scrobbling ──────────────────────────────────


class Scrobbler:
    """Keeps the server posted on what's playing, and files the play once
    it counts.

    A track counts after half its length or four minutes of listening,
    whichever comes first; anything shorter than 30 seconds never counts.
    Only real listening adds up — pauses and skips ahead don't, since the
    time is accumulated from how far the clock actually crept forward.

    Requests go out on a background thread so a slow server never stalls
    the interface, and a failed one is dropped: a missing scrobble isn't
    worth interrupting the music over.
    """

    MIN_DURATION = 30.0  # shorter tracks are never scrobbled
    MAX_REQUIRED = 240.0  # four minutes is always enough
    PING_INTERVAL = 30.0  # how often to refresh "now playing"
    MAX_STEP = 2.0  # a bigger jump than this is a seek, not listening

    def __init__(self, client: SubsonicClient) -> None:
        self._client = client
        self._outbox: queue.Queue[tuple[str, bool, int | None]] = queue.Queue()
        self._song: Song | None = None
        self._started_at = 0.0
        self._listened = 0.0
        self._last_pos = 0.0
        self._next_ping = 0.0
        self._submitted = False
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        while True:
            song_id, submission, timestamp = self._outbox.get()
            try:
                self._client.scrobble(song_id, submission, timestamp)
            except Exception:
                pass

    def track_started(self, song: Song) -> None:
        self._song = song
        self._started_at = time.time()
        self._listened = 0.0
        self._last_pos = 0.0
        self._submitted = False
        self._ping()

    def stopped(self) -> None:
        self._song = None

    def tick(self, position: float, duration: float, paused: bool) -> None:
        """Feed in the playback clock; call this a couple of times a second."""
        if self._song is None:
            return
        step = position - self._last_pos
        self._last_pos = position
        if paused:
            return
        if 0 < step <= self.MAX_STEP:
            self._listened += step
        if time.monotonic() >= self._next_ping:
            self._ping()
        if not self._submitted and self._counts_as_played(duration):
            self._submitted = True
            self._outbox.put((self._song.id, True, int(self._started_at * 1000)))

    def _counts_as_played(self, duration: float) -> bool:
        if duration < self.MIN_DURATION:
            return False
        return self._listened >= min(duration / 2, self.MAX_REQUIRED)

    def _ping(self) -> None:
        if self._song is None:
            return
        self._next_ping = time.monotonic() + self.PING_INTERVAL
        self._outbox.put((self._song.id, False, None))


# ────────────────────────────────── helpers ───────────────────────────────────


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


# ────────────────────────────────── widgets ───────────────────────────────────


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
    /* the cursor row mirrors the mouse-hover block (ansi_white, palette
       color 7) — reverse video proved invisible on some terminals; black
       text keeps it readable on both light and dark palettes */
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


# ─────────────────────────────── setup screen ─────────────────────────────────


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
                self._status, f"[{DIM}]☂ couldn't get in: {exc}[/]"
            )
            return
        config = Config(server=server, username=username)
        config.save()
        config.store_password(password)
        self.app.call_from_thread(self.app.finish_setup, client)


# ─────────────────────────────── main screen ──────────────────────────────────


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

    def __init__(self) -> None:
        super().__init__()
        self.albums: list[Album] = []
        self.songs: list[Song] = []
        self.queue: list[Song] = []
        self.queue_index: int = -1
        self.search_mode: str = "albums"
        self.sort_index: int = 0
        self.scrobbler: Scrobbler | None = None

    # ── layout ──

    def compose(self) -> ComposeResult:
        yield Static(
            f"[{ACCENT}]✿ {APP_NAME}[/]  "
            f"[{DIM}]· space pause · ←→ seek · n next · / search · s sort · q quit[/]",
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
            random.shuffle(albums)
        self.app.call_from_thread(self._show_albums, albums)

    def _show_albums_note(self, note: str) -> None:
        lst = self.query_one("#albums", CozyList)
        lst.clear_options()
        lst.add_option(Option(f"[{DIM}]{note}[/]", disabled=True))

    def _show_albums_error(self, message: str) -> None:
        lst = self.query_one("#albums", CozyList)
        lst.clear_options()
        lst.add_option(Option(f"☂ {message}", disabled=True))

    @work(thread=True, exclusive=True, group="albums")
    def run_search_albums(self, query: str) -> None:
        try:
            albums = self.app.client.search_albums(query)
        except Exception as exc:
            self.app.call_from_thread(self._show_albums_error, str(exc))
            return
        note = None if albums else f"☾ nothing found for “{query}”"
        self.app.call_from_thread(self._show_albums, albums, note, "search")

    def _show_albums(
        self,
        albums: list[Album],
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
            lst.add_option(Option(f"{album.name}  [{DIM}]{album.artist}[/]{year}"))
        if albums:
            lst.highlighted = 0

    @work(thread=True, exclusive=True, group="songs")
    def load_album_songs(self, album_id: str) -> None:
        try:
            songs = self.app.client.album_songs(album_id)
        except Exception as exc:
            self.app.call_from_thread(self._show_songs, [], f"☂ {exc}")
            return
        self.app.call_from_thread(self._show_songs, songs)

    @work(thread=True, exclusive=True, group="songs")
    def run_search(self, query: str) -> None:
        try:
            songs = self.app.client.search_songs(query)
        except Exception as exc:
            self.app.call_from_thread(self._show_songs, [], f"☂ {exc}")
            return
        note = None if songs else f"☾ nothing found for “{query}”"
        self.app.call_from_thread(self._show_songs, songs, note)

    def _show_songs(self, songs: list[Song], note: str | None = None) -> None:
        self.songs = songs
        lst = self.query_one("#songs", CozyList)
        lst.clear_options()
        if note:
            lst.add_option(Option(note, disabled=True))
        for song in songs:
            length = f"  [{DIM}]{fmt_time(song.duration)}[/]" if song.duration else ""
            lst.add_option(Option(f"{song.title}  [{DIM}]{song.artist}[/]{length}"))
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
        widget.update(
            f"[{ACCENT}]{mark}[/] {song.title}  [{DIM}]{song.artist}[/]\n{bar}  {times}"
        )


# ──────────────────────────────────── app ─────────────────────────────────────


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
        try:
            self.player.start()
        except (FileNotFoundError, RuntimeError):
            self.exit(
                message="☂ mpv is needed for playback — brew install mpv, then come back!"
            )
            return
        if self.client is None:
            config = Config.load()
            password = config.password() if config else None
            if config and password:
                self.client = SubsonicClient(config.server, config.username, password)
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
    PirApp().run()


if __name__ == "__main__":
    main()
