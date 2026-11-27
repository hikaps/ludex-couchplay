"""The subset of gbe_fork's ``net.proto`` (proto3) the agent speaks, hand-coded so there is no protobuf dependency."""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass, field

LOBBY_CONNECT_APPID = 0xFFFFFFFE

# Common_Message oneof field numbers
_ANNOUNCE, _LOW_LEVEL, _FRIEND, _FRIEND_MESSAGES = 3, 4, 9, 11
_KINDS = {_ANNOUNCE: "announce", _LOW_LEVEL: "low_level", _FRIEND: "friend", _FRIEND_MESSAGES: "friend_messages"}


def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if pos >= len(data) or shift > 63:
            raise ValueError("truncated varint")
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7


def fields(data: bytes) -> Iterator[tuple[int, int, int | bytes]]:
    """Yield ``(field number, wire type, value)``; length-delimited values are bytes."""
    pos = 0
    while pos < len(data):
        tag, pos = _read_varint(data, pos)
        number, wire = tag >> 3, tag & 7
        if wire == 0:
            value, pos = _read_varint(data, pos)
        elif wire == 2:
            size, pos = _read_varint(data, pos)
            if pos + size > len(data):
                raise ValueError("truncated field")
            value, pos = data[pos : pos + size], pos + size
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            if pos + size > len(data):
                raise ValueError("truncated field")
            value, pos = int.from_bytes(data[pos : pos + size], "little"), pos + size
        else:
            raise ValueError(f"unsupported wire type {wire}")
        yield number, wire, value


@dataclass
class Friend:
    id: int = 0
    name: str = ""
    appid: int = 0
    lobby_id: int = 0
    rich_presence: dict[str, str] = field(default_factory=dict)


@dataclass
class Message:
    source_id: int = 0
    dest_id: int = 0
    kind: str = ""  # announce | low_level | friend | friend_messages | "" for anything else
    announce_type: int = 0  # 0 PING, 1 PONG
    ids: list[int] = field(default_factory=list)
    tcp_port: int = 0
    appid: int = 0
    friend: Friend | None = None


def _text(value: int | bytes) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else ""


def _decode_announce(data: bytes, message: Message) -> None:
    for number, wire, value in fields(data):
        if number == 1 and wire == 0:
            message.announce_type = int(value)
        elif number == 2 and wire == 0:
            message.ids.append(int(value))
        elif number == 2 and wire == 2 and isinstance(value, bytes):  # packed
            pos = 0
            while pos < len(value):
                item, pos = _read_varint(value, pos)
                message.ids.append(item)
        elif number == 3 and wire == 0:
            message.tcp_port = int(value)
        elif number == 5 and wire == 0:
            message.appid = int(value)


def _decode_friend(data: bytes) -> Friend:
    friend = Friend()
    for number, wire, value in fields(data):
        if number == 1 and wire == 0:
            friend.id = int(value)
        elif number == 2 and wire == 2:
            friend.name = _text(value)
        elif number == 3 and wire == 2 and isinstance(value, bytes):
            entry = {n: v for n, _, v in fields(value)}
            friend.rich_presence[_text(entry.get(1, b""))] = _text(entry.get(2, b""))
        elif number == 4 and wire == 0:
            friend.appid = int(value)
        elif number == 5 and wire == 0:
            friend.lobby_id = int(value)
    return friend


def decode(data: bytes) -> Message:
    message = Message()
    for number, wire, value in fields(data):
        if number == 1 and wire == 0:
            message.source_id = int(value)
        elif number == 2 and wire == 0:
            message.dest_id = int(value)
        elif number in _KINDS and wire == 2 and isinstance(value, bytes):
            message.kind = _KINDS[number]
            if number == _ANNOUNCE:
                _decode_announce(value, message)
            elif number == _FRIEND:
                message.friend = _decode_friend(value)
    return message


def _field(number: int, value: int) -> bytes:  # proto3 leaves defaults out
    return varint(number << 3) + varint(value) if value else b""


def _bytes(number: int, value: bytes) -> bytes:
    return varint(number << 3 | 2) + varint(len(value)) + value


def _common(source_id: int, dest_id: int = 0) -> bytes:
    return _field(1, source_id) + _field(2, dest_id)


def hello(source_id: int) -> bytes:
    return _common(source_id)


def heartbeat(source_id: int) -> bytes:
    return _common(source_id) + _bytes(_LOW_LEVEL, b"")


def announce(source_id: int, ping: bool, tcp_port: int, appid: int) -> bytes:
    body = _field(1, 0 if ping else 1) + _bytes(2, varint(source_id)) + _field(3, tcp_port) + _field(5, appid)
    return _common(source_id) + _bytes(_ANNOUNCE, body)


def _friend_messages(source_id: int, dest_id: int, body: bytes) -> bytes:
    return _common(source_id, dest_id) + _bytes(_FRIEND_MESSAGES, body)


def friend(dest_id: int, record: Friend) -> bytes:
    """The inviter's own ``Friend`` record, which a game must already hold before it honours the inviter's invite."""
    body = _field(1, record.id) + _bytes(2, record.name.encode()) + _field(4, record.appid) + _field(5, record.lobby_id)
    for key, value in record.rich_presence.items():
        body += _bytes(3, _bytes(1, key.encode()) + _bytes(2, value.encode()))
    return _common(record.id, dest_id) + _bytes(_FRIEND, body)


def lobby_invite(source_id: int, dest_id: int, lobby_id: int) -> bytes:
    return _friend_messages(source_id, dest_id, _field(2, lobby_id))


def game_invite(source_id: int, dest_id: int, connect: str) -> bytes:
    return _friend_messages(source_id, dest_id, _field(1, 1) + _bytes(3, connect.encode()))


def frame(payload: bytes) -> bytes:
    return struct.pack("<I", len(payload)) + payload
