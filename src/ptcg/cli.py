"""Command-line entry point for simulations and interactive matches."""

from __future__ import annotations

import argparse
import random
import sys
from collections.abc import Sequence

from ptcg.console.policy import pass_or_first
from ptcg.core.action import Action
from ptcg.core.envs import PokemonTCG


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ptcg",
        description="Run a Pokemon TCG engine simulation.",
        epilog="For an interactive match, run: ptcg play --help",
    )
    parser.add_argument("--deck1", help="Deck name or path for player 1.")
    parser.add_argument("--deck2", help="Deck name or path for player 2.")
    parser.add_argument("--seed", type=int, default=0, help="Random seed. Defaults to 0.")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=1000,
        help="Maximum number of actions to run before stopping. Defaults to 1000.",
    )
    parser.add_argument(
        "--policy",
        choices=("first", "random"),
        default="first",
        help="Action selection policy. Defaults to first.",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="Record the game with the engine recorder.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose engine logging.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print the final result.",
    )
    return parser


def build_play_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ptcg play",
        description="Play an interactive Pokemon TCG match against a built-in policy.",
    )
    parser.add_argument("--deck", help="Deck name or path for the human player.")
    parser.add_argument("--opponent-deck", help="Deck name or path for the opponent.")
    parser.add_argument("--seed", type=int, default=0, help="Random seed. Defaults to 0.")
    parser.add_argument(
        "--max-steps",
        type=_positive_int,
        default=1000,
        help="Maximum number of engine actions. Defaults to 1000.",
    )
    parser.add_argument(
        "--opponent-policy",
        choices=("first", "random", "pass"),
        default="random",
        help="Opponent action policy; pass ends the turn whenever legal. Defaults to random.",
    )
    parser.add_argument(
        "--seat",
        choices=("first", "second", "flip", "choice"),
        default="choice",
        help="Turn order: forced first/second, a coin flip, or a coin for who chooses. "
        "Defaults to choice.",
    )
    parser.add_argument(
        "--opponent-choice",
        choices=("first", "second", "random"),
        default="first",
        help="What the opponent picks when it wins the flip in choice mode. Defaults to first.",
    )
    parser.add_argument(
        "--go-first", dest="seat", action="store_const", const="first",
        help="Deprecated alias for --seat first.",
    )
    parser.add_argument(
        "--go-second", dest="seat", action="store_const", const="second",
        help="Deprecated alias for --seat second.",
    )
    parser.add_argument(
        "--item-lock-turns",
        type=_turn_list,
        default=(),
        help="Comma-separated human turn numbers on which Item cards are hidden, e.g. 2,4.",
    )
    parser.add_argument(
        "--goldfish-log",
        help="Append one goldfish.csv row to this file when the game ends or you quit.",
    )
    parser.add_argument(
        "--marks",
        type=_code_list,
        default=None,
        help=(
            "Reject the human deck unless every card carries one of these regulation marks "
            "(comma list, e.g. H,I,J; 'standard' = the current Standard marks)."
        ),
    )
    parser.add_argument(
        "--sets",
        type=_code_list,
        default=None,
        help="Reject the human deck unless every card comes from one of these set codes (comma list, e.g. TWM,MEG).",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="Record the game with the engine recorder.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose engine logging.",
    )
    return parser


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _code_list(value: str) -> frozenset[str]:
    codes = frozenset(part.strip() for part in value.split(",") if part.strip())
    if not codes:
        raise argparse.ArgumentTypeError("expected a comma-separated list")
    return codes


def check_deck_legality(
    deck: str | None, marks: frozenset[str] | None, sets: frozenset[str] | None
) -> int:
    """Validate the human deck against --marks / --sets. Returns 0 when legal, 2 otherwise.

    Prints one line per violation and one per reprint note (an old printing credited
    through a current same-name reprint). No filters means no check.
    """
    if marks is None and sets is None:
        return 0
    from ptcg.core.envs import DEFAULT_DECK
    from ptcg.legality import explain_deck, standard_marks
    from ptcg.utils.load_deck import load_deck

    if marks is not None and "standard" in marks:
        marks = frozenset(standard_marks()) | (marks - {"standard"})
    cards = load_deck(deck or DEFAULT_DECK).cards
    violations, reprints = explain_deck(
        [card.id for card in cards],
        set(marks) if marks is not None else None,
        set(sets) if sets is not None else None,
    )
    for note in reprints:
        print(f"note: {note}")
    for violation in violations:
        print(f"illegal: {violation}")
    if violations:
        print(f"Deck rejected: {len(violations)} card(s) fail the --marks/--sets filter.")
        return 2
    return 0


def _turn_list(value: str) -> tuple[int, ...]:
    try:
        turns = tuple(int(part) for part in value.split(",") if part.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be comma-separated integers") from exc
    if not turns or any(turn <= 0 for turn in turns):
        raise argparse.ArgumentTypeError("turn numbers must be positive integers")
    return turns


def select_action(actions: Sequence[Action], policy: str, rng: random.Random) -> Action:
    if policy == "random":
        return rng.choice(actions)
    if policy == "pass":
        return pass_or_first(actions)
    return actions[0]


def describe_action(action: Action) -> str:
    try:
        return action.to_nl()
    except Exception:  # noqa: BLE001 - action renderers are third-party card code
        return repr(action)


def run(args: argparse.Namespace) -> int:
    rng = random.Random(args.seed)

    env = PokemonTCG(
        seed=args.seed,
        deck1=args.deck1,
        deck2=args.deck2,
        verbose=args.verbose,
        record_game=args.record,
    )
    env.set_seed(args.seed)

    _obs, reward, done, info = env.reset()
    steps = 0

    while not done and steps < args.max_steps:
        actions = info.get("raw_available_actions", [])
        if not actions:
            print(f"No available actions at step {steps}.")
            return 2

        action = select_action(actions, args.policy, rng)
        if not args.quiet:
            turn = info.get("turn")
            print(f"{steps + 1:04d} {turn}: {describe_action(action)}")

        _obs, reward, done, info = env.step(action)
        steps += 1

    winner = info.get("winner") or env.winner
    if done:
        print(f"Game finished in {steps} steps. Winner: {winner}. Reward: {reward}.")
        return 0

    print(f"Stopped after {steps} steps without a winner. Last reward: {reward}.")
    return 1


def run_play(args: argparse.Namespace) -> int:
    from ptcg.console import PlayConfig, RichTerminal, run_interactive

    legality = check_deck_legality(args.deck, args.marks, args.sets)
    if legality:
        return legality
    config = PlayConfig(
        deck=args.deck,
        opponent_deck=args.opponent_deck,
        opponent_policy=args.opponent_policy,
        seed=args.seed,
        max_steps=args.max_steps,
        record=args.record,
        verbose=args.verbose,
        seat=args.seat,
        opponent_choice=args.opponent_choice,
        item_lock_turns=args.item_lock_turns,
        goldfish_log=args.goldfish_log,
    )
    result = run_interactive(config, RichTerminal())
    return result.exit_code


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else sys.argv[1:]
    if arguments and arguments[0] == "play":
        return run_play(build_play_parser().parse_args(arguments[1:]))
    if arguments and arguments[0] == "cards":
        from ptcg.legality_cli import run_cards

        return run_cards(arguments[1:])

    parser = build_parser()
    args = parser.parse_args(arguments)
    return run(args)
