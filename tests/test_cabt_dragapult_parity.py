"""Legal-action parity rules found by diffing ptcg against the CABT referee (cg.dll) on
1081 Dragapult-mirror main-phase positions (tcg-agent scratch/crosswalk_dragapult_receipt.md,
2026-10-30). Each test pins one rule; each was a non-zero row in that diff."""

from __future__ import annotations

from ptcg.core.action import (
    AttackAction,
    PutStadiumAction,
    UseAbilityAction,
    UseItemAction,
    UseSupporterAction,
)
from ptcg.core.enums import CardType, PlayerId
from tests.helpers.cards import make_card
from tests.helpers.state_builder import PlayerZones, make_state


def _of(actions, cls):
    return [a for a in actions if isinstance(a, cls)]


def _dreepy():
    card = make_card("TWM-128")
    card.firstTurnPlayed = False
    return card


def test_same_name_stadium_cannot_be_played_over_itself():
    ruins = make_card("MEG-127")
    state = make_state(
        PlayerZones(active=[_dreepy()], hand=[ruins]),
        PlayerZones(active=[_dreepy()]),
    )
    assert len(_of(state.player1.get_actions(state), PutStadiumAction)) == 1
    state.stadium = [make_card("MEG-127")]
    assert _of(state.player1.get_actions(state), PutStadiumAction) == []


def test_crushing_hammer_needs_an_opposing_pokemon_with_energy():
    hammer = make_card("POR-071")
    target = _dreepy()
    state = make_state(
        PlayerZones(active=[_dreepy()], hand=[hammer]),
        PlayerZones(active=[target]),
    )
    assert _of(state.player1.get_actions(state), UseItemAction) == []
    energy = make_card("SVE-002")
    target.attachment.append(energy)
    target.energy.extend(energy.provides)
    assert len(_of(state.player1.get_actions(state), UseItemAction)) == 1


def test_recon_directive_is_once_per_pokemon_not_per_name():
    first, second = make_card("TWM-129"), make_card("TWM-129")
    for card in (first, second):
        card.firstTurnPlayed = False
    state = make_state(
        PlayerZones(active=[_dreepy()], bench=[first, second], left=[_dreepy(), _dreepy()]),
        PlayerZones(active=[_dreepy()]),
    )
    first.abilityUsed = True
    state.player1.onceUsedTurn[first.ability[0].name] = True  # what the old engine recorded
    sources = [a.source for a in _of(state.player1.get_actions(state), UseAbilityAction)]
    assert sources == [second]


def test_adrena_brain_needs_a_damaged_own_pokemon():
    munkidori = make_card("TWM-095")
    munkidori.firstTurnPlayed = False
    dark = make_card("SVE-007")
    munkidori.attachment = [dark]
    munkidori.energy = list(dark.provides)
    mine = _dreepy()
    state = make_state(
        PlayerZones(active=[mine], bench=[munkidori]),
        PlayerZones(active=[_dreepy()]),
    )
    assert _of(state.player1.get_actions(state), UseAbilityAction) == []
    mine.hp -= 10
    assert len(_of(state.player1.get_actions(state), UseAbilityAction)) == 1


def test_adrena_brain_is_once_per_pokemon_not_per_name():
    pair = []
    for _ in range(2):
        card = make_card("TWM-095")
        card.firstTurnPlayed = False
        dark = make_card("SVE-007")
        card.attachment = [dark]
        card.energy = list(dark.provides)
        pair.append(card)
    mine = _dreepy()
    mine.hp -= 10
    state = make_state(
        PlayerZones(active=[mine], bench=pair),
        PlayerZones(active=[_dreepy()]),
    )
    pair[0].abilityUsed = True
    state.player1.onceUsedTurn[pair[0].ability[0].name] = True  # what the old engine recorded
    sources = [a.source for a in _of(state.player1.get_actions(state), UseAbilityAction)]
    assert sources == [pair[1]]


def test_player_going_first_cannot_play_a_supporter_on_turn_one():
    state = make_state(
        PlayerZones(active=[_dreepy()], hand=[make_card("ASC-192")]),
        PlayerZones(active=[_dreepy()]),
    )
    me = state.player1
    me.firstTurn, me.wentFirst = True, True
    assert _of(me.get_actions(state), UseSupporterAction) == []
    me.wentFirst = False  # going second: a Supporter is legal on your first turn
    assert len(_of(me.get_actions(state), UseSupporterAction)) == 1
    me.firstTurn, me.wentFirst = False, True
    assert len(_of(me.get_actions(state), UseSupporterAction)) == 1


def test_dunsparce_dig_costs_two_colorless():
    dunsparce = make_card("TEF-128")
    dunsparce.firstTurnPlayed = False
    energy = make_card("SVE-002")
    dunsparce.attachment = [energy]
    dunsparce.energy = list(energy.provides)
    state = make_state(
        PlayerZones(active=[dunsparce]),
        PlayerZones(active=[_dreepy()]),
        turn=PlayerId.PLAYER1,
    )
    state.player1.firstTurn = False
    names = sorted(a.attack.name for a in _of(state.player1.get_actions(state), AttackAction))
    assert names == ["Gnaw"]
    dunsparce.energy.append(CardType.FIRE)
    names = sorted(a.attack.name for a in _of(state.player1.get_actions(state), AttackAction))
    assert names == ["Dig", "Gnaw"]
