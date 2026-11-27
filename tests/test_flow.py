from __future__ import annotations

from ludex_lan.control import Invite, Peer, Roster
from ludex_lan.flow import (
    CHOICE_TIMEOUT_MS,
    TOAST_MS,
    Answer,
    Hide,
    InviteFlow,
    RefreshPeers,
    SendInvite,
    Show,
    StartCapture,
    StopCapture,
)

BOB = Invite("1", "Bob")
KEY_A = {"event": "key", "name": "a"}
KEY_B = {"event": "key", "name": "b"}
UP = {"event": "key", "name": "dpad-up"}
DOWN = {"event": "key", "name": "dpad-down"}
CAPTURED = {"event": "captured"}

SAM = Peer("a" * 32, "Sam")
EVE = Peer("b" * 32, "Eve", with_me=True)
OLD = Peer("c" * 32, "Old")


def hosted() -> InviteFlow:
    flow = InviteFlow()
    assert flow.on_host(True) == [StartCapture()]
    return flow


def shown(flow: InviteFlow | None = None, invite: Invite = BOB) -> InviteFlow:
    flow = flow or hosted()
    flow.on_invites([invite])
    return flow


def picking(roster: Roster | None) -> InviteFlow:
    flow = hosted()
    flow.on_capture_event(CAPTURED)
    flow.on_roster(roster)
    return flow


def text(effects: list) -> str:
    [show] = [effect for effect in effects if isinstance(effect, Show)]
    return show.text


# --- the capture follows the host

def test_capture_starts_once_when_a_host_answers_and_stops_when_it_goes():
    flow = InviteFlow()
    assert flow.on_host(True) == [StartCapture()]
    assert flow.on_host(True) == []
    assert flow.on_host(False) == [StopCapture(), Hide()]
    assert flow.on_host(False) == []


def test_a_pending_invite_shows_a_notice_and_waits_for_the_chord():
    assert hosted().on_invites([BOB]) == [Show("Invite from Bob\nHold LB + RB + Y to respond")]


def test_nothing_happens_without_an_invite():
    assert hosted().on_invites([]) == []


# --- answering an invite

def test_keys_before_the_pad_is_captured_do_nothing():
    assert shown().on_capture_event(KEY_A) == []


def test_capture_switches_the_notice_to_the_choice():
    [show] = shown().on_capture_event(CAPTURED)
    assert show.timeout_ms == CHOICE_TIMEOUT_MS and "Accept" in show.text and "Decline" in show.text


def test_a_accepts_and_b_declines():
    for key, accept in ((KEY_A, True), (KEY_B, False)):
        flow = shown()
        flow.on_capture_event(CAPTURED)
        assert flow.on_capture_event(key) == [Answer(BOB, accept), StopCapture(), Hide()]
        assert not flow.active
        assert flow.on_host(True) == [StartCapture()]  # the next check hands the pad back to waiting


def test_other_buttons_are_ignored_while_choosing():
    flow = shown()
    flow.on_capture_event(CAPTURED)
    assert flow.on_capture_event(UP) == []
    assert flow.active


def test_an_answered_invite_the_host_still_lists_is_not_shown_again():
    flow = shown()
    flow.on_capture_event(CAPTURED)
    flow.on_capture_event(KEY_A)
    flow.on_host(True)
    assert flow.on_invites([BOB]) == []
    assert flow.on_invites([]) == []
    assert flow.on_invites([BOB]) == [Show("Invite from Bob\nHold LB + RB + Y to respond")]


def test_the_notice_goes_when_the_host_drops_the_invite():
    flow = shown()
    assert flow.on_invites([]) == [StopCapture(), Hide()]
    assert not flow.active


def test_a_second_invite_waits_for_the_first():
    assert shown().on_invites([BOB, Invite("2", "Eve")]) == []


def test_giving_up_after_the_chord_leaves_the_invite_pending_to_be_shown_again():
    flow = shown()
    flow.on_capture_event(CAPTURED)
    assert flow.on_timeout() == [StopCapture(), Hide()]
    flow.on_host(True)
    assert flow.on_invites([BOB]) == [Show("Invite from Bob\nHold LB + RB + Y to respond")]


def test_a_timeout_before_the_chord_does_nothing():
    assert shown().on_timeout() == []


def test_a_capture_that_dies_hides_the_notice_without_stopping_it_again():
    flow = shown()
    assert flow.on_capture_ended() == [Hide()]
    assert flow.on_capture_ended() == []
    assert flow.on_host(True) == [StartCapture()]


def test_the_host_going_away_closes_a_shown_invite():
    assert shown().on_host(False) == [StopCapture(), Hide()]


# --- the picker

def test_the_chord_without_an_invite_opens_the_picker_and_asks_for_the_roster():
    flow = hosted()
    effects = flow.on_capture_event(CAPTURED)
    assert [type(effect) for effect in effects] == [Show, RefreshPeers]
    assert "Looking for players" in text(effects) and flow.picking
    assert effects[0].timeout_ms == CHOICE_TIMEOUT_MS


