import pytest

from ptcg.core.action import UseSupporterAction
from tests.helpers.cards import make_card
from tests.helpers.generator_driver import drive_choices
from tests.helpers.state_builder import PlayerZones, make_state

CRISPIN_TEXT = (
    "Search your deck for up to 2 Basic Energy cards of different types, reveal them, "
    "and put 1 of them into your hand. Attach the other to 1 of your Pokémon. "
    "Then, shuffle your deck."
)


@pytest.mark.card("SCR-133")
def test_crispin_text_is_verbatim():
    assert make_card("SCR-133").text == CRISPIN_TEXT


@pytest.mark.card("SCR-133")
def test_crispin_puts_one_energy_in_hand_and_attaches_the_other(monkeypatch):
    monkeypatch.setattr("ptcg.utils.utils.random.shuffle", lambda _cards: None)
    crispin = make_card("SCR-133")
    fire_a = make_card("SVE-002")
    fire_b = make_card("SVE-002")
    lightning = make_card("SVE-004")
    target = make_card("TWM-128")
    state = make_state(PlayerZones(hand=[crispin], left=[fire_a, fire_b, lightning], active=[target]))

    actions = crispin.get_actions(state)
    assert len(actions) == 1 and isinstance(actions[0], UseSupporterAction)

    # prompt order: (1) up to 2 energy from deck, (2) which one goes to hand, (3) attach target
    drive_choices(
        crispin.reduce_action(actions[0], state),
        [
            lambda _i: [fire_a, lightning],
            lambda _i: [lightning],
            lambda _i: [target],
        ],
    )

    assert state.player1.hand == [lightning]
    assert target.attachment == [fire_a]
    assert target.energy == fire_a.provides
    assert state.player1.left == [fire_b]
    assert crispin in state.player1.discard
    assert state.player1.supporterPlayedTurn is True


@pytest.mark.card("SCR-133")
def test_crispin_only_offers_energy_pairs_of_different_types():
    crispin = make_card("SCR-133")
    fire_a = make_card("SVE-002")
    fire_b = make_card("SVE-002")
    lightning = make_card("SVE-004")
    target = make_card("TWM-128")
    state = make_state(PlayerZones(hand=[crispin], left=[fire_a, fire_b, lightning], active=[target]))

    prompts = drive_choices(
        crispin.reduce_action(crispin.get_actions(state)[0], state),
        [lambda _i: [fire_a, lightning], lambda _i: [lightning], lambda _i: [target]],
    )

    offered = [
        [c.id for c in choice.chosen] for choice in prompts[0]["raw_available_actions"]
    ]
    assert [fire_a.id, fire_b.id] not in offered


@pytest.mark.card("SCR-133")
def test_crispin_unavailable_after_a_supporter_was_played():
    crispin = make_card("SCR-133")
    state = make_state(PlayerZones(hand=[crispin], left=[make_card("SVE-002")]))
    state.player1.supporterPlayedTurn = True

    assert crispin.get_actions(state) == []
