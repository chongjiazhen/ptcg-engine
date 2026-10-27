import pytest

from ptcg.core.action import UseSupporterAction
from ptcg.core.enums import CardType
from tests.helpers.cards import make_card
from tests.helpers.generator_driver import drive_choices
from tests.helpers.state_builder import PlayerZones, make_state

JUDGE_TEXT = "Each player shuffles their hand into their deck and draws 4 cards."
ROSA_TEXT = (
    "You can use this card only if you have more Prize cards remaining than your opponent.\n"
    "Attach up to 2 Basic Energy cards from your discard pile to 1 of your Stage 2 Pokémon."
)


def _cards(card_id, n):
    return [make_card(card_id) for _ in range(n)]


@pytest.mark.card("POR-076")
def test_judge_text_is_verbatim():
    assert make_card("POR-076").text == JUDGE_TEXT


@pytest.mark.card("POR-076")
def test_judge_shuffles_both_hands_into_decks_and_each_player_draws_four(monkeypatch):
    monkeypatch.setattr("ptcg.utils.utils.random.shuffle", lambda _cards: None)
    judge = make_card("POR-076")
    my_hand = _cards("SVE-004", 3)
    opp_hand = _cards("SVE-005", 5)
    my_deck = _cards("SVE-002", 6)
    opp_deck = _cards("SVE-007", 6)
    state = make_state(
        PlayerZones(hand=[judge] + my_hand, left=my_deck),
        PlayerZones(hand=opp_hand, left=opp_deck),
    )

    actions = judge.get_actions(state)
    assert len(actions) == 1 and isinstance(actions[0], UseSupporterAction)

    list(judge.reduce_action(actions[0], state) or [])

    assert len(state.player1.hand) == 4
    assert len(state.player2.hand) == 4
    assert len(state.player1.left) == 6 + 3 - 4
    assert len(state.player2.left) == 6 + 5 - 4
    assert judge in state.player1.discard
    assert state.player1.supporterPlayedTurn is True
    assert sorted(c.id for c in state.player2.hand + state.player2.left) == sorted(
        c.id for c in opp_hand + opp_deck
    )


@pytest.mark.card("POR-076")
def test_judge_unavailable_after_a_supporter_was_played():
    judge = make_card("POR-076")
    state = make_state(PlayerZones(hand=[judge], left=_cards("SVE-002", 4)))
    state.player1.supporterPlayedTurn = True

    assert judge.get_actions(state) == []


@pytest.mark.card("POR-084")
def test_rosas_encouragement_text_is_verbatim():
    assert make_card("POR-084").text == ROSA_TEXT


def _rosa_state(my_prizes, opp_prizes):
    rosa = make_card("POR-084")
    stage2 = make_card("TWM-200")
    stage1 = make_card("TWM-129")
    basics = [make_card("SVE-002"), make_card("SVE-004"), make_card("SVE-005")]
    special = make_card("TEF-161")
    state = make_state(
        PlayerZones(
            hand=[rosa],
            discard=basics + [special],
            prize=_cards("SVE-002", my_prizes),
            active=[stage1],
            bench=[stage2],
        ),
        PlayerZones(prize=_cards("SVE-002", opp_prizes)),
    )
    return state, rosa, stage2, stage1, basics, special


@pytest.mark.card("POR-084")
def test_rosas_encouragement_unavailable_unless_more_prizes_remaining_than_opponent():
    for mine, theirs in [(4, 4), (3, 4)]:
        state, rosa, *_ = _rosa_state(mine, theirs)
        assert rosa.get_actions(state) == [], (mine, theirs)


@pytest.mark.card("POR-084")
def test_rosas_encouragement_attaches_up_to_two_basic_energy_to_a_stage_2():
    state, rosa, stage2, stage1, basics, special = _rosa_state(5, 4)

    actions = rosa.get_actions(state)
    assert len(actions) == 1 and isinstance(actions[0], UseSupporterAction)

    # prompt order: (1) up to 2 Basic Energy from discard, (2) a Stage 2 Pokémon
    prompts = drive_choices(
        rosa.reduce_action(actions[0], state),
        [lambda _i: [basics[0], basics[1]], lambda _i: [stage2]],
    )

    assert set(prompts[0]["prompt"].candidates) == set(basics)  # no special Energy
    assert prompts[1]["prompt"].candidates == [stage2]  # Stage 1 is not a target
    assert stage2.attachment == [basics[0], basics[1]]
    assert stage2.energy == [CardType.FIRE, CardType.LIGHTNING]
    assert basics[2] in state.player1.discard
    assert special in state.player1.discard
    assert rosa in state.player1.discard
    assert stage1.attachment == []


@pytest.mark.card("POR-084")
def test_rosas_encouragement_unavailable_without_a_stage_2_pokemon():
    state, rosa, stage2, *_ = _rosa_state(5, 4)
    state.player1.bench.remove(stage2)

    assert rosa.get_actions(state) == []
