"""First-turn rules: only the player who goes first is barred from attacking on
their first turn. Neither player may evolve on their own first turn."""

from __future__ import annotations

import pytest

from ptcg import PokemonTCG
from ptcg.core.action import AttackAction, EvolvePokemonAction
from ptcg.core.enums import CardPosition, CardType, PlayerId, PokemonPosition
from ptcg.utils.utils import next_turn
from tests.helpers.cards import make_card


def _started(first: PlayerId) -> PokemonTCG:
    env = PokemonTCG(seed=0, record_game=False, first_player=first)
    _obs, _reward, _done, info = env.reset()
    for _ in range(2):
        _obs, _reward, _done, info = env.step(info["raw_available_actions"][0])
    assert env.gamestate.turn == first
    return env


def _arm(player) -> None:
    player.active[0].energy = [CardType.FIRE] * 4


def _attacks(player, state):
    return [a for a in player.get_actions(state) if isinstance(a, AttackAction)]


def _evolutions(player, state):
    return [a for a in player.get_actions(state) if isinstance(a, EvolvePokemonAction)]


def _stage_evolution(player) -> None:
    dreepy = make_card("TWM-128")
    dreepy.firstTurnPlayed = False
    player.bench = [dreepy]
    dreepy.position = PokemonPosition.BENCH
    dreepy.cardPosition = CardPosition.BENCH
    dreepy.index = 1
    player.hand.append(make_card("TWM-129"))


@pytest.mark.parametrize("first", [PlayerId.PLAYER1, PlayerId.PLAYER2])
def test_second_player_can_attack_on_their_first_turn(first):
    env = _started(first)
    state = env.gamestate
    second = state.player2 if first == PlayerId.PLAYER1 else state.player1
    _arm(state.player1)
    _arm(state.player2)

    next_turn(state)  # the starter passes

    assert state.turn == second.id
    assert second.firstTurn is True
    assert len(_attacks(second, state)) > 0


@pytest.mark.parametrize("first", [PlayerId.PLAYER1, PlayerId.PLAYER2])
def test_starter_cannot_attack_on_their_first_turn(first):
    env = _started(first)
    state = env.gamestate
    starter = state.player1 if first == PlayerId.PLAYER1 else state.player2
    _arm(starter)

    assert starter.firstTurn is True
    assert _attacks(starter, state) == []


def test_starter_can_attack_on_their_second_turn():
    env = _started(PlayerId.PLAYER1)
    state = env.gamestate
    _arm(state.player1)
    next_turn(state)  # P1 passes
    next_turn(state)  # P2 passes

    assert state.turn == PlayerId.PLAYER1
    assert state.player1.firstTurn is False
    assert len(_attacks(state.player1, state)) > 0


@pytest.mark.parametrize("first", [PlayerId.PLAYER1, PlayerId.PLAYER2])
def test_neither_player_can_evolve_on_their_first_turn(first):
    env = _started(first)
    state = env.gamestate
    starter = state.player1 if first == PlayerId.PLAYER1 else state.player2
    second = state.player2 if starter is state.player1 else state.player1
    _stage_evolution(starter)
    _stage_evolution(second)

    assert _evolutions(starter, state) == []

    next_turn(state)  # the starter passes

    assert state.turn == second.id
    assert second.firstTurn is True
    assert _evolutions(second, state) == []

    # Control: the same board can evolve once the first-turn flag is gone.
    second.firstTurn = False
    assert len(_evolutions(second, state)) > 0
