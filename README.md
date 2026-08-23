# ✿ cozydrome

a cozy little [Navidrome](https://www.navidrome.org/) client for your terminal.

no borders — just gentle padding, cute symbols, and your terminal's own
colors (the palette is deliberately tiny: magenta for warmth, bright-black
for whispers, and your default fg/bg for everything else).

```
  ✿ cozydrome   · space pause · n next · / search · r shuffle · q quit

  ✧ albums                            ♫ songs
   ❀ Evening Tea  The Kettles  2021    · Steam  The Kettles  3:01
   ❀ Rainy Windows  Cloud Choir       · Chamomile  The Kettles  3:42

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
.venv/bin/cozydrome
```

first run asks for your server url, username, and password. the password
goes into your **system keychain** (via `keyring` — Keychain on macOS,
Secret Service on Linux); only the server url and username are written to
`~/.config/cozydrome/config.toml` (chmod 600). requests use subsonic
salted-token auth, so the raw password is never placed in a url.

## keys

| key     | does                                  |
| ------- | ------------------------------------- |
| `j`/`k`/arrows | wander the lists               |
| `tab`   | hop between albums and songs          |
| `enter` | on an album: peek inside · on a song: play from here |
| `space` | pause / resume                        |
| `n`/`b` | next / back                           |
| `/`     | search songs                          |
| `r`     | shuffle in a fresh batch of albums    |
| `q`     | goodnight ☾                           |

## forgetting a login

```sh
python3 -c "import keyring; keyring.delete_password('cozydrome', 'YOUR_USERNAME')"
rm ~/.config/cozydrome/config.toml
```

## tests

```sh
.venv/bin/pip install pytest pytest-asyncio
.venv/bin/python -m pytest test_smoke.py -q
```
