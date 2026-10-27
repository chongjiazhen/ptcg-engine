"""Step-function form of the interactive match loop, shared by the console and HTTP drivers."""

from __future__ import annotations

import dataclasses
import random
from collections.abc import Callable, Sequence
from typing import Any

from ptcg.console import goldfish
from ptcg.console.model import DecisionFrame, PlayConfig, SessionResult
from ptcg.console.session import (
    _finish_aborted,
    _player_name,
    _select_policy_action,
    build_decision_frame,
    choice_for_indices,
    describe_action,
)
from ptcg.core.action import Action
from ptcg.core.enums import PlayerId
from ptcg.core.envs import PokemonTCG


class NeedSeatChoice(ValueError):
    """The human won the flip under seat=choice and no pick was supplied."""


class Stepper:
    """One human-vs-policy match. Opponent turns auto-advance to the next human decision."""

    def __init__(
        self,
        config: PlayConfig,
        *,
        env: Any = None,
        seat_pick: str | None = None,
        ask_seat: Callable[[], str] | None = None,
        env_factory: Callable[..., Any] | None = None,
    ) -> None:
        if config.opponent_policy not in {"first", "random", "pass"}:
            raise ValueError("opponent_policy must be one of 'first', 'random' or 'pass'")
        if config.max_steps <= 0:
            raise ValueError("max_steps must be greater than zero")
        self.config = config
        self.tracker = goldfish.GoldfishTracker(config.item_lock_turns)
        self.frame: DecisionFrame | None = None
        self.actions: Sequence[Action] = ()
        self.result: SessionResult | None = None
        self.first_player: PlayerId | None = None
        self.steps = 0
        self.hints = 0
        self._hinted = False
        self._reward = 0.0
        self._done = False
        self._info: dict = {}
        self._events: list[str] = []
        self._policy_rng = random.Random(config.seed)

        if env is None:

            def ask() -> str:
                if seat_pick is not None:
                    return seat_pick
                if ask_seat is not None:
                    return ask_seat()
                raise NeedSeatChoice("You won the flip: pick 'first' or 'second'")

            decision = goldfish.decide_seat(
                config.seat, config.opponent_choice, random.Random(config.seed), ask
            )
            self.tracker.set_first_player(decision.first_player)
            self.tracker.notices.append(decision.notice)
            env = (env_factory or PokemonTCG)(
                seed=config.seed,
                deck1=config.deck,
                deck2=config.opponent_deck,
                verbose=config.verbose,
                record_game=config.record,
                first_player=decision.first_player,
            )
        self.env = env

        try:
            _obs, self._reward, self._done, self._info = env.reset()
        except KeyboardInterrupt:
            self._abort("interrupt")
            return
        self._events = list(self._info.get("auto_executed", []))
        started = getattr(env, "first_player", None)
        if started is not None:
            self.tracker.set_first_player(started)
        self.first_player = started
        self._advance()

    # -- public surface -------------------------------------------------

    @property
    def done(self) -> bool:
        return self.result is not None

    def submit(self, action: Action) -> None:
        """Apply the human's action, then advance to the next human decision."""
        if self.result is not None:
            raise RuntimeError("the match is over")
        self._events = []
        self.tracker.record_action(action)
        try:
            self._step(action)
        except KeyboardInterrupt:
            self._abort("interrupt")
            return
        self._advance()

    def submit_choice(self, indices: Sequence[int]) -> None:
        """Apply a card-prompt pick by candidate index (ValueError if not offered)."""
        if self.result is not None:
            raise RuntimeError("the match is over")
        self.submit(choice_for_indices(self.actions, indices))

    def hint(self) -> Sequence[Action]:
        """The legal actions; counts one hint per decision however often it is pressed."""
        if not self._hinted:
            self._hinted = True
            self.hints += 1
        return self.actions

    def abort(self, reason: str) -> SessionResult:
        return self._abort(reason)

    def finish(self, note: str = "") -> goldfish.GoldfishRecord:
        """Build the CSV row and append it when a log path is configured."""
        record = self.tracker.record(note)
        if "hints" in {f.name for f in dataclasses.fields(record)}:
            record = dataclasses.replace(record, hints=self.hints)
        if self.config.goldfish_log:
            goldfish.append_row(self.config.goldfish_log, record)
        return record

    # -- internals ------------------------------------------------------

    def _abort(self, reason: str) -> SessionResult:
        self.frame = None
        self.result = _finish_aborted(
            self.env,
            status="aborted",
            reason=reason,
            steps=self.steps,
            reward=self._reward,
            events=self._events,
        )
        return self.result

    def _step(self, action: Action) -> None:
        self._events.append(describe_action(action))
        _obs, self._reward, self._done, self._info = self.env.step(action)
        self._events.extend(self._info.get("auto_executed", []))
        self.steps += 1

    def _advance(self) -> None:
        env, config = self.env, self.config
        try:
            while not self._done and self.steps < config.max_steps:
                actions: Sequence[Action] = self._info.get("raw_available_actions", [])
                if not actions:
                    self.frame = None
                    self.result = _finish_aborted(
                        env,
                        status="error",
                        reason="no_available_actions",
                        steps=self.steps,
                        reward=self._reward,
                        events=self._events,
                    )
                    return
                if actions[0].playerId == PlayerId.PLAYER1:
                    self._present(actions)
                    return
                action = _select_policy_action(actions, config.opponent_policy, self._policy_rng)
                self.tracker.opponent_acted(action)
                self._step(action)
        except KeyboardInterrupt:
            self._abort("interrupt")
            return

        self.frame = None
        if self._done:
            winner = self._info.get("winner") or env.winner
            self.result = SessionResult(
                status="finished",
                steps=self.steps,
                reward=float(self._reward),
                winner=_player_name(winner),
                reason=self._info.get("termination_reason"),
                events=tuple(self._events),
            )
        else:
            self.result = _finish_aborted(
                env,
                status="stopped",
                reason="max_steps",
                steps=self.steps,
                reward=self._reward,
                events=self._events,
            )

    def _present(self, actions: Sequence[Action]) -> None:
        observation = self.env.observe(PlayerId.PLAYER1)
        human_turn = self.tracker.observe(observation, _mulligans(self.env))
        actions, lock_note = goldfish.filter_item_locked(
            actions, human_turn, self.config.item_lock_turns
        )
        if not lock_note and _engine_item_locked(self.env):
            lock_note = goldfish.ITEM_LOCK_NOTE
        notices = [*self.tracker.notices, *([lock_note] if lock_note else [])]
        self.tracker.notices.clear()
        self.actions = actions
        self._hinted = False
        self.frame = build_decision_frame(
            self.config, observation, actions, self._info, self._events, notices=notices
        )


def _engine_item_locked(match: Any) -> bool:
    player = getattr(getattr(match, "gamestate", None), "player1", None)
    return bool(getattr(player, "itemLocked", False))


def _mulligans(match: Any) -> int:
    player = getattr(getattr(match, "gamestate", None), "player1", None)
    return int(getattr(player, "mulligan_count", 0) or 0)
