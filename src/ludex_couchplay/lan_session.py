"""Runs a CouchPlay session with gbe_fork LAN invites: gives each seat its own gbe identity, runs the
``ludex_lan`` agent next to the session and stops it when CouchPlay exits.

Started by the "Play split-screen with LAN invites" action (see ``ludex_couchplay.actions``).
"""
from __future__ import annotations

import argparse
import asyncio
import configparser
import contextlib
import signal
import sys
from pathlib import Path

from ludex_lan import identity
from ludex_lan.agent import Agent
from ludex_lan.backends.gbe.peer import GbeBackend
from ludex_lan.backends.gbe.settings import set_user, user_ini

_FLATPAK = Path.home() / ".var/app/io.github.hikaps.couchplay"
CONFIG_FILES = (_FLATPAK / "config/couchplayrc", Path.home() / ".config/couchplayrc")
PROFILE_DIRS = (_FLATPAK / "data/hikaps/CouchPlay/profiles", Path.home() / ".local/share/hikaps/CouchPlay/profiles")


def _ini(path: Path) -> configparser.ConfigParser | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # type: ignore[assignment,method-assign]  # Qt keys are case-sensitive
    try:
        parser.read_string(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, configparser.Error):
        return None
    return parser


def _value(parser: configparser.ConfigParser, section: str, key: str) -> str:
    value = parser.get(section, key, fallback="").strip()
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] == '"' else value


def storage_dir() -> Path | None:
    """CouchPlay's player storage folder (``[Players] StorageDir``)."""
    for path in CONFIG_FILES:
        parser = _ini(path)
        if parser and (value := _value(parser, "Players", "StorageDir")):
            return Path(value)
    return None


def profile_players(profile: str) -> list[str]:
    """The players of a saved CouchPlay profile, in seat order."""
    for directory in PROFILE_DIRS:
        for path in sorted(directory.glob("*.conf")):
            parser = _ini(path)
            if not parser or _value(parser, "General", "name") != profile:
                continue
            seats = []
            for section in parser.sections():
                number = section.removeprefix("Instance")
                if section.startswith("Instance") and number.isascii() and number.isdigit() and (player := _value(parser, section, "player")):
                    seats.append((int(number), player))
            return [player for _, player in sorted(seats)]
    return []


def seat_prefixes(storage: Path, player: str, app_id: str) -> list[Path]:
    """The Wine prefixes of a game under a player's CouchPlay home."""
    home = storage / player / "home"
    found = [
        *home.glob(f".couchplay/steam-libs/*/steamapps/compatdata/{app_id}/pfx"),
        *home.glob(f".local/share/Steam/steamapps/compatdata/{app_id}/pfx"),
    ]
    return sorted(path for path in found if path.is_dir())


def _report(message: str) -> None:
    print(message, flush=True)


async def _session(players: list[str], ids: dict[str, str], couchplay: list[str]) -> int:
    agent = asyncio.ensure_future(Agent(GbeBackend(), players, ids.__getitem__).serve())

    def stopped(task: asyncio.Future[None]) -> None:
        if not task.cancelled() and task.exception() is not None:
            print(f"LAN agent stopped: {task.exception()}", file=sys.stderr, flush=True)

    agent.add_done_callback(stopped)
    try:
        process = await asyncio.create_subprocess_exec(*couchplay)
        for number in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_running_loop().add_signal_handler(number, process.terminate)
        return await process.wait()
    finally:
        agent.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await agent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ludex-couchplay-lan", description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("couchplay", nargs=argparse.REMAINDER, help="after --: the CouchPlay command to run")
    args = parser.parse_args(argv)
    couchplay = args.couchplay[1:] if args.couchplay[:1] == ["--"] else args.couchplay
    if not (args.app_id.isascii() and args.app_id.isdigit()):
        parser.error("--app-id takes digits")
    if not couchplay:
        parser.error("the CouchPlay command is missing")
    players = profile_players(args.profile)
    if not players:
        print(f"ludex-couchplay: CouchPlay profile '{args.profile}' not found or has no players", file=sys.stderr)
        return 2
    storage = storage_dir()
    if storage is None:
        print("ludex-couchplay: CouchPlay has no player storage folder (set it in CouchPlay's settings)", file=sys.stderr)
        return 2
    ids = {player: str(identity.steam_id(player)) for player in players}
    for player in players:
        prefixes = seat_prefixes(storage, player, args.app_id)
        if not prefixes:
            _report(f'{player}: no Wine prefix for app {args.app_id} yet; start the game once with "Play split-screen", then use LAN invites again')
        for prefix in prefixes:
            try:
                set_user(user_ini(prefix), player, int(ids[player]))
            except (OSError, ValueError) as error:
                _report(f"{player}: could not write the gbe identity: {error}")
            else:
                _report(f"{player}: gbe id {ids[player]} -> {user_ini(prefix)}")
    return asyncio.run(_session(players, ids, couchplay))
