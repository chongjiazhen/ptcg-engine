from ptcg.core.action import UseSupporterAction, choose_card_actions
from ptcg.core.card import SupporterCard
from ptcg.core.enums import CardPosition, CardType, EnergyType, PokemonPosition, SuperType
from ptcg.core.reducer import reduce_choose_card_actions
from ptcg.utils.utils import (
    current_all_pokemon,
    current_player,
    move_cards,
    shuffle_cards,
)


class SCR133Crispin(SupporterCard):
    def __init__(self):
        super().__init__()
        self.set_name = "SCR"
        self.number = "133"
        self.id = f"{self.set_name}-{self.number}"
        self.name = "Crispin"
        self.cardType = CardType.NONE
        self.text = (
            "Search your deck for up to 2 Basic Energy cards of different types, reveal them, "
            "and put 1 of them into your hand. Attach the other to 1 of your Pokémon. "
            "Then, shuffle your deck."
        )

    def get_actions(self, state):
        player = current_player(state)
        if not player.supporterPlayedTurn and player.left:  # nothing to search with an empty deck
            return [UseSupporterAction(state.turn, self)]
        return []

    def reduce_action(self, action, state):
        if not isinstance(action, UseSupporterAction):
            return
        player = current_player(state)
        move_cards(self, (player.id, CardPosition.HAND), (player.id, CardPosition.DISCARD), state)
        player.supporterPlayedTurn = True

        # One representative per energy type: identical cards are interchangeable, and this
        # keeps the choice space free of same-type pairs.
        by_type = {}
        for card in player.left:
            if (
                card.superType == SuperType.ENERGY
                and card.energyType == EnergyType.BASIC
                and card.provides[0] not in by_type
            ):
                by_type[card.provides[0]] = card
        candidates = list(by_type.values())

        tips = (
            "You used Crispin. Choose up to 2 Basic Energy cards of different types "
            "from your deck."
        )
        actions = choose_card_actions(
            player.id, player.id, 0, min(2, len(candidates)), candidates, tips=tips, source=self
        )
        found = yield from reduce_choose_card_actions(actions, state)

        if len(found) == 1:
            move_cards(found, (player.id, CardPosition.LEFT), (player.id, CardPosition.HAND), state)
        elif len(found) == 2:
            tips = "Choose the Energy card to put into your hand. The other will be attached."
            actions = choose_card_actions(player.id, player.id, 1, 1, found, tips=tips, source=self)
            to_hand = (yield from reduce_choose_card_actions(actions, state))[0]
            to_attach = next(card for card in found if card is not to_hand)

            move_cards(
                to_hand, (player.id, CardPosition.LEFT), (player.id, CardPosition.HAND), state
            )

            tips = "Choose 1 of your Pokémon to attach the Energy card to."
            actions = choose_card_actions(
                player.id, player.id, 1, 1, current_all_pokemon(state), tips=tips, source=self
            )
            target = (yield from reduce_choose_card_actions(actions, state))[0]
            if target.position == PokemonPosition.ACTIVE:
                area = (player.id, CardPosition.ACTIVE_ATTACHMENT)
            else:
                area = (player.id, CardPosition.BENCH_ATTACHMENT, target.index)
            target.energy.extend(to_attach.provides)
            move_cards(to_attach, (player.id, CardPosition.LEFT), area, state)

        shuffle_cards(player.left, state)
