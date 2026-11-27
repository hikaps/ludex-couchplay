"""Client for the per-player control socket of the ludex-lan agent.

The host listens on ``<control dir>/run-<pid>.sock``. One request is one newline-terminated line and gets one
reply line. A dead host leaves its socket file behind, so the newest sockets are tried first and refused ones
skipped.
"""

from __future__ import annotations

import json
import re
import socket
from dataclasses import dataclass, field
from pathlib import Path

PEER_ID = re.compile(r"[A-Za-z0-9_.:-]{1,64}")


class ControlError(Exception):
    """No host answered."""


@dataclass(frozen=True)
class Invite:
    id: str
    name: str


@dataclass(frozen=True)
class Peer:
    id: str  # opaque backend id, e.g. a decimal SteamID64
    name: str
    with_me: bool = False  # already in the game's lobby or session
    this_pc: bool = False


@dataclass(frozen=True)
class Roster:
    can_invite: bool
    peers: list[Peer] = field(default_factory=list)


def _sockets(directory: Path) -> list[Path]:
    found = []
    for path in directory.glob("run-*.sock"):
        try:
            found.append((path.stat().st_mtime, path))
        except OSError:
            continue  # removed since the listing
    return [path for _, path in sorted(found, reverse=True)]


def request(directory: Path, line: str, timeout: float = 1.0) -> str:
    """Send one request to the newest answering host and return its reply line."""
    for path in _sockets(directory):
        try:
            with socket.socket(socket.AF_UNIX) as sock:
                sock.settimeout(timeout)
                sock.connect(str(path))
                sock.sendall(line.encode() + b"\n")
                reply = b""
                while not reply.endswith(b"\n"):
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    reply += chunk
                return reply.decode().strip()
        except OSError:
            continue  # stale socket, or a host that went away mid-request
    raise ControlError(f"no ludex-lan agent answers in {directory}")


def invites(directory: Path) -> list[Invite]:
    """Pending invites. Empty when the host cannot track them or none are waiting."""
    reply = request(directory, "invites")
    if reply == "0":
        return []
    try:
        items = json.loads(reply)
        return [Invite(str(item["id"]), str(item["name"])) for item in items]
    except (ValueError, KeyError, TypeError) as error:
        raise ControlError(f"unexpected reply to invites: {reply!r}") from error


def answer(directory: Path, invite: Invite, accept: bool) -> bool:
    """Accept or decline an invite. False when the host no longer knows it."""
    return request(directory, f"{'accept' if accept else 'decline'} {invite.id}") == "1"


def peers(directory: Path) -> Roster | None:
    """Who an invite could go to, or None when the host cannot say (no game running yet)."""
    reply = request(directory, "peers")
    if reply == "0":
        return None
    try:
        data = json.loads(reply)
        found = [
            Peer(
                str(item["id"]),
                str(item["name"]),
                bool(item["with_me"]),
                bool(item["this_pc"]),
            )
            for item in data["peers"]
        ]
        return Roster(bool(data["can_invite"]), found)
    except (ValueError, KeyError, TypeError) as error:
        raise ControlError(f"unexpected reply to peers: {reply!r}") from error


def invite(directory: Path, peer: Peer) -> bool:
    """Ask the host to invite one player. True means queued for the game, not that the player received it."""
    if not PEER_ID.fullmatch(peer.id):
        return False
    return request(directory, f"invite {peer.id}") == "1"
