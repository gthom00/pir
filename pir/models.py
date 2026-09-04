"""Data models for the Subsonic/Navidrome API."""

from dataclasses import dataclass


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
