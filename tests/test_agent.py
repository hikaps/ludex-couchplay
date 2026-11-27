from __future__ import annotations

import asyncio
import json
import time

import pytest

from ludex_lan import agent as agent_module
from ludex_lan.agent import INVITE_TTL_S, Agent
from ludex_lan.backends import Presence

A = Presence("1", "A", "49520", "lobby:9", "10.0.0.1")
B = Presence("2", "B", "49520", "", "10.0.0.1")
C = Presence("3", "C", "49520", "lobby:9", "10.0.0.2")
OTHER_GAME = Presence("4", "D", "1", "lobby:1", "10.0.0.2")


class FakeBackend:
    name = "fake"

    def __init__(self) -> None:
        self.presences: list[Presence] = []
        self.delivered: list[tuple[Presence, str, str]] = []
        self.reachable = True

    async def run(self) -> None: ...

    def roster(self) -> list[Presence]:
        return self.presences

    def deliver(self, to: Presence, inviter_id: str, session: str) -> bool:
        self.delivered.append((to, inviter_id, session))
        return self.reachable


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def agent(backend) -> Agent:
    return Agent(backend, ["a", "b"], {"a": "1", "b": "2"}.__getitem__)


def ask(agent: Agent, player: str, line: str) -> str:
    return asyncio.run(agent.handle(player, line))


def test_peers_is_unavailable_until_the_players_game_shows_up(agent):
    assert ask(agent, "a", "peers") == "0"


def test_peers_lists_the_same_game_with_session_and_pc_flags(agent, backend):
    backend.presences = [A, B, C, OTHER_GAME]
    reply = json.loads(ask(agent, "a", "peers"))
    assert reply["can_invite"] is True
    assert reply["peers"] == [
        {"id": "2", "name": "B", "with_me": False, "this_pc": True},
        {"id": "3", "name": "C", "with_me": True, "this_pc": False},
    ]


def test_nothing_can_be_invited_to_before_a_session_exists(agent, backend):
    backend.presences = [A, B]
    assert json.loads(ask(agent, "b", "peers"))["can_invite"] is False
    assert ask(agent, "b", "invite 1") == "0"


def test_a_local_invite_is_listed_and_accepting_delivers_it(agent, backend):
    backend.presences = [A, B]
    assert ask(agent, "a", "invite 2") == "1"
    [listed] = json.loads(ask(agent, "b", "invites"))
    assert listed["name"] == "A" and ask(agent, "a", "invites") == "[]"
    assert ask(agent, "b", f"accept {listed['id']}") == "1"
    assert backend.delivered == [(B, "1", "lobby:9")]
    assert ask(agent, "b", f"accept {listed['id']}") == "0"


def test_declining_removes_the_invite(agent, backend):
    backend.presences = [A, B]
    ask(agent, "a", "invite 2")
    [listed] = json.loads(ask(agent, "b", "invites"))
    assert ask(agent, "b", f"decline {listed['id']}") == "1"
    assert ask(agent, "b", "invites") == "[]" and backend.delivered == []


def test_only_the_invited_player_can_answer_an_invite(agent, backend):
    backend.presences = [A, B]
    ask(agent, "a", "invite 2")
    [listed] = json.loads(ask(agent, "b", "invites"))
    assert ask(agent, "a", f"accept {listed['id']}") == "0"
    assert backend.delivered == []


def test_a_failed_delivery_reports_failure(agent, backend):
    backend.presences = [A, B]
    backend.reachable = False
    ask(agent, "a", "invite 2")
    [listed] = json.loads(ask(agent, "b", "invites"))
    assert ask(agent, "b", f"accept {listed['id']}") == "0"


def test_an_invite_for_a_stranger_is_rejected(agent):
    message = {"id": "x", "from_id": "3", "from_name": "C", "to_id": "99", "game": "1", "session": "lobby:1"}
    assert agent.receive(message) == "0"
    assert agent.receive({**message, "to_id": "2"}) == "1"
    assert agent.receive({"id": 5}) == "0"


def test_a_repeat_invite_from_the_same_player_replaces_the_old_one(agent, backend):
    message = {"id": "x", "from_id": "3", "from_name": "C", "to_id": "2", "game": "1", "session": "lobby:1"}
    agent.receive(message)
    agent.receive({**message, "id": "y"})
    assert [i["id"] for i in json.loads(ask(agent, "b", "invites"))] == ["y"]


def test_an_old_invite_expires(agent, monkeypatch):
    message = {"id": "x", "from_id": "3", "from_name": "C", "to_id": "2", "game": "1", "session": "lobby:1"}
    agent.receive(message)
    later = time.monotonic() + INVITE_TTL_S + 1
    monkeypatch.setattr(agent_module.time, "monotonic", lambda: later)
    assert ask(agent, "b", "invites") == "[]"


def test_an_unreachable_remote_agent_fails_the_invite(agent, backend, monkeypatch):
    backend.presences = [A, C]
    monkeypatch.setattr(agent_module, "AGENT_PORT", 1)  # nothing listens there
    assert ask(agent, "a", "invite 3") == "0"
