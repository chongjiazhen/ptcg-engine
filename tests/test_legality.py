"""Regulation-mark and set legality (slice D)."""

from __future__ import annotations

from ptcg import cli, legality


def test_marks_json_has_twm_128_as_mark_h():
    assert legality.card_mark("TWM-128") == "H"


def test_marks_json_has_meg_127_as_mark_i():
    assert legality.card_mark("MEG-127") == "I"


def test_validate_deck_flags_g_mark_card_under_standard_marks(monkeypatch):
    # Pinned to a synthetic table: the catalog export carries no G-mark rows.
    monkeypatch.setattr(
        legality,
        "load_marks",
        lambda: {
            "ZZZ-001": {"mark": "G", "set": "ZZZ", "name": "Old Card"},
            "TWM-128": {"mark": "H", "set": "TWM", "name": "Dreepy"},
        },
    )
    violations = legality.validate_deck(["ZZZ-001", "TWM-128"], marks=legality.standard_marks())

    assert [v.card_id for v in violations] == ["ZZZ-001"]
    assert violations[0].mark == "G"
    assert "mark" in violations[0].reason


def test_validate_deck_with_sets_flags_card_from_other_set():
    violations = legality.validate_deck(["TWM-128", "PAL-188"], sets={"TWM"})

    assert [v.card_id for v in violations] == ["PAL-188"]
    assert violations[0].set == "PAL"
    assert "set not allowed" in violations[0].reason


def test_validate_deck_reports_unknown_card():
    violations = legality.validate_deck(["NOPE-999"])

    assert len(violations) == 1
    assert violations[0].card_id == "NOPE-999"
    assert "unknown card" in violations[0].reason


def test_validate_deck_marks_filter_flags_card_absent_from_table():
    violations = legality.validate_deck(["PAL-188"], marks=legality.standard_marks())

    assert [v.card_id for v in violations] == ["PAL-188"]
    assert "unknown card" in violations[0].reason


def test_standard_marks_is_h_i_j():
    assert legality.standard_marks() == {"H", "I", "J"}


def test_cards_subcommand_lists_dreepy_for_twm(capsys):
    assert cli.main(["cards", "--set", "TWM"]) == 0

    assert "Dreepy" in capsys.readouterr().out


def _deck_ids() -> list[str]:
    from pathlib import Path

    import ptcg

    path = Path(ptcg.__file__).parent / "decks" / "dragapult_29678.txt"
    ids = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts and parts[0].isdigit():
            ids.append(f"{parts[-2]}-{int(parts[-1]):03d}")
    return ids


def test_29678_deck_is_standard_legal_with_two_reprint_notes():
    violations, reprints = legality.explain_deck(_deck_ids(), marks=legality.standard_marks())

    assert violations == []
    assert sorted((r.card_id, r.via.split("-")[0]) for r in reprints) == [
        ("PAF-091", "MEG"),
        ("PAL-265", "MEG"),
    ]
    assert {r.name for r in reprints} == {"Boss's Orders", "Ultra Ball"}
    assert str([r for r in reprints if r.card_id == "PAL-265"][0]) == (
        "Boss's Orders PAL-265 legal via MEG-114"
    )


def test_pal_card_without_current_reprint_still_violates():
    # PAL-171 is an implemented card whose name has no H/I/J printing in the table.
    from ptcg.core.card_registry import registry

    name = registry.get("PAL-171")().name
    assert not any(e["name"] == name for e in legality.load_marks().values())

    violations = legality.validate_deck(["PAL-171"], marks=legality.standard_marks())

    assert [v.card_id for v in violations] == ["PAL-171"]


def test_basic_energy_passes_set_and_mark_filters():
    assert legality.validate_deck(["SVE-002"], sets={"TWM"}) == []
    assert legality.validate_deck(["SVE-002"], marks=legality.standard_marks()) == []


def test_validate_deck_return_is_violations_only():
    assert legality.validate_deck(["PAL-265"], marks=legality.standard_marks()) == []