def test_the_roster_lists_players_with_their_state_and_a_marker():
    flow = picking(None)
    effects = flow.on_roster(Roster(True, [SAM, EVE, OLD]))
    lines = text(effects).splitlines()
    assert lines[1:4] == ["▶ Sam", "    Eve (in game)", "    Old"]


def test_the_split_screen_sibling_is_labelled_and_still_invitable():
    flow = picking(Roster(True, [Peer("d" * 32, "Pal", this_pc=True)]))
    flow.on_capture_event(KEY_A)
    assert flow.on_capture_event(KEY_A) == [SendInvite(Peer("d" * 32, "Pal", this_pc=True))]


def test_dpad_moves_the_marker_and_stops_at_the_ends():
    flow = picking(Roster(True, [SAM, EVE, OLD]))
    assert "▶ Eve" in text(flow.on_capture_event(DOWN))
    flow.on_capture_event(DOWN)
    assert "▶ Old" in text(flow.on_capture_event(DOWN))  # already last
    flow.on_capture_event(UP)
    flow.on_capture_event(UP)
    assert "▶ Sam" in text(flow.on_capture_event(UP))


def test_moving_restarts_the_timeout():
    flow = picking(Roster(True, [SAM, OLD]))
    [show] = flow.on_capture_event(DOWN)
    assert show.timeout_ms == CHOICE_TIMEOUT_MS


def test_a_invites_the_highlighted_player_and_the_result_is_shown_briefly():
    flow = picking(Roster(True, [SAM, OLD]))
    flow.on_capture_event(DOWN)
    assert flow.on_capture_event(KEY_A) == [SendInvite(OLD)]
    assert flow.on_invite_sent(OLD, True) == [Show("Invite sent to Old", TOAST_MS)]
    assert flow.on_capture_event(KEY_A) == []  # the toast is not a menu
    assert flow.on_roster(Roster(True, [SAM])) == []
    assert flow.on_timeout() == [StopCapture(), Hide()]
    assert not flow.picking


def test_a_failed_invite_says_so():
    flow = picking(Roster(True, [SAM]))
    assert flow.on_invite_sent(SAM, False) == [Show("Couldn't send the invite", TOAST_MS)]


def test_a_on_a_player_already_in_the_game_does_nothing():
    flow = picking(Roster(True, [EVE]))
    assert flow.on_capture_event(KEY_A) == []


def test_b_closes_the_picker_and_hands_the_pad_back():
    flow = picking(Roster(True, [SAM]))
    assert flow.on_capture_event(KEY_B) == [StopCapture(), Hide()]
    assert not flow.picking


def test_nothing_to_invite_to_is_said_and_a_does_nothing():
    assert "Start the game first" in picking(None)._picker_text()
    flow = picking(Roster(False, [SAM]))
    assert "Nothing to invite to yet" in flow._picker_text()
    assert flow.on_capture_event(KEY_A) == []


def test_an_empty_roster_says_no_players():
    assert "No players found" in picking(Roster(True, []))._picker_text()


def test_an_unchanged_roster_does_not_redraw_or_restart_the_timeout():
    flow = picking(Roster(True, [SAM]))
    assert flow.on_roster(Roster(True, [SAM])) == []
    assert "Sam" in text(flow.on_roster(Roster(True, [SAM, OLD]))) and "Old" in flow._picker_text()


def test_a_shrinking_roster_keeps_the_marker_on_a_player():
    flow = picking(Roster(True, [SAM, EVE, OLD]))
    flow.on_capture_event(DOWN)
    flow.on_capture_event(DOWN)
    assert "▶ Sam" in text(flow.on_roster(Roster(True, [SAM])))


def test_a_long_roster_scrolls_to_keep_the_marker_in_view():
    many = [Peer(f"{i:032x}", f"P{i}") for i in range(12)]
    flow = picking(Roster(True, many))
    for _ in range(9):
        effects = flow.on_capture_event(DOWN)
    rows = text(effects).splitlines()[1:-1]
    assert len(rows) == 6 and "▶ P9" in rows


def test_a_pending_invite_takes_over_an_open_picker():
    flow = picking(Roster(True, [SAM]))
    [show] = flow.on_invites([BOB])
    assert "Invite from Bob" in show.text and "Accept" in show.text and not flow.picking
    assert flow.on_capture_event(KEY_A) == [Answer(BOB, True), StopCapture(), Hide()]


def test_the_picker_closes_when_the_host_goes_away():
    assert picking(Roster(True, [SAM])).on_host(False) == [StopCapture(), Hide()]


def test_a_capture_that_dies_closes_the_picker():
    flow = picking(Roster(True, [SAM]))
    assert flow.on_capture_ended() == [Hide()]
    assert not flow.picking
