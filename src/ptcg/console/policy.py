"""Opponent policy helpers shared by the CLI and the interactive session."""

from __future__ import annotations

from collections.abc import Sequence

from ptcg.core.action import Action, ChooseCardActionSpace
from ptcg.core.enums import ActionType


def pass_or_first(actions: Sequence[Action]) -> Action:
    """PassTurn whenever legal, otherwise the first legal action."""
    if not isinstance(actions, ChooseCardActionSpace):
        for action in actions:
            if action.actionType == ActionType.PASS_TURN:
                return action
    return actions[0]
