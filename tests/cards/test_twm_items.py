import pytest

from ptcg.core.action import UseItemAction
from ptcg.core.enums import CardTag
from tests.helpers.cards import make_card
from tests.helpers.generator_driver import drive_choices
from tests.helpers.state_builder import PlayerZones, make_state


@pytest.mark.card("TWM-152")
@pytest.mark.card_coverage(
    "TWM-152",
    "get_actions",
    "reduce_action",
    "choice_flow",
    "negative_case",
    "zone_change",
)
def test_hyper_aroma_searches_stage1_pokemon_from_deck():
    card = make_card("TWM-152")
    stage1_a = make_card("TWM-129")  # Drakloak - Stage 1
    stage1_b = make_card("TEF-129")  # Dudunsparce - Stage 1
    basic = make_card("PAF-007")  # Charmander - Basic (not eligible)
    state = make_state(PlayerZones(hand=[card], left=[stage1_a, stage1_b, basic]))

    actions = card.get_actions(state)
    assert len(actions) == 1
    assert isinstance(actions[0], UseItemAction)

    prompts = drive_choices(
        card.reduce_action(actions[0], state),
        [lambda _info: [stage1_a, stage1_b]],
    )

    assert set(prompts[0]["prompt"].candidates) == {stage1_a, stage1_b}
    assert stage1_a in state.player1.hand
    assert stage1_b in state.player1.hand
    assert basic not in state.player1.hand
    assert card in state.player1.discard


def test_hyper_aroma_unavailable_with_empty_deck():
    card = make_card("TWM-152")
    state = make_state(PlayerZones(hand=[card]))

    assert card.get_actions(state) == []


@pytest.mark.card("TWM-163")
@pytest.mark.card_coverage(
    "TWM-163",
    "get_actions",
    "reduce_action",
    "choice_flow",
    "negative_case",
    "zone_change",
)
def test_secret_box_searches_item_tool_supporter_stadium_from_deck():
    card = make_card("TWM-163")
    discard1 = make_card("SVE-002")
    discard2 = make_card("SVE-004")
    discard3 = make_card("SVE-005")
    deck_item = make_card("TEF-144")  # Buddy-Buddy Poffin - Item
    deck_tool = make_card("TEF-151")  # Heavy Baton - Tool
    deck_supporter = make_card("TEF-145")  # Ciphermaniac's Codebreaking - Supporter
    deck_stadium = make_card("BRS-137")  # Collapsed Stadium - Stadium
    state = make_state(
        PlayerZones(
            hand=[card, discard1, discard2, discard3],
            left=[deck_item, deck_tool, deck_supporter, deck_stadium],
        )
    )

    actions = card.get_actions(state)
    assert len(actions) == 1

    drive_choices(
        card.reduce_action(actions[0], state),
        [
            lambda _info: [discard1, discard2, discard3],
            lambda _info: [deck_item],
            lambda _info: [deck_tool],
            lambda _info: [deck_supporter],
            lambda _info: [deck_stadium],
        ],
    )

    assert deck_item in state.player1.hand
    assert deck_tool in state.player1.hand
    assert deck_supporter in state.player1.hand
    assert deck_stadium in state.player1.hand
    assert discard1 in state.player1.discard
    assert card in state.player1.discard


def test_secret_box_unavailable_with_fewer_than_three_other_hand_cards():
    card = make_card("TWM-163")
    make_state(PlayerZones(hand=[card, make_card("SVE-002"), make_card("SVE-004")]))
    # only 2 other cards, need 3
    state2 = make_state(PlayerZones(hand=[card, make_card("SVE-002")]))

    assert card.get_actions(state2) == []


STAMP_TEXT = (
    "You can use this card only if any of your Pokémon were Knocked Out during your "
    "opponent's last turn.\nEach player shuffles their hand into their deck. "
    "Then, you draw 5 cards, and your opponent draws 2 cards."
)


def _stamp_deck(n):
    return [make_card("SVE-002") for _ in range(n)]


@pytest.mark.card("TWM-165")
def test_unfair_stamp_text_and_ace_spec_tag():
    stamp = make_card("TWM-165")
    assert stamp.text == STAMP_TEXT
    assert stamp.cardTag == CardTag.ACE_SPEC


@pytest.mark.card("TWM-165")
def test_unfair_stamp_unavailable_without_knockout_last_turn():
    stamp = make_card("TWM-165")
    state = make_state(PlayerZones(hand=[stamp], left=_stamp_deck(10)))
    state.player1.hasPokemonDead = False

    assert stamp.get_actions(state) == []


@pytest.mark.card("TWM-165")
def test_unfair_stamp_shuffles_both_hands_and_draws_five_and_two(monkeypatch):
    monkeypatch.setattr("ptcg.utils.utils.random.shuffle", lambda _cards: None)
    stamp = make_card("TWM-165")
    my_hand = [make_card("SVE-004"), make_card("SVE-005")]
    opp_hand = [make_card("SVE-007"), make_card("SVE-008"), make_card("SVE-004")]
    my_deck = _stamp_deck(8)
    opp_deck = _stamp_deck(6)
    state = make_state(
        PlayerZones(hand=[stamp] + my_hand, left=my_deck),
        PlayerZones(hand=opp_hand, left=opp_deck),
    )
    state.player1.hasPokemonDead = True

    actions = stamp.get_actions(state)
    assert len(actions) == 1 and isinstance(actions[0], UseItemAction)

    list(stamp.reduce_action(actions[0], state) or [])

    assert len(state.player1.hand) == 5
    assert len(state.player2.hand) == 2
    assert stamp in state.player1.discard
    assert len(state.player1.left) == 8 + 2 - 5
    assert len(state.player2.left) == 6 + 3 - 2
    assert sorted(c.id for c in state.player1.hand + state.player1.left) == sorted(
        c.id for c in my_deck + my_hand
    )
