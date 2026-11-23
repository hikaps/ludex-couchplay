# ludex-couchplay

A [ludex](https://github.com/hikaps/ludex) plugin that adds **Play split-screen** to Steam and Heroic games, started through [CouchPlay](https://github.com/hikaps/couchplay).

It adds buttons to a game's page in `ludex gui` and the commands `ludex action GAME couchplay:quick` and `ludex action GAME couchplay:split-screen`. It needs a CouchPlay with `--game` and `--quick` (hikaps/couchplay#181 and #182).

- **Quick split-screen (N players)**: always offered. CouchPlay starts a session with no profile: N players (2 to 4) named `player1`..`playerN` (created if missing), controllers assigned automatically, default layout and display. Nothing is saved.
- **Play split-screen**: offered once you set a profile. CouchPlay starts that saved profile with this game replacing the game of the players who use the game's launcher; the profile itself is not changed.

## Install

```sh
ludex plugin add ludex-couchplay        # runs with your permissions
ludex config couchplay.players 3                    # players in a quick session (2, 3 or 4; default 2)
ludex config couchplay.profile "My profile"         # optional: also offer "Play split-screen"
```

The profile is the name of a saved CouchPlay profile (its players, controllers and screens).

CouchPlay is found as the `couchplay-gamemode` command, else as the Flatpak `io.github.hikaps.couchplay`.

| ludex store | CouchPlay `--game` |
| --- | --- |
| `steam` | `steam:APPID` |
| `heroic` (sideloads) | `heroic:sideload:APPNAME` |
| `epic` | `heroic:legendary:APPNAME` |

Needs a ludex release with plugin `actions` (see hikaps/ludex#123).

## Develop

```sh
uv venv && uv pip install -e ".[test]" /path/to/ludex/packages/core
.venv/bin/python -m pytest
```

## License

GPL-3.0-or-later.
