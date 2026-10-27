from ptcg.core.action import UseSupporterAction, choose_card_actions
from ptcg.core.card import SupporterCard
from ptcg.core.enums import (
    CardPosition,
    CardType,
    EnergyType,
    PokemonPosition,
    Stage,
    SuperType,
)
from ptcg.core.reducer import reduce_choose_card_actions
from ptcg.utils.utils import (
    current_all_pokemon,
    current_player,
    move_cards,
    opponent_player,
)


def _stage2_pokemon(state):
    return [p for p in current_all_pokemon(state) if p.stage == Stage.STAGE_2]


class POR084RosasEncouragement(SupporterCard):
    def __init__(self):
        super().__init__()
        self.set_name = "POR"
        self.number = "084"
        self.id = f"{self.set_name}-{self.number}"
        self.name = "Rosa's Encouragement"
        self.cardType = CardType.NONE
        self.text = (
            "You can use this card only if you have more Prize cards remaining than your "
            "opponent.\n"
            "Attach up to 2 Basic Energy cards from your discard pile to 1 of your Stage 2 "
            "Pokémon."
        )

    def get_actions(self, state):
        player = current_player(state)
        if (
            not player.supporterPlayedTurn
            and len(player.prize) > len(opponent_player(state).prize)
            and _stage2_pokemon(state)
        ):
            return [UseSupporterAction(state.turn, self)]
        return []

    def reduce_action(self, action, state):
        if not isinstance(action, UseSupporterAction):
            return
        player = current_player(state)
        move_cards(self, (player.id, CardPosition.HAND), (player.id, CardPosition.DISCARD), state)
        player.supporterPlayedTurn = True

        energies = [
            card
            for card in player.discard
            if card.superType == SuperType.ENERGY and card.energyType == EnergyType.BASIC
        ]
        tips = (
            "You used Rosa's Encouragement. Choose up to 2 Basic Energy cards "
            "from your discard pile."
        )
        actions = choose_card_actions(
            player.id, player.id, 0, min(2, len(energies)), energies, tips=tips, source=self
        )
        chosen = yield from reduce_choose_card_actions(actions, state)
        if not chosen:
            return

        tips = "Choose 1 of your Stage 2 Pokémon to attach the Energy cards to."
        actions = choose_card_actions(
            player.id, player.id, 1, 1, _stage2_pokemon(state), tips=tips, source=self
        )
        target = (yield from reduce_choose_card_actions(actions, state))[0]

        for energy in chosen:
            if target.position == PokemonPosition.ACTIVE:
                area = (player.id, CardPosition.ACTIVE_ATTACHMENT)
            else:
                area = (player.id, CardPosition.BENCH_ATTACHMENT, target.index)
            target.energy.extend(energy.provides)
            move_cards(energy, (player.id, CardPosition.DISCARD), area, state)
