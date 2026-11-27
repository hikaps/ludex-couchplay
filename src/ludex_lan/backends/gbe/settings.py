"""gbe_fork's per-user identity file: the name and Steam id a game announces on the LAN."""

from __future__ import annotations

import os
from pathlib import Path

SECTION = "[user::general]"
KEYS = ("account_name", "account_steamid")


def user_ini(pfx: Path) -> Path:
    """``configs.user.ini`` inside a Wine prefix (gbe reads it from the user's roaming AppData)."""
    return pfx / "drive_c/users/steamuser/AppData/Roaming/GSE Saves/settings/configs.user.ini"


def set_user(path: Path, name: str, steam_id: int) -> None:
    """Set ``account_name`` and ``account_steamid`` in ``[user::general]``, keeping every other line."""
    if not name or any(c in name for c in "\r\n="):
        raise ValueError(f"{name!r} cannot be a gbe account name")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    header = next((i for i, line in enumerate(lines) if line.strip() == SECTION), None)
    if header is None:
        lines.append(SECTION)
        header = len(lines) - 1
    end = next((i for i in range(header + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
    kept = [line for line in lines[header + 1 : end] if line.partition("=")[0].strip() not in KEYS]
    lines[header + 1 : end] = [f"account_name={name}", f"account_steamid={steam_id}", *kept]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temporary, path)
