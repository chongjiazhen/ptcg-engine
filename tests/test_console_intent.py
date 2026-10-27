"""Board intents: fixed menu, strict parser, resolve-by-identity, and the inverse."""

from __future__ import annotations

import inspect
import random
from collections.abc import Iterator

import pytest

from ptcg import PokemonTCG
from ptcg.console.intent import Intent, IntentError, intent_of, menu_for, resolve
from ptcg.core.action import ChooseCardAction, ChooseCardActionSpace
from ptcg.core.enums import ActionType, PlayerId

DECK = "dragapult_29678"
MAX_DECISIONS = 250


def walk(seeds, max_decisions: int = MAX_DECISIONS) -> Iterator[tuple]:
    """Random-walk self-play; yield (state, actions) at every decision, live."""
    for seed in seeds:
        env = PokemonTCG(seed=seed, deck1=DECK, deck2=DECK, record_game=False)
        rng = random.Random(seed)
        _obs, _reward, done, info = env.reset()
        for _ in range(max_decisions):
            if done:
                break
            actions = info["raw_available_actions"]
            yield env.gamestate, actions
            if isinstance(actions, ChooseCardActionSpace):
                action = actions[rng.randrange(len(actions))]
            else:
                action = rng.choice(list(actions))
            _obs, _reward, done, info = env.step(action)


def _is_choice(actions) -> bool:
    return isinstance(actions, ChooseCardActionSpace) or any(
        isinstance(a, ChooseCardAction) for a in actions
    )


def _find(predicate, seeds=range(60)):
    """First live decision satisfying predicate(state, actions); fail loudly if none."""
    gen = walk(seeds)
    for state, actions in gen:
        if not _is_choice(actions) and predicate(state, actions):
            return gen, state, actions
    pytest.fail("no decision in the walk satisfied the predicate")


def _player(state, actions):
    return state.player1 if actions[0].playerId == PlayerId.PLAYER1 else state.player2


# --- round trip ------------------------------------------------------------------


def test_round_trip_over_forty_seeded_games():
    kinds: set[str] = set()
    multi_target_attach = 0
    checked = 0
    for state, actions in walk(range(40)):
        if _is_choice(actions):
            continue
        player = actions[0].playerId
        intents = [intent_of(a, state) for a in actions]
        attach_targets: dict[str, set] = {}
        for action, intent in zip(actions, intents):
            assert resolve(intent, actions, state, player=player) is action, intent
            assert sum(1 for other in intents if other == intent) == 1, intent
            kinds.add(intent.kind)
            checked += 1
            if intent.kind == "attach":
                attach_targets.setdefault(intent.source, set()).add(intent.target)
        multi_target_attach += sum(len(t) > 1 for t in attach_targets.values())
    assert checked > 1000
    assert {"play", "attach", "attack", "pass", "evolve"} <= kinds
    assert multi_target_attach > 0  # the attach target test must be exercised


# --- fabricated intents ------------------------------------------------------------


def test_attack_name_not_printed_resolves_none():
    gen, state, actions = _find(
        lambda s, a: any(x.actionType == ActionType.ATTACK_ACTION for x in a)
    )
    gen.close()
    player = actions[0].playerId
    real = next(x for x in actions if x.actionType == ActionType.ATTACK_ACTION)
    ok = resolve(Intent("attack", "A1", name=real.attack.name), actions, state, player=player)
    assert ok is real
    fake = Intent("attack", "A1", name="Not A Printed Attack")
    assert resolve(fake, actions, state, player=player) is None


def test_evolve_onto_non_evolve_from_target_resolves_none():
    gen, state, actions = _find(
        lambda s, a: any(x.actionType == ActionType.EVOLVE_POKEMON_ACTION for x in a)
    )
    gen.close()
    me = _player(state, actions)
    player = actions[0].playerId
    evo = next(x for x in actions if x.actionType == ActionType.EVOLVE_POKEMON_ACTION)
    legal_targets = {
        id(x.target)
        for x in actions
        if x.actionType == ActionType.EVOLVE_POKEMON_ACTION and x.source is evo.source
    }
    source_ref = intent_of(evo, state).source
    refs = [(f"A{i + 1}", p) for i, p in enumerate(me.active)]
    refs += [(f"B{i + 1}", p) for i, p in enumerate(me.bench)]
    illegal = [ref for ref, p in refs if id(p) not in legal_targets]
    assert illegal, "need an in-play Pokemon that is not a legal evolve target"
    assert resolve(Intent("evolve", source_ref, illegal[0]), actions, state, player=player) is None


