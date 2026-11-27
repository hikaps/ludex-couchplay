# LAN invites (`ludex_lan`)

Companion to [ludex](https://github.com/hikaps/ludex) for LAN co-op of Windows games under Proton, on one PC or
several. A small **agent** watches the LAN for players and routes invites; a controller **overlay** shows the accept
prompt and a peer picker in the player's own [CouchPlay](https://github.com/hikaps/couchplay) pane.

```text
game (gbe_fork steam_api.dll) <-- UDP/TCP 47584-47593 --> agent <-- TCP 47600 --> agents on other PCs
                                                           ^ control socket
                                                        overlay (LB+RB+Y)
```

## Backends

A backend turns "which players exist, which session each has joined" into `Presence` records and delivers an invite
into a game (`backends/__init__.py`). One backend serves a whole family of games.

| backend | games | state |
| --- | --- | --- |
| `gbe` | Steamworks games, via the pinned [gbe_fork](https://github.com/Detanup01/gbe_fork) `steam_api(64).dll` | works |

An invite is only handed to the game after the player accepts in the overlay.

### gbe

ludex-lan does not patch or launch games. A game takes part once it runs with gbe_fork's `steam_api(64).dll`:

```sh
ludex patches patch --directory "<game dir>" gbe_fork --app-id 49520    # ludex-patches: pinned gbe_fork, restorable
```

The agent matches each local player to the Steam id that player's game announces, so each player's game needs a known
id. gbe reads it from `configs.user.ini` in the Wine prefix, `drive_c/users/steamuser/AppData/Roaming/GSE Saves/settings/`
(one prefix per player, so players sharing a game folder keep their own id), or from the game's `steam_settings` folder:

```ini
[user::general]
account_name=Player 1
account_steamid=76561198000000001
```

Without it gbe makes up a random id and the agent cannot tell which player the game belongs to. ludex-couchplay's
"Play split-screen with LAN invites" writes it into each CouchPlay seat's prefix (see the README); standalone, write it
yourself. Games on an
old Steamworks SDK may also need a `steam_interfaces.txt`, which ludex-patches does not write (`[INFERENCE]`: Pummel
Party works without it, BL2 was not tried without).

Launching is not this tool's job: start each player's game however you like (ludex, `umu-run` with one `WINEPREFIX`
per player, or [ludex-couchplay](https://github.com/hikaps/ludex-couchplay) for split-screen). Players on different PCs
need only a shared network, such as a LAN or a VPN that passes UDP broadcast (gbe finds peers by broadcast).

The agent is another gbe peer. Players are listed as soon as their game announces itself, by Steam id until the game
sends its name. A game sends its name, app id and lobby when it creates or leaves a lobby, so **a player can be invited
only once their game has a lobby** (host or open one first); the picker says so otherwise.

### Agent

```sh
ludex-lan agent --player "Player 1=76561198000000001" --player "Player 2=76561198000000002"
```

One control socket per local player. `STEAMID` is that player's `account_steamid`; without `=STEAMID` the agent derives
an id from the name and this machine's id, which only helps when the same derivation wrote the player's ini.

Run one agent per PC. Agents find each other over the gbe announces and talk on TCP 47600.

Firewall: allow UDP and TCP 47584-47593 (gbe) and TCP 47600 (agents).

## Invite overlay

`ludex-lan-overlay` lets one CouchPlay player answer invites and invite other players with the controller alone.
It shows its notices and lists in that player's pane.

The overlay waits for the player to hold LB + RB + Y for about 600 ms. CouchPlay then hands that player's pad to
the overlay (`couchplay pad capture --wait-chord`), so the game sees no input. What the hold opens:

- **An invite is pending** (a notice names the sender): A accepts, B declines.
- **No invite is pending**: a list of the players on the LAN. D-pad up/down moves, A invites the highlighted
  player, B closes. Players already in the game are marked and cannot be invited. The list says so when the game has
  nothing to invite to yet (start the game and host first).
- An invite that arrives while the list is open takes over the screen.

Doing nothing for 20 s gives the pad back; a pending invite stays pending.

```sh
ludex-lan-overlay --player "Player 2" --pane 1920,0,1920,1080
```

- `--player`: the CouchPlay player name whose controller answers. It also selects the agent's control socket.
- `--pane`: `X,Y,WIDTH,HEIGHT` of that player's pane. The overlay is placed in its top-left corner with a KWin
  script, so it needs KDE Plasma.
- `--control-dir`: the agent's control directory for that player (default: `$XDG_RUNTIME_DIR/ludex-lan/<player>`,
  or set `LUDEX_LAN_CONTROL_DIR`).
- `--couchplay`: command that runs CouchPlay. Default: `couchplay`, else `flatpak run --die-with-parent
  io.github.hikaps.couchplay`.

Requires a CouchPlay with `pad capture` (not released yet). Run one overlay per player; the pane geometry is
passed by hand for now.

## Development

```sh
uv venv && uv pip install -e ".[test]" /path/to/ludex/packages/core
.venv/bin/python -m pytest
```

The state machine (`flow.py`), the control-socket client (`control.py`), the agent and the gbe wire codec are tested
without Qt or a game. The overlay needs `pip install "ludex-couchplay[overlay]"` (PySide6).
