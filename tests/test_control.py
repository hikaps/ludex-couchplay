from __future__ import annotations

import os
import shutil
import socket
import tempfile
import threading
from pathlib import Path

import pytest

from ludex_lan import control
from ludex_lan.control import ControlError, Invite, Peer, Roster


@pytest.fixture
def directory():
    path = Path(tempfile.mkdtemp(prefix="ll-", dir="/tmp"))  # tmp_path can exceed the unix socket path limit
    yield path
    shutil.rmtree(path, ignore_errors=True)


def serve(directory: Path, name: str, replies: dict[str, str]) -> list[str]:
    """A host that answers each request line from ``replies`` and records what it was asked."""
    asked: list[str] = []
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(directory / name))
    server.listen()

    def run() -> None:
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            with conn:
                line = conn.makefile().readline().strip()
                asked.append(line)
                conn.sendall(replies.get(line, "0").encode() + b"\n")

    threading.Thread(target=run, daemon=True).start()
    return asked


def test_invites_are_parsed(directory):
    serve(directory, "run-1.sock", {"invites": '[{"id":"7","name":"Bob"}]'})
    assert control.invites(directory) == [Invite("7", "Bob")]


def test_no_invites_and_an_unavailable_host_both_give_an_empty_list(directory):
    serve(directory, "run-1.sock", {"invites": "[]"})
    assert control.invites(directory) == []
    other = directory / "other"
    other.mkdir()
    serve(other, "run-2.sock", {"invites": "0"})
    assert control.invites(other) == []


def test_a_stale_socket_is_skipped_for_one_that_answers(directory):
    serve(directory, "run-1.sock", {"invites": '[{"id":"7","name":"Bob"}]'})
    stale = socket.socket(socket.AF_UNIX)
    stale.bind(str(directory / "run-2.sock"))
    stale.close()  # leaves the file, nobody listens
    os.utime(directory / "run-2.sock", (9e9, 9e9))  # newest, so it is tried first
    assert control.invites(directory) == [Invite("7", "Bob")]


def test_no_socket_is_an_error(directory):
    with pytest.raises(ControlError):
        control.invites(directory)


def test_a_garbled_reply_is_an_error(directory):
    serve(directory, "run-1.sock", {"invites": "nope"})
    with pytest.raises(ControlError):
        control.invites(directory)


def test_accept_and_decline_send_the_invite_id_and_report_whether_it_was_queued(directory):
    asked = serve(directory, "run-1.sock", {"accept 7": "1", "decline 8": "0"})
    assert control.answer(directory, Invite("7", "Bob"), accept=True) is True
    assert control.answer(directory, Invite("8", "Eve"), accept=False) is False
    assert asked == ["accept 7", "decline 8"]


PEERS = (
    '{"can_invite":true,"peers":[{"id":"%s","name":"Sam","with_me":false,"this_pc":true}]}'
    % ("a" * 32)
)


def test_peers_are_parsed(directory):
    serve(directory, "run-1.sock", {"peers": PEERS})
    assert control.peers(directory) == Roster(True, [Peer("a" * 32, "Sam", False, True)])


def test_an_unavailable_roster_is_none_not_empty(directory):
    serve(directory, "run-1.sock", {"peers": "0"})
    assert control.peers(directory) is None


def test_a_garbled_roster_is_an_error(directory):
    serve(directory, "run-1.sock", {"peers": '{"can_invite":true}'})
    with pytest.raises(ControlError):
        control.peers(directory)


def test_invite_sends_the_peer_id_and_reports_whether_it_was_queued(directory):
    asked = serve(directory, "run-1.sock", {"invite " + "a" * 32: "1"})
    assert control.invite(directory, Peer("a" * 32, "Sam")) is True
    assert control.invite(directory, Peer("b" * 32, "Eve")) is False
    assert asked == ["invite " + "a" * 32, "invite " + "b" * 32]


def test_a_malformed_peer_id_is_never_sent(directory):
    asked = serve(directory, "run-1.sock", {})
    assert control.invite(directory, Peer("a b", "Bad")) is False
    assert asked == []
