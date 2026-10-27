"""Goldfish console features: pass policy, item lock, flip/roll, CSV row."""

from __future__ import annotations

import csv
import random
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


def test_play_parser_accepts_pass_policy_and_goldfish_flags():
    args = cli.build_play_parser().parse_args(
        [
            "--opponent-policy", "pass", "--go-second",
            "--item-lock-turns", "2,4", "--goldfish-log", "out.csv",
        ]
    )
    assert args.opponent_policy == "pass"
    assert args.go_second is True and args.go_first is False
    assert args.item_lock_turns == (2, 4)
    assert args.goldfish_log == "out.csv"


def test_play_parser_go_first_and_defaults():
    args = cli.build_play_parser().parse_args(["--go-first"])
    assert args.go_first is True and args.go_second is False
    assert args.item_lock_turns == () and args.goldfish_log is None


def test_play_parser_rejects_go_first_with_go_second():
    import pytest

    with pytest.raises(SystemExit):
        cli.build_play_parser().parse_args(["--go-first", "--go-second"])


def test_play_config_carries_goldfish_fields():
    config = PlayConfig(go_first=True, item_lock_turns=(2,), goldfish_log="x.csv")
    assert (config.go_first, config.item_lock_turns, config.goldfish_log) == (True, (2,), "x.csv")


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


def test_find_seed_matches_requested_turn_order_and_reports_a_reproducible_seed():
    from ptcg.core.envs import PokemonTCG

    def make(seed):
        return PokemonTCG(seed=seed, deck1="charizard_ex", deck2="miraidon_ex")

    first = goldfish.find_seed(0, True, make)
    second = goldfish.find_seed(0, False, make)
    assert first != second

    import pytest

    with pytest.raises(ValueError):
        goldfish.find_seed(0, True, make, cap=0)


def test_tracker_counts_human_turns_and_seat_from_public_observations():
    def obs(turn_number, active):
        return {"turn_number": turn_number, "self": {
            "hand": [], "active": [{"name": n} for n in active], "bench": []}}

    tracker = goldfish.GoldfishTracker()
    tracker.opponent_acted(_act(ActionType.PASS_TURN))  # opponent moved before the human's first turn
    assert tracker.observe(obs(0, []), mulligans=2) == 0  # setup frame
    assert tracker.observe(obs(1, ["Dreepy"])) == 1
    assert tracker.observe(obs(1, ["Dreepy"])) == 1
    tracker.opponent_acted(_act(ActionType.PASS_TURN))
    assert tracker.observe(obs(3, ["Dreepy"])) == 2
    record = tracker.record()
    assert (record.seat, record.active, record.mulligans) == ("S", "Dreepy", 2)
    assert record.t3_attacker_rp is None
