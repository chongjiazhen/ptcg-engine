"""Regulation-mark and set legality checks over the bundled marks table."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

# Regulation marks legal in Standard as of 2026-10-27.
STANDARD_MARKS = frozenset({"H", "I", "J"})


# Set codes in release order; the earliest legal printing is reported as a reprint.
_RELEASE_ORDER = (
    "SVI PAL OBF MEW PAR PAF TEF TWM SFA SCR SSP PRE JTG DRI BLK WHT MEG PFL ASC POR CRI PBL"
).split()


@dataclass(frozen=True)
class Reprint:
    """A card id with no mark data that is legal through a same-name printing."""

    card_id: str
    name: str
    via: str

    def __str__(self) -> str:
        return f"{self.name} {self.card_id} legal via {self.via}"


@dataclass(frozen=True)
class Violation:
    card_id: str
    mark: str | None
    set: str | None
    reason: str

    def __str__(self) -> str:
        return f"{self.card_id} (mark={self.mark}, set={self.set}): {self.reason}"


def standard_marks() -> set[str]:
    """Regulation marks legal in Standard (true on 2026-10-27)."""
    return set(STANDARD_MARKS)


@lru_cache(maxsize=1)
def _load_marks_cached() -> dict[str, dict[str, str]]:
    text = resources.files("ptcg.data").joinpath("marks.json").read_text(encoding="utf-8")
    return json.loads(text)


def load_marks() -> dict[str, dict[str, str]]:
    """Return {card_id: {"mark", "set", "name"}} from the bundled marks.json."""
    return _load_marks_cached()


def card_mark(card_id: str) -> str | None:
    entry = load_marks().get(card_id)
    return entry["mark"] if entry else None


def _print_rank(card_id: str) -> tuple[int, str]:
    code = card_id.partition("-")[0]
    rank = _RELEASE_ORDER.index(code) if code in _RELEASE_ORDER else len(_RELEASE_ORDER)
    return rank, card_id


@lru_cache(maxsize=1)
def _ids_by_name() -> dict[str, tuple[str, ...]]:
    by_name: dict[str, list[str]] = {}
    for card_id, entry in load_marks().items():
        by_name.setdefault(entry["name"], []).append(card_id)
    return {name: tuple(sorted(ids, key=_print_rank)) for name, ids in by_name.items()}


def _registry_card(card_id: str):
    from ptcg.core.card_registry import registry

    card_class = registry.get(card_id)
    return card_class() if card_class else None


def _is_basic_energy(card) -> bool:
    from ptcg.core.enums import EnergyType, SuperType

    return (
        card is not None
        and getattr(card, "superType", None) == SuperType.ENERGY
        and getattr(card, "energyType", None) == EnergyType.BASIC
    )


def explain_deck(
    card_ids: Sequence[str],
    marks: set[str] | None = None,
    sets: set[str] | None = None,
) -> tuple[list[Violation], list[Reprint]]:
    """Return (violations, reprint notes), one per distinct card id in first-seen order.

    The set check runs before the mark lookup. Basic Energy is always legal. A card
    with no mark data is legal when a same-name card (exact match) carries an allowed
    mark; that is reported as a Reprint. With no filters, only unknown ids violate.
    """
    table = load_marks()
    violations: list[Violation] = []
    reprints: list[Reprint] = []
    seen: set[str] = set()
    for card_id in card_ids:
        if card_id in seen:
            continue
        seen.add(card_id)
        card = None
        entry = table.get(card_id)
        if entry is None:
            card = _registry_card(card_id)
            if _is_basic_energy(card):
                continue
        set_code = entry["set"] if entry else card_id.partition("-")[0]
        if sets is not None and set_code not in sets:
            violations.append(
                Violation(card_id, entry["mark"] if entry else None, set_code, "set not allowed")
            )
            continue
        if entry is None:
            if marks is None:
                if sets is None:
                    violations.append(
                        Violation(card_id, None, set_code, "unknown card (no mark data)")
                    )
                continue
            name = getattr(card, "name", None)
            via = next(
                (i for i in _ids_by_name().get(name, ()) if table[i]["mark"] in marks), None
            )
            if via is not None:
                reprints.append(Reprint(card_id, name, via))
            else:
                violations.append(Violation(card_id, None, set_code, "unknown card (no mark data)"))
            continue
        if marks is not None and entry["mark"] not in marks:
            violations.append(Violation(card_id, entry["mark"], set_code, "mark not allowed"))
    return violations, reprints


def validate_deck(
    card_ids: Sequence[str],
    marks: set[str] | None = None,
    sets: set[str] | None = None,
) -> list[Violation]:
    """Violations only; see explain_deck for the reprint notes."""
    return explain_deck(card_ids, marks, sets)[0]
