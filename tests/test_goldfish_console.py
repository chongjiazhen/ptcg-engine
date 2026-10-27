"""Goldfish console features: pass policy, item lock, flip/roll, CSV row."""

from __future__ import annotations

import csv
import random

import pytest
from types import SimpleNamespace

from ptcg import cli
from ptcg.console import goldfish, session
from ptcg.console.model import PlayConfig
from ptcg.core.action import PassTurn, UseItemAction
from ptcg.core.enums import ActionType, PlayerId

CSV_HEADER = (
    "date,hand,var,seat,active,mulligans,supporters_in_7,t1_two_dreepy_or_dreepy_budew,"
    "t1_search,t2_drakloak,t2_supporter,t3_attacker_rp,lock_variation,decide,note"
).split(",")


def _act(action_type: ActionType):
    return SimpleNamespace(playerId=PlayerId.PLAYER2, actionType=action_type)


def test_pass_policy_picks_pass_turn_when_legal():
    actions = [_act(ActionType.ATTACH_ENERGY_ACTION), PassTurn(PlayerId.PLAYER2, object())]
    chosen = session._select_policy_action(actions, "pass", random.Random(0))
    assert chosen is actions[1]


def test_pass_policy_falls_back_to_first_action_without_pass():
    actions = [_act(ActionType.PLAY_POKEMON_ACTION), _act(ActionType.ATTACH_ENERGY_ACTION)]
    assert session._select_policy_action(actions, "pass", random.Random(0)) is actions[0]


def test_cli_select_action_supports_pass_policy():
    actions = [_act(ActionType.ATTACH_ENERGY_ACTION), PassTurn(PlayerId.PLAYER2, object())]
    assert cli.select_action(actions, "pass", random.Random(0)) is actions[1]


def test_item_lock_hides_items_only_on_listed_human_turns():
    item = _act(ActionType.USE_ITEM_ACTION)
    other = _act(ActionType.ATTACH_ENERGY_ACTION)
    actions = [item, other]

    kept, note = goldfish.filter_item_locked(actions, human_turn=2, lock_turns=(2, 4))
    assert kept == [other]
    assert note == "Items locked this turn (simulated Budew)"

    kept, note = goldfish.filter_item_locked(actions, human_turn=3, lock_turns=(2, 4))
    assert kept == actions and note is None


def test_flip_returns_heads_or_tails_from_seeded_rng():
    results = {goldfish.flip(random.Random(seed)) for seed in range(20)}
    assert results == {"heads", "tails"}
    assert goldfish.flip(random.Random(5)) == goldfish.flip(random.Random(5))


def test_roll_defaults_to_d6_and_honours_sides():
    assert all(1 <= goldfish.roll(random.Random(s)) <= 6 for s in range(50))
    assert all(1 <= goldfish.roll(random.Random(s), 20) <= 20 for s in range(50))
    assert goldfish.roll(random.Random(9), 1) == 1


def test_csv_columns_are_the_goldfish_header_in_order():
    assert list(goldfish.CSV_COLUMNS) == CSV_HEADER


def test_append_row_writes_fifteen_columns_and_increments_hand(tmp_path):
    path = tmp_path / "out.csv"
    path.write_text(",".join(CSV_HEADER) + "\n2026-10-27,6,J,F,Dreepy,0,1,0,none,1,1,0,0,D,x\n")
    record = goldfish.GoldfishRecord(
        seat="S", active="Budew", mulligans=1, supporters_in_7=2,
        t1_two_dreepy_or_dreepy_budew=1, t1_search="Pad+Poffin", t2_drakloak=0,
        t2_supporter=1, t3_attacker_rp=None, lock_variation=1, note="n, with comma",
    )
    goldfish.append_row(str(path), record, today="2026-10-28")

    rows = list(csv.reader(path.read_text().splitlines()))
    assert rows[-1] == [
        "2026-10-28", "7", "J", "S", "Budew", "1", "2", "1", "Pad+Poffin",
        "0", "1", "", "1", "", "n, with comma",
    ]
    assert len(rows[-1]) == 15


def test_append_row_starts_at_hand_one_for_a_new_file(tmp_path):
    path = tmp_path / "new.csv"
    goldfish.append_row(str(path), goldfish.GoldfishRecord(), today="2026-10-28")
    rows = list(csv.reader(path.read_text().splitlines()))
    assert rows[0] == CSV_HEADER and rows[1][1] == "1"


