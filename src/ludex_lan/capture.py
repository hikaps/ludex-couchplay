"""Runs ``couchplay pad capture`` and turns its JSON lines into Qt signals."""

from __future__ import annotations

import json
import shlex
import shutil

from PySide6.QtCore import QObject, QProcess, Signal

FLATPAK_ID = "io.github.hikaps.couchplay"


def default_command() -> list[str]:
    """``couchplay`` when it is on PATH, else the Flatpak. ``--die-with-parent`` stops the sandbox with us."""
    if shutil.which("couchplay"):
        return ["couchplay"]
    return ["flatpak", "run", "--die-with-parent", FLATPAK_ID]


def parse_command(text: str) -> list[str]:
    return shlex.split(text)


class PadCapture(QObject):
    """One ``--wait-chord`` capture of one player's pad. ``event`` carries each JSON line as a dict."""

    event = Signal(dict)
    ended = Signal()

    def __init__(self, command: list[str], player: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._command = command
        self._player = player
        self._process: QProcess | None = None
        self._buffer = b""

    @property
    def running(self) -> bool:
        return self._process is not None

    def start(self) -> None:
        if self._process is not None:
            return
        process = QProcess(self)
        process.readyReadStandardOutput.connect(self._read)
        process.finished.connect(lambda *_: self._finished(process))
        self._buffer = b""
        self._process = process
        process.start(self._command[0], [*self._command[1:], "pad", "capture", "--player", self._player, "--wait-chord"])

    def stop(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        process.finished.disconnect()
        process.readyReadStandardOutput.disconnect()
        process.terminate()  # the client sees SIGTERM and exits, which hands the pad back
        if not process.waitForFinished(2000):
            process.kill()
            process.waitForFinished(1000)
        process.deleteLater()

    def _read(self) -> None:
        process = self._process
        if process is None:
            return
        self._buffer += bytes(process.readAllStandardOutput())
        *lines, self._buffer = self._buffer.split(b"\n")
        for line in lines:
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                self.event.emit(parsed)

    def _finished(self, process: QProcess) -> None:
        if process is not self._process:
            return
        self._process = None
        process.deleteLater()
        self.ended.emit()
