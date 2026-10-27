from ptcg.core.action import UseItemAction
from ptcg.core.card import ItemCard
from ptcg.core.enums import CardPosition, CardTag, CardType
from ptcg.utils.utils import current_player, move_cards, opponent_player, shuffle_cards


class TWM165UnfairStamp(ItemCard):
    def __init__(self):
        super().__init__()
        self.set_name = "TWM"
        self.number = "165"
        self.id = f"{self.set_name}-{self.number}"
        self.name = "Unfair Stamp"
        self.cardType = CardType.NONE
        self.cardTag = CardTag.ACE_SPEC
        self.text = (
            "You can use this card only if any of your Pokémon were Knocked Out during your "
            "opponent's last turn.\n"
            "Each player shuffles their hand into their deck. Then, you draw 5 cards, and "
            "your opponent draws 2 cards."
        )

    def get_actions(self, state):
        if current_player(state).hasPokemonDead:
            return [UseItemAction(state.turn, self)]
        return []

    def reduce_action(self, action, state):
        if not isinstance(action, UseItemAction):
            return
        player = current_player(state)
        move_cards(self, (player.id, CardPosition.HAND), (player.id, CardPosition.DISCARD), state)

        for who, count in ((player, 5), (opponent_player(state), 2)):
            if who.hand:
                move_cards(
                    who.hand[:], (who.id, CardPosition.HAND), (who.id, CardPosition.LEFT), state
                )
            shuffle_cards(who.left, state)
            draw = who.left[: min(count, len(who.left))]
            move_cards(draw, (who.id, CardPosition.LEFT), (who.id, CardPosition.HAND), state)
