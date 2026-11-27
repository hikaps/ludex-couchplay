"""Where a player's pane is: asked of CouchPlay (``couchplay pad panes``) or given by hand."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @classmethod
    def parse(cls, text: str) -> Rect:
        try:
            x, y, width, height = (int(part) for part in text.split(","))
        except ValueError:
            raise ValueError(f"expected X,Y,WIDTH,HEIGHT, got {text!r}") from None
        if width <= 0 or height <= 0:
            raise ValueError(f"the pane must have a positive size, got {text!r}")
        return cls(x, y, width, height)


def overlay_rect(pane: Rect, width: int = 458, height: int = 108, margin: int = 16) -> Rect:
    """Top-left of the pane, shrunk to fit it."""
    return Rect(
        pane.x + margin,
        pane.y + margin,
        max(1, min(width, pane.width - 2 * margin)),
        max(1, min(height, pane.height - 2 * margin)),
    )


def lookup(command: list[str], player: str, timeout: float = 5.0) -> Rect | None:
    """The player's pane in the running session, or None when CouchPlay has no such running player."""
    try:
        done = subprocess.run([*command, "pad", "panes"], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    try:
        panes = json.loads(done.stdout.splitlines()[0])["panes"]
        for pane in panes:
            if pane["player"] == player:
                return Rect(int(pane["x"]), int(pane["y"]), int(pane["width"]), int(pane["height"]))
    except (IndexError, ValueError, KeyError, TypeError):
        pass
    return None
