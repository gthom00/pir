"""Constants used across the pir package."""

import os
from pathlib import Path

APP_NAME = "pir"
API_VERSION = "1.16.1"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.toml"

ACCENT = "bold"
DIM = "dim"
