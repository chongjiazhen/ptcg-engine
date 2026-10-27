from ptcg.core.action import UseItemAction, choose_card_actions
from ptcg.core.card import ItemCard
from ptcg.core.enums import CardPosition, CardType, PokemonRule, PokemonType, SuperType
from ptcg.core.reducer import reduce_choose_card_actions
from ptcg.utils.utils import current_player, move_cards, shuffle_cards


def has_rule_box(card) -> bool:
    return card.pokemonType != PokemonType.NORMAL or card.pokemonRule == PokemonRule.RADIANT


class POR081PokePad(ItemCard):
    def __init__(self):
        super().__init__()
        self.set_name = "POR"
        self.number = "081"
        self.id = f"{self.set_name}-{self.number}"
        self.name = "Poké Pad"
        self.cardType = CardType.NONE
        self.text = (
            "Search your deck for a Pokémon that doesn't have a Rule Box, reveal it, and put "
            "it into your hand. Then, shuffle your deck.\n"
            "(Pokémon ex, Pokémon V, etc. have Rule Boxes.)"
        )

    def get_actions(self, state):
        return [UseItemAction(state.turn, self)]

    def reduce_action(self, action, state):
        if not isinstance(action, UseItemAction):
            return
        player = current_player(state)
        move_cards(self, (player.id, CardPosition.HAND), (player.id, CardPosition.DISCARD), state)

        candidates = [
            card
            for card in player.left
            if card.superType == SuperType.POKEMON and not has_rule_box(card)
        ]
        tips = "You used Poké Pad. You can choose 1 Pokémon without a Rule Box from your deck."
        actions = choose_card_actions(
            player.id, player.id, 0, min(1, len(candidates)), candidates, tips=tips, source=self
        )
        chosen = yield from reduce_choose_card_actions(actions, state)
        if chosen:
            move_cards(
                chosen, (player.id, CardPosition.LEFT), (player.id, CardPosition.HAND), state
            )
        shuffle_cards(player.left, state)
