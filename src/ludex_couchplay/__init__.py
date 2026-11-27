"""Offers "Play split-screen" on Steam and Heroic games, started through CouchPlay.

Two actions: "Play split-screen" starts a saved CouchPlay profile (its players, controllers and screens)
with ``--game`` replacing the game of the players whose launcher matches, and is offered once the
``profile`` setting is set; "Quick split-screen" starts a session without a profile (``--quick N``: new
default players, controllers assigned automatically, nothing saved) and is always offered. CouchPlay is
found as the ``couchplay-gamemode`` command, else as the Flatpak ``io.github.hikaps.couchplay``.
"""
from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from ludex.plugins import ConfigField, GameAction, Provider

FLATPAK_ID = "io.github.hikaps.couchplay"


def _flatpak_installed(home: Path | None = None) -> bool:
    """Whether the Flatpak is installed for this user or the system (a directory check: no process is started)."""
    base = (home or Path.home()) / ".local/share/flatpak/app"
    return any((root / FLATPAK_ID).is_dir() for root in (base, Path("/var/lib/flatpak/app")))


def command() -> list[str] | None:
    """The argv that starts CouchPlay, before its options, or ``None`` when it is not installed."""
    native = shutil.which("couchplay-gamemode")
    if native:
        return [os.path.realpath(native)]
    flatpak = shutil.which("flatpak")
    if flatpak and _flatpak_installed():
        return [flatpak, "run", FLATPAK_ID]
    return None


def game_argument(store: str, store_id: str) -> str | None:
    """CouchPlay's ``--game`` value for a game, or ``None`` when its store is not one CouchPlay can start."""
    if store == "steam" and store_id.isascii() and store_id.isdigit() and int(store_id) > 0:
        return f"steam:{store_id}"
    if store == "heroic" and store_id:
        return f"heroic:sideload:{store_id}"
    if store == "epic" and store_id:  # ludex's own Epic launch also goes through Heroic's legendary runner
        return f"heroic:legendary:{store_id}"
    return None


PLAYERS = ("2", "3", "4")
# ludex puts this plugin's folder on sys.path only inside its own process, so the action hands it to the interpreter.
LAN_BOOT = "import sys; sys.path.insert(0, sys.argv.pop(1)); from ludex_couchplay.lan_session import main; sys.exit(main())"


def actions(store: str, store_id: str, settings: Mapping[str, str]) -> Sequence[GameAction]:
    game = game_argument(store, str(store_id))
    start = command() if game else None
    if start is None or game is None:
        return []
    found = []
    profile = settings.get("profile", "").strip()
    if profile and not profile.startswith("-") and "\0" not in profile:
        found.append(GameAction("split-screen", "Play split-screen", [*start, "--profile", profile, "--start", "--game", game]))
        if store == "steam" and settings.get("lan") == "yes":
            found.append(GameAction(
                "split-screen-lan", "Play split-screen with LAN invites",
                [sys.executable, "-c", LAN_BOOT, str(Path(__file__).resolve().parents[1]),
                 "--profile", profile, "--app-id", str(store_id), "--",
                 *start, "--profile", profile, "--start", "--exit-after-session", "--game", game],
            ))
    players = settings.get("players", PLAYERS[0])
    if players in PLAYERS:
        found.append(GameAction("quick", f"Quick split-screen ({players} players)", [*start, "--quick", players, "--game", game]))
    return found


PLUGIN = Provider(
    name="couchplay",
    help="Play a Steam or Heroic game in split-screen with CouchPlay",
    config_fields=(),
    settings=(
        ConfigField("profile", "CouchPlay profile for \"Play split-screen\" (leave empty to offer only the quick session)", optional=True),
        ConfigField("players", "Players in a quick session", optional=True, kind="choice", choices=PLAYERS),
        ConfigField("lan", "Also offer \"Play split-screen with LAN invites\" on Steam games (gbe_fork; needs the profile)", optional=True, kind="yes_no"),
    ),
    actions=actions,
)
