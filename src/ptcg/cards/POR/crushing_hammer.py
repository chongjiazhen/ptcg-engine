from ptcg.core.action import UseItemAction, choose_card_actions
from ptcg.core.card import ItemCard
from ptcg.core.enums import CardPosition, CardType, Coin, PokemonPosition, SuperType
from ptcg.core.reducer import reduce_choose_card_actions
from ptcg.utils.utils import (
    current_player,
    flip_coin,
    move_cards,
    opponent_all_pokemon,
    opponent_player,
)


class POR071CrushingHammer(ItemCard):
    def __init__(self):
        super().__init__()
        self.set_name = "POR"
        self.number = "071"
        self.id = f"{self.set_name}-{self.number}"
        self.name = "Crushing Hammer"
        self.cardType = CardType.NONE
        self.text = (
            "Flip a coin. If heads, discard an Energy attached to 1 of your opponent's Pokémon."
        )

    def get_actions(self, state):
        return [UseItemAction(state.turn, self)]

    def reduce_action(self, action, state):
        if not isinstance(action, UseItemAction):
            return
        player = current_player(state)
        opponent = opponent_player(state)
        move_cards(self, (player.id, CardPosition.HAND), (player.id, CardPosition.DISCARD), state)

        if flip_coin(state) != Coin.HEAD:
            return

        victims = [
            p
            for p in opponent_all_pokemon(state)
            if any(c.superType == SuperType.ENERGY for c in p.attachment)
        ]
        if not victims:
            return

        tips = "Heads. Choose 1 of your opponent's Pokémon to discard an Energy from."
        actions = choose_card_actions(player.id, player.id, 1, 1, victims, tips=tips, source=self)
        victim = (yield from reduce_choose_card_actions(actions, state))[0]

        energies = [c for c in victim.attachment if c.superType == SuperType.ENERGY]
        tips = "Choose an Energy attached to that Pokémon to discard."
        actions = choose_card_actions(player.id, player.id, 1, 1, energies, tips=tips, source=self)
        energy = (yield from reduce_choose_card_actions(actions, state))[0]

        if victim.position == PokemonPosition.ACTIVE:
            area = (opponent.id, CardPosition.ACTIVE_ATTACHMENT)
        else:
            area = (opponent.id, CardPosition.BENCH_ATTACHMENT, victim.index)
        for provided in energy.provides:
            if provided in victim.energy:
                victim.energy.remove(provided)
        move_cards(energy, area, (opponent.id, CardPosition.DISCARD), state)
