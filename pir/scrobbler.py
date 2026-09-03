"""Scrobbling: keeps the server posted on what's playing and files plays."""

import queue
import threading
import time

from .models import Song
from .services import SubsonicClient


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
