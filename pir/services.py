"""Subsonic/Navidrome REST API client with salted-token auth."""

import hashlib
import secrets

import requests

from .consts import API_VERSION, APP_NAME
from .models import Album, Song, SubsonicError


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
