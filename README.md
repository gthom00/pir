# ✿ pir

A small [Navidrome](https://www.navidrome.org/) client for the terminal.

No borders, no scrollbars, no colours — just your terminal's own
foreground and background, dressed up with bold and dim.

```
  ✿ pir   · space pause · ←→ seek · n next · / search · s sort · q quit

  ✻ albums  · alphabetical · 132       ✻ songs
   Evening Tea  The Kettles  2021       Steam  The Kettles  3:01
   Rainy Windows  Cloud Choir           Chamomile  The Kettles  3:42

  ♪ Steam  The Kettles
  ─────────●──────────────────  0:42 / 3:01
```

## Needs

Python 3.11 or newer, and [mpv](https://mpv.io/) on your PATH
(`brew install mpv`) — mpv does the actual listening.

## Install

With [uv](https://docs.astral.sh/uv/), which puts `pir` on your PATH in
its own isolated environment:

```sh
uv tool install .
```

That drops the executable in `~/.local/bin`; if that isn't on your PATH
yet, `uv tool update-shell` will add it. After a `git pull`, reinstall
with `uv tool install . --force` — the version number doesn't move
between commits, so a plain upgrade has nothing to go on. `uv tool
uninstall pir` to be rid of it.

[pipx](https://pipx.pypa.io/) does the same job if you'd rather:

```sh
pipx install .
```

Or keep it local to the checkout and skip PATH entirely:

```sh
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/pir
```

The first run asks for your server URL, username, and password. The
password goes into your system keychain via `keyring` — Keychain on
macOS, Secret Service on Linux. Only the server URL and username are
written to `~/.config/pir/config.toml`, chmod 600. Requests use Subsonic
salted-token auth, so the raw password never appears in a URL.

## Keys

| key             | does                                                   |
| --------------- | ------------------------------------------------------ |
| arrows          | move through the lists                                 |
| `tab`           | switch between albums and songs                        |
| `enter`         | on an album: open it · on a song: play from there      |
| `space`         | pause / resume                                         |
| `←` `→`         | scrub 5 seconds (hold shift for 30)                    |
| `n` `b`         | next / previous track                                  |
| `/`             | search albums (`tab` in the box switches to songs)     |
| `s`             | cycle sort: alphabetical, recently added, recently played, random |
| `r`             | jump straight to a fresh shuffle                       |
| `q`             | quit                                                   |

The albums pane always holds your whole library; the pane title shows the
current sort and the album count.

## Scrobbling

pir reports what you're listening to as you listen. The moment a track
starts it tells the server, and refreshes that every 30 seconds, so
Navidrome's web UI shows the same thing you're hearing.

The play itself is recorded once you've heard half the track or four
minutes of it, whichever comes first — the usual rule. Tracks under 30
seconds never count, and neither does time you skipped past: pir adds up
how far the clock actually moved, so scrubbing to the end doesn't earn a
scrobble. Everything goes out on a background thread, and a request that
fails is quietly dropped rather than interrupting playback.

## Forgetting a login

```sh
python3 -c "import keyring; keyring.delete_password('pir', 'YOUR_USERNAME')"
rm ~/.config/pir/config.toml
```

## Tests

```sh
.venv/bin/pip install pytest pytest-asyncio
.venv/bin/python -m pytest test_smoke.py -q
```

## License

[MIT](LICENSE)