def test_attach_to_empty_bench_slot_resolves_none():
    gen, state, actions = _find(
        lambda s, a: any(x.actionType == ActionType.ATTACH_ENERGY_ACTION for x in a)
        and len(_player(s, a).bench) < 5
    )
    gen.close()
    me = _player(state, actions)
    player = actions[0].playerId
    real = next(x for x in actions if x.actionType == ActionType.ATTACH_ENERGY_ACTION)
    src = intent_of(real, state).source
    empty = f"B{len(me.bench) + 1}"
    assert resolve(Intent("attach", src, empty), actions, state, player=player) is None


def test_out_of_range_and_empty_legal_resolve_none():
    gen, state, actions = _find(lambda s, a: True)
    gen.close()
    player = actions[0].playerId
    assert resolve(Intent("play", "H99"), actions, state, player=player) is None
    assert resolve(Intent("pass", None), [], state, player=player) is None


# --- the menu never reads the legal set ---------------------------------------------


def test_menu_for_signature_has_no_legal_parameter():
    names = set(inspect.signature(menu_for).parameters)
    assert not {"actions", "legal", "legal_actions"} & names


def test_menu_for_never_calls_the_engine_legal_generator(monkeypatch):
    from ptcg.core.player import Player

    gen, state, actions = _find(
        lambda s, a: len(_player(s, a).hand) >= 3 and _player(s, a).active
    )
    gen.close()
    me = _player(state, actions)
    pid = actions[0].playerId

    def boom(*args, **kwargs):
        raise AssertionError("menu_for consulted the legal action list")

    monkeypatch.setattr(Player, "get_actions", boom)
    for i in range(len(me.hand)):
        assert menu_for(f"H{i + 1}", state, player=pid)
    assert menu_for("A1", state, player=pid)


def test_menu_entries_follow_printed_card_type():
    from ptcg.core.card import EnergyCard, PokemonCard, TrainerCard
    from ptcg.core.enums import Stage, TrainerType

    pid = PlayerId.PLAYER1
    seen: dict[str, set[str]] = {}
    want = {"basic", "evo", "energy", "item_or_supporter", "active"}
    for state, actions in walk(range(60), 400):
        if _is_choice(actions) or actions[0].playerId != pid:
            continue
        me = state.player1
        for i, card in enumerate(me.hand):
            k = {e.kind for e in menu_for(f"H{i + 1}", state, player=pid)}
            assert "pass" in k
            if isinstance(card, PokemonCard) and card.stage == Stage.BASIC:
                assert {"play", "active"} <= k and not {"evolve", "attach"} & k
                seen["basic"] = k
            elif isinstance(card, PokemonCard):
                assert "evolve" in k and not {"play", "attach"} & k
                seen["evo"] = k
            elif isinstance(card, EnergyCard):
                assert "attach" in k and "play" not in k
                seen["energy"] = k
            elif isinstance(card, TrainerCard) and card.trainerType == TrainerType.TOOL:
                assert "tool" in k
            elif isinstance(card, TrainerCard) and card.trainerType == TrainerType.STADIUM:
                assert "stadium" in k
            elif isinstance(card, TrainerCard):
                assert "play" in k
                seen["item_or_supporter"] = k
        if me.active:
            entries = menu_for("A1", state, player=pid)
            attacks = [e.name for e in entries if e.kind == "attack"]
            assert attacks == [a.name for a in me.active[0].attacks]
            assert any(e.kind == "retreat" for e in entries)
            seen["active"] = {e.kind for e in entries}
        if want <= set(seen):
            break
    assert want <= set(seen)


