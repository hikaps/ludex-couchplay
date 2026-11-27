"""``ludex-lan``: run the invite agent."""

from __future__ import annotations

import argparse
import asyncio
import signal

from . import identity
from .agent import Agent
from .backends import BACKENDS


def parse_player(value: str) -> tuple[str, str]:
    """``NAME`` or ``NAME=STEAMID``: the player's name and the Steam id their game announces."""
    name, _, steam_id = value.partition("=")
    if not name:
        raise argparse.ArgumentTypeError("a player needs a name")
    if not steam_id:
        return name, str(identity.steam_id(name))
    if not (steam_id.isascii() and steam_id.isdigit()):
        raise argparse.ArgumentTypeError(f"{steam_id!r} is not a Steam id (digits only)")
    return name, steam_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ludex-lan", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("agent", help="answer the overlays and carry invites between PCs")
    run.add_argument(
        "--player",
        action="append",
        type=parse_player,
        required=True,
        metavar="NAME[=STEAMID]",
        help="a local player; repeat for each. STEAMID is the account_steamid in that player's gbe configs.user.ini "
        "(default: an id derived from the name and this machine)",
    )
    run.add_argument("--backend", choices=sorted(BACKENDS), default="gbe")

    args = parser.parse_args(argv)
    ids = dict(args.player)
    asyncio.run(_serve(Agent(BACKENDS[args.backend](), list(ids), ids.__getitem__)))
    return 0


async def _serve(agent: Agent) -> None:
    task = asyncio.ensure_future(agent.serve())
    for number in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(number, task.cancel)
    try:
        await task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
