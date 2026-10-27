"""Goldfish-drill helpers: item lock, dice, milestone tracking, and the CSV row."""

from __future__ import annotations

import copy
import csv
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ptcg.core.action import ChooseCardActionSpace
from ptcg.core.card_registry import registry
from ptcg.core.enums import ActionType, PlayerId

CSV_COLUMNS = (
    "date,hand,var,seat,active,mulligans,supporters_in_7,t1_two_dreepy_or_dreepy_budew,"
    "t1_search,t2_drakloak,t2_supporter,t3_attacker_rp,lock_variation,decide,note"
).split(",")

ITEM_LOCK_NOTE = "Items locked this turn (simulated Budew)"
SEED_SEARCH_CAP = 200

_SEARCH_NAMES = {"Buddy-Buddy Poffin": "Poffin", "Poké Pad": "Pad", "Ultra Ball": "UB"}


def filter_item_locked(
    actions: Sequence[Any], human_turn: int, lock_turns: Sequence[int]
) -> tuple[Sequence[Any], str | None]:
    """Hide Item plays on the human's listed turns; return (actions, note)."""
    if human_turn not in lock_turns:
        return actions, None
    if isinstance(actions, ChooseCardActionSpace):
        return actions, ITEM_LOCK_NOTE
    kept = [a for a in actions if getattr(a, "actionType", None) != ActionType.USE_ITEM_ACTION]
    return kept, ITEM_LOCK_NOTE


def flip(rng: random.Random) -> str:
    return "heads" if rng.random() < 0.5 else "tails"


def roll(rng: random.Random, sides: int = 6) -> int:
    return rng.randint(1, sides)


def _pokemon(observation: dict) -> list[dict]:
    me = observation["self"]
    return [*me.get("active", []), *me.get("bench", [])]


def _names(observation: dict) -> list[str]:
    return [p.get("name") for p in _pokemon(observation)]


def t1_two_dreepy_or_dreepy_budew(observation: dict) -> int:
    names = _names(observation)
    dreepy = names.count("Dreepy")
    return int(dreepy >= 2 or (dreepy >= 1 and "Budew" in names))


def t2_drakloak(observation: dict) -> int:
    return int("Drakloak" in _names(observation))


def t3_attacker_rp(observation: dict) -> int:
    for pokemon in _pokemon(observation):
        energy = pokemon.get("energy", [])
        if pokemon.get("name") == "Dragapult ex" and "fire" in energy and "psychic" in energy:
            return 1
    return 0


@dataclass
class GoldfishRecord:
    seat: str = ""
    active: str = ""
    mulligans: int = 0
    supporters_in_7: int = 0
    t1_two_dreepy_or_dreepy_budew: int | None = None
    t1_search: str | None = None
    t2_drakloak: int | None = None
    t2_supporter: int | None = None
    t3_attacker_rp: int | None = None
    lock_variation: int = 0
    note: str = ""


def _blank(value: object) -> str:
    return "" if value is None else str(value)


def append_row(path: str, record: GoldfishRecord, today: str | None = None) -> int:
    """Append one row in goldfish.csv column order; return the hand number used."""
    target = Path(path)
    hand = 1
    needs_header = True
    needs_newline = False
    if target.exists() and target.stat().st_size > 0:
        needs_header = False
        text = target.read_text(encoding="utf-8")
        needs_newline = not text.endswith("\n")
        for row in csv.reader(text.splitlines()):
            if len(row) > 1 and row[1].isdigit():
                hand = int(row[1]) + 1
    values = [
        today or date.today().isoformat(), hand, "J", record.seat, record.active,
        record.mulligans, record.supporters_in_7, _blank(record.t1_two_dreepy_or_dreepy_budew),
        _blank(record.t1_search), _blank(record.t2_drakloak), _blank(record.t2_supporter),
        _blank(record.t3_attacker_rp), record.lock_variation, "", record.note,
    ]
    with target.open("a", encoding="utf-8", newline="") as handle:
        if needs_newline:
            handle.write("\n")
        writer = csv.writer(handle, lineterminator="\n")
        if needs_header:
            writer.writerow(CSV_COLUMNS)
        writer.writerow(values)
    return hand