def test_attach_and_evolve_menu_targets_are_every_own_in_play_pokemon():
    from ptcg.core.card import EnergyCard

    pid = PlayerId.PLAYER1
    for state, actions in walk(range(60), 400):
        if _is_choice(actions) or actions[0].playerId != pid:
            continue
        me = state.player1
        if not me.active or not me.bench:
            continue
        every = {f"A{i + 1}" for i in range(len(me.active))}
        every |= {f"B{i + 1}" for i in range(len(me.bench))}
        for i, card in enumerate(me.hand):
            if isinstance(card, EnergyCard):
                entry = next(
                    e for e in menu_for(f"H{i + 1}", state, player=pid) if e.kind == "attach"
                )
                assert set(entry.targets) == every
                return
    pytest.fail("never saw an Energy in hand with a bench")


# --- grammar -------------------------------------------------------------------------

GRAMMAR = [
    ("play H3", Intent("play", "H3")),
    ("active H3", Intent("active", "H3")),
    ("attach H5 B2", Intent("attach", "H5", "B2")),
    ("evolve H4 B1", Intent("evolve", "H4", "B1")),
    ("ability B1", Intent("ability", "B1")),
    ("ability A1 Jewel Seeker", Intent("ability", "A1", name="Jewel Seeker")),
    ("attack Phantom Dive", Intent("attack", "A1", name="Phantom Dive")),
    ("retreat", Intent("retreat", "A1")),
    ("pass", Intent("pass", None)),
    ("stadium H2", Intent("stadium", "H2")),
    ("stadium S1", Intent("stadium", "S1")),
    ("tool H2 B1", Intent("tool", "H2", "B1")),
]


@pytest.mark.parametrize("text,expected", GRAMMAR)
def test_text_grammar_parses_and_formats_round_trip(text, expected):
    parsed = Intent.parse(text)
    assert parsed == expected
    assert Intent.parse(parsed.format()) == parsed
    assert parsed.format().lower() == text.lower()


@pytest.mark.parametrize("text,expected", GRAMMAR)
def test_dict_form_round_trips(text, expected):
    assert Intent.from_dict(expected.to_dict()) == expected


@pytest.mark.parametrize(
    "bad",
    ["", "dance H1", "play", "play H0", "play X3", "play H3 B1", "attach H5", "attach H5 Z1",
     "evolve H4", "attack", "pass now", "retreat A1 extra", "tool H2"],
)
def test_text_parser_is_strict(bad):
    with pytest.raises(IntentError):
        Intent.parse(bad)


@pytest.mark.parametrize(
    "bad",
    [None, "play H3", [], {}, {"kind": "play"}, {"kind": "play", "source": "H3", "extra": 1},
     {"kind": "attach", "source": "H3"}, {"kind": "attack", "source": "A1"},
     {"kind": "nope", "source": "H3"}, {"kind": "play", "source": 3},
     {"kind": "play", "source": "H3", "target": "B1"}, {"kind": "pass", "source": "H3"}],
)
def test_dict_parser_is_strict(bad):
    with pytest.raises(IntentError):
        Intent.from_dict(bad)


def test_intent_error_is_a_value_error():
    assert issubclass(IntentError, ValueError)


# --- targeted live-engine round trips for kinds the random walk never reaches -------------


def _round_trip_all(state, actions, player=PlayerId.PLAYER1):
    intents = [intent_of(a, state) for a in actions]
    for action, intent in zip(actions, intents):
        assert resolve(intent, actions, state, player=player) is action, intent
        assert Intent.parse(intent.format()) == intent, intent
        assert sum(1 for other in intents if other == intent) == 1, intent
    return intents


def _builder():
    from tests.helpers.cards import make_card
    from tests.helpers.state_builder import PlayerZones, make_state

    return make_card, PlayerZones, make_state


