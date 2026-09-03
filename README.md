# [pir](https://www.youtube.com/watch?v=Zagwerydn7o)

simple [navidrome](https://www.navidrome.org/) client for the terminal

```
  ✿ pir   · space pause · ←→ seek · n next · / search · s sort · q quit

  ✻ albums  · alphabetical · 132       ✻ songs
   Evening Tea  The Kettles  2021       Steam  The Kettles  3:01
   Rainy Windows  Cloud Choir           Chamomile  The Kettles  3:42

  ♪ Steam  The Kettles
  ─────────●──────────────────  0:42 / 3:01
```

## needs

- python 3.11 or newer, 
- [mpv](https://mpv.io/) on your PATH

## install

with [uv](https://docs.astral.sh/uv/):

```sh
uv tool install .
```

[pipx](https://pipx.pypa.io/) does the same job if you'd rather:

```sh
pipx install .
```

the first run asks for your server url, username, and password. the
password goes into your system keychain via `keyring`. only the server
url and username are written to `~/.config/pir/config.toml`, chmod 600.
requests use subsonic salted-token auth

## keys

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

## scrobbling

pir reports what you're listening to as you listen to the server. i only did this for discord rpc

## forgetting a login

```sh
python3 -c "import keyring; keyring.delete_password('pir', 'YOUR_USERNAME')"
rm ~/.config/pir/config.toml
```

## tests

```sh
.venv/bin/pip install pytest pytest-asyncio
.venv/bin/python -m pytest test_smoke.py -q
```

## license

[MIT](LICENSE)
