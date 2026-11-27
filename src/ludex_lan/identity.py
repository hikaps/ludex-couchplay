"""Per-player identities shared by the agent, the overlay and the emulator installer."""

from __future__ import annotations

import hashlib
import os
import socket
from pathlib import Path

STEAM_ID_BASE = 76561197960265728


def machine_id() -> str:
    try:
        return Path("/etc/machine-id").read_text().strip() or socket.gethostname()
    except OSError:
        return socket.gethostname()


def steam_id(player: str) -> int:
    """A stable SteamID64 for one player on this machine, so two PCs never share one."""
    digest = hashlib.sha256(f"{machine_id()}:{player}".encode()).digest()
    return STEAM_ID_BASE + 1 + (int.from_bytes(digest[:4], "big") & 0x7FFFFFFF)


def control_dir(player: str) -> Path:
    override = os.environ.get("LUDEX_LAN_CONTROL_DIR")
    if override:
        return Path(override)
    return Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "ludex-lan" / player
