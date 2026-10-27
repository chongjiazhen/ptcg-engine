from __future__ import annotations

import pytest

from ptcg import PokemonTCG
from ptcg.core.action import AttackAction
from ptcg.core.enums import CardType, PlayerId

# Starters produced by the coin flip at HEAD d113635 with the default decks,
# pinned so a change to the None path is caught.
COIN_STARTER = {0: PlayerId.PLAYER2, 1: PlayerId.PLAYER1}


def _play_setup(env: PokemonTCG) -> None:
    """Reset and answer both opening-Active prompts through the public API."""
    _obs, _reward, _done, info = env.reset()
    for _ in range(2):
        _obs, _reward, _done, info = env.step(info["raw_available_actions"][0])


def _signature(env: PokemonTCG) -> tuple:
    state = env.gamestate
    return (
        tuple(card.id for card in state.player1.hand),
        tuple(card.id for card in state.player1.prize),
        tuple(card.id for card in state.player1.left),
        tuple(card.id for card in state.player2.hand),
        tuple(card.id for card in state.player2.prize),
        tuple(card.id for card in state.player2.left),
    )


def _env(seed: int, first_player: PlayerId | None = None) -> PokemonTCG:
    return PokemonTCG(seed=seed, record_game=False, first_player=first_player)


@pytest.mark.parametrize("seed", [0, 1])
@pytest.mark.parametrize("starter", [PlayerId.PLAYER1, PlayerId.PLAYER2])
def test_override_decides_who_takes_turn_one(seed, starter):
    env = _env(seed, first_player=starter)

    _play_setup(env)

    assert env.gamestate.turn == starter
    assert env.first_player == starter


def test_override_blocks_supporter_for_the_chosen_starter_only():
    env = _env(0, first_player=PlayerId.PLAYER1)

    _play_setup(env)

    assert env.gamestate.player1.supporterPlayedTurn is True
    assert env.gamestate.player2.supporterPlayedTurn is False


def test_override_is_known_immediately_after_reset():
    env = _env(0, first_player=PlayerId.PLAYER1)

    env.reset()

    assert env.first_player == PlayerId.PLAYER1


@pytest.mark.parametrize("seed", [0, 1])
def test_none_keeps_the_coin_flip_result(seed):
    env = _env(seed)

    _play_setup(env)

    assert env.gamestate.turn == COIN_STARTER[seed]
    assert env.first_player == COIN_STARTER[seed]


def test_none_and_default_construction_agree():
    explicit = _env(0, first_player=None)
    default = PokemonTCG(seed=0, record_game=False)

    _play_setup(explicit)
    _play_setup(default)

    assert explicit.gamestate.turn == default.gamestate.turn
    assert _signature(explicit) == _signature(default)


@pytest.mark.parametrize("starter", [PlayerId.PLAYER1, PlayerId.PLAYER2])
def test_override_does_not_change_shuffles_or_opening_hands(starter):
    plain = _env(0)
    forced = _env(0, first_player=starter)

    _play_setup(plain)
    _play_setup(forced)

    # The starter's turn-1 draw moves one card from deck to hand, so compare
    # hand + deck together; prizes must match exactly.
    def zones(env):
        p1, p2 = env.gamestate.player1, env.gamestate.player2
        return (
            sorted(c.id for c in p1.hand + p1.left),
            tuple(c.id for c in p1.prize),
            sorted(c.id for c in p2.hand + p2.left),
            tuple(c.id for c in p2.prize),
        )

    assert zones(forced) == zones(plain)


def test_override_skips_the_start_stage_coin_flip():
    forced = _env(0, first_player=PlayerId.PLAYER1)

    _play_setup(forced)

    assert not any("Coin flip" in event for event in forced.gamestate.auto_events)


def test_override_survives_a_second_reset():
    env = _env(0, first_player=PlayerId.PLAYER2)
    _play_setup(env)

    _play_setup(env)

    assert env.gamestate.turn == PlayerId.PLAYER2


@pytest.mark.parametrize("seed,starter", [(0, PlayerId.PLAYER1), (1, PlayerId.PLAYER2), (0, None)])
def test_starter_draws_on_turn_one_and_the_other_player_does_not(seed, starter):
    env = _env(seed, first_player=starter)

    _play_setup(env)

    state = env.gamestate
    first = state.player1 if state.turn == PlayerId.PLAYER1 else state.player2
    second = state.player2 if first is state.player1 else state.player1
    assert first.mulligan_count == 0 and second.mulligan_count == 0
    # 7-card opening hand minus the chosen Active, plus the starter's turn-1 draw.
    assert len(second.hand) == 6
    assert len(first.hand) == 7
    assert len(first.left) == len(second.left) - 1


def test_starter_still_cannot_attack_or_play_supporter_on_turn_one():
    env = _env(0, first_player=PlayerId.PLAYER1)
    _play_setup(env)
    state = env.gamestate
    starter = state.player1
    starter.active[0].energy = [CardType.FIRE] * 4

    assert starter.firstTurn is True
    assert starter.supporterPlayedTurn is True
    assert [a for a in starter.get_actions(state) if isinstance(a, AttackAction)] == []

    # Control: with the first-turn flag cleared the same Active can attack.
    starter.firstTurn = False
    assert [a for a in starter.get_actions(state) if isinstance(a, AttackAction)] != []
