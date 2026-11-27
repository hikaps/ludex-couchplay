"""What the overlay shows and asks for, as a pure state machine with no Qt or I/O.

While a game's host answers, the pad capture waits for the player's LB + RB + Y hold. What the hold opens depends
on the moment:

- An invite is pending: a notice names the sender, and once the controller is captured A accepts and B declines.
  A pending invite always wins over the picker.
- Nothing is pending: the peer picker. D-pad up and down move, A invites the highlighted player, B closes.

Either way the capture is stopped when the player is done, which hands the pad back to the game, and started
again by the next host check.
"""

from __future__ import annotations

from dataclasses import dataclass

from .control import Invite, Peer, Roster

CHOICE_TIMEOUT_MS = 20_000  # a captured pad nobody uses goes back to the game
TOAST_MS = 2_000
MAX_ROWS = 6  # players shown at once


@dataclass(frozen=True)
class Show:
    text: str
    timeout_ms: int | None = None  # how long until the flow is asked to give up (restarted by each Show)


@dataclass(frozen=True)
class Hide:
    pass


@dataclass(frozen=True)
class StartCapture:
    pass


@dataclass(frozen=True)
class StopCapture:
    pass


@dataclass(frozen=True)
class Answer:
    invite: Invite
    accept: bool


@dataclass(frozen=True)
class RefreshPeers:
    """Fetch the roster and report it with ``on_roster``."""


@dataclass(frozen=True)
class SendInvite:
    """Invite this player and report it with ``on_invite_sent``."""

    peer: Peer


Effect = Show | Hide | StartCapture | StopCapture | Answer | RefreshPeers | SendInvite


def _row(peer: Peer) -> str:
    notes = []
    if peer.with_me:
        notes.append("in game")
    if peer.this_pc:
        notes.append("this PC")
    return f"{peer.name or 'Unnamed'} ({', '.join(notes)})" if notes else peer.name or "Unnamed"


class InviteFlow:
    def __init__(self) -> None:
        self._current: Invite | None = None
        self._captured = False
        self._capturing = False
        self._answered: set[str] = set()  # answered but possibly still listed by the host for a moment
        self._picking = False
        self._loaded = False  # the picker has had a reply, even if it was "unavailable"
        self._roster: Roster | None = None
        self._cursor = 0
        self._sent = False  # the picker is showing the outcome of an invite
        self._text = ""  # what is on screen, so an unchanged picker does not restart the timeout

    @property
    def active(self) -> bool:
        return self._current is not None

    @property
    def picking(self) -> bool:
        return self._picking

    @property
    def capturing(self) -> bool:
        return self._capturing

    def on_host(self, up: bool) -> list[Effect]:
        """Whether a host answers. The pad capture follows it."""
        if up:
            if self._capturing:
                return []
            self._capturing = True
            return [StartCapture()]
        return self._finish() if (self._capturing or self._visible) else []

    def on_invites(self, pending: list[Invite]) -> list[Effect]:
        ids = {invite.id for invite in pending}
        self._answered &= ids
        if self._current is not None:
            if self._current.id in ids:
                return []
            return self._finish()  # answered elsewhere, or the host dropped it
        for invite in pending:
            if invite.id not in self._answered:
                self._current = invite
                self._picking = False
                self._sent = False
                return [self._show_invite()]
        return []

    def on_capture_event(self, event: dict) -> list[Effect]:
        kind = event.get("event")
        if kind == "captured":
            self._captured = True
            if self._current is not None:
                return [self._show_invite()]
            self._picking = True
            self._loaded = False
            self._roster = None
            self._cursor = 0
            self._sent = False
            return [self._show_picker(), RefreshPeers()]
        if kind != "key" or not self._captured:
            return []
        name = event.get("name")
        if self._current is not None:
            if name in ("a", "b"):
                invite = self._current
                self._answered.add(invite.id)
                return [Answer(invite, name == "a"), *self._finish()]
            return []
        if not self._picking or self._sent:
            return []
        if name == "b":
            return self._finish()
        peers = self._peers()
        if name in ("dpad-up", "dpad-down") and peers:
            step = -1 if name == "dpad-up" else 1
            self._cursor = max(0, min(len(peers) - 1, self._cursor + step))
            return [self._show_picker()]
        if name == "a" and peers and self._roster is not None and self._roster.can_invite:
            peer = peers[self._cursor]
            if not peer.with_me:
                return [SendInvite(peer)]
        return []

    def on_roster(self, roster: Roster | None) -> list[Effect]:
        """The host's roster (None: it can't say)."""
        if not self._picking or self._sent:
            return []
        self._loaded = True
        self._roster = roster
        self._cursor = max(0, min(self._cursor, len(self._peers()) - 1))
        return [] if self._picker_text() == self._text else [self._show_picker()]

    def on_invite_sent(self, peer: Peer, ok: bool) -> list[Effect]:
        if not self._picking:
            return []
        self._sent = True
        return [self._show(f"Invite sent to {peer.name}" if ok else "Couldn't send the invite", TOAST_MS)]

    def on_capture_ended(self) -> list[Effect]:
        """The capture process stopped by itself (error, session over). A pending invite stays pending."""
        self._capturing = False
        effects: list[Effect] = [Hide()] if self._visible else []
        self._reset()
        return effects

    def on_timeout(self) -> list[Effect]:
        """The player held the chord but did not choose. A pending invite stays pending."""
        return self._finish() if self._captured else []

    @property
    def _visible(self) -> bool:
        return self._current is not None or self._picking

    def _peers(self) -> list[Peer]:
        return self._roster.peers if self._roster is not None else []

    def _reset(self) -> None:
        self._current = None
        self._captured = False
        self._picking = False
        self._loaded = False
        self._roster = None
        self._cursor = 0
        self._sent = False
        self._text = ""

    def _finish(self) -> list[Effect]:
        self._capturing = False
        self._reset()
        return [StopCapture(), Hide()]

    def _show(self, text: str, timeout_ms: int | None = None) -> Show:
        self._text = text
        return Show(text, timeout_ms)

    def _show_invite(self) -> Show:
        assert self._current is not None
        if self._captured:
            return self._show(f"Invite from {self._current.name}\nA: Accept    B: Decline", CHOICE_TIMEOUT_MS)
        return self._show(f"Invite from {self._current.name}\nHold LB + RB + Y to respond")

    def _show_picker(self) -> Show:
        return self._show(self._picker_text(), CHOICE_TIMEOUT_MS)

    def _picker_text(self) -> str:
        title = "Invite a player"
        close = "B: Close"
        if not self._loaded:
            return f"{title}\nLooking for players…\n{close}"
        if self._roster is None:
            return f"{title}\nStart the game first\n{close}"
        if not self._roster.can_invite:
            return f"{title}\nNothing to invite to yet\n{close}"
        peers = self._roster.peers
        if not peers:
            return f"{title}\nNo players found\n{close}"
        start = max(0, min(self._cursor - 2, len(peers) - MAX_ROWS))
        rows = [
            f"{'▶ ' if start + i == self._cursor else '    '}{_row(peer)}"
            for i, peer in enumerate(peers[start : start + MAX_ROWS])
        ]
        return "\n".join([title, *rows, "D-pad: Move    A: Invite    B: Close"])
