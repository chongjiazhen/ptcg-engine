import pytest

from ptcg.core.action import AttackAction
from ptcg.core.enums import CardType, Stage
from tests.helpers.cards import make_card
from tests.helpers.generator_driver import drive_choices
from tests.helpers.state_builder import PlayerZones, make_state


@pytest.mark.card("ASC-016")
@pytest.mark.card_coverage("ASC-016", "metadata", "get_actions", "reduce_action", "damage")
def test_budew_printed_stats_and_itchy_pollen_text():
    budew = make_card("ASC-016")

    assert budew.name == "Budew"
    assert budew.hp == 30
    assert budew.cardType == CardType.GRASS
    assert budew.stage == Stage.BASIC
    assert budew.retreat == []
    assert budew.weakness == [CardType.FIRE]
    assert [a.name for a in budew.attacks] == ["Itchy Pollen"]
    attack = budew.attacks[0]
    assert attack.cost == []
    assert attack.damage == 10
    assert (
        attack.text
        == "During your opponent's next turn, they can't play any Item cards from their hand."
    )


def test_budew_itchy_pollen_deals_10_with_no_energy():
    budew = make_card("ASC-016")
    defender = make_card("PAF-007")
    state = make_state(
        PlayerZones(left=[make_card("SVE-002")], active=[budew]),
        PlayerZones(left=[make_card("SVE-005") for _ in range(3)], active=[defender]),
    )
    hp_before = defender.hp

    attacks = [a for a in budew.get_actions(state) if isinstance(a, AttackAction)]
    assert [a.attack.name for a in attacks] == ["Itchy Pollen"]
    drive_choices(budew.reduce_action(attacks[0], state), [])

    assert defender.hp == hp_before - 10
