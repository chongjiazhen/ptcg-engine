from ptcg.core.action import UseSupporterAction
from ptcg.core.card import SupporterCard
from ptcg.core.enums import CardPosition, CardType
from ptcg.utils.utils import current_player, move_cards, opponent_player, shuffle_cards


class POR076Judge(SupporterCard):
    def __init__(self):
        super().__init__()
        self.set_name = "POR"
        self.number = "076"
        self.id = f"{self.set_name}-{self.number}"
        self.name = "Judge"
        self.cardType = CardType.NONE
        self.text = "Each player shuffles their hand into their deck and draws 4 cards."

    def get_actions(self, state):
        player = current_player(state)
        if not player.supporterPlayedTurn:
            return [UseSupporterAction(state.turn, self)]
        return []

    def reduce_action(self, action, state):
        if not isinstance(action, UseSupporterAction):
            return
        player = current_player(state)
        move_cards(self, (player.id, CardPosition.HAND), (player.id, CardPosition.DISCARD), state)
        player.supporterPlayedTurn = True

        for who in (player, opponent_player(state)):
            if who.hand:
                move_cards(
                    who.hand[:], (who.id, CardPosition.HAND), (who.id, CardPosition.LEFT), state
                )
            shuffle_cards(who.left, state)
            draw = who.left[: min(4, len(who.left))]
            move_cards(draw, (who.id, CardPosition.LEFT), (who.id, CardPosition.HAND), state)
