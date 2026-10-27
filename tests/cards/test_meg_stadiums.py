import pytest

from ptcg.core.action import EvolvePokemonAction, PlayPokemonAction, PutStadiumAction
from ptcg.core.enums import CardPosition, PlayerId, PokemonPosition
from ptcg.core.reducer import reduce_evolve_pokemon_action, reduce_play_pokemon_action
from tests.helpers.cards import make_card
from tests.helpers.generator_driver import drive_choices
from tests.helpers.state_builder import PlayerZones, make_state

RUINS_TEXT = (
    "Whenever any player puts a Basic non-[D] Pokémon onto their Bench during their turn, "
    "place 2 damage counters on that Pokémon."
)


def _state_with_ruins(p1=None, p2=None, turn=PlayerId.PLAYER1):
    ruins = make_card("MEG-127")
    state = make_state(p1, p2, turn=turn)
    state.stadium = [ruins]
    return state


def _bench(state, player, card):
    reduce_play_pokemon_action(PlayPokemonAction(player.id, card, PokemonPosition.BENCH), state)


@pytest.mark.card("MEG-127")
@pytest.mark.card_coverage("MEG-127", "metadata", "get_actions", "reduce_action", "zone_change")
def test_risky_ruins_text_and_stadium_play():
    ruins = make_card("MEG-127")
    state = make_state(PlayerZones(hand=[ruins]))
    state.player1.firstTurn = False

    assert ruins.name == "Risky Ruins"
    assert ruins.text == RUINS_TEXT
    actions = ruins.get_actions(state)
    assert len(actions) == 1 and isinstance(actions[0], PutStadiumAction)
    ruins.reduce_action(actions[0], state)
    assert state.stadium == [ruins]
    assert ruins.cardPosition == CardPosition.STADIUM


def test_risky_ruins_is_playable_on_first_turn():
    ruins = make_card("MEG-127")
    state = make_state(PlayerZones(hand=[ruins]))

    assert state.player1.firstTurn is True
    actions = ruins.get_actions(state)
    assert len(actions) == 1 and isinstance(actions[0], PutStadiumAction)


@pytest.mark.card("MEG-127")
@pytest.mark.card_coverage("MEG-127", "reduce_action", "damage")
def test_risky_ruins_puts_two_counters_on_own_benched_non_dark_basic():
    dunsparce = make_card("TEF-128")
    state = _state_with_ruins(PlayerZones(hand=[dunsparce], active=[make_card("PAF-007")]))

    _bench(state, state.player1, dunsparce)

    assert dunsparce in state.player1.bench
    assert dunsparce.hp == 60 - 20


def test_risky_ruins_puts_two_counters_on_opponents_basic_on_their_turn():
    dreepy = make_card("TWM-128")
    state = _state_with_ruins(
        PlayerZones(active=[make_card("PAF-007")]),
        PlayerZones(hand=[dreepy], active=[make_card("PAF-007")]),
        turn=PlayerId.PLAYER2,
    )

    _bench(state, state.player2, dreepy)

    assert dreepy.hp == 70 - 20


def test_risky_ruins_ignores_darkness_basic():
    fezandipiti = make_card("SFA-092")
    state = _state_with_ruins(PlayerZones(hand=[fezandipiti], active=[make_card("PAF-007")]))

    _bench(state, state.player1, fezandipiti)

    assert fezandipiti in state.player1.bench
    assert fezandipiti.hp == 210


def test_risky_ruins_ignores_basic_placed_active():
    dunsparce = make_card("TEF-128")
    state = _state_with_ruins(PlayerZones(hand=[dunsparce]))

    reduce_play_pokemon_action(
        PlayPokemonAction(PlayerId.PLAYER1, dunsparce, PokemonPosition.ACTIVE), state
    )

    assert dunsparce.hp == 60


def test_risky_ruins_ignores_evolution():
    dreepy = make_card("TWM-128")
    drakloak = make_card("TWM-129")
    state = _state_with_ruins(
        PlayerZones(hand=[drakloak], bench=[dreepy], active=[make_card("PAF-007")])
    )
    state.player1.firstTurn = False

    reduce_evolve_pokemon_action(EvolvePokemonAction(PlayerId.PLAYER1, drakloak, dreepy), state)

    assert drakloak in state.player1.bench
    assert drakloak.hp == 90


def test_no_counters_without_ruins_in_play():
    dunsparce = make_card("TEF-128")
    state = make_state(PlayerZones(hand=[dunsparce], active=[make_card("PAF-007")]))

    _bench(state, state.player1, dunsparce)

    assert dunsparce.hp == 60


def test_risky_ruins_triggers_on_buddy_buddy_poffin_bench_entry():
    poffin = make_card("TEF-144")
    dunsparce = make_card("TEF-128")
    state = _state_with_ruins(
        PlayerZones(hand=[poffin], left=[dunsparce], active=[make_card("PAF-007")])
    )

    action = poffin.get_actions(state)[0]
    drive_choices(poffin.reduce_action(action, state), [lambda _info: [dunsparce]])

    assert dunsparce in state.player1.bench
    assert dunsparce.hp == 60 - 20
