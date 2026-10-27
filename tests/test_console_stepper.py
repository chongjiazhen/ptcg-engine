"""Stepper: the per-decision loop shared by the terminal console and the HTTP driver."""

from __future__ import annotations

import random

import pytest

from ptcg.console import goldfish
from ptcg.console.model import PlayConfig
from ptcg.console.stepper import NeedSeatChoice, Stepper
from ptcg.core.enums import PlayerId

DECK = "dragapult_29678"


def _seed_with_coin(side: str) -> int:
    return next(s for s in range(200) if goldfish.flip(random.Random(s)) == side)


def _config(**kwargs) -> PlayConfig:
    base = dict(deck=DECK, opponent_deck=DECK, opponent_policy="pass", seed=0, seat="first")
    base.update(kwargs)
    return PlayConfig(**base)


def _hand(stepper: Stepper) -> list[str]:
    return [card.name for card in stepper.frame.human.hand]


def test_first_decision_is_setup_prompt_for_player1():
    stepper = Stepper(_config())
    assert not stepper.done
    assert stepper.first_player == PlayerId.PLAYER1
    assert stepper.frame.prompt is not None
    assert "basic Pokemon" in stepper.frame.prompt.tips
    assert stepper.actions[0].playerId == PlayerId.PLAYER1


def test_submit_choice_advances_opponent_without_a_human_call():
    stepper = Stepper(_config())
    before = stepper.steps
    stepper.submit_choice([0])
    assert stepper.steps - before > 1  # the pick plus at least one opponent step
    assert stepper.done or stepper.actions[0].playerId == PlayerId.PLAYER1


def test_submit_rejects_an_action_that_was_not_offered():
    stepper = Stepper(_config())
    with pytest.raises(ValueError):
        stepper.submit_choice([999])


def test_choice_seat_raises_when_human_wins_the_flip():
    with pytest.raises(NeedSeatChoice):
        Stepper(_config(seat="choice", seed=_seed_with_coin("heads")))


def test_choice_seat_with_pick_second_gives_player2_first():
    seed = _seed_with_coin("heads")
    stepper = Stepper(_config(seat="choice", seed=seed), seat_pick="second")
    assert stepper.first_player == PlayerId.PLAYER2


def test_choice_seat_with_pick_first_gives_player1_first():
    seed = _seed_with_coin("heads")
    stepper = Stepper(_config(seat="choice", seed=seed), seat_pick="first")
    assert stepper.first_player == PlayerId.PLAYER1


def test_choice_seat_tails_never_asks():
    seed = _seed_with_coin("tails")
    stepper = Stepper(_config(seat="choice", seed=seed, opponent_choice="first"))
    assert stepper.first_player == PlayerId.PLAYER2


def test_same_seed_same_opening_hand_with_and_without_rerun():
    seed = _seed_with_coin("heads")
    with pytest.raises(NeedSeatChoice):
        Stepper(_config(seat="choice", seed=seed))
    rerun = Stepper(_config(seat="choice", seed=seed), seat_pick="first")
    direct = Stepper(_config(seat="first", seed=seed))
    assert _hand(rerun) == _hand(direct) and _hand(direct)


def test_finish_writes_one_csv_row(tmp_path):
    log = tmp_path / "goldfish.csv"
    stepper = Stepper(_config(goldfish_log=str(log)))
    stepper.finish("note-x")
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and lines[1].endswith("note-x")


def test_hint_counts_once_per_decision():
    stepper = Stepper(_config())
    first = stepper.hint()
    assert stepper.hint() is first and stepper.hints == 1
    stepper.submit_choice([0])
    stepper.hint()
    assert stepper.hints == 2
