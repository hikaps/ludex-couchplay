# ludex-couchplay

A [ludex](https://github.com/hikaps/ludex) plugin that adds **Play split-screen** to Steam and Heroic games, started through [CouchPlay](https://github.com/hikaps/couchplay).

It adds a button to a game's page in `ludex gui` and a `ludex action GAME couchplay:split-screen` command. The game opens in the CouchPlay profile you choose, for the players who use that game's launcher; your saved profile is not changed. CouchPlay needs the `--game` option (hikaps/couchplay#181).

## Install

```sh
ludex plugin add ludex-couchplay        # runs with your permissions
ludex config couchplay.profile "My profile"
```

The profile is the name of a saved CouchPlay profile (its players, controllers and screens). Without it nothing is offered.

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
