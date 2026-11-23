"""Offers "Play split-screen" on Steam and Heroic games, started through CouchPlay.

CouchPlay starts a saved profile (its players, controllers and screens) with ``--game`` replacing the
game of the players whose launcher matches. The profile is the plugin's one setting. CouchPlay is found
as the ``couchplay-gamemode`` command, else as the Flatpak ``io.github.hikaps.couchplay``.
"""
from __future__ import annotations

import os
import shutil
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


def actions(store: str, store_id: str, settings: Mapping[str, str]) -> Sequence[GameAction]:
    profile = settings.get("profile", "").strip()
    game = game_argument(store, str(store_id))
    start = command() if profile and game else None
    if start is None or profile.startswith("-") or "\0" in profile:
        return []
    return [GameAction("split-screen", "Play split-screen", [*start, "--profile", profile, "--start", "--game", game])]


PLUGIN = Provider(
    name="couchplay",
    help="Play a Steam or Heroic game in split-screen with CouchPlay",
    config_fields=(),
    settings=(ConfigField("profile", "CouchPlay profile to start the game in", optional=True),),
    actions=actions,
)
