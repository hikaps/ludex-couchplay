from __future__ import annotations

import argparse

import pytest

from ludex_lan import identity
from ludex_lan.cli import parse_player


def test_a_player_with_an_id_keeps_it():
    assert parse_player("couch2=76561198000000001") == ("couch2", "76561198000000001")


def test_a_player_without_an_id_gets_the_derived_one():
    assert parse_player("couch2") == ("couch2", str(identity.steam_id("couch2")))


@pytest.mark.parametrize("value", ["=1", "p=abc", "p=-5", "p=٣"])
def test_a_nameless_player_or_a_non_numeric_id_is_refused(value):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_player(value)
