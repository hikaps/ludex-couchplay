from __future__ import annotations

import pytest

from ludex_lan.panes import Rect, lookup, overlay_rect

TWO = '{"event":"panes","panes":[{"player":"A","x":0,"y":0,"width":960,"height":1080},{"player":"B","x":960,"y":0,"width":960,"height":1080}]}'


def fake(tmp_path, stdout: str, status: int = 0) -> list[str]:
    script = tmp_path / "couchplay"
    script.write_text(f"#!/bin/sh\n[ \"$1 $2\" = 'pad panes' ] || exit 9\ncat <<'EOF'\n{stdout}\nEOF\nexit {status}\n")
    script.chmod(0o755)
    return [str(script)]


def test_the_players_own_pane_is_picked(tmp_path):
    assert lookup(fake(tmp_path, TWO), "B") == Rect(960, 0, 960, 1080)


@pytest.mark.parametrize("stdout", ["", "not json", '{"event":"panes"}', '{"event":"panes","panes":[{"player":"B"}]}'])
def test_unreadable_output_is_no_pane(tmp_path, stdout):
    assert lookup(fake(tmp_path, stdout), "B") is None


def test_an_unknown_player_and_a_failing_command_are_no_pane(tmp_path):
    assert lookup(fake(tmp_path, TWO), "C") is None
    assert lookup(fake(tmp_path, TWO, status=1), "A") is None
    assert lookup([str(tmp_path / "missing")], "A") is None


def test_the_overlay_sits_in_the_pane_corner_and_shrinks_to_a_small_pane():
    assert overlay_rect(Rect(100, 50, 960, 1080)) == Rect(116, 66, 458, 108)
    assert overlay_rect(Rect(0, 0, 300, 100)) == Rect(16, 16, 268, 68)


def test_a_pane_option_needs_four_integers_and_a_positive_size():
    assert Rect.parse("1,2,3,4") == Rect(1, 2, 3, 4)
    for bad in ("1,2,3", "a,b,c,d", "0,0,0,5"):
        with pytest.raises(ValueError):
            Rect.parse(bad)
