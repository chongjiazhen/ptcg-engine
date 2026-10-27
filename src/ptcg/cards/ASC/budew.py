from ptcg.core.action import AttackAction, PlayPokemonAction
from ptcg.core.attack import Attack
from ptcg.core.card import PokemonCard
from ptcg.core.enums import CardType, PokemonPosition, PokemonRule, PokemonType, Stage
from ptcg.core.reducer import reduce_attack_action, reduce_play_pokemon_action
from ptcg.utils.utils import check_energy, opponent_active, opponent_player


class ASC016Budew(PokemonCard):
    def __init__(self) -> None:
        super().__init__()
        self.name = "Budew"
        self.set_name = "ASC"
        self.number = "016"
        self.id = f"{self.set_name}-{self.number}"

        self.hp = 30
        self.pokemonType = PokemonType.NORMAL
        self.pokemonRule = PokemonRule.NONE
        self.stage = Stage.BASIC
        self.cardType = CardType.GRASS

        self.retreat = []
        self.weakness = [CardType.FIRE]
        self.resistance = []
        self.prize = 1

        self.energy = []
        self.attachment = []
        self.evolved = []
        self.evolveFrom = []

        self.attacks = [
            Attack(
                {
                    "name": "Itchy Pollen",
                    "damage": 10,
                    "cost": [],
                    "text": "During your opponent's next turn, they can't play any Item cards from their hand.",
                }
            )
        ]

    def get_actions(self, state):
        actions = []
        if self.position == PokemonPosition.ACTIVE:
            for attack in self.attacks:
                if check_energy(attack.cost, self.energy):
                    for target in opponent_active(state):
                        actions.append(AttackAction(state.turn, self, attack, target))
        return actions

    def reduce_action(self, action, state):
        if isinstance(action, PlayPokemonAction):
            reduce_play_pokemon_action(action, state)

        elif isinstance(action, AttackAction):
            # Set before the attack: reduce_attack_action ends the turn.
            opponent_player(state).itemLocked = True
            yield from reduce_attack_action(action, state)
