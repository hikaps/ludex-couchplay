from __future__ import annotations

import pytest

from ludex_lan.backends.gbe import wire
from ludex_lan.backends.gbe.wire import LOBBY_CONNECT_APPID, varint


def test_a_lobby_invite_has_the_bytes_gbe_expects():
    assert wire.lobby_invite(1, 2, 5) == bytes.fromhex("080110025a021005")


def test_an_announce_survives_a_round_trip():
    message = wire.decode(wire.announce(7, True, 47585, LOBBY_CONNECT_APPID))
    assert (message.kind, message.announce_type, message.ids) == ("announce", 0, [7])
    assert (message.source_id, message.tcp_port, message.appid) == (7, 47585, LOBBY_CONNECT_APPID)
    assert wire.decode(wire.announce(7, False, 1, 1)).announce_type == 1


def test_announce_ids_are_read_packed_or_unpacked():
    def announce(body: bytes) -> bytes:
        return b"\x08\x01\x1a" + bytes([len(body)]) + body

    assert wire.decode(announce(b"\x12\x02\x05\x06")).ids == [5, 6]  # packed
    assert wire.decode(announce(b"\x10\x05\x10\x06")).ids == [5, 6]  # one varint each


def entry(key: str, value: str) -> bytes:
    body = b"\x0a" + varint(len(key)) + key.encode() + b"\x12" + varint(len(value)) + value.encode()
    return b"\x1a" + varint(len(body)) + body


def test_a_friend_record_is_decoded():
    friend = b"\x08\x05\x12\x03Sam" + entry("connect", "+x") + b"\x20" + varint(49520) + b"\x28\x09"
    message = wire.decode(b"\x08\x05\x4a" + varint(len(friend)) + friend)
    assert message.kind == "friend" and message.friend is not None
    assert (message.friend.id, message.friend.name, message.friend.appid, message.friend.lobby_id) == (
        5,
        "Sam",
        49520,
        9,
    )
    assert message.friend.rich_presence == {"connect": "+x"}


def test_unknown_fields_are_skipped():
    assert wire.decode(b"\x08\x03\xc0\x08\x01").source_id == 3  # field 128 varint


def test_truncated_input_is_an_error():
    with pytest.raises(ValueError):
        wire.decode(wire.announce(7, True, 1, 1)[:-1])


def test_frames_carry_a_little_endian_length():
    assert wire.frame(b"abc") == b"\x03\x00\x00\x00abc"


def test_a_friend_record_survives_the_round_trip():
    record = wire.Friend(id=7, name="Host", appid=49520, lobby_id=9, rich_presence={"connect": "1.2.3.4"})
    message = wire.decode(wire.friend(8, record))
    assert (message.source_id, message.dest_id, message.kind) == (7, 8, "friend")
    assert message.friend == record