def test_ability_round_trip_drakloak_and_munkidori():
    from ptcg.core.enums import CardType

    make_card, Zones, make_state = _builder()
    drakloak = make_card("TWM-129")
    munkidori = make_card("TWM-095")
    dark = make_card("SVE-007")
    munkidori.energy = [CardType.DARK]
    munkidori.attachment = [dark]
    state = make_state(
        Zones(active=[make_card("TWM-128")], bench=[drakloak, munkidori], left=[make_card("TWM-128")]),
        Zones(active=[make_card("TWM-128")]),
    )
    actions = state.player1.get_actions(state)
    intents = _round_trip_all(state, actions)
    abilities = {(i.source, i.name) for i in intents if i.kind == "ability"}
    assert ("B1", drakloak.ability[0].name) in abilities
    assert ("B2", munkidori.ability[0].name) in abilities
    typed = {i.format() for i in intents if i.kind == "ability"}
    assert f"ability B1 {drakloak.ability[0].name}" in typed
    # Name-less typed form resolves while the Pokemon has a single ability.
    bare = Intent.parse("ability B1")
    assert resolve(bare, actions, state).ability.name == drakloak.ability[0].name
    # A name the card does not print never resolves.
    assert resolve(Intent("ability", "B1", name="Nope"), actions, state) is None


def test_retreat_round_trip_dreepy_with_energy_and_budew_at_zero_cost():
    from ptcg.core.enums import CardType

    make_card, Zones, make_state = _builder()
    dreepy = make_card("TWM-128")
    dreepy.energy = [CardType.FIRE]
    state = make_state(Zones(active=[dreepy], bench=[make_card("TWM-128")]), Zones(active=[make_card("TWM-128")]))
    actions = state.player1.get_actions(state)
    intents = _round_trip_all(state, actions)
    assert Intent("retreat", "A1") in intents
    assert Intent.parse("retreat") == Intent("retreat", "A1")
    assert resolve(Intent.parse("retreat"), actions, state) is next(
        a for a in actions if a.actionType == ActionType.RETREAT_ACTION
    )

    budew = make_card("ASC-016")
    state = make_state(Zones(active=[budew], bench=[make_card("TWM-128")]), Zones(active=[make_card("TWM-128")]))
    actions = state.player1.get_actions(state)
    assert Intent("retreat", "A1") in _round_trip_all(state, actions)

    # Unaffordable retreat (no energy on Dreepy) is not offered, so the intent resolves None.
    bare = make_state(Zones(active=[make_card("TWM-128")], bench=[make_card("TWM-128")]), Zones())
    assert resolve(Intent("retreat", "A1"), bare.player1.get_actions(bare), bare) is None


def test_stadium_round_trip_play_from_hand_and_use_discard_forms():
    from ptcg.core.action import DiscardStadiumAction, UseStadiumAction

    make_card, Zones, make_state = _builder()
    ruins = make_card("MEG-127")
    state = make_state(Zones(hand=[ruins], active=[make_card("TWM-128")]), Zones(active=[make_card("TWM-128")]))
    actions = state.player1.get_actions(state)
    intents = _round_trip_all(state, actions)
    assert Intent("stadium", "H1") in intents
    assert Intent.parse("stadium H1") in intents

    # Risky Ruins offers no use/discard action once in play, so exercise S1 with
    # synthetic offered actions on a board that holds the stadium.
    in_play = make_card("MEG-127")
    state = make_state(Zones(active=[make_card("TWM-128")]), Zones(active=[make_card("TWM-128")]))
    state.stadium.append(in_play)
    offered = [UseStadiumAction(PlayerId.PLAYER1, in_play), DiscardStadiumAction(PlayerId.PLAYER1, in_play)]
    assert [i.format() for i in _round_trip_all(state, offered)] == ["stadium S1", "discard S1"]
    assert resolve(Intent("stadium", "S2"), offered, state) is None
    assert [e.kind for e in menu_for("S1", state)] == ["stadium", "discard", "pass"]


def test_tool_round_trip_rigid_band():
    make_card, Zones, make_state = _builder()
    band = make_card("MEW-165")
    state = make_state(
        Zones(hand=[band], active=[make_card("MEW-017")], bench=[make_card("MEW-017")]),
        Zones(active=[make_card("TWM-128")]),
    )
    actions = state.player1.get_actions(state)
    intents = _round_trip_all(state, actions)
    assert Intent("tool", "H1", "A1") in intents and Intent("tool", "H1", "B1") in intents
    assert Intent.parse("tool H1 B1") in intents
    assert Intent("tool", "H1", "B2") not in intents
    assert resolve(Intent("tool", "H1", "B2"), actions, state) is None
    assert [e.kind for e in menu_for("H1", state)] == ["tool", "pass"]
