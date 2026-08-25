# ✿ pir

a cozy little [Navidrome](https://www.navidrome.org/) client for your terminal.

no borders, no scrollbars, no colors — just gentle padding, a few cute
symbols, and your terminal's default fg/bg dressed up with nothing but
bold, dim, and reverse.

```
  ✿ pir   · space pause · n next · / search · s sort · r shuffle · q quit

  ✻ albums  · alphabetical · 132       ✻ songs
   Evening Tea  The Kettles  2021       Steam  The Kettles  3:01
   Rainy Windows  Cloud Choir           Chamomile  The Kettles  3:42

  ♪ Steam  The Kettles
  ─────────●──────────────────  0:42 / 3:01
```

## needs

- python 3.11+
- [mpv](https://mpv.io/) on your PATH (`brew install mpv`) — it does the
  actual listening

## setup

```sh
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/pir
```

first run asks for your server url, username, and password. the password
goes into your **system keychain** (via `keyring` — Keychain on macOS,
Secret Service on Linux); only the server url and username are written to
`~/.config/pir/config.toml` (chmod 600). requests use subsonic
salted-token auth, so the raw password is never placed in a url.

pir used to be called cozydrome — an old login is copied over
automatically the first time pir runs.

## keys

| key     | does                                  |
| ------- | ------------------------------------- |
| `j`/`k`/arrows | wander the lists               |
| `tab`   | hop between albums and songs          |
| `enter` | on an album: peek inside · on a song: play from here |
| `space` | pause / resume                        |
| `n`/`b` | next / back                           |
| `/`     | search albums (`tab` in the box switches to songs) |
| `s`     | cycle sort: alphabetical · recently added · recently played · random |
| `r`     | jump straight to a fresh shuffle      |
| `q`     | goodnight ☾                           |

the albums pane always holds your whole library; the pane title shows the
current sort and how many albums live there.

## forgetting a login

```sh
python3 -c "import keyring; keyring.delete_password('pir', 'YOUR_USERNAME')"
rm ~/.config/pir/config.toml
```

(if you upgraded from cozydrome, the old entries may still be around —
same two commands with `pir` swapped for `cozydrome`.)

## license

[MIT](LICENSE)

## tests

```sh
.venv/bin/pip install pytest pytest-asyncio
.venv/bin/python -m pytest test_smoke.py -q
```
