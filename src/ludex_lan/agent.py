"""The ludex-lan agent: answers each local player's overlay and carries invites between PCs.

An overlay asks over a per-player unix socket (see ``control``). An invite for a player on another PC travels
agent to agent over TCP ``AGENT_PORT``; it reaches the game only after the invited player accepts, and then
the backend delivers it.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import identity
from .backends import Backend, Presence

AGENT_PORT = 47600
INVITE_TTL_S = 300
REMOTE_TIMEOUT_S = 0.5  # under the overlay client's 1 s
FIELDS = ("id", "from_id", "from_name", "to_id", "game", "session")


@dataclass
class PendingInvite:
    id: str
    from_id: str
    from_name: str
    to_id: str
    game: str
    session: str
    at: float


class Agent:
    def __init__(self, backend: Backend, players: list[str], player_id: Callable[[str], str]) -> None:
        self._backend = backend
        self._players = players
        self._player_id = player_id
        self._ids = {player_id(player) for player in players}
        self._pending: dict[str, PendingInvite] = {}

    def _me(self, player: str) -> Presence | None:
        mine = self._player_id(player)
        return next((p for p in self._backend.roster() if p.id == mine), None)

    def _prune(self) -> None:
        now = time.monotonic()
        for key in [k for k, invite in self._pending.items() if invite.at + INVITE_TTL_S < now]:
            del self._pending[key]

    async def handle(self, player: str, line: str) -> str:
        command, _, argument = line.strip().partition(" ")
        me = self._player_id(player)
        mine = self._me(player)
        match command:
            case "peers" if mine:
                peers = sorted((p for p in self._backend.roster() if p.game == mine.game and p.id != me), key=lambda p: p.name)
                return json.dumps(
                    {
                        "can_invite": mine.session != "",
                        "peers": [
                            {
                                "id": p.id,
                                "name": p.name,
                                "with_me": p.session != "" and p.session == mine.session,
                                "this_pc": p.address == mine.address,
                            }
                            for p in peers
                        ],
                    }
                )
            case "invite" if mine and mine.session:
                target = next((p for p in self._backend.roster() if p.id == argument and p.game == mine.game), None)
                if target is None:
                    return "0"
                message = {
                    "id": uuid.uuid4().hex,
                    "from_id": me,
                    "from_name": mine.name,
                    "to_id": target.id,
                    "game": mine.game,
                    "session": mine.session,
                }
                if target.id in self._ids:
                    return self.receive(message)
                return await self._send_remote(target.address, message)
            case "invites":
                self._prune()
                waiting = sorted((i for i in self._pending.values() if i.to_id == me), key=lambda i: i.at)
                return json.dumps([{"id": i.id, "name": i.from_name} for i in waiting])
            case "accept":
                invite = self._pending.get(argument)
                if invite is None or invite.to_id != me or mine is None:
                    return "0"
                del self._pending[argument]
                return "1" if self._backend.deliver(mine, invite.from_id, invite.session) else "0"
            case "decline":
                invite = self._pending.get(argument)
                if invite is None or invite.to_id != me:
                    return "0"
                del self._pending[argument]
                return "1"
        return "0"

    def receive(self, message: dict) -> str:
        if not all(isinstance(message.get(key), str) for key in FIELDS) or message["to_id"] not in self._ids:
            return "0"
        for key in [k for k, i in self._pending.items() if (i.from_id, i.to_id) == (message["from_id"], message["to_id"])]:
            del self._pending[key]
        self._pending[message["id"]] = PendingInvite(**{key: message[key] for key in FIELDS}, at=time.monotonic())
        return "1"

    @staticmethod
    async def _send_remote(address: str, message: dict) -> str:
        async def exchange() -> str:
            reader, writer = await asyncio.open_connection(address, AGENT_PORT)
            try:
                writer.write(json.dumps(message).encode() + b"\n")
                await writer.drain()
                return (await reader.readline()).decode().strip()
            finally:
                writer.close()

        try:
            return "1" if await asyncio.wait_for(exchange(), REMOTE_TIMEOUT_S) == "1" else "0"
        except (OSError, asyncio.TimeoutError):
            return "0"

    # --- sockets

    async def _control(self, player: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), 2.0)
            writer.write((await self.handle(player, line.decode())).encode() + b"\n")
            await writer.drain()
        except (OSError, asyncio.TimeoutError, UnicodeDecodeError):
            pass
        finally:
            writer.close()

    async def _peer_agent(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await asyncio.wait_for(reader.readuntil(b"\n"), 2.0)
            try:
                reply = self.receive(json.loads(line))
            except (ValueError, AttributeError):
                reply = "0"
            writer.write(reply.encode() + b"\n")
            await writer.drain()
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            pass
        finally:
            writer.close()

    async def serve(self) -> None:
        sockets: list[Path] = []
        servers = []
        try:
            for player in self._players:
                directory = identity.control_dir(player)
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                path = directory / f"run-{os.getpid()}.sock"
                path.unlink(missing_ok=True)
                servers.append(await asyncio.start_unix_server(lambda r, w, p=player: self._control(p, r, w), path=str(path)))
                sockets.append(path)
            servers.append(await asyncio.start_server(self._peer_agent, "0.0.0.0", AGENT_PORT, limit=4096))
            await self._backend.run()
        finally:
            for server in servers:
                server.close()
            for path in sockets:
                path.unlink(missing_ok=True)
