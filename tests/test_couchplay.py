from __future__ import annotations

import pytest

import ludex_couchplay as cp


@pytest.fixture
def native(monkeypatch, tmp_path):
    exe = tmp_path / "couchplay-gamemode"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    monkeypatch.setattr(cp.shutil, "which", lambda name: str(exe) if name == "couchplay-gamemode" else None)
    return str(exe)


@pytest.mark.parametrize(
    ("store", "store_id", "expected"),
    [
        ("steam", "220", "steam:220"), ("steam", "0", None), ("steam", "12a", None), ("steam", "٣", None),
        ("heroic", "abc", "heroic:sideload:abc"), ("epic", "Fortnite", "heroic:legendary:Fortnite"),
        ("heroic", "", None), ("local", "x", None),
    ],
)
def test_game_argument_maps_each_store_to_couchplays_form(store, store_id, expected):
    assert cp.game_argument(store, store_id) == expected


def test_the_action_starts_the_profile_with_the_game(native):
    [action] = cp.actions("steam", "220", {"profile": "Couch"})
    assert (action.id, action.label) == ("split-screen", "Play split-screen")
    assert action.argv == [native, "--profile", "Couch", "--start", "--game", "steam:220"]


def test_nothing_is_offered_without_a_profile_a_supported_store_or_couchplay(native, monkeypatch):
    assert cp.actions("steam", "220", {}) == [] and cp.actions("steam", "220", {"profile": "  "}) == []
    assert cp.actions("local", "x", {"profile": "Couch"}) == []
    assert cp.actions("steam", "220", {"profile": "--game"}) == []  # a profile can never act as an option
    monkeypatch.setattr(cp.shutil, "which", lambda name: None)
    assert cp.actions("steam", "220", {"profile": "Couch"}) == []


def test_the_flatpak_is_used_when_the_command_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(cp.shutil, "which", lambda name: "/usr/bin/flatpak" if name == "flatpak" else None)
    monkeypatch.setattr(cp, "_flatpak_installed", lambda home=None: True)
    [action] = cp.actions("heroic", "abc", {"profile": "P"})
    assert action.argv == ["/usr/bin/flatpak", "run", cp.FLATPAK_ID, "--profile", "P", "--start", "--game", "heroic:sideload:abc"]
    monkeypatch.setattr(cp, "_flatpak_installed", lambda home=None: False)
    assert cp.actions("heroic", "abc", {"profile": "P"}) == []


def test_flatpak_detection_looks_for_the_app_directory(tmp_path):
    assert cp._flatpak_installed(tmp_path) is False
    (tmp_path / ".local/share/flatpak/app" / cp.FLATPAK_ID).mkdir(parents=True)
    assert cp._flatpak_installed(tmp_path) is True


def test_ludex_loads_it_and_asks_for_its_settings(native, monkeypatch, tmp_path):
    from importlib.metadata import EntryPoint

    from ludex.loader import load_providers

    monkeypatch.setenv("LUDEX_HOME", str(tmp_path))
    loaded, problems = load_providers([EntryPoint("couchplay", "ludex_couchplay:PLUGIN", "ludex.providers")])
    assert problems == {} and loaded["couchplay"].capabilities == ("actions",)
    assert loaded["couchplay"].actions("steam", "220") == []  # the setting is read per call; none is set
