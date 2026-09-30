"""Ask macOS which way the interface is facing, so the theme can follow."""

import subprocess
import sys


def prefers_dark() -> bool:
    """True when the OS is in dark mode (False when light, or unknown).

    The key only exists once the user leaves light mode behind — its
    absence is macOS's way of saying it's daytime. `defaults` asks
    cfprefsd directly, so a mode switch is visible here immediately,
    rather than whenever the plist on disk gets around to catching up.
    """
    if sys.platform != "darwin":
        return False
    try:
        probe = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False  # no `defaults`, no verdict — assume daylight
    return probe.stdout.strip() == b"Dark"
