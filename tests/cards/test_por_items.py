import pytest

from ptcg.core.action import UseItemAction
from ptcg.core.enums import CardType, PokemonRule
from tests.helpers.cards import make_card
from tests.helpers.generator_driver import drive_choices
from tests.helpers.state_builder import PlayerZones, make_state

POKE_PAD_TEXT = (
    "Search your deck for a Pokémon that doesn't have a Rule Box, reveal it, and put it "
    "into your hand. Then, shuffle your deck.\n(Pokémon ex, Pokémon V, etc. have Rule Boxes.)"
)
HAMMER_TEXT = "Flip a coin. If heads, discard an Energy attached to 1 of your opponent's Pokémon."


class FixedRng:
    """Deterministic stand-in for state.rng: randint(0, 1) == 0 is heads."""

    def __init__(self, value):
        self.value = value
        self.flips = 0

    def randint(self, _a, _b):
        self.flips += 1
        return self.value

    def shuffle(self, _cards):
        return None


@pytest.mark.card("POR-081")
def test_poke_pad_text_is_verbatim():
    assert make_card("POR-081").text == POKE_PAD_TEXT


@pytest.mark.card("POR-081")
def test_poke_pad_offers_only_pokemon_without_a_rule_box(monkeypatch):
    monkeypatch.setattr("ptcg.utils.utils.random.shuffle", lambda _cards: None)
    pad = make_card("POR-081")
    dreepy = make_card("TWM-128")
    munkidori = make_card("TWM-095")
    dragapult_ex = make_card("TWM-200")
    fezandipiti_ex = make_card("SFA-092")
    radiant = make_card("TWM-128")
    radiant.pokemonRule = PokemonRule.RADIANT  # synthetic: Radiant Pokémon carry a Rule Box
    energy = make_card("SVE-002")
    deck = [dreepy, munkidori, dragapult_ex, fezandipiti_ex, radiant, energy]
    state = make_state(PlayerZones(hand=[pad], left=deck))

    actions = pad.get_actions(state)
    assert len(actions) == 1 and isinstance(actions[0], UseItemAction)

    prompts = drive_choices(pad.reduce_action(actions[0], state), [lambda _i: [munkidori]])

    assert set(prompts[0]["prompt"].candidates) == {dreepy, munkidori}
    assert state.player1.hand == [munkidori]
    assert munkidori not in state.player1.left
    assert pad in state.player1.discard


@pytest.mark.card("POR-081")
def test_poke_pad_shuffles_the_deck(monkeypatch):
    shuffled = []
    monkeypatch.setattr("ptcg.utils.utils.random.shuffle", lambda cards: shuffled.append(cards))
    pad = make_card("POR-081")
    dreepy = make_card("TWM-128")
    state = make_state(PlayerZones(hand=[pad], left=[dreepy, make_card("SVE-002")]))

    drive_choices(pad.reduce_action(pad.get_actions(state)[0], state), [lambda _i: [dreepy]])

    assert shuffled, "deck was not shuffled after the search"


@pytest.mark.card("POR-071")
def test_crushing_hammer_text_is_verbatim():
    assert make_card("POR-071").text == HAMMER_TEXT


def _hammer_state(coin_value):
    hammer = make_card("POR-071")
    attached = make_card("SVE-002")
    other_attached = make_card("SVE-004")
    victim = make_card("TWM-128")
    victim.attachment = [attached, other_attached]
    victim.energy = [CardType.FIRE, CardType.LIGHTNING]
    state = make_state(
        PlayerZones(hand=[hammer], active=[make_card("TWM-095")]),
        PlayerZones(active=[victim]),
    )
    state.rng = FixedRng(coin_value)
    return state, hammer, victim, attached, other_attached


@pytest.mark.card("POR-071")
def test_crushing_hammer_heads_discards_one_chosen_energy_from_opponent_pokemon():
    state, hammer, victim, attached, other_attached = _hammer_state(0)

    actions = hammer.get_actions(state)
    assert len(actions) == 1 and isinstance(actions[0], UseItemAction)

    # prompt order: (1) which opposing Pokémon, (2) which Energy on it
    drive_choices(
        hammer.reduce_action(actions[0], state),
        [lambda _i: [victim], lambda _i: [attached]],
    )

    assert attached in state.player2.discard
    assert victim.attachment == [other_attached]
    assert victim.energy == [CardType.LIGHTNING]
    assert hammer in state.player1.discard


@pytest.mark.card("POR-071")
def test_crushing_hammer_tails_discards_nothing():
    state, hammer, victim, attached, other_attached = _hammer_state(1)

    list(hammer.reduce_action(hammer.get_actions(state)[0], state) or [])

    assert victim.attachment == [attached, other_attached]
    assert victim.energy == [CardType.FIRE, CardType.LIGHTNING]
    assert state.player2.discard == []
    assert hammer in state.player1.discard


@pytest.mark.card("POR-071")
def test_crushing_hammer_flip_goes_through_flip_coin():
    state, hammer, victim, attached, _other = _hammer_state(0)

    drive_choices(
        hammer.reduce_action(hammer.get_actions(state)[0], state),
        [lambda _i: [victim], lambda _i: [attached]],
    )

    assert state.rng.flips == 1
