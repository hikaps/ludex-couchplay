"""Places the overlay window inside a pane with a KWin script.

Wayland clients cannot position their own windows, so a small KWin script moves any window with the overlay's
caption into the pane and keeps it above the game without taking focus.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from PySide6.QtDBus import QDBusConnection, QDBusInterface

from .panes import Rect

PLUGIN = "ludex-lan-overlay"



def script_source(caption: str, rect: Rect) -> str:
    return f"""
const caption = {json.dumps(caption)};
const target = {json.dumps({"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height})};
function place(window) {{
    if (window.caption !== caption) return;
    window.keepAbove = true;
    window.skipTaskbar = true;
    window.skipPager = true;
    window.skipSwitcher = true;
    window.frameGeometry = target;
}}
workspace.windowList().forEach(place);
workspace.windowAdded.connect(place);
"""


class Placement:
    """Loads the KWin script; ``close`` unloads it. ``available`` is False when KWin cannot be reached."""

    def __init__(self, caption: str, rect: Rect) -> None:
        self.available = False
        bus = QDBusConnection.sessionBus()
        scripting = QDBusInterface("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", bus)
        if not scripting.isValid():
            return
        scripting.call("unloadScript", PLUGIN)  # one left behind by a crashed run
        handle = tempfile.NamedTemporaryFile("w", suffix=".js", prefix="ludex-lan-", delete=False)
        with handle:
            handle.write(script_source(caption, rect))
        self._path = Path(handle.name)
        reply = scripting.call("loadScript", str(self._path), PLUGIN)
        script_id = reply.arguments()[0] if reply.arguments() else -1
        if not isinstance(script_id, int) or script_id < 0:
            self._path.unlink(missing_ok=True)
            return
        script = QDBusInterface("org.kde.KWin", f"/Scripting/Script{script_id}", "org.kde.kwin.Script", bus)
        script.call("run")
        self._scripting = scripting
        self.available = True

    def close(self) -> None:
        if self.available:
            self._scripting.call("unloadScript", PLUGIN)
            self._path.unlink(missing_ok=True)
            self.available = False
