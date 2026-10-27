from ptcg.core.action import AttackAction, UseItemAction
from ptcg.core.enums import PlayerId
from ptcg.utils.utils import next_turn
from tests.helpers.cards import make_card
from tests.helpers.generator_driver import drive_choices
from tests.helpers.state_builder import PlayerZones, make_state


def _item_actions(player, state):
    return [a for a in player.get_actions(state) if isinstance(a, UseItemAction)]


def _deck():
    return [make_card("SVE-002") for _ in range(10)]


def _two_player_state(p1_active, p2_hand):
    return make_state(
        PlayerZones(left=_deck(), prize=[make_card("SVE-004")], active=[p1_active]),
        PlayerZones(
            hand=p2_hand,
            left=_deck(),
            prize=[make_card("SVE-007")],
            active=[make_card("TEF-128")],
        ),
    )


def test_item_lock_flag_removes_use_item_actions():
    poffin = make_card("TEF-144")
    state = make_state(PlayerZones(hand=[poffin], left=[make_card("TEF-128")]))
    player = state.player1

    assert len(_item_actions(player, state)) == 1  # control: playable unlocked

    player.itemLocked = True

    assert _item_actions(player, state) == []


def test_item_lock_flag_clears_when_locked_player_turn_ends():
    state = _two_player_state(make_card("TEF-128"), [make_card("TEF-144")])
    state.turn = PlayerId.PLAYER2
    state.player2.itemLocked = True

    next_turn(state)  # P2's turn ends

    assert state.player2.itemLocked is False


def test_itchy_pollen_locks_items_for_opponents_next_turn_only():
    budew = make_card("ASC-016")
    poffin = make_card("TEF-144")
    state = _two_player_state(budew, [poffin])
    pollen = next(a for a in budew.get_actions(state) if isinstance(a, AttackAction))

    assert len(_item_actions(state.player2, state)) == 1  # control: legal before the lock

    drive_choices(budew.reduce_action(pollen, state), [])

    assert state.turn == PlayerId.PLAYER2
    assert _item_actions(state.player2, state) == []

    next_turn(state)  # P2 passes
    next_turn(state)  # P1 passes

    assert state.turn == PlayerId.PLAYER2
    assert len(_item_actions(state.player2, state)) == 1


def test_itchy_pollen_does_not_lock_the_attacker():
    budew = make_card("ASC-016")
    state = _two_player_state(budew, [])
    state.player1.hand = [make_card("TEF-144")]
    pollen = next(a for a in budew.get_actions(state) if isinstance(a, AttackAction))

    drive_choices(budew.reduce_action(pollen, state), [])

    assert state.player1.itemLocked is False
