"""Board intents: a fixed menu from printed card text, and server-side resolution.

An intent names cards by board reference (H3 hand, A1 active, B2 bench, S1 stadium)
and never carries an engine ``Action``. ``resolve`` turns it into one of the
engine's own offered action objects by identity, or None. Nothing here reads the
legal set except ``resolve`` itself, so the menu leaks nothing.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger

from ptcg.core.action import Action, ChooseCardActionSpace
from ptcg.core.card_registry import registry
from ptcg.core.enums import ActionType, PlayerId, PokemonPosition

KINDS = (
    "play", "active", "attach", "tool", "evolve", "ability", "attack", "retreat",
    "stadium", "discard", "pass",
)
_REF = re.compile(r"^([HABS])([1-9][0-9]*)$")
_DICT_KEYS = {"kind", "source", "target", "name"}


class IntentError(ValueError):
    """A malformed intent (bad grammar, bad ref, wrong fields for its kind)."""


def _ref_zone(ref: object) -> str | None:
    match = _REF.match(ref) if isinstance(ref, str) else None
    return match.group(1) if match else None


def _check(kind: str, source: Any, target: Any, name: Any) -> None:
    if kind not in KINDS:
        raise IntentError(f"unknown intent kind: {kind!r}")
    for label, value in (("source", source), ("target", target), ("name", name)):
        if value is not None and not isinstance(value, str):
            raise IntentError(f"{label} must be a string")
    zone = _ref_zone(source)
    if kind == "pass":
        if source is not None or target is not None or name is not None:
            raise IntentError("pass takes no arguments")
        return
    if zone is None:
        raise IntentError(f"{kind} needs a valid source ref, got {source!r}")
    allowed_source = {
        "play": "H", "active": "H", "attach": "H", "tool": "H", "evolve": "H",
        "ability": "AB", "attack": "A", "retreat": "A", "stadium": "HS", "discard": "S",
    }[kind]
    if zone not in allowed_source:
        raise IntentError(f"{kind} cannot use source {source}")
    if kind in ("attach", "tool", "evolve"):
        if _ref_zone(target) not in ("A", "B"):
            raise IntentError(f"{kind} needs a target on your board (A1, B2), got {target!r}")
    elif target is not None:
        raise IntentError(f"{kind} takes no target")
    if kind == "attack":
        if not name:
            raise IntentError("attack needs a printed attack name")
    elif kind == "ability":
        if name == "":
            raise IntentError("ability name must not be empty")
    elif name is not None:
        raise IntentError(f"{kind} takes no name")


@dataclass(frozen=True)
class Intent:
    kind: str
    source: str | None = None
    target: str | None = None
    name: str | None = None

    def __post_init__(self) -> None:
        _check(self.kind, self.source, self.target, self.name)

    # -- compact dict -------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: object) -> Intent:
        if not isinstance(data, dict):
            raise IntentError("intent must be an object")
        extra = set(data) - _DICT_KEYS
        if extra:
            raise IntentError(f"unknown intent fields: {sorted(extra)}")
        kind = data.get("kind")
        if not isinstance(kind, str):
            raise IntentError("intent needs a string kind")
        return cls(kind, data.get("source"), data.get("target"), data.get("name"))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "source": self.source, "target": self.target, "name": self.name}

    # -- text grammar -------------------------------------------------------------
    @classmethod
    def parse(cls, text: str) -> Intent:
        if not isinstance(text, str):
            raise IntentError("intent text must be a string")
        words = text.split()
        if not words:
            raise IntentError("empty intent")
        kind, args = words[0].lower(), words[1:]
        refs = [a.upper() for a in args]
        if kind == "pass" and not args:
            return cls("pass")
        if kind == "retreat" and not args:
            return cls("retreat", "A1")
        if kind == "attack":
            if not args:
                raise IntentError("attack needs a name")
            return cls("attack", "A1", name=" ".join(args))
        if kind == "ability" and args:
            return cls("ability", refs[0], name=" ".join(args[1:]) or None)
        if kind in ("play", "active", "stadium", "discard") and len(args) == 1:
            return cls(kind, refs[0])
        if kind in ("attach", "tool", "evolve") and len(args) == 2:
            return cls(kind, refs[0], refs[1])
        raise IntentError(f"cannot parse intent: {text!r}")

    def format(self) -> str:
        if self.kind == "pass":
            return "pass"
        if self.kind == "retreat":
            return "retreat"
        if self.kind == "attack":
            return f"attack {self.name}"
        parts = [self.kind, self.source]
        if self.target:
            parts.append(self.target)
        if self.kind == "ability" and self.name:
            parts.append(self.name)
        return " ".join(parts)


# -- board references ----------------------------------------------------------------


def _me(state: Any, player: PlayerId) -> Any:
    return state.player1 if player == PlayerId.PLAYER1 else state.player2


def _zones(state: Any, player: PlayerId) -> dict[str, Sequence[Any]]:
    me = _me(state, player)
    return {"H": me.hand, "A": me.active, "B": me.bench, "S": list(state.stadium)}


def _object(ref: str | None, state: Any, player: PlayerId) -> Any | None:
    match = _REF.match(ref) if isinstance(ref, str) else None
    if not match:
        return None
    zone = _zones(state, player)[match.group(1)]
    index = int(match.group(2)) - 1
    return zone[index] if index < len(zone) else None


def _ref_of(card: Any, state: Any, player: PlayerId) -> str | None:
    for letter, zone in _zones(state, player).items():
        for index, candidate in enumerate(zone):
            if candidate is card:
                return f"{letter}{index + 1}"
    return None


# -- fixed menu ------------------------------------------------------------------------


@dataclass(frozen=True)
class MenuEntry:
    kind: str
    label: str
    source: str | None = None
    targets: tuple[str, ...] = ()
    name: str | None = None


def _printed(card: Any) -> dict[str, Any]:
    details = registry.describe(str(card.set_name), str(card.number))
    return details if details is not None else card.get_info()


def menu_for(card_or_ref: Any, state: Any, player: PlayerId = PlayerId.PLAYER1) -> list[MenuEntry]:
    """Action types for a card from its printed type alone; never reads legal actions."""
    pass_entry = MenuEntry("pass", "Pass")
    if card_or_ref is None:
        return [pass_entry]
    card = _object(card_or_ref, state, player) if isinstance(card_or_ref, str) else card_or_ref
    if card is None:
        return [pass_entry]
    ref = _ref_of(card, state, player)
    zone = ref[0] if ref else "H"
    me = _me(state, player)
    in_play = tuple(f"A{i + 1}" for i in range(len(me.active))) + tuple(
        f"B{i + 1}" for i in range(len(me.bench))
    )
    info = _printed(card)
    entries: list[MenuEntry] = []
    if zone == "S":
        entries += [MenuEntry("stadium", "Use stadium", ref), MenuEntry("discard", "Discard stadium", ref)]
    elif info.get("superType") == "POKEMON":
        if zone == "H":
            if info.get("stage") == "BASIC":
                entries += [
                    MenuEntry("play", "Play to bench", ref),
                    MenuEntry("active", "Set as Active", ref),
                ]
            else:
                entries.append(MenuEntry("evolve", "Evolve", ref, in_play))
        else:
            for ability in info.get("abilities", []):
                entries.append(MenuEntry("ability", f"Ability: {ability['name']}", ref, name=ability["name"]))
            if zone == "A":
                for attack in info.get("attacks", []):
                    entries.append(MenuEntry("attack", f"Attack: {attack['name']}", ref, name=attack["name"]))
                entries.append(MenuEntry("retreat", "Retreat", ref))
    elif info.get("superType") == "ENERGY" and zone == "H":
        entries.append(MenuEntry("attach", "Attach", ref, in_play))
    elif info.get("superType") == "TRAINER" and zone == "H":
        kind = info.get("trainerType")
        if kind == "TOOL":
            entries.append(MenuEntry("tool", "Attach tool", ref, in_play))
        elif kind == "STADIUM":
            entries.append(MenuEntry("stadium", "Play stadium", ref))
        else:
            entries.append(MenuEntry("play", "Play", ref))
    entries.append(pass_entry)
    return entries


# -- resolve / inverse ----------------------------------------------------------------

_AT = ActionType


def _matches(intent: Intent, action: Action, source: Any, target: Any) -> bool:
    kind, atype = intent.kind, action.actionType
    if kind == "pass":
        return atype == _AT.PASS_TURN
    if kind == "retreat":
        return atype == _AT.RETREAT_ACTION and action.active_pokemon is source
    if getattr(action, "source", None) is not source:
        return False
    if kind == "play":
        return (
            atype == _AT.PLAY_POKEMON_ACTION and action.position == PokemonPosition.BENCH
        ) or atype in (_AT.USE_ITEM_ACTION, _AT.USE_SUPPORTER_ACTION)
    if kind == "active":
        return atype == _AT.PLAY_POKEMON_ACTION and action.position == PokemonPosition.ACTIVE
    if kind == "attach":
        return atype == _AT.ATTACH_ENERGY_ACTION and action.target is target
    if kind == "tool":
        return atype == _AT.USE_TOOL_ACTION and action.target is target
    if kind == "evolve":
        return atype == _AT.EVOLVE_POKEMON_ACTION and action.target is target
    if kind == "ability":
        return atype == _AT.USE_ABILITY_ACTION and (
            intent.name is None or action.ability.name == intent.name
        )
    if kind == "attack":
        return atype == _AT.ATTACK_ACTION and action.attack.name == intent.name
    if kind == "stadium":
        wanted = _AT.PUT_STADIUM_ACTION if intent.source[0] == "H" else _AT.USE_STADIUM_ACTION
        return atype == wanted
    if kind == "discard":
        return atype == _AT.DISCARD_STADIUM_ACTION
    return False


def resolve(
    intent: Intent,
    legal_actions: Sequence[Action],
    state: Any,
    player: PlayerId = PlayerId.PLAYER1,
) -> Action | None:
    """Return the single offered action the intent names, else None."""
    if isinstance(legal_actions, ChooseCardActionSpace):
        return None
    source = target = None
    if intent.kind != "pass":
        source = _object(intent.source, state, player)
        if source is None:
            return None
    if intent.kind in ("attach", "tool", "evolve"):
        target = _object(intent.target, state, player)
        if target is None:
            return None
    found = [
        a for a in legal_actions
        if getattr(a, "playerId", player) == player and _matches(intent, a, source, target)
    ]
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        logger.warning("intent {} matched {} legal actions; refusing", intent.format(), len(found))
    return None


def intent_of(action: Action, state: Any, player: PlayerId | None = None) -> Intent:
    """Inverse of ``resolve`` for non-prompt actions."""
    who = player if player is not None else action.playerId

    def ref(card: Any) -> str:
        found = _ref_of(card, state, who)
        if found is None:
            raise IntentError(f"card {getattr(card, 'name', card)!r} is not on the board")
        return found

    atype = action.actionType
    if atype == _AT.PASS_TURN:
        return Intent("pass")
    if atype == _AT.PLAY_POKEMON_ACTION:
        kind = "play" if action.position == PokemonPosition.BENCH else "active"
        return Intent(kind, ref(action.source))
    if atype in (_AT.USE_ITEM_ACTION, _AT.USE_SUPPORTER_ACTION):
        return Intent("play", ref(action.source))
    if atype == _AT.EVOLVE_POKEMON_ACTION:
        return Intent("evolve", ref(action.source), ref(action.target))
    if atype == _AT.ATTACH_ENERGY_ACTION:
        return Intent("attach", ref(action.source), ref(action.target))
    if atype == _AT.USE_TOOL_ACTION:
        return Intent("tool", ref(action.source), ref(action.target))
    if atype == _AT.USE_ABILITY_ACTION:
        return Intent("ability", ref(action.source), name=action.ability.name)
    if atype == _AT.ATTACK_ACTION:
        return Intent("attack", ref(action.source), name=action.attack.name)
    if atype == _AT.RETREAT_ACTION:
        return Intent("retreat", ref(action.active_pokemon))
    if atype in (_AT.PUT_STADIUM_ACTION, _AT.USE_STADIUM_ACTION):
        return Intent("stadium", ref(action.source))
    if atype == _AT.DISCARD_STADIUM_ACTION:
        return Intent("discard", ref(action.source))
    raise IntentError(f"no intent for {atype.name}")
