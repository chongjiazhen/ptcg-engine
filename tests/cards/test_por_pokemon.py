import pytest

from ptcg.core.action import AttackAction, PlayPokemonAction
from ptcg.core.enums import CardType, PokemonPosition, PokemonType, Stage
from tests.helpers.cards import make_card
from tests.helpers.generator_driver import drive_choices
from tests.helpers.state_builder import PlayerZones, make_state

ABILITY_TEXT = (
    "Once during your turn, when you play this Pokémon from your hand onto your Bench, "
    "you may use this Ability. Search your deck for a Supporter card, reveal it, and put "
    "it into your hand. Then, shuffle your deck. You can't use more than 1 Ability that "
    'has "Last-Ditch" in its name each turn.'
)
ATTACK_TEXT = "Put this Pokémon and all attached cards into your hand."


@pytest.mark.card("POR-062")
def test_meowth_ex_printed_stats():
    meowth = make_card("POR-062")

    assert meowth.name == "Meowth ex"
    assert meowth.hp == 170
    assert meowth.prize == 2
    assert meowth.pokemonType == PokemonType.EX
    assert meowth.stage == Stage.BASIC
    assert meowth.cardType == CardType.COLORLESS
    assert meowth.weakness == [CardType.FIGHTING]
    assert meowth.resistance == []
    assert meowth.retreat == [CardType.COLORLESS]
    assert meowth.ability[0].name == "Last-Ditch Catch"
    assert meowth.ability[0].text == ABILITY_TEXT
    attack = meowth.attacks[0]
    assert attack.name == "Tuck Tail"
    assert attack.damage == 60
    assert attack.cost == [CardType.COLORLESS] * 3
    assert attack.text == ATTACK_TEXT


def _bench_play(meowth, state):
    return PlayPokemonAction(state.turn, meowth, PokemonPosition.BENCH)


@pytest.mark.card("POR-062")
def test_last_ditch_catch_fetches_a_supporter_when_played_onto_the_bench(monkeypatch):
    monkeypatch.setattr("ptcg.utils.utils.random.shuffle", lambda _cards: None)
    meowth = make_card("POR-062")
    supporter = make_card("ASC-192")
    other_supporter = make_card("PAL-265")
    item = make_card("TEF-144")
    state = make_state(
        PlayerZones(
            hand=[meowth],
            left=[supporter, other_supporter, item],
            active=[make_card("TWM-095")],
        )
    )

    # one prompt: up to 1 Supporter from the deck (the "may" is the 0-card choice)
    prompts = drive_choices(
        meowth.reduce_action(_bench_play(meowth, state), state), [lambda _i: [supporter]]
    )

    assert meowth in state.player1.bench
    assert set(prompts[0]["prompt"].candidates) == {supporter, other_supporter}
    assert state.player1.hand == [supporter]
    assert state.player1.onceUsedTurn["Last-Ditch Catch"] is True


@pytest.mark.card("POR-062")
def test_last_ditch_catch_may_be_declined(monkeypatch):
    monkeypatch.setattr("ptcg.utils.utils.random.shuffle", lambda _cards: None)
    meowth = make_card("POR-062")
    supporter = make_card("ASC-192")
    state = make_state(PlayerZones(hand=[meowth], left=[supporter], active=[make_card("TWM-095")]))

    drive_choices(meowth.reduce_action(_bench_play(meowth, state), state), [lambda _i: []])

    assert state.player1.hand == []
    assert state.player1.left == [supporter]


@pytest.mark.card("POR-062")
def test_last_ditch_catch_does_not_trigger_when_played_as_active():
    meowth = make_card("POR-062")
    supporter = make_card("ASC-192")
    state = make_state(PlayerZones(hand=[meowth], left=[supporter]))
    action = PlayPokemonAction(state.turn, meowth, PokemonPosition.ACTIVE)

    list(meowth.reduce_action(action, state) or [])

    assert meowth in state.player1.active
    assert state.player1.hand == []


@pytest.mark.card("POR-062")
def test_last_ditch_catch_blocked_after_another_last_ditch_ability_this_turn():
    meowth = make_card("POR-062")
    supporter = make_card("ASC-192")
    state = make_state(PlayerZones(hand=[meowth], left=[supporter], active=[make_card("TWM-095")]))
    state.player1.onceUsedTurn["Last-Ditch Catch"] = True

    list(meowth.reduce_action(_bench_play(meowth, state), state) or [])

    assert meowth in state.player1.bench
    assert state.player1.hand == []


@pytest.mark.card("POR-062")
def test_tuck_tail_needs_three_energy():
    meowth = make_card("POR-062")
    meowth.energy = [CardType.FIRE, CardType.FIRE]
    state = make_state(PlayerZones(active=[meowth]), PlayerZones(active=[make_card("TWM-095")]))

    assert [a for a in meowth.get_actions(state) if isinstance(a, AttackAction)] == []


@pytest.mark.card("POR-062")
def test_tuck_tail_deals_60_then_returns_meowth_and_attached_cards_to_hand():
    meowth = make_card("POR-062")
    energies = [make_card("SVE-002"), make_card("SVE-004"), make_card("SVE-005")]
    meowth.attachment = list(energies)
    meowth.energy = [e.provides[0] for e in energies]
    defender = make_card("TWM-095")
    hp_before = defender.hp
    bench_mon = make_card("TWM-128")
    state = make_state(
        PlayerZones(active=[meowth], bench=[bench_mon]), PlayerZones(active=[defender])
    )

    attacks = [a for a in meowth.get_actions(state) if isinstance(a, AttackAction)]
    assert len(attacks) == 1

    # the only prompt allowed is promoting the benched Pokémon into the empty Active spot
    drive_choices(meowth.reduce_action(attacks[0], state), [lambda _i: [bench_mon]])

    assert defender.hp == hp_before - 60
    assert meowth in state.player1.hand
    assert all(e in state.player1.hand for e in energies)
    assert meowth not in state.player1.active
    assert meowth.attachment == [] and meowth.energy == []
