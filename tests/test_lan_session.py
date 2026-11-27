from __future__ import annotations

import asyncio
import sys

import pytest

from ludex_couchplay import lan_session
from ludex_lan import identity
from ludex_lan.backends.gbe.settings import set_user, user_ini


def test_set_user_replaces_the_identity_and_keeps_everything_else(tmp_path):
    path = tmp_path / "configs.user.ini"
    path.write_text("[user::general]\n# c\nlanguage=english\naccount_steamid=1\n[other]\naccount_name=keep\n")
    set_user(path, "couch2", 42)
    lines = path.read_text().splitlines()
    assert lines[:2] == ["[user::general]", "account_name=couch2"]
    assert lines.count("account_steamid=42") == 1 and "account_steamid=1" not in lines
    assert {"# c", "language=english", "[other]", "account_name=keep"} <= set(lines)


def test_set_user_creates_the_file_and_rejects_names_that_break_the_format(tmp_path):
    path = user_ini(tmp_path / "pfx")
    set_user(path, "couch5", 7)
    assert path.read_text() == "[user::general]\naccount_name=couch5\naccount_steamid=7\n"
    with pytest.raises(ValueError):
        set_user(path, "a=b", 1)


@pytest.fixture
def couchplay(tmp_path, monkeypatch):
    config, profiles, storage = tmp_path / "couchplayrc", tmp_path / "profiles", tmp_path / "storage"
    profiles.mkdir()
    config.write_text(f"[Players]\nStorageDir={storage}\n")
    (profiles / "steam.conf").write_text("[General]\nname=steam\n[Instance1]\nplayer=couch5\n[Instance0]\nplayer=couch2\n")
    (profiles / "steam.conf.bak").write_text("[General]\nname=steam\n[Instance0]\nplayer=old\n")
    monkeypatch.setattr(lan_session, "CONFIG_FILES", (tmp_path / "missing", config))
    monkeypatch.setattr(lan_session, "PROFILE_DIRS", (profiles,))
    return storage


def test_a_profiles_players_come_in_seat_order_and_an_unknown_profile_has_none(couchplay):
    assert lan_session.profile_players("steam") == ["couch2", "couch5"]
    assert lan_session.profile_players("nope") == []
    assert lan_session.storage_dir() == couchplay


def test_seat_prefixes_are_those_of_the_game(couchplay):
    pfx = couchplay / "couch2/home/.couchplay/steam-libs/1/steamapps/compatdata/49520/pfx"
    pfx.mkdir(parents=True)
    (couchplay / "couch2/home/.couchplay/steam-libs/1/steamapps/compatdata/7/pfx").mkdir(parents=True)
    assert lan_session.seat_prefixes(couchplay, "couch2", "49520") == [pfx]


def test_main_writes_each_seats_identity_and_returns_the_sessions_exit_code(couchplay, monkeypatch):
    pfx = couchplay / "couch2/home/.couchplay/steam-libs/1/steamapps/compatdata/49520/pfx"
    pfx.mkdir(parents=True)

    async def idle(self):
        await asyncio.sleep(3600)

    monkeypatch.setattr(lan_session.Agent, "serve", idle)
    argv = ["--profile", "steam", "--app-id", "49520", "--", sys.executable, "-c", "raise SystemExit(3)"]
    assert lan_session.main(argv) == 3
    assert f"account_steamid={identity.steam_id('couch2')}" in user_ini(pfx).read_text().splitlines()
    assert lan_session.main(["--profile", "nope", "--app-id", "1", "--", "true"]) == 2
