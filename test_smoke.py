"""Headless smoke tests: mount the app with a fake client and fake player,
drive it with Textual's pilot, and make sure the cozy machinery works.

Run:  .venv/bin/python -m pytest test_smoke.py -q
"""

from __future__ import annotations

import pytest

import cozydrome
from cozydrome import Album, CozydromeApp, MainScreen, Song, fmt_time, progress_bar


class FakeClient:
    def __init__(self) -> None:
        self.albums = [
            Album(id="a1", name="Evening Tea", artist="The Kettles", year=2021),
            Album(id="a2", name="Rainy Windows", artist="Cloud Choir", year=2019),
        ]
        self.songs = {
            "a1": [
                Song(id="s1", title="Steam", artist="The Kettles", album="Evening Tea", duration=181),
                Song(id="s2", title="Chamomile", artist="The Kettles", album="Evening Tea", duration=222),
            ],
            "a2": [
                Song(id="s3", title="Drizzle", artist="Cloud Choir", album="Rainy Windows", duration=143),
            ],
        }

    def album_list(self, list_type="newest", size=100):
        return self.albums

    def album_songs(self, album_id):
        return self.songs[album_id]

    def search_songs(self, query, count=50):
        return [s for songs in self.songs.values() for s in songs if query.lower() in s.title.lower()]

    def search_albums(self, query, count=50):
        return [a for a in self.albums if query.lower() in a.name.lower()]

    def stream_url(self, song_id):
        return f"fake://stream/{song_id}"


class FakePlayer:
    def __init__(self) -> None:
        self.time_pos = 42.0
        self.duration = 181.0
        self.paused = False
        self.played: list[str] = []

    def start(self):
        pass

    def play(self, url):
        self.played.append(url)

    def toggle_pause(self):
        self.paused = not self.paused

    def stop(self):
        pass

    def shutdown(self):
        pass


def make_app() -> CozydromeApp:
    app = CozydromeApp(client=FakeClient())
    app.player = FakePlayer()
    return app


@pytest.mark.asyncio
async def test_mounts_and_lists_albums():
    app = make_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.3)
        assert isinstance(app.screen, MainScreen)
        albums = app.screen.query_one("#albums")
        assert albums.option_count == 2
        # highlighting the first album loads its songs
        songs = app.screen.query_one("#songs")
        assert songs.option_count == 2


@pytest.mark.asyncio
async def test_play_pause_and_advance():
    app = make_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.3)
        # jump to the songs pane and play the first track
        await pilot.press("tab")
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert app.player.played == ["fake://stream/s1"]
        # space toggles pause
        await pilot.press("space")
        assert app.player.paused is True
        # n advances the queue
        await pilot.press("n")
        await pilot.pause(0.1)
        assert app.player.played[-1] == "fake://stream/s2"
        # footer shows the cozy now-playing line
        app.screen._render_now_playing()
        await pilot.pause(0.1)


@pytest.mark.asyncio
async def test_album_search_is_default():
    app = make_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("slash")
        assert app.screen.search_mode == "albums"
        for ch in "rainy":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause(0.3)
        albums = app.screen.query_one("#albums")
        assert albums.option_count == 1
        assert app.screen.albums[0].id == "a2"


@pytest.mark.asyncio
async def test_song_search_via_toggle():
    app = make_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("slash")
        # tab inside the search box flips the target instead of moving focus
        await pilot.press("tab")
        assert app.screen.search_mode == "songs"
        assert app.screen.focused.id == "search"
        for ch in "drizzle":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause(0.3)
        songs = app.screen.query_one("#songs")
        assert songs.option_count == 1
        assert app.screen.songs[0].id == "s3"


def test_fmt_time():
    assert fmt_time(0) == "0:00"
    assert fmt_time(61) == "1:01"
    assert fmt_time(3599) == "59:59"


def test_progress_bar_renders():
    assert "●" in progress_bar(30, 60)
    assert "●" not in progress_bar(0, 0)


def test_auth_token_never_contains_password():
    client = cozydrome.SubsonicClient("https://x.example", "graham", "sekrit")
    params = client._auth_params()
    assert "sekrit" not in "".join(params.values())
    url = client.stream_url("song1")
    assert "sekrit" not in url
    assert "t=" in url and "s=" in url


@pytest.mark.asyncio
async def test_setup_screen_mounts(monkeypatch):
    monkeypatch.setattr(cozydrome.Config, "load", classmethod(lambda cls: None))
    app = CozydromeApp()
    app.player = FakePlayer()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.3)
        assert isinstance(app.screen, cozydrome.SetupScreen)
        # submitting with empty fields shows the gentle nag, not a crash
        await pilot.press("enter")
        app.screen.query_one("#password")
