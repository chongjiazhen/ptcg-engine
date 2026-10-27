from ptcg.core.ability import ActiveAbility
from ptcg.core.action import AttackAction, PlayPokemonAction, choose_card_actions
from ptcg.core.attack import Attack
from ptcg.core.card import PokemonCard
from ptcg.core.enums import (
    AbilityType,
    CardPosition,
    CardType,
    PokemonPosition,
    PokemonRule,
    PokemonType,
    Stage,
    SuperType,
    TrainerType,
)
from ptcg.core.reducer import (
    _force_active_replacement,
    reduce_attack_damage,
    reduce_choose_card_actions,
    reduce_play_pokemon_action,
)
from ptcg.utils.utils import (
    check_energy,
    current_player,
    move_cards,
    next_turn,
    opponent_active,
    shuffle_cards,
)

ABILITY_NAME = "Last-Ditch Catch"


class POR062MeowthEX(PokemonCard):
    def __init__(self) -> None:
        super().__init__()
        self.set_name = "POR"
        self.number = "062"
        self.id = f"{self.set_name}-{self.number}"
        self.name = "Meowth ex"
        self.hp = 170
        self.pokemonType = PokemonType.EX
        self.pokemonRule = PokemonRule.NONE
        self.stage = Stage.BASIC
        self.cardType = CardType.COLORLESS
        self.retreat = [CardType.COLORLESS]
        self.weakness = [CardType.FIGHTING]
        self.resistance = []
        self.prize = 2

        self.energy = []
        self.attachment = []
        self.evolveFrom = []
        self.evolved = []

        self.attacks = [
            Attack(
                {
                    "name": "Tuck Tail",
                    "damage": 60,
                    "cost": [CardType.COLORLESS, CardType.COLORLESS, CardType.COLORLESS],
                    "text": "Put this Pokémon and all attached cards into your hand.",
                }
            )
        ]

        self.abilityUsed = False
        self.ability = [
            ActiveAbility(
                {
                    "name": ABILITY_NAME,
                    "abilityType": AbilityType.ACTIVE_ABILITY,
                    "onceUsedPerTurn": True,
                    "text": "Once during your turn, when you play this Pokémon from your hand "
                    "onto your Bench, you may use this Ability. Search your deck for a Supporter "
                    "card, reveal it, and put it into your hand. Then, shuffle your deck. "
                    'You can\'t use more than 1 Ability that has "Last-Ditch" in its name '
                    "each turn.",
                }
            )
        ]

    def get_actions(self, state):
        actions = []
        if self.position == PokemonPosition.ACTIVE:
            for attack in self.attacks:
                if check_energy(attack.cost, self.energy):
                    targets = opponent_active(state)
                    if targets:
                        actions.append(AttackAction(state.turn, self, attack, targets[0]))
        return actions

    def reduce_action(self, action, state):
        if isinstance(action, PlayPokemonAction):
            reduce_play_pokemon_action(action, state)
            if action.position == PokemonPosition.BENCH:
                yield from self._last_ditch_catch(state)

        elif isinstance(action, AttackAction):
            yield from reduce_attack_damage(action, state)
            player = current_player(state)
            if self in player.active:
                yield from self._tuck_tail(player, state)
            next_turn(state)

    def _last_ditch_catch(self, state):
        player = current_player(state)
        if any(used and "Last-Ditch" in name for name, used in player.onceUsedTurn.items()):
            return
        supporters = [
            card
            for card in player.left
            if card.superType == SuperType.TRAINER and card.trainerType == TrainerType.SUPPORTER
        ]
        if not supporters:
            return
        tips = "Last-Ditch Catch: you may choose 1 Supporter card from your deck."
        actions = choose_card_actions(player.id, player.id, 0, 1, supporters, tips=tips, source=self)
        chosen = yield from reduce_choose_card_actions(actions, state)
        if not chosen:
            return
        move_cards(chosen, (player.id, CardPosition.LEFT), (player.id, CardPosition.HAND), state)
        shuffle_cards(player.left, state)
        player.onceUsedTurn[ABILITY_NAME] = True

    def _tuck_tail(self, player, state):
        player.active.remove(self)
        for card in self.attachment:
            card.cardPosition = CardPosition.HAND
            player.hand.append(card)
        self.cardPosition = CardPosition.HAND
        player.hand.append(self)
        for idx, card in enumerate(player.hand):
            card.index = idx + 1
        self.attachment = []
        self.energy = []
        self.position = None
        self.hp = 170  # damage counters leave play with the card

        if player.bench:
            yield from _force_active_replacement(player, state, state.turn)
