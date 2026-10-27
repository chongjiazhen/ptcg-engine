"""Generate src/ptcg/data/marks.json from the tcgdex catalog export.

Usage: py -3 scripts/build_marks.py [catalog.json] [out.json]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DEFAULT_CATALOG = Path(r"C:\tcg-agent\games\pokemon\catalog\catalog.json")
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "src" / "ptcg" / "data" / "marks.json"

# tcgdex set id -> Limitless set code (checked against limitlesstcg.com/cards, 2026-10-28).
SET_CODES = {
    "sv01": "SVI",
    "sv02": "PAL",
    "sv03": "OBF",
    "sv03.5": "MEW",
    "sv04": "PAR",
    "sv04.5": "PAF",
    "sv05": "TEF",
    "sv06": "TWM",
    "sv06.5": "SFA",
    "sv07": "SCR",
    "sv08": "SSP",
    "sv08.5": "PRE",
    "sv09": "JTG",
    "sv10": "DRI",
    "sv10.5b": "BLK",
    "sv10.5w": "WHT",
    "sve": "SVE",
    "svp": "SVP",
    "me01": "MEG",
    "me02": "PFL",
    "me02.5": "ASC",
    "me03": "POR",
    "me04": "CRI",
    "me05": "PBL",
    "mee": "MEE",
    "mep": "MEP",
}


def build(catalog: dict) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in catalog["rows"]:
        tcgdex_set, _, _ = row["id"].rpartition("-")
        code = SET_CODES.get(tcgdex_set)
        if code is None:
            raise SystemExit(f"no engine set code for tcgdex set {tcgdex_set!r} ({row['id']})")
        number = row["number"]
        if re.fullmatch(r"\d+", number):
            number = number.zfill(3)
        card_id = f"{code}-{number}"
        if card_id in out:
            raise SystemExit(f"duplicate engine id {card_id}")
        out[card_id] = {"mark": row["mark"], "set": code, "name": row["name"]}
    return dict(sorted(out.items()))


def main(argv: list[str]) -> int:
    src = Path(argv[0]) if argv else DEFAULT_CATALOG
    dst = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUT
    catalog = json.loads(src.read_text(encoding="utf-8"))
    marks = build(catalog)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(marks, fh, indent=1, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    print(f"wrote {len(marks)} cards to {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
