"""mpv playback driver over JSON IPC socket."""

import json
import os
import socket
import subprocess
import tempfile
import threading
import time

from .consts import REPLAYGAIN_MODES


class MpvPlayer:
    """Drives an mpv subprocess over its JSON IPC socket."""

    def __init__(self, on_track_end=None, replaygain: str = "track") -> None:
        self.on_track_end = on_track_end
        self.replaygain = replaygain
        self.time_pos: float = 0.0
        self.duration: float = 0.0
        self.paused: bool = False
        self.volume: float = 100.0
        self._sock: socket.socket | None = None
        self._proc: subprocess.Popen | None = None
        self._sock_path = os.path.join(
            tempfile.gettempdir(), f"pir-mpv-{os.getpid()}.sock"
        )
        self._lock = threading.Lock()

    def _replaygain_flag(self) -> str:
        """Startup flag matching the mode (mpv spells "off" as "no")."""
        value = "no" if self.replaygain == "off" else self.replaygain
        return f"--replaygain={value}"

    def start(self) -> None:
        self._proc = subprocess.Popen(
            [
                "mpv",
                "--idle=yes",
                "--no-video",
                "--no-terminal",
                self._replaygain_flag(),
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
        for prop_id, prop in (
            (1, "time-pos"),
            (2, "duration"),
            (3, "pause"),
            (4, "volume"),
        ):
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
            elif name == "volume" and isinstance(data, (int, float)):
                self.volume = float(data)
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

    def set_replaygain(self, mode: str) -> None:
        """Switch the ReplayGain mode (off, track, or album).

        mpv re-applies the gain to the loaded file as soon as the property
        changes, so the switch is heard without restarting the track.
        """
        if mode not in REPLAYGAIN_MODES:
            raise ValueError(f"unknown replaygain mode: {mode!r}")
        self.replaygain = mode
        # mpv models "off" as the boolean no; track/album are plain strings
        value: object = False if mode == "off" else mode
        self._send({"command": ["set_property", "replaygain", value]})

    def seek(self, seconds: float) -> None:
        """Jump `seconds` forwards (or backwards, if negative)."""
        self._send({"command": ["seek", seconds, "relative"]})
        # move the clock now so the bar answers the keypress; mpv's own
        # time-pos will overwrite this within a tick
        limit = self.duration if self.duration > 0 else self.time_pos + seconds
        self.time_pos = min(max(0.0, self.time_pos + seconds), limit)

    def adjust_volume(self, delta: float) -> None:
        """Change the volume by `delta`; mpv clamps to its own [0, max] range."""
        self._send({"command": ["add", "volume", delta]})
        # move the dial now so the footer answers the keypress; mpv's own
        # volume property will overwrite this within a tick
        self.volume = min(max(0.0, self.volume + delta), 130.0)

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
