"""Configuration and credential storage."""

import os
from dataclasses import dataclass
from pathlib import Path

import keyring

from .consts import APP_NAME, CONFIG_DIR, CONFIG_FILE


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
