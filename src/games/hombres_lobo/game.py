import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from .roles import Role, Team, ROLES_INFO, get_roles_for_players


class GamePhase(Enum):
    LOBBY = "lobby"
    NIGHT = "night"
    DAY_ANNOUNCEMENT = "day_announcement"
    DAY_DISCUSSION = "day_discussion"
    DAY_VOTING = "day_voting"
    FINISHED = "finished"


class NightPhase(Enum):
    CUPIDO = "cupido"
    PROTECTOR = "protector"
    LOBOS = "lobos"
    VIDENTE = "vidente"
    BRUJA = "bruja"
    FLAUTISTA = "flautista"
    DONE = "done"


@dataclass
class Player:
    user_id: int
    name: str
    username: Optional[str] = None
    role: Optional[Role] = None
    is_alive: bool = True
    has_seen_role: bool = False
    # Estados especiales
    is_protected: bool = False
    is_in_love: bool = False
    lover_id: Optional[int] = None
    is_enchanted: bool = False  # Por el flautista
    # Acciones
    vote: Optional[int] = None
    night_action_done: bool = False


@dataclass
class WerewolfGame:
    chat_id: int
    creator_id: int
    phase: GamePhase = GamePhase.LOBBY
    night_phase: NightPhase = NightPhase.CUPIDO
    players: dict = field(default_factory=dict)
    day_number: int = 0
    min_players: int = 6
    # Acciones nocturnas
    wolf_target: Optional[int] = None
    protected_player: Optional[int] = None
    last_protected: Optional[int] = None
    witch_heal_used: bool = False
    witch_kill_used: bool = False
    witch_heal_target: Optional[int] = None
    witch_kill_target: Optional[int] = None
    # Resultados de la noche
    night_deaths: list = field(default_factory=list)
    night_messages: list = field(default_factory=list)

    def add_player(self, user_id: int, name: str, username: Optional[str] = None) -> tuple[bool, str]:
        if self.phase != GamePhase.LOBBY:
            return False, "El juego ya ha comenzado."
        if user_id in self.players:
            return False, "Ya estas en la partida."

        self.players[user_id] = Player(user_id=user_id, name=name, username=username)
        return True, f"{name} se ha unido! ({len(self.players)} jugadores)"

    def remove_player(self, user_id: int) -> tuple[bool, str]:
        if user_id not in self.players:
            return False, "No estas en la partida."

        name = self.players[user_id].name
        del self.players[user_id]

        if len(self.players) == 0:
            return True, "GAME_EMPTY"

        return True, f"{name} ha salido. ({len(self.players)} jugadores)"

    def start_game(self, user_id: int) -> tuple[bool, str]:
        if user_id != self.creator_id:
            return False, "Solo el creador puede iniciar la partida."
        if len(self.players) < self.min_players:
            return False, f"Se necesitan al menos {self.min_players} jugadores."

        # Asignar roles
        roles = get_roles_for_players(len(self.players))
        random.shuffle(roles)

        for player, role in zip(self.players.values(), roles):
            player.role = role

        self.phase = GamePhase.NIGHT
        self.day_number = 1
        self._reset_night_phase()

        return True, self._get_night_start_message()

    def _reset_night_phase(self):
        self.night_phase = NightPhase.CUPIDO
        self.wolf_target = None
        self.protected_player = None
        self.witch_heal_target = None
        self.witch_kill_target = None
        self.night_deaths = []
        self.night_messages = []
        for player in self.players.values():
            player.is_protected = False
            player.night_action_done = False
            player.vote = None

    def _get_night_start_message(self) -> str:
        return f"NOCHE {self.day_number}\n\nLa aldea duerme... Los roles con acciones nocturnas seran contactados."

    def get_player_role(self, user_id: int) -> tuple[bool, str]:
        if user_id not in self.players:
            return False, "No estas en esta partida."

        player = self.players[user_id]
        player.has_seen_role = True

        role_info = ROLES_INFO[player.role]
        return True, f"{role_info.emoji} Eres: {role_info.name}\n\n{role_info.description}"

    def get_wolves(self) -> list[Player]:
        return [p for p in self.players.values() if p.role == Role.HOMBRE_LOBO and p.is_alive]

    def get_alive_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.is_alive]

    def get_alive_non_wolves(self) -> list[Player]:
        return [p for p in self.players.values() if p.is_alive and p.role != Role.HOMBRE_LOBO]

    # Acciones nocturnas
    def cupido_action(self, cupido_id: int, lover1_id: int, lover2_id: int) -> tuple[bool, str]:
        if self.day_number != 1:
            return False, "Cupido solo actua la primera noche."

        player = self.players.get(cupido_id)
        if not player or player.role != Role.CUPIDO:
            return False, "No eres Cupido."

        if lover1_id not in self.players or lover2_id not in self.players:
            return False, "Jugadores invalidos."

        self.players[lover1_id].is_in_love = True
        self.players[lover1_id].lover_id = lover2_id
        self.players[lover2_id].is_in_love = True
        self.players[lover2_id].lover_id = lover1_id
        player.night_action_done = True

        return True, f"Has enamorado a {self.players[lover1_id].name} y {self.players[lover2_id].name}!"

    def protector_action(self, protector_id: int, target_id: int) -> tuple[bool, str]:
        player = self.players.get(protector_id)
        if not player or player.role != Role.PROTECTOR:
            return False, "No eres el Protector."

        if target_id == self.last_protected:
            return False, "No puedes proteger al mismo jugador dos noches seguidas."

        if target_id not in self.players or not self.players[target_id].is_alive:
            return False, "Jugador invalido."

        self.protected_player = target_id
        self.players[target_id].is_protected = True
        player.night_action_done = True

        return True, f"Proteges a {self.players[target_id].name} esta noche."

    def wolf_vote(self, wolf_id: int, target_id: int) -> tuple[bool, str]:
        player = self.players.get(wolf_id)
        if not player or player.role != Role.HOMBRE_LOBO:
            return False, "No eres un Hombre Lobo."

        target = self.players.get(target_id)
        if not target or not target.is_alive or target.role == Role.HOMBRE_LOBO:
            return False, "Objetivo invalido."

        player.vote = target_id
        player.night_action_done = True

        # Contar votos de lobos
        wolves = self.get_wolves()
        votes = [w.vote for w in wolves if w.vote]

        if len(votes) == len(wolves):
            # Todos votaron, elegir victima
            from collections import Counter
            vote_count = Counter(votes)
            self.wolf_target = vote_count.most_common(1)[0][0]
            return True, f"Los lobos han elegido a {self.players[self.wolf_target].name}."

        return True, f"Voto registrado. ({len(votes)}/{len(wolves)} lobos han votado)"

    def vidente_action(self, vidente_id: int, target_id: int) -> tuple[bool, str]:
        player = self.players.get(vidente_id)
        if not player or player.role != Role.VIDENTE:
            return False, "No eres la Vidente."

        target = self.players.get(target_id)
        if not target or not target.is_alive:
            return False, "Jugador invalido."

        player.night_action_done = True
        role_info = ROLES_INFO[target.role]

        if target.role == Role.HOMBRE_LOBO:
            return True, f"{target.name} es un {role_info.emoji} HOMBRE LOBO!"
        else:
            return True, f"{target.name} es {role_info.emoji} {role_info.name}."

    def bruja_action(self, bruja_id: int, heal: bool = False, kill_target: Optional[int] = None) -> tuple[bool, str]:
        player = self.players.get(bruja_id)
        if not player or player.role != Role.BRUJA:
            return False, "No eres la Bruja."

        messages = []

        if heal and not self.witch_heal_used and self.wolf_target:
            self.witch_heal_target = self.wolf_target
            self.witch_heal_used = True
            messages.append(f"Usas la pocion de vida para salvar a {self.players[self.wolf_target].name}.")

        if kill_target and not self.witch_kill_used:
            if kill_target in self.players and self.players[kill_target].is_alive:
                self.witch_kill_target = kill_target
                self.witch_kill_used = True
                messages.append(f"Usas la pocion de muerte en {self.players[kill_target].name}.")

        player.night_action_done = True

        if not messages:
            return True, "No usas ninguna pocion esta noche."
        return True, "\n".join(messages)

    def resolve_night(self) -> tuple[bool, str]:
        """Resuelve la noche y devuelve el resultado."""
        deaths = []

        # Victima de los lobos
        if self.wolf_target:
            target = self.players[self.wolf_target]
            # Verificar proteccion y curacion
            if not target.is_protected and self.witch_heal_target != self.wolf_target:
                deaths.append(self.wolf_target)

        # Victima de la bruja
        if self.witch_kill_target:
            if self.witch_kill_target not in deaths:
                deaths.append(self.witch_kill_target)

        # Procesar muertes
        for death_id in deaths:
            self.players[death_id].is_alive = False
            # Verificar enamorados
            if self.players[death_id].is_in_love:
                lover_id = self.players[death_id].lover_id
                if lover_id and self.players[lover_id].is_alive:
                    self.players[lover_id].is_alive = False
                    deaths.append(lover_id)

        self.night_deaths = deaths
        self.last_protected = self.protected_player

        # Mensaje de amanecer
        if not deaths:
            msg = f"DIA {self.day_number}\n\nAmanece en la aldea. Nadie ha muerto esta noche."
        else:
            dead_names = [self.players[d].name for d in deaths]
            msg = f"DIA {self.day_number}\n\nAmanece en la aldea.\n\nHan muerto: {', '.join(dead_names)}"

        # Verificar fin de juego
        winner = self._check_winner()
        if winner:
            self.phase = GamePhase.FINISHED
            return True, msg + f"\n\n{winner}"

        self.phase = GamePhase.DAY_DISCUSSION
        return True, msg + "\n\nEs hora de debatir. Usen /votar cuando esten listos."

    def start_voting(self) -> tuple[bool, str]:
        if self.phase != GamePhase.DAY_DISCUSSION:
            return False, "No es momento de votar."

        self.phase = GamePhase.DAY_VOTING
        for player in self.players.values():
            player.vote = None

        alive = self.get_alive_players()
        return True, f"VOTACION\n\nVoten por quien quieren linchar. ({len(alive)} jugadores vivos)"

    def day_vote(self, voter_id: int, target_id: int) -> tuple[bool, str]:
        if self.phase != GamePhase.DAY_VOTING:
            return False, "No es momento de votar."

        voter = self.players.get(voter_id)
        if not voter or not voter.is_alive:
            return False, "No puedes votar."

        target = self.players.get(target_id)
        if not target or not target.is_alive:
            return False, "Objetivo invalido."

        voter.vote = target_id

        alive = self.get_alive_players()
        votes = sum(1 for p in alive if p.vote)

        if votes == len(alive):
            return self._resolve_voting()

        return True, f"Voto registrado. ({votes}/{len(alive)})"

    def _resolve_voting(self) -> tuple[bool, str]:
        from collections import Counter

        alive = self.get_alive_players()
        votes = [p.vote for p in alive if p.vote]
        vote_count = Counter(votes)

        if not vote_count:
            self.phase = GamePhase.NIGHT
            self.day_number += 1
            self._reset_night_phase()
            return True, "Nadie fue linchado.\n\n" + self._get_night_start_message()

        most_voted_id, max_votes = vote_count.most_common(1)[0]

        # Verificar empate
        tied = [uid for uid, v in vote_count.items() if v == max_votes]
        if len(tied) > 1:
            self.phase = GamePhase.NIGHT
            self.day_number += 1
            self._reset_night_phase()
            return True, "Empate en la votacion. Nadie fue linchado.\n\n" + self._get_night_start_message()

        # Linchar
        lynched = self.players[most_voted_id]
        lynched.is_alive = False
        role_info = ROLES_INFO[lynched.role]

        msg = f"El pueblo ha decidido linchar a {lynched.name}.\n"
        msg += f"Era: {role_info.emoji} {role_info.name}\n"

        # Verificar enamorado
        if lynched.is_in_love and lynched.lover_id:
            lover = self.players[lynched.lover_id]
            if lover.is_alive:
                lover.is_alive = False
                lover_role = ROLES_INFO[lover.role]
                msg += f"\n{lover.name} muere de amor. Era: {lover_role.emoji} {lover_role.name}\n"

        # Verificar fin de juego
        winner = self._check_winner()
        if winner:
            self.phase = GamePhase.FINISHED
            return True, msg + f"\n{winner}"

        # Cazador
        if lynched.role == Role.CAZADOR:
            msg += "\nEl Cazador puede elegir a quien llevarse con el! Usa /disparar"
            return True, msg

        self.phase = GamePhase.NIGHT
        self.day_number += 1
        self._reset_night_phase()
        return True, msg + "\n" + self._get_night_start_message()

    def hunter_shot(self, hunter_id: int, target_id: int) -> tuple[bool, str]:
        hunter = self.players.get(hunter_id)
        if not hunter or hunter.role != Role.CAZADOR:
            return False, "No eres el Cazador."
        if hunter.is_alive:
            return False, "El Cazador solo dispara al morir."

        target = self.players.get(target_id)
        if not target or not target.is_alive:
            return False, "Objetivo invalido."

        target.is_alive = False
        role_info = ROLES_INFO[target.role]

        msg = f"El Cazador dispara a {target.name}!\nEra: {role_info.emoji} {role_info.name}\n"

        winner = self._check_winner()
        if winner:
            self.phase = GamePhase.FINISHED
            return True, msg + f"\n{winner}"

        self.phase = GamePhase.NIGHT
        self.day_number += 1
        self._reset_night_phase()
        return True, msg + "\n" + self._get_night_start_message()

    def _check_winner(self) -> Optional[str]:
        alive = self.get_alive_players()
        wolves_alive = [p for p in alive if p.role == Role.HOMBRE_LOBO]
        villagers_alive = [p for p in alive if p.role != Role.HOMBRE_LOBO]

        if not wolves_alive:
            return "GANAN LOS ALDEANOS! Todos los lobos han sido eliminados."

        if len(wolves_alive) >= len(villagers_alive):
            return "GANAN LOS HOMBRES LOBO! Han igualado o superado a los aldeanos."

        # Verificar flautista
        flautista = next((p for p in alive if p.role == Role.FLAUTISTA), None)
        if flautista:
            others = [p for p in alive if p.user_id != flautista.user_id]
            if all(p.is_enchanted for p in others):
                return f"GANA EL FLAUTISTA ({flautista.name})! Todos estan hechizados."

        return None

    def get_players_list(self) -> str:
        lines = ["Jugadores:"]
        for i, player in enumerate(self.players.values(), 1):
            status = "" if player.is_alive else " (muerto)"
            creator = " (creador)" if player.user_id == self.creator_id else ""
            lines.append(f"{i}. {player.name}{status}{creator}")
        return "\n".join(lines)

    def get_alive_list(self) -> str:
        alive = self.get_alive_players()
        lines = [f"Jugadores vivos ({len(alive)}):"]
        for i, player in enumerate(alive, 1):
            lines.append(f"{i}. {player.name}")
        return "\n".join(lines)
