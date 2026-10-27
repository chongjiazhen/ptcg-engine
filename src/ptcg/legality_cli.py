"""`ptcg cards`: list cards from the marks table and flag engine-implemented ones."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from ptcg.legality import load_marks


def build_cards_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ptcg cards", description="List known cards.")
    parser.add_argument("--set", dest="set_code", help="Only this set code, e.g. TWM.")
    parser.add_argument("--mark", help="Only this regulation mark, e.g. H.")
    parser.add_argument(
        "--implemented-only", action="store_true", help="Only cards implemented in the engine."
    )
    return parser


def run_cards(argv: Sequence[str]) -> int:
    from ptcg.core.card_registry import registry

    args = build_cards_parser().parse_args(list(argv))
    implemented = set(registry.list_all())
    set_code = args.set_code.upper() if args.set_code else None
    mark = args.mark.upper() if args.mark else None
    for card_id, entry in sorted(load_marks().items()):
        if set_code and entry["set"] != set_code:
            continue
        if mark and entry["mark"] != mark:
            continue
        have = card_id in implemented
        if args.implemented_only and not have:
            continue
        print(f"{'*' if have else ' '} {card_id:<9} {entry['mark']}  {entry['name']}")
    return 0
