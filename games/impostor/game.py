import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from .words import PALABRAS


class GameState(Enum):
    LOBBY = "lobby"
    PLAYING = "playing"
    VOTING = "voting"
    FINISHED = "finished"


@dataclass
class Player:
    user_id: int
    name: str
    username: Optional[str] = None
    is_impostor: bool = False
    has_seen_role: bool = False
    vote: Optional[int] = None


@dataclass
class ImpostorGame:
    chat_id: int
    creator_id: int
    state: GameState = GameState.LOBBY
    players: dict = field(default_factory=dict)
    word: str = ""
    impostor_id: Optional[int] = None
    min_players: int = 3

    def add_player(self, user_id: int, name: str, username: Optional[str] = None) -> tuple[bool, str]:
        if self.state != GameState.LOBBY:
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

        # Elegir palabra e impostor
        self.word = random.choice(PALABRAS)
        self.impostor_id = random.choice(list(self.players.keys()))
        self.players[self.impostor_id].is_impostor = True
        self.state = GameState.PLAYING

        return True, "El juego ha comenzado!"

    def get_player_role(self, user_id: int) -> tuple[bool, str]:
        if user_id not in self.players:
            return False, "No estas en esta partida."
        if self.state != GameState.PLAYING:
            return False, "El juego no esta en curso."

        player = self.players[user_id]
        player.has_seen_role = True

        if player.is_impostor:
            return True, "Eres el IMPOSTOR! No conoces la palabra secreta. Intenta descubrirla sin que te descubran."
        else:
            return True, f"La palabra secreta es: {self.word}"

    def all_players_seen_role(self) -> bool:
        return all(p.has_seen_role for p in self.players.values())

    def start_voting(self) -> tuple[bool, str]:
        if self.state != GameState.PLAYING:
            return False, "El juego no esta en curso."

        self.state = GameState.VOTING
        for player in self.players.values():
            player.vote = None

        return True, "Votacion iniciada! Voten por quien creen que es el impostor."

    def vote(self, voter_id: int, target_id: int) -> tuple[bool, str]:
        if self.state != GameState.VOTING:
            return False, "No es momento de votar."
        if voter_id not in self.players:
            return False, "No estas en la partida."
        if target_id not in self.players:
            return False, "Ese jugador no existe."
        if voter_id == target_id:
            return False, "No puedes votar por ti mismo."

        self.players[voter_id].vote = target_id
        votes_count = sum(1 for p in self.players.values() if p.vote is not None)

        return True, f"Voto registrado! ({votes_count}/{len(self.players)})"

    def all_voted(self) -> bool:
        return all(p.vote is not None for p in self.players.values())

    def get_results(self) -> tuple[str, bool]:
        """Devuelve (mensaje_resultado, ganaron_jugadores)"""
        votes = {}
        for player in self.players.values():
            if player.vote:
                votes[player.vote] = votes.get(player.vote, 0) + 1

        if not votes:
            return "Nadie voto!", False

        max_votes = max(votes.values())
        most_voted = [uid for uid, v in votes.items() if v == max_votes]

        result = "RESULTADOS:\n\n"
        for uid, player in self.players.items():
            voted_for = self.players.get(player.vote)
            voted_name = voted_for.name if voted_for else "Nadie"
            result += f"{player.name} voto por: {voted_name}\n"

        result += f"\nLa palabra era: {self.word}\n"
        result += f"El impostor era: {self.players[self.impostor_id].name}\n\n"

        if len(most_voted) == 1 and most_voted[0] == self.impostor_id:
            result += "GANAN LOS JUGADORES! Encontraron al impostor!"
            return result, True
        else:
            result += "GANA EL IMPOSTOR! No lo descubrieron!"
            return result, False

    def get_players_list(self) -> str:
        if not self.players:
            return "No hay jugadores."

        lines = ["Jugadores:"]
        for i, player in enumerate(self.players.values(), 1):
            creator_mark = " (creador)" if player.user_id == self.creator_id else ""
            lines.append(f"{i}. {player.name}{creator_mark}")
        return "\n".join(lines)

    def get_voting_options(self) -> list[tuple[int, str]]:
        return [(p.user_id, p.name) for p in self.players.values()]