def test_milestones_from_stub_observations():
    def board(active, bench):
        return {"self": {"active": [{"name": a} for a in active], "bench": [{"name": b} for b in bench]}}

    assert goldfish.t1_two_dreepy_or_dreepy_budew(board(["Dreepy"], ["Dreepy"])) == 1
    assert goldfish.t1_two_dreepy_or_dreepy_budew(board(["Budew"], ["Dreepy"])) == 1
    assert goldfish.t1_two_dreepy_or_dreepy_budew(board(["Dreepy"], ["Munkidori"])) == 0
    assert goldfish.t2_drakloak(board(["Dreepy"], ["Drakloak"])) == 1
    assert goldfish.t2_drakloak(board(["Dreepy"], [])) == 0


# --- seat selection (slice C2) ---------------------------------------------


def _seed_with_coin(result: str) -> int:
    return next(seed for seed in range(100) if goldfish.flip(random.Random(seed)) == result)


def test_play_parser_seat_defaults_to_choice_and_opponent_choice_to_first():
    args = cli.build_play_parser().parse_args([])
    assert args.seat == "choice"
    assert args.opponent_choice == "first"


def test_play_parser_accepts_each_seat_mode_and_opponent_choice():
    for mode in ("first", "second", "flip", "choice"):
        assert cli.build_play_parser().parse_args(["--seat", mode]).seat == mode
    for pick in ("first", "second", "random"):
        args = cli.build_play_parser().parse_args(["--opponent-choice", pick])
        assert args.opponent_choice == pick


def test_play_parser_rejects_unknown_seat_mode():
    with pytest.raises(SystemExit):
        cli.build_play_parser().parse_args(["--seat", "sideways"])


def test_go_first_and_go_second_are_deprecated_aliases_for_seat():
    assert cli.build_play_parser().parse_args(["--go-first"]).seat == "first"
    assert cli.build_play_parser().parse_args(["--go-second"]).seat == "second"


def test_play_parser_goldfish_flags_still_parse():
    args = cli.build_play_parser().parse_args(
        ["--opponent-policy", "pass", "--item-lock-turns", "2,4", "--goldfish-log", "o.csv"]
    )
    assert (args.opponent_policy, args.item_lock_turns, args.goldfish_log) == (
        "pass", (2, 4), "o.csv")


def test_play_config_carries_seat_fields():
    config = PlayConfig(seat="flip", opponent_choice="second")
    assert (config.seat, config.opponent_choice) == ("flip", "second")
    assert PlayConfig().seat == "choice" and PlayConfig().opponent_choice == "first"


def test_forced_seats_skip_the_coin_and_the_prompt():
    rng = random.Random(1)
    state = rng.getstate()
    asked = []
    first = goldfish.decide_seat("first", "first", rng, lambda: asked.append(1))
    second = goldfish.decide_seat("second", "first", rng, lambda: asked.append(1))
    assert first.first_player == PlayerId.PLAYER1
    assert second.first_player == PlayerId.PLAYER2
    assert rng.getstate() == state and asked == []


def test_flip_mode_heads_means_human_goes_first_and_is_reproducible():
    for seed in range(20):
        decision = goldfish.decide_seat("flip", "first", random.Random(seed), lambda: "first")
        heads = goldfish.flip(random.Random(seed)) == "heads"
        assert decision.first_player == (PlayerId.PLAYER1 if heads else PlayerId.PLAYER2)
        assert decision.first_player == goldfish.decide_seat(
            "flip", "first", random.Random(seed), lambda: "first").first_player


def test_seat_notice_reports_flip_result_and_resulting_seat():
    heads = goldfish.decide_seat("flip", "first", random.Random(_seed_with_coin("heads")), None)
    tails = goldfish.decide_seat("flip", "first", random.Random(_seed_with_coin("tails")), None)
    assert "heads" in heads.notice.lower() and "first" in heads.notice.lower()
    assert "tails" in tails.notice.lower() and "second" in tails.notice.lower()


def test_choice_mode_human_win_prompts_and_applies_the_answer():
    seed = _seed_with_coin("heads")
    asked = []

    def ask() -> str:
        asked.append(1)
        return "second"

    decision = goldfish.decide_seat("choice", "first", random.Random(seed), ask)
    assert asked == [1]
    assert decision.first_player == PlayerId.PLAYER2
    assert "won the flip" in decision.notice.lower()


