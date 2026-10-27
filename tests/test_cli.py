from __future__ import annotations

import pytest

from ptcg import cli
from ptcg.console.model import SessionResult


def test_play_parser_uses_confirmed_defaults():
    args = cli.build_play_parser().parse_args([])

    assert args.deck is None
    assert args.opponent_deck is None
    assert args.opponent_policy == "random"
    assert args.seed == 0
    assert args.max_steps == 1000


def test_main_dispatches_play_subcommand(monkeypatch):
    captured = {}

    def fake_run_interactive(config, terminal):
        captured["config"] = config
        captured["terminal"] = terminal
        return SessionResult(status="finished", steps=3, reward=1.0, winner="player1")

    monkeypatch.setattr("ptcg.console.run_interactive", fake_run_interactive)

    exit_code = cli.main(
        [
            "play",
            "--deck",
            "charizard_ex",
            "--opponent-deck",
            "miraidon_ex",
            "--opponent-policy",
            "first",
            "--seed",
            "7",
        ]
    )

    assert exit_code == 0
    assert captured["config"].deck == "charizard_ex"
    assert captured["config"].opponent_deck == "miraidon_ex"
    assert captured["config"].opponent_policy == "first"
    assert captured["config"].seed == 7


def test_main_keeps_legacy_simulation_dispatch(monkeypatch):
    captured = {}

    def fake_run(args):
        captured["args"] = args
        return 17

    monkeypatch.setattr(cli, "run", fake_run)

    exit_code = cli.main(["--deck1", "charizard_ex", "--policy", "first", "--quiet"])

    assert exit_code == 17
    assert captured["args"].deck1 == "charizard_ex"
    assert captured["args"].policy == "first"
    assert captured["args"].quiet is True


def test_play_parser_rejects_a_non_positive_step_limit():
    with pytest.raises(SystemExit):
        cli.build_play_parser().parse_args(["--max-steps", "0"])


def test_main_passes_goldfish_flags_into_play_config(monkeypatch):
    captured = {}

    def fake_run_interactive(config, terminal):
        captured["config"] = config
        return SessionResult(status="finished", steps=1, reward=0.0)

    monkeypatch.setattr("ptcg.console.run_interactive", fake_run_interactive)

    cli.main(
        ["play", "--opponent-policy", "pass", "--seat", "flip", "--opponent-choice", "random", "--item-lock-turns", "2,4",
         "--goldfish-log", "g.csv"]
    )

    config = captured["config"]
    assert config.opponent_policy == "pass"
    assert (config.seat, config.opponent_choice) == ("flip", "random")
    assert config.item_lock_turns == (2, 4)
    assert config.goldfish_log == "g.csv"


def test_play_parser_parses_marks_and_sets_as_code_sets():
    args = cli.build_play_parser().parse_args(["--marks", "H,I,J", "--sets", "TWM, MEG"])

    assert args.marks == frozenset({"H", "I", "J"})
    assert args.sets == frozenset({"TWM", "MEG"})
    assert cli.build_play_parser().parse_args([]).marks is None


def test_check_deck_legality_passes_29678_under_standard_marks(capsys):
    assert cli.check_deck_legality("dragapult_29678", frozenset({"standard"}), None) == 0
    out = capsys.readouterr().out
    assert "legal via MEG-114" in out
    assert "illegal:" not in out


def test_check_deck_legality_rejects_29678_under_a_set_filter(capsys):
    assert cli.check_deck_legality("dragapult_29678", None, frozenset({"TWM"})) == 2
    out = capsys.readouterr().out
    assert "illegal: ASC-016" in out
    assert "Deck rejected" in out


def test_main_play_stops_before_the_session_when_the_deck_is_illegal(monkeypatch):
    called = []
    monkeypatch.setattr("ptcg.console.run_interactive", lambda config, terminal: called.append(1))

    exit_code = cli.main(["play", "--deck", "dragapult_29678", "--sets", "TWM"])

    assert exit_code == 2
    assert called == []

