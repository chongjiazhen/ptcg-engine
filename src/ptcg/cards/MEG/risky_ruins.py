from ptcg.core.ability import PassiveAbility
from ptcg.core.action import DiscardStadiumAction, PlayPokemonAction, PutStadiumAction
from ptcg.core.card import StadiumCard
from ptcg.core.enums import (
    AbilityTrigger,
    AbilityType,
    CardPosition,
    CardType,
    PokemonPosition,
    Stage,
)
from ptcg.utils.utils import current_player, discard_card, move_cards, opponent_player


class MEG127RiskyRuins(StadiumCard):
    def __init__(self):
        super().__init__()
        self.set_name = "MEG"
        self.number = "127"
        self.id = f"{self.set_name}-{self.number}"
        self.name = "Risky Ruins"
        self.cardType = CardType.NONE
        self.text = (
            "Whenever any player puts a Basic non-[D] Pokémon onto their Bench during their turn, "
            "place 2 damage counters on that Pokémon."
        )
        self.playedFrom = None
        self.ability = [
            PassiveAbility(
                {
                    "name": "Risky Ruins",
                    "abilityType": AbilityType.PASSIVE_ABILITY,
                    "abilityTrigger": AbilityTrigger.BENCH_ENTRY,
                    "onceUsedPerTurn": False,
                    "text": self.text,
                }
            )
        ]

    def use_ability(self, action, state):
        if not isinstance(action, PlayPokemonAction) or action.position != PokemonPosition.BENCH:
            return
        pokemon = action.source
        if action.playerId != state.turn:
            return
        if pokemon.stage == Stage.BASIC and pokemon.cardType != CardType.DARK:
            pokemon.hp -= 20

    def get_actions(self, state):
        player = current_player(state)
        if not player.firstTurn and self in player.hand:
            return [PutStadiumAction(player.id, self)]
        return []

    def reduce_action(self, action, state):
        if isinstance(action, PutStadiumAction):
            player = current_player(state)

            if state.stadium:
                for stadium in state.stadium[:]:
                    state.stadium.remove(stadium)
                    discard_card(player, stadium)

            move_cards(
                self,
                (player.id, CardPosition.HAND),
                (player.id, CardPosition.STADIUM),
                state,
            )
            self.playedFrom = player.id

        elif isinstance(action, DiscardStadiumAction):
            player = current_player(state)
            opponent = opponent_player(state)

            state.stadium.remove(self)
            if self.playedFrom == player.id:
                discard_card(player, self)
            elif self.playedFrom == opponent.id:
                discard_card(opponent, self)