def find_seed(
    start_seed: int, go_first: bool, make_env: Callable[[int], Any], cap: int = SEED_SEARCH_CAP
) -> int:
    """First seed in [start, start+cap) whose coin gives the human the wanted turn order.

    The engine flips the coin after both setup choices and exposes no override,
    so each candidate is played through setup with first-listed choices (the coin
    does not depend on them).
    """
    for seed in range(start_seed, start_seed + cap):
        env = make_env(seed)
        _obs, _reward, _done, info = env.reset()
        for _ in range(2):
            actions = info["raw_available_actions"]
            if isinstance(actions, ChooseCardActionSpace):
                action = actions.action_for_candidate_indices([0])
            else:
                action = actions[0]
            _obs, _reward, _done, info = env.step(action)
        if (env.gamestate.turn == PlayerId.PLAYER1) == go_first:
            return seed
    wanted = "first" if go_first else "second"
    raise ValueError(f"No seed in {start_seed}..{start_seed + cap - 1} lets the human go {wanted}")


def _is_supporter(card: dict) -> bool:
    details = registry.describe(str(card.get("set_name", "")), str(card.get("number", "")))
    return bool(details) and details.get("trainerType") == "SUPPORTER"


class GoldfishTracker:
    """Derives drill milestones from the public state the console session already sees."""

    def __init__(self, lock_turns: Sequence[int] = ()) -> None:
        self.lock_turns = tuple(lock_turns)
        self.human_turn = 0
        self.notices: list[str] = []
        self.supporters_in_7 = 0
        self.mulligans = 0
        self.active = ""
        self.seat = "F"
        self._opening_seen = False
        self._started = False
        self._turn_key: object = None
        self._boards: dict[int, dict] = {}
        self._items: dict[int, list[str]] = {}
        self._supporter_turns: set[int] = set()

    def opponent_acted(self, action: Any) -> None:
        self._turn_key = None
        if self._started or action.actionType == ActionType.CHOOSE_CARD_ACTION:
            return
        self.seat = "S"

    def observe(self, observation: dict, mulligans: int = 0) -> int:
        """Register a human decision point; return the human's current turn number."""
        me = observation["self"]
        if not self._opening_seen:
            self._opening_seen = True
            self.mulligans = mulligans
            self.supporters_in_7 = sum(_is_supporter(c) for c in me.get("hand") or [])
        if not me.get("active"):
            return 0
        self._started = True
        if not self.active:
            self.active = me["active"][0]["name"]
        key = observation.get("turn_number")
        if key != self._turn_key or self.human_turn == 0:
            self.human_turn += 1
            self._turn_key = key
        self._boards[self.human_turn] = copy.deepcopy({"self": me})
        return self.human_turn

    def record_action(self, action: Any) -> None:
        turn = self.human_turn
        source = getattr(action, "source", None)
        if action.actionType == ActionType.USE_ITEM_ACTION and source is not None:
            name = _SEARCH_NAMES.get(source.name)
            if name:
                self._items.setdefault(turn, []).append(name)
        elif action.actionType == ActionType.USE_SUPPORTER_ACTION:
            self._supporter_turns.add(turn)

    def record(self, note: str = "") -> GoldfishRecord:
        def at(turn: int, fn: Callable[[dict], int]) -> int | None:
            board = self._boards.get(turn)
            return None if board is None else fn(board)

        items = self._items.get(1, [])
        return GoldfishRecord(
            seat=self.seat,
            active=self.active,
            mulligans=self.mulligans,
            supporters_in_7=self.supporters_in_7,
            t1_two_dreepy_or_dreepy_budew=at(1, t1_two_dreepy_or_dreepy_budew),
            t1_search=("+".join(items) if items else "none") if 1 in self._boards else None,
            t2_drakloak=at(2, t2_drakloak),
            t2_supporter=int(2 in self._supporter_turns) if 2 in self._boards else None,
            t3_attacker_rp=at(3, t3_attacker_rp),
            lock_variation=int(bool(self.lock_turns)),
            note=note,
        )
