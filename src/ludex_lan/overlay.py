"""``ludex-lan-overlay``: shows LAN invites in one CouchPlay player's pane and answers them with the pad.

Run one per player next to ``ludex-lan agent``. Holding LB + RB + Y answers a pending invite, or opens a
list of players to invite when none is pending:

    ludex-lan-overlay --player couch2 --pane 1920,0,1920,1080
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel

from . import control, identity, panes
from .capture import PadCapture, default_command, parse_command
from .flow import Answer, Effect, Hide, InviteFlow, RefreshPeers, SendInvite, Show, StartCapture, StopCapture
from .panes import Rect, overlay_rect
from .placement import Placement

POLL_MS = 500
WIDTH = 520
LINE_HEIGHT = 32  # one line of text at the label's font size
CHROME_HEIGHT = 44  # padding and border around the text
RETRY_AFTER_S = 3.0  # after the capture stopped by itself, so a broken setup does not respawn it in a loop


class Overlay:
    def __init__(self, player: str, pane: Rect | None, control_dir: Path, command: list[str]) -> None:
        self._player = player
        self._pane = pane
        self._command = command
        self._dir = control_dir
        self._flow = InviteFlow()
        self._shown_pane: Rect | None = None  # the pane looked up for what is on screen
        self._lines = 0
        self._retry_at = 0.0
        self._caption = f"ludex-lan invite {uuid.uuid4()}"
        self._placement: Placement | None = None
        self._label = QLabel()
        self._label.setWindowTitle(self._caption)
        self._label.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self._label.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._label.setTextFormat(Qt.TextFormat.PlainText)  # a player's name is not markup
        self._label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._label.setStyleSheet(
            "background: rgba(18, 20, 28, 235); color: white; border: 2px solid #5b8def;"
            " border-radius: 12px; padding: 12px; font-size: 20px;"
        )
        self._label.resize(WIDTH, CHROME_HEIGHT + 2 * LINE_HEIGHT)

        self._capture = PadCapture(command, player)
        self._capture.event.connect(self._on_event)
        self._capture.ended.connect(self._on_capture_ended)

        self._choice_timer = QTimer()
        self._choice_timer.setSingleShot(True)
        self._choice_timer.timeout.connect(lambda: self._apply(self._flow.on_timeout()))
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(POLL_MS)

    def _place(self) -> None:
        """Size the label for its lines and put it in the player's pane."""
        height = CHROME_HEIGHT + self._lines * LINE_HEIGHT
        if self._shown_pane is None:
            self._shown_pane = self._pane or panes.lookup(self._command, self._player)
            if self._shown_pane is None:
                print("ludex-lan: CouchPlay reports no pane for this player; showing the overlay unplaced", file=sys.stderr)
        self._unplace()
        if self._shown_pane is None:
            self._label.resize(WIDTH, height)
            return
        rect = overlay_rect(self._shown_pane, WIDTH, height)
        self._label.resize(rect.width, rect.height)
        self._placement = Placement(self._caption, rect)
        if not self._placement.available:
            print("ludex-lan: KWin scripting is unavailable; the overlay is not placed in the pane", file=sys.stderr)

    def _unplace(self) -> None:
        if self._placement is not None:
            self._placement.close()
            self._placement = None

    def close(self) -> None:
        self._poll_timer.stop()
        self._capture.stop()
        self._label.hide()
        self._unplace()

    def _poll(self) -> None:
        try:
            pending = control.invites(self._dir)
        except control.ControlError:
            self._apply(self._flow.on_host(False))  # no game yet, or it ended
            return
        if time.monotonic() >= self._retry_at:
            self._apply(self._flow.on_host(True))
        self._apply(self._flow.on_invites(pending))
        if self._flow.picking:
            self._refresh_peers()

    def _refresh_peers(self) -> None:
        try:
            roster = control.peers(self._dir)
        except control.ControlError:
            roster = None
        self._apply(self._flow.on_roster(roster))

    def _on_event(self, event: dict) -> None:
        self._apply(self._flow.on_capture_event(event))

    def _on_capture_ended(self) -> None:
        self._retry_at = time.monotonic() + RETRY_AFTER_S
        self._apply(self._flow.on_capture_ended())

    def _apply(self, effects: list[Effect]) -> None:
        for effect in effects:
            match effect:
                case Show(text, timeout_ms):
                    lines = text.count("\n") + 1
                    changed = lines != self._lines
                    self._label.setText(text)
                    self._lines = lines
                    self._choice_timer.stop()
                    if timeout_ms is not None:
                        self._choice_timer.start(timeout_ms)
                    if not self._label.isVisible():
                        self._place()
                        self._label.show()
                    elif changed:
                        self._place()
                case Hide():
                    self._choice_timer.stop()
                    self._label.hide()
                    self._unplace()
                    self._shown_pane = None
                    self._lines = 0
                case StartCapture():
                    self._capture.start()
                case StopCapture():
                    self._capture.stop()
                case RefreshPeers():
                    self._refresh_peers()
                case SendInvite(peer):
                    try:
                        sent = control.invite(self._dir, peer)
                    except control.ControlError as error:
                        print(f"ludex-lan: {error}", file=sys.stderr)
                        sent = False
                    self._apply(self._flow.on_invite_sent(peer, sent))
                case Answer(invite, accept):
                    try:
                        control.answer(self._dir, invite, accept)
                    except control.ControlError as error:
                        print(f"ludex-lan: {error}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ludex-lan-overlay", description=__doc__.split("\n\n")[0])
    parser.add_argument("--player", required=True, help="CouchPlay player whose pad answers the invite")
    parser.add_argument(
        "--pane",
        type=Rect.parse,
        help="X,Y,WIDTH,HEIGHT of that player's pane (default: ask CouchPlay when an invite arrives)",
    )
    parser.add_argument(
        "--control-dir",
        type=Path,
        help="the agent's control directory for the player (default: $LUDEX_LAN_CONTROL_DIR, else the runtime dir)",
    )
    parser.add_argument(
        "--couchplay",
        type=parse_command,
        default=None,
        help="command that runs CouchPlay (default: couchplay, else its Flatpak)",
    )
    args = parser.parse_args(argv)
    if args.control_dir is None:
        args.control_dir = identity.control_dir(args.player)

    app = QApplication(sys.argv[:1])
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, lambda *_: app.quit())
    wake = QTimer()  # lets the interpreter see the signal while Qt runs
    wake.timeout.connect(lambda: None)
    wake.start(200)
    overlay = Overlay(args.player, args.pane, args.control_dir, args.couchplay or default_command())
    app.aboutToQuit.connect(overlay.close)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
