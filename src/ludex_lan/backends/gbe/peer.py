"""The gbe_fork backend: joins the emulator's LAN as one more peer to read presence and deliver invites.

gbe games find each other with UDP announces on ports 47584-47593 and then keep a TCP stream per peer. The agent
announces itself with gbe's "connect to anyone" appid, so every game accepts its TCP stream. A game sends its
``Friend`` record (name, appid, lobby) over that stream whenever it changes, e.g. when it creates a lobby. An invite is
one UDP datagram sent to the invited game's own port.
"""

from __future__ import annotations

import asyncio
import socket
import struct
import time
from dataclasses import dataclass

from ... import identity
from .. import Presence
from . import wire

PORTS = range(47584, 47594)
ANNOUNCE_S = 5.0
HEARTBEAT_S = 10.0
EXPIRE_S = 20.0
MAX_FRAME = 1 << 20


@dataclass
class _Peer:
    udp: tuple[str, int]
    tcp: tuple[str, int]
    appid: int
    seen: float


class GbeBackend:
    name = "gbe"

    def __init__(self) -> None:
        self.agent_id = identity.steam_id("ludex-lan-agent")
        self._peers: dict[int, _Peer] = {}
        self._friends: dict[int, wire.Friend] = {}
        self._streams: dict[tuple[str, int], asyncio.StreamWriter] = {}
        self._udp: asyncio.DatagramTransport | None = None
        self._tcp_port = 0
        self._tasks: set[asyncio.Task] = set()

    # --- state

    def _expire(self) -> None:
        cutoff = time.monotonic() - EXPIRE_S
        for peer_id in [i for i, peer in self._peers.items() if peer.seen < cutoff]:
            del self._peers[peer_id]
            self._friends.pop(peer_id, None)

    def _touch(self, peer_id: int) -> None:
        if peer_id in self._peers:
            self._peers[peer_id].seen = time.monotonic()

    def roster(self) -> list[Presence]:
        self._expire()
        found = []
        for peer_id, peer in self._peers.items():
            if (peer_id >> 52) & 0xF != 1 or peer.appid in (0, wire.LOBBY_CONNECT_APPID):
                continue  # not a user account (gbe also announces a game-server id) or another agent
            friend = self._friends.get(peer_id)
            session = ""
            if friend:
                connect = friend.rich_presence.get("connect", "")
                session = f"lobby:{friend.lobby_id}" if friend.lobby_id else f"connect:{connect}" if connect else ""
            found.append(Presence(str(peer_id), friend.name if friend else str(peer_id), str(peer.appid), session, peer.udp[0]))
        return found

    def deliver(self, to: Presence, inviter_id: str, session: str) -> bool:
        peer = self._peers.get(int(to.id))
        kind, _, value = session.partition(":")
        if peer is None or self._udp is None or not value:
            return False
        if kind == "lobby" and value.isdigit():
            payload = wire.lobby_invite(int(inviter_id), int(to.id), int(value))
        elif kind == "connect":
            payload = wire.game_invite(int(inviter_id), int(to.id), value)
        else:
            return False
        inviter = self._friends.get(int(inviter_id))
        if inviter:
            self._udp.sendto(wire.friend(int(to.id), inviter), peer.udp)
        self._udp.sendto(payload, peer.udp)
        return True

    # --- network

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        udp, tcp = self._bind()
        self._tcp_port = tcp.getsockname()[1]
        transport, _ = await loop.create_datagram_endpoint(lambda: _Udp(self), sock=udp)
        self._udp = transport
        server = await asyncio.start_server(self._accepted, sock=tcp)
        try:
            await asyncio.gather(self._announce_loop(), self._heartbeat_loop())
        finally:
            transport.close()
            server.close()
            for writer in list(self._streams.values()):
                writer.close()

    @staticmethod
    def _bind() -> tuple[socket.socket, socket.socket]:
        for port in PORTS:
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                udp.bind(("0.0.0.0", port))
                tcp.bind(("0.0.0.0", port))
                tcp.setblocking(False)
                return udp, tcp
            except OSError:
                udp.close()
                tcp.close()
        raise SystemExit("no free gbe port in 47584-47593")

    async def _announce_loop(self) -> None:
        ping = wire.announce(self.agent_id, True, self._tcp_port, wire.LOBBY_CONNECT_APPID)
        while True:
            for port in PORTS:
                for host in ("255.255.255.255", "127.0.0.1"):
                    self._udp.sendto(ping, (host, port))
            self._expire()
            await asyncio.sleep(ANNOUNCE_S)

    async def _heartbeat_loop(self) -> None:
        beat = wire.frame(wire.heartbeat(self.agent_id))
        while True:
            await asyncio.sleep(HEARTBEAT_S)
            for writer in list(self._streams.values()):
                writer.write(beat)

    def on_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            message = wire.decode(data)
        except ValueError:
            return
        if message.source_id in (0, self.agent_id):
            return
        if message.kind != "announce":
            self._touch(message.source_id)
            return
        if message.announce_type == 0:
            self._udp.sendto(wire.announce(self.agent_id, False, self._tcp_port, wire.LOBBY_CONNECT_APPID), addr)
        tcp = (addr[0], message.tcp_port)
        for peer_id in message.ids or [message.source_id]:
            self._peers[peer_id] = _Peer(addr, tcp, message.appid, time.monotonic())
        if message.tcp_port and tcp not in self._streams:
            task = asyncio.ensure_future(self._connect(tcp))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _connect(self, tcp: tuple[str, int]) -> None:
        if tcp in self._streams:
            return
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(*tcp), 2.0)
        except (OSError, asyncio.TimeoutError):
            return
        self._streams[tcp] = writer
        writer.write(wire.frame(wire.hello(self.agent_id)))
        await self._read(reader, writer, tcp)

    async def _accepted(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await self._read(reader, writer, None)

    async def _read(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, key: tuple[str, int] | None) -> None:
        try:
            while True:
                (size,) = struct.unpack("<I", await reader.readexactly(4))
                if size > MAX_FRAME:
                    break
                message = wire.decode(await reader.readexactly(size))
                if message.source_id == self.agent_id:
                    continue
                self._touch(message.source_id)
                if message.kind == "friend" and message.friend and message.friend.id:
                    self._friends[message.friend.id] = message.friend
        except (asyncio.IncompleteReadError, OSError, ValueError):
            pass
        finally:
            if key is not None and self._streams.get(key) is writer:
                del self._streams[key]
            writer.close()


class _Udp(asyncio.DatagramProtocol):
    def __init__(self, backend: GbeBackend) -> None:
        self._backend = backend

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._backend.on_datagram(data, addr)
