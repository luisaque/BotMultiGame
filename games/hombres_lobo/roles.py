from enum import Enum
from dataclasses import dataclass
from typing import Optional


class Role(Enum):
    # Bando Aldeanos
    ALDEANO = "aldeano"
    VIDENTE = "vidente"
    BRUJA = "bruja"
    CAZADOR = "cazador"
    CUPIDO = "cupido"
    PROTECTOR = "protector"
    # Bando Lobos
    HOMBRE_LOBO = "hombre_lobo"
    # Independientes
    FLAUTISTA = "flautista"


class Team(Enum):
    ALDEANOS = "aldeanos"
    LOBOS = "lobos"
    INDEPENDIENTE = "independiente"


@dataclass
class RoleInfo:
    name: str
    emoji: str
    team: Team
    description: str
    night_action: bool = False
    priority: int = 0  # Orden de accion nocturna (menor = primero)


ROLES_INFO = {
    Role.ALDEANO: RoleInfo(
        name="Aldeano",
        emoji="👨‍🌾",
        team=Team.ALDEANOS,
        description="Un aldeano comun sin poderes especiales. Debe usar su intuicion para descubrir a los lobos.",
        night_action=False,
    ),
    Role.VIDENTE: RoleInfo(
        name="Vidente",
        emoji="🔮",
        team=Team.ALDEANOS,
        description="Cada noche puede ver el rol de un jugador.",
        night_action=True,
        priority=20,
    ),
    Role.BRUJA: RoleInfo(
        name="Bruja",
        emoji="🧙‍♀️",
        team=Team.ALDEANOS,
        description="Tiene 2 pociones: una para salvar a la victima de los lobos y otra para matar a alguien.",
        night_action=True,
        priority=30,
    ),
    Role.CAZADOR: RoleInfo(
        name="Cazador",
        emoji="🏹",
        team=Team.ALDEANOS,
        description="Cuando muere, puede llevarse a otro jugador con el.",
        night_action=False,
    ),
    Role.CUPIDO: RoleInfo(
        name="Cupido",
        emoji="💘",
        team=Team.ALDEANOS,
        description="La primera noche elige a dos enamorados. Si uno muere, el otro tambien.",
        night_action=True,
        priority=1,
    ),
    Role.PROTECTOR: RoleInfo(
        name="Protector",
        emoji="🛡️",
        team=Team.ALDEANOS,
        description="Cada noche protege a un jugador de los lobos. No puede proteger al mismo dos noches seguidas.",
        night_action=True,
        priority=5,
    ),
    Role.HOMBRE_LOBO: RoleInfo(
        name="Hombre Lobo",
        emoji="🐺",
        team=Team.LOBOS,
        description="Cada noche se reune con los otros lobos para elegir una victima.",
        night_action=True,
        priority=10,
    ),
    Role.FLAUTISTA: RoleInfo(
        name="Flautista",
        emoji="🪈",
        team=Team.INDEPENDIENTE,
        description="Cada noche hechiza a 2 jugadores. Gana si todos los vivos estan hechizados.",
        night_action=True,
        priority=40,
    ),
}


def get_roles_for_players(num_players: int) -> list[Role]:
    """Devuelve la lista de roles segun el numero de jugadores."""
    if num_players < 6:
        return []

    roles = []

    # Lobos: 1 por cada 4-5 jugadores
    num_lobos = max(1, num_players // 5)
    roles.extend([Role.HOMBRE_LOBO] * num_lobos)

    # Roles especiales fijos
    roles.append(Role.VIDENTE)

    if num_players >= 8:
        roles.append(Role.BRUJA)

    if num_players >= 9:
        roles.append(Role.CAZADOR)

    if num_players >= 10:
        roles.append(Role.PROTECTOR)

    if num_players >= 12:
        roles.append(Role.CUPIDO)

    # Rellenar con aldeanos
    num_aldeanos = num_players - len(roles)
    roles.extend([Role.ALDEANO] * num_aldeanos)

    return roles