def test_choice_mode_opponent_win_applies_opponent_choice_without_prompting():
    seed = _seed_with_coin("tails")

    def ask() -> str:
        raise AssertionError("human must not be prompted when the opponent wins the flip")

    opp_first = goldfish.decide_seat("choice", "first", random.Random(seed), ask)
    opp_second = goldfish.decide_seat("choice", "second", random.Random(seed), ask)
    assert opp_first.first_player == PlayerId.PLAYER2
    assert opp_second.first_player == PlayerId.PLAYER1
    random_pick = goldfish.decide_seat("choice", "random", random.Random(seed), ask)
    assert random_pick.first_player in (PlayerId.PLAYER1, PlayerId.PLAYER2)
    assert random_pick.first_player == goldfish.decide_seat(
        "choice", "random", random.Random(seed), ask).first_player


class _StubEnv:
    instances: list = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.first_player = kwargs.get("first_player")
        self.winner = None
        self.recorder = None
        _StubEnv.instances.append(self)

    def reset(self):
        return {}, 0, True, {"winner": None}


class _SeatTerminal:
    def __init__(self, answer: str = "first") -> None:
        self.answer = answer
        self.asked = 0
        self.result = None

    def choose_seat(self) -> str:
        self.asked += 1
        return self.answer

    def choose(self, frame):
        raise AssertionError("no decision expected")

    def show_error(self, message: str) -> None:
        pass

    def show_result(self, result) -> None:
        self.result = result


def _run_with_stub(monkeypatch, config, terminal):
    _StubEnv.instances = []
    monkeypatch.setattr(session, "PokemonTCG", _StubEnv)
    session.run_interactive(config, terminal)
    return _StubEnv.instances[-1]


def test_session_builds_env_with_first_player_for_forced_seats(monkeypatch):
    env = _run_with_stub(monkeypatch, PlayConfig(seat="second"), _SeatTerminal())
    assert env.kwargs["first_player"] == PlayerId.PLAYER2
    env = _run_with_stub(monkeypatch, PlayConfig(seat="first"), _SeatTerminal())
    assert env.kwargs["first_player"] == PlayerId.PLAYER1


def test_session_flip_mode_uses_seed_only(monkeypatch):
    for result, expected in (("heads", PlayerId.PLAYER1), ("tails", PlayerId.PLAYER2)):
        config = PlayConfig(seat="flip", seed=_seed_with_coin(result))
        env = _run_with_stub(monkeypatch, config, _SeatTerminal())
        assert env.kwargs["first_player"] == expected


def test_session_choice_mode_prompts_human_on_win_and_uses_opponent_choice_on_loss(monkeypatch):
    terminal = _SeatTerminal(answer="second")
    env = _run_with_stub(
        monkeypatch, PlayConfig(seat="choice", seed=_seed_with_coin("heads")), terminal)
    assert terminal.asked == 1 and env.kwargs["first_player"] == PlayerId.PLAYER2

    terminal = _SeatTerminal(answer="second")
    env = _run_with_stub(
        monkeypatch,
        PlayConfig(seat="choice", seed=_seed_with_coin("tails"), opponent_choice="second"),
        terminal,
    )
    assert terminal.asked == 0 and env.kwargs["first_player"] == PlayerId.PLAYER1


def test_tracker_counts_human_turns_and_takes_seat_from_first_player():
    def obs(turn_number, active):
        return {"turn_number": turn_number, "self": {
            "hand": [], "active": [{"name": n} for n in active], "bench": []}}

    tracker = goldfish.GoldfishTracker()
    tracker.set_first_player(PlayerId.PLAYER2)
    assert tracker.observe(obs(0, []), mulligans=2) == 0  # setup frame
    assert tracker.observe(obs(1, ["Dreepy"])) == 1
    assert tracker.observe(obs(1, ["Dreepy"])) == 1
    tracker.opponent_acted(_act(ActionType.PASS_TURN))
    assert tracker.observe(obs(3, ["Dreepy"])) == 2
    record = tracker.record()
    assert (record.seat, record.active, record.mulligans) == ("S", "Dreepy", 2)
    assert record.t3_attacker_rp is None
    other = goldfish.GoldfishTracker()
    other.set_first_player(PlayerId.PLAYER1)
    assert other.record().seat == "F"
