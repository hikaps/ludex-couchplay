"""Backends: one per emulator family. The agent only ever talks to this contract."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Presence:
    id: str  # backend player id, fits control.PEER_ID (gbe: decimal SteamID64)
    name: str
    game: str  # gbe: decimal appid
    session: str  # "" means nothing to invite to; gbe: "lobby:<id>" or "connect:<string>"
    address: str  # IPv4 of the player's PC


class Backend(Protocol):
    name: str

    async def run(self) -> None:
        """Network loop; runs until cancelled."""

    def roster(self) -> list[Presence]:
        """Everyone currently seen, local players included."""

    def deliver(self, to: Presence, inviter_id: str, session: str) -> bool:
        """Make ``to``'s game raise its join event for ``session``. False when it cannot be reached."""


from .gbe.peer import GbeBackend  # noqa: E402  (needs Presence above)

BACKENDS: dict[str, Callable[[], Backend]] = {"gbe": GbeBackend}
