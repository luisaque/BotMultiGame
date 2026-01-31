import os
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from games.impostor import ImpostorGame
from games.hombres_lobo import WerewolfGame
from games.hombres_lobo.roles import Role, ROLES_INFO

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Almacen de partidas activas
impostor_games: dict[int, ImpostorGame] = {}
werewolf_games: dict[int, WerewolfGame] = {}

# Mapeo de user_id -> chat_id para acciones privadas
user_to_game: dict[int, int] = {}


# ==================== UTILIDADES ====================

def get_game_for_user(user_id: int) -> tuple[WerewolfGame | None, int | None]:
    """Obtiene el juego en el que participa un usuario."""
    chat_id = user_to_game.get(user_id)
    if chat_id:
        game = werewolf_games.get(chat_id)
        if game and user_id in game.players:
            return game, chat_id
    return None, None


async def send_night_actions(context: ContextTypes.DEFAULT_TYPE, game: WerewolfGame, chat_id: int):
    """Envia las acciones nocturnas a cada rol."""

    from games.hombres_lobo.roles import Role

    # Mensaje en el grupo
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🌙 *NOCHE {game.day_number}*\n\nLa aldea duerme... Los roles especiales estan actuando.",
        parse_mode="Markdown"
    )

    # Lista de jugadores vivos para botones
    alive_players = game.get_alive_players()

    for player in alive_players:
        role = player.role

        try:
            # CUPIDO - Solo primera noche
            if role == Role.CUPIDO and game.day_number == 1:
                keyboard = []
                for p in alive_players:
                    keyboard.append([InlineKeyboardButton(
                        f"💕 {p.name}",
                        callback_data=f"cupido_{chat_id}_{p.user_id}"
                    )])
                keyboard.append([InlineKeyboardButton("✅ Confirmar enamorados", callback_data=f"cupido_confirm_{chat_id}")])

                await context.bot.send_message(
                    chat_id=player.user_id,
                    text="💘 *CUPIDO*\n\nElige a 2 jugadores para enamorarlos.\n(Haz click en 2 nombres)",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )

            # PROTECTOR
            elif role == Role.PROTECTOR:
                keyboard = []
                for p in alive_players:
                    if p.user_id != game.last_protected:  # No puede repetir
                        keyboard.append([InlineKeyboardButton(
                            f"🛡️ {p.name}",
                            callback_data=f"protector_{chat_id}_{p.user_id}"
                        )])

                await context.bot.send_message(
                    chat_id=player.user_id,
                    text="🛡️ *PROTECTOR*\n\n¿A quien proteges esta noche?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )

            # HOMBRES LOBO
            elif role == Role.HOMBRE_LOBO:
                # Mostrar quienes son los otros lobos
                wolves = game.get_wolves()
                wolf_names = [w.name for w in wolves if w.user_id != player.user_id]

                keyboard = []
                for p in game.get_alive_non_wolves():
                    keyboard.append([InlineKeyboardButton(
                        f"🩸 {p.name}",
                        callback_data=f"lobo_{chat_id}_{p.user_id}"
                    )])

                otros_lobos = f"\nOtros lobos: {', '.join(wolf_names)}" if wolf_names else ""

                await context.bot.send_message(
                    chat_id=player.user_id,
                    text=f"🐺 *HOMBRE LOBO*{otros_lobos}\n\n¿A quien devoran esta noche?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )

            # VIDENTE
            elif role == Role.VIDENTE:
                keyboard = []
                for p in alive_players:
                    if p.user_id != player.user_id:
                        keyboard.append([InlineKeyboardButton(
                            f"🔮 {p.name}",
                            callback_data=f"vidente_{chat_id}_{p.user_id}"
                        )])

                await context.bot.send_message(
                    chat_id=player.user_id,
                    text="🔮 *VIDENTE*\n\n¿A quien quieres investigar?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )

            # BRUJA - Se le envia despues de que los lobos elijan
            elif role == Role.BRUJA:
                # Guardar referencia para enviarle despues
                pass

        except Exception as e:
            print(f"Error enviando accion a {player.name}: {e}")


async def send_witch_action(context: ContextTypes.DEFAULT_TYPE, game: WerewolfGame, chat_id: int):
    """Envia la accion de la bruja despues de que los lobos elijan."""

    bruja = next((p for p in game.get_alive_players() if p.role == Role.BRUJA), None)
    if not bruja:
        return

    keyboard = []

    # Pocion de vida
    if not game.witch_heal_used and game.wolf_target:
        victim_name = game.players[game.wolf_target].name
        keyboard.append([InlineKeyboardButton(
            f"💚 Salvar a {victim_name}",
            callback_data=f"bruja_heal_{chat_id}"
        )])

    # Pocion de muerte
    if not game.witch_kill_used:
        keyboard.append([InlineKeyboardButton(
            "💀 Usar pocion de muerte",
            callback_data=f"bruja_kill_{chat_id}"
        )])

    keyboard.append([InlineKeyboardButton(
        "⏭️ No hacer nada",
        callback_data=f"bruja_skip_{chat_id}"
    )])

    victim_msg = ""
    if game.wolf_target:
        victim_msg = f"\n\nLos lobos atacaron a: {game.players[game.wolf_target].name}"

    pociones = []
    if not game.witch_heal_used:
        pociones.append("💚 Vida")
    if not game.witch_kill_used:
        pociones.append("💀 Muerte")
    pociones_msg = f"\nPociones disponibles: {', '.join(pociones)}" if pociones else "\nNo te quedan pociones."

    try:
        await context.bot.send_message(
            chat_id=bruja.user_id,
            text=f"🧙‍♀️ *BRUJA*{victim_msg}{pociones_msg}\n\n¿Que quieres hacer?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Error enviando accion a Bruja: {e}")


async def check_night_complete(context: ContextTypes.DEFAULT_TYPE, game: WerewolfGame, chat_id: int):
    """Verifica si todas las acciones nocturnas estan completas."""

    alive = game.get_alive_players()

    # Verificar Cupido (solo noche 1)
    cupido = next((p for p in alive if p.role == Role.CUPIDO), None)
    if cupido and game.day_number == 1 and not cupido.night_action_done:
        return False

    # Verificar Protector
    protector = next((p for p in alive if p.role == Role.PROTECTOR), None)
    if protector and not protector.night_action_done:
        return False

    # Verificar Lobos
    wolves = game.get_wolves()
    if not game.wolf_target:
        return False

    # Verificar Vidente
    vidente = next((p for p in alive if p.role == Role.VIDENTE), None)
    if vidente and not vidente.night_action_done:
        return False

    # Verificar Bruja
    bruja = next((p for p in alive if p.role == Role.BRUJA), None)
    if bruja and not bruja.night_action_done:
        # Enviar accion a la bruja si los lobos ya eligieron
        if game.wolf_target and not hasattr(game, '_witch_notified'):
            game._witch_notified = True
            await send_witch_action(context, game, chat_id)
        return False

    # Todas las acciones completas - resolver noche
    game._witch_notified = False
    success, msg = game.resolve_night()

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"☀️ {msg}",
        parse_mode="Markdown"
    )

    # Si el juego termino
    if game.phase.value == "finished":
        del werewolf_games[chat_id]
        # Limpiar mapeo de usuarios
        for player in game.players.values():
            if player.user_id in user_to_game:
                del user_to_game[player.user_id]

    return True


# ==================== COMANDOS GENERALES ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎭 El Impostor", callback_data="menu_impostor")],
        [InlineKeyboardButton("🐺 Hombres Lobo", callback_data="menu_werewolf")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🎮 *Bot MultiGame*\n\n"
        "Bienvenido! Elige un juego:\n\n"
        "🎭 *El Impostor* - 3+ jugadores\n"
        "🐺 *Hombres Lobo* - 6+ jugadores",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Comandos disponibles*\n\n"
        "*Generales:*\n"
        "/start - Menu principal\n"
        "/ayuda - Ver comandos\n\n"
        "*El Impostor:*\n"
        "/impostor - Crear partida\n"
        "/unirse - Unirse a partida\n"
        "/iniciar - Iniciar juego\n"
        "/votar - Iniciar votacion\n\n"
        "*Hombres Lobo:*\n"
        "/lobos - Crear partida\n"
        "/unirse - Unirse a partida\n"
        "/iniciar - Iniciar juego\n"
        "/votar - Iniciar votacion\n"
        "/vivos - Ver jugadores vivos\n\n",
        parse_mode="Markdown"
    )


# ==================== EL IMPOSTOR ====================

async def impostor_crear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id in impostor_games:
        await update.message.reply_text("Ya hay una partida de El Impostor en este chat.")
        return

    game = ImpostorGame(chat_id=chat_id, creator_id=user.id)
    game.add_player(user.id, user.full_name, user.username)
    impostor_games[chat_id] = game

    await update.message.reply_text(
        f"🎭 *El Impostor*\n\n"
        f"Partida creada por {user.full_name}!\n\n"
        f"Usen /unirse para entrar.\n"
        f"El creador usa /iniciar cuando esten listos.\n\n"
        f"Jugadores: 1/{game.min_players}+",
        parse_mode="Markdown"
    )


async def impostor_unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    game = impostor_games.get(chat_id)
    if not game:
        await update.message.reply_text("No hay partida activa. Usa /impostor para crear una.")
        return

    success, msg = game.add_player(user.id, user.full_name, user.username)
    await update.message.reply_text(msg)


async def impostor_salir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    game = impostor_games.get(chat_id)
    if not game:
        await update.message.reply_text("No hay partida activa.")
        return

    success, msg = game.remove_player(user.id)
    if msg == "GAME_EMPTY":
        del impostor_games[chat_id]
        await update.message.reply_text("Partida cancelada (no quedan jugadores).")
    else:
        await update.message.reply_text(msg)


async def impostor_iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    game = impostor_games.get(chat_id)
    if not game:
        await update.message.reply_text("No hay partida activa.")
        return

    success, msg = game.start_game(user.id)
    if not success:
        await update.message.reply_text(msg)
        return

    # Crear botones para ver rol
    keyboard = []
    for i, player in enumerate(game.players.values()):
        keyboard.append([InlineKeyboardButton(f"👤 {player.name}", callback_data=f"imp_rol_{player.user_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🎭 *El juego ha comenzado!*\n\n"
        "Cada jugador debe hacer click en su nombre para ver su rol.\n\n"
        "Recuerda: El impostor NO conoce la palabra secreta.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def impostor_rol_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    game = impostor_games.get(chat_id)
    if not game:
        await query.answer("No hay partida activa.")
        return

    target_id = int(query.data.split("_")[2])

    if user.id != target_id:
        await query.answer("Este boton no es para ti!", show_alert=True)
        return

    success, msg = game.get_player_role(user.id)
    await query.answer(msg, show_alert=True)

    if game.all_players_seen_role():
        await query.message.reply_text(
            "Todos han visto su rol!\n\n"
            "Ahora discutan sobre la palabra. Pueden dar pistas o hacer preguntas.\n\n"
            "Cuando esten listos para votar, usen /votar"
        )


async def impostor_votar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    game = impostor_games.get(chat_id)
    if not game:
        await update.message.reply_text("No hay partida activa.")
        return

    success, msg = game.start_voting()
    if not success:
        await update.message.reply_text(msg)
        return

    keyboard = []
    for player in game.players.values():
        keyboard.append([InlineKeyboardButton(f"🗳️ {player.name}", callback_data=f"imp_vote_{player.user_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🗳️ *VOTACION*\n\n"
        "Voten por quien creen que es el impostor!",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def impostor_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id

    game = impostor_games.get(chat_id)
    if not game:
        await query.answer("No hay partida activa.")
        return

    target_id = int(query.data.split("_")[2])

    success, msg = game.vote(user.id, target_id)
    await query.answer(msg)

    if game.all_voted():
        result, players_won = game.get_results()
        emoji = "🎉" if players_won else "😈"

        await query.message.reply_text(f"{emoji} {result}")
        del impostor_games[chat_id]


# ==================== HOMBRES LOBO ====================

async def lobos_crear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id in werewolf_games:
        await update.message.reply_text("Ya hay una partida de Hombres Lobo en este chat.")
        return

    game = WerewolfGame(chat_id=chat_id, creator_id=user.id)
    game.add_player(user.id, user.full_name, user.username)
    werewolf_games[chat_id] = game

    await update.message.reply_text(
        f"🐺 *Hombres Lobo de Castronegro*\n\n"
        f"Partida creada por {user.full_name}!\n\n"
        f"Usen /unirse para entrar.\n"
        f"El creador usa /iniciar cuando esten listos.\n\n"
        f"Jugadores: 1/{game.min_players}+",
        parse_mode="Markdown"
    )


async def lobos_unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    game = werewolf_games.get(chat_id)
    if not game:
        game = impostor_games.get(chat_id)
        if game:
            success, msg = game.add_player(user.id, user.full_name, user.username)
            await update.message.reply_text(msg)
            return

        await update.message.reply_text("No hay partida activa. Usa /impostor o /lobos para crear una.")
        return

    success, msg = game.add_player(user.id, user.full_name, user.username)
    await update.message.reply_text(msg)


async def lobos_salir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    game = werewolf_games.get(chat_id) or impostor_games.get(chat_id)
    if not game:
        await update.message.reply_text("No hay partida activa.")
        return

    success, msg = game.remove_player(user.id)
    if msg == "GAME_EMPTY":
        if chat_id in werewolf_games:
            del werewolf_games[chat_id]
        if chat_id in impostor_games:
            del impostor_games[chat_id]
        await update.message.reply_text("Partida cancelada (no quedan jugadores).")
    else:
        await update.message.reply_text(msg)


async def lobos_iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    game = werewolf_games.get(chat_id)
    if not game:
        game = impostor_games.get(chat_id)
        if game:
            await impostor_iniciar(update, context)
            return

        await update.message.reply_text("No hay partida activa.")
        return

    success, msg = game.start_game(user.id)
    if not success:
        await update.message.reply_text(msg)
        return

    # Mapear usuarios al juego
    for player in game.players.values():
        user_to_game[player.user_id] = chat_id

    # Enviar roles por privado
    roles_enviados = []
    roles_fallidos = []

    for player in game.players.values():
        try:
            _, role_msg = game.get_player_role(player.user_id)
            role_info = ROLES_INFO[player.role]
            await context.bot.send_message(
                chat_id=player.user_id,
                text=f"🐺 *Hombres Lobo - Tu rol:*\n\n{role_info.emoji} *{role_info.name}*\n\n{role_info.description}",
                parse_mode="Markdown"
            )
            roles_enviados.append(player.name)
        except Exception:
            roles_fallidos.append(player.name)

    msg_enviados = f"Roles enviados a: {', '.join(roles_enviados)}" if roles_enviados else ""
    msg_fallidos = f"\n⚠️ No pude enviar a: {', '.join(roles_fallidos)}\n(Deben iniciar chat conmigo primero)" if roles_fallidos else ""

    await update.message.reply_text(
        f"🐺 *El juego ha comenzado!*\n\n{msg_enviados}{msg_fallidos}",
        parse_mode="Markdown"
    )

    # Iniciar la primera noche
    await send_night_actions(context, game, chat_id)


async def lobos_rol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    game = werewolf_games.get(chat_id) or impostor_games.get(chat_id)
    if not game:
        await update.message.reply_text("No hay partida activa.")
        return

    if user.id not in game.players:
        await update.message.reply_text("No estas en la partida.")
        return

    player = game.players[user.id]

    if hasattr(player, 'role') and player.role:
        role_info = ROLES_INFO[player.role]
        msg = f"{role_info.emoji} *{role_info.name}*\n\n{role_info.description}"
    else:
        success, msg = game.get_player_role(user.id)

    try:
        await context.bot.send_message(chat_id=user.id, text=msg, parse_mode="Markdown")
        await update.message.reply_text("Te envie tu rol por privado.")
    except Exception:
        await update.message.reply_text("No pude enviarte el mensaje. Inicia una conversacion conmigo primero.")


async def lobos_jugadores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    game = werewolf_games.get(chat_id) or impostor_games.get(chat_id)
    if not game:
        await update.message.reply_text("No hay partida activa.")
        return

    await update.message.reply_text(game.get_players_list())


async def lobos_vivos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    game = werewolf_games.get(chat_id)
    if not game:
        await update.message.reply_text("No hay partida activa de Hombres Lobo.")
        return

    await update.message.reply_text(game.get_alive_list())


async def lobos_votar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    game = werewolf_games.get(chat_id)
    if not game:
        game = impostor_games.get(chat_id)
        if game:
            await impostor_votar(update, context)
            return

        await update.message.reply_text("No hay partida activa.")
        return

    success, msg = game.start_voting()
    if not success:
        await update.message.reply_text(msg)
        return

    keyboard = []
    for player in game.get_alive_players():
        keyboard.append([InlineKeyboardButton(f"🗳️ {player.name}", callback_data=f"wolf_vote_{chat_id}_{player.user_id}")])

    keyboard.append([InlineKeyboardButton("⏭️ No linchar a nadie", callback_data=f"wolf_vote_{chat_id}_skip")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🗳️ *VOTACION DEL PUEBLO*\n\n{game.get_alive_list()}\n\nVoten por quien quieren linchar!",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


# ==================== CALLBACKS ACCIONES NOCTURNAS ====================

# Almacen temporal para seleccion de Cupido
cupido_selections: dict[int, list[int]] = {}

async def cupido_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data

    parts = data.split("_")

    if parts[1] == "confirm":
        # Confirmar enamorados
        chat_id = int(parts[2])
        game = werewolf_games.get(chat_id)

        if not game:
            await query.answer("Partida no encontrada.")
            return

        selections = cupido_selections.get(user.id, [])
        if len(selections) != 2:
            await query.answer("Debes seleccionar exactamente 2 jugadores!", show_alert=True)
            return

        success, msg = game.cupido_action(user.id, selections[0], selections[1])
        await query.answer(msg, show_alert=True)

        if success:
            # Notificar a los enamorados
            for lover_id in selections:
                other_id = selections[1] if lover_id == selections[0] else selections[0]
                other_name = game.players[other_id].name
                try:
                    await context.bot.send_message(
                        chat_id=lover_id,
                        text=f"💕 *Cupido te ha elegido!*\n\nEstas enamorado/a de {other_name}.\nSi uno muere, el otro tambien morira de amor.",
                        parse_mode="Markdown"
                    )
                except:
                    pass

            await query.edit_message_text("💘 Has enamorado a los jugadores seleccionados!")
            del cupido_selections[user.id]

            await check_night_complete(context, game, chat_id)
    else:
        # Seleccionar jugador
        chat_id = int(parts[1])
        target_id = int(parts[2])

        if user.id not in cupido_selections:
            cupido_selections[user.id] = []

        selections = cupido_selections[user.id]

        if target_id in selections:
            selections.remove(target_id)
            await query.answer(f"Deseleccionado")
        elif len(selections) < 2:
            selections.append(target_id)
            await query.answer(f"Seleccionado ({len(selections)}/2)")
        else:
            await query.answer("Ya seleccionaste 2 jugadores!", show_alert=True)


async def protector_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    parts = query.data.split("_")
    chat_id = int(parts[1])
    target_id = int(parts[2])

    game = werewolf_games.get(chat_id)
    if not game:
        await query.answer("Partida no encontrada.")
        return

    success, msg = game.protector_action(user.id, target_id)
    await query.answer(msg, show_alert=True)

    if success:
        await query.edit_message_text(f"🛡️ Proteges a {game.players[target_id].name} esta noche.")
        await check_night_complete(context, game, chat_id)


async def lobo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    parts = query.data.split("_")
    chat_id = int(parts[1])
    target_id = int(parts[2])

    game = werewolf_games.get(chat_id)
    if not game:
        await query.answer("Partida no encontrada.")
        return

    success, msg = game.wolf_vote(user.id, target_id)
    await query.answer(msg)

    if success:
        target_name = game.players[target_id].name
        await query.edit_message_text(f"🐺 Has votado por {target_name}.\n\n{msg}")

        # Si todos los lobos votaron, notificar a la bruja
        if game.wolf_target:
            await check_night_complete(context, game, chat_id)


async def vidente_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    parts = query.data.split("_")
    chat_id = int(parts[1])
    target_id = int(parts[2])

    game = werewolf_games.get(chat_id)
    if not game:
        await query.answer("Partida no encontrada.")
        return

    success, msg = game.vidente_action(user.id, target_id)
    await query.answer(msg, show_alert=True)

    if success:
        await query.edit_message_text(f"🔮 Resultado de tu investigacion:\n\n{msg}")
        await check_night_complete(context, game, chat_id)


async def bruja_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    parts = query.data.split("_")
    action = parts[1]
    chat_id = int(parts[2])

    game = werewolf_games.get(chat_id)
    if not game:
        await query.answer("Partida no encontrada.")
        return

    if action == "heal":
        success, msg = game.bruja_action(user.id, heal=True)
        await query.answer(msg, show_alert=True)
        await query.edit_message_text(f"🧙‍♀️ {msg}")

    elif action == "kill":
        # Mostrar lista de jugadores para matar
        keyboard = []
        for p in game.get_alive_players():
            if p.user_id != user.id:
                keyboard.append([InlineKeyboardButton(
                    f"💀 {p.name}",
                    callback_data=f"bruja_target_{chat_id}_{p.user_id}"
                )])
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data=f"bruja_skip_{chat_id}")])

        await query.edit_message_text(
            "🧙‍♀️ ¿A quien quieres matar con tu pocion?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif action == "target":
        target_id = int(parts[3])
        success, msg = game.bruja_action(user.id, kill_target=target_id)
        await query.answer(msg, show_alert=True)
        await query.edit_message_text(f"🧙‍♀️ {msg}")

    elif action == "skip":
        player = game.players.get(user.id)
        if player:
            player.night_action_done = True
        await query.edit_message_text("🧙‍♀️ No usas ninguna pocion esta noche.")

    await check_night_complete(context, game, chat_id)


# ==================== CALLBACK VOTACION DIURNA ====================

async def wolf_day_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    parts = query.data.split("_")
    chat_id = int(parts[2])
    target = parts[3]

    game = werewolf_games.get(chat_id)
    if not game:
        await query.answer("Partida no encontrada.")
        return

    if target == "skip":
        # Votar por no linchar
        voter = game.players.get(user.id)
        if voter and voter.is_alive:
            voter.vote = -1  # Voto especial para "no linchar"
            alive = game.get_alive_players()
            votes = sum(1 for p in alive if p.vote is not None)
            await query.answer(f"Votaste por no linchar. ({votes}/{len(alive)})")

            if votes == len(alive):
                # Contar votos
                skip_votes = sum(1 for p in alive if p.vote == -1)
                if skip_votes > len(alive) // 2:
                    game.phase = game.phase.__class__.NIGHT
                    game.day_number += 1
                    game._reset_night_phase()
                    await query.message.reply_text(
                        "El pueblo decide no linchar a nadie.\n\n" + game._get_night_start_message()
                    )
                    await send_night_actions(context, game, chat_id)
                else:
                    # Resolver votacion normal
                    success, msg = game._resolve_voting()
                    await query.message.reply_text(f"🐺 {msg}")

                    if game.phase.value == "finished":
                        del werewolf_games[chat_id]
                    elif game.phase.value == "night":
                        await send_night_actions(context, game, chat_id)
        return

    target_id = int(target)
    success, msg = game.day_vote(user.id, target_id)
    await query.answer(msg if len(msg) < 200 else "Voto registrado!")

    if game.phase.value == "finished":
        await query.message.reply_text(f"🐺 {msg}")
        del werewolf_games[chat_id]
        for player in game.players.values():
            if player.user_id in user_to_game:
                del user_to_game[player.user_id]
    elif game.phase.value == "night":
        await query.message.reply_text(f"🐺 {msg}")
        await send_night_actions(context, game, chat_id)


# ==================== CALLBACKS MENU ====================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "menu_impostor":
        await query.message.reply_text(
            "🎭 *El Impostor*\n\n"
            "Un jugador es el impostor y no conoce la palabra secreta.\n"
            "Los demas deben descubrirlo!\n\n"
            "Usa /impostor para crear una partida.",
            parse_mode="Markdown"
        )
    elif query.data == "menu_werewolf":
        await query.message.reply_text(
            "🐺 *Hombres Lobo de Castronegro*\n\n"
            "Aldeanos vs Hombres Lobo.\n"
            "De noche los lobos cazan, de dia el pueblo vota.\n\n"
            "Usa /lobos para crear una partida.",
            parse_mode="Markdown"
        )


# ==================== SETUP ====================

async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "Menu principal"),
        BotCommand("ayuda", "Ver comandos"),
        BotCommand("impostor", "Crear partida El Impostor"),
        BotCommand("lobos", "Crear partida Hombres Lobo"),
        BotCommand("unirse", "Unirse a partida"),
        BotCommand("salir", "Salir de partida"),
        BotCommand("iniciar", "Iniciar juego"),
        BotCommand("votar", "Iniciar votacion"),
        BotCommand("vivos", "Ver jugadores vivos"),
    ])


def main():
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    # Comandos generales
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("help", ayuda))

    # El Impostor
    app.add_handler(CommandHandler("impostor", impostor_crear))

    # Hombres Lobo
    app.add_handler(CommandHandler("lobos", lobos_crear))
    app.add_handler(CommandHandler("werewolf", lobos_crear))

    # Comandos compartidos
    app.add_handler(CommandHandler("unirse", lobos_unirse))
    app.add_handler(CommandHandler("salir", lobos_salir))
    app.add_handler(CommandHandler("iniciar", lobos_iniciar))
    app.add_handler(CommandHandler("rol", lobos_rol))
    app.add_handler(CommandHandler("votar", lobos_votar))
    app.add_handler(CommandHandler("jugadores", lobos_jugadores))
    app.add_handler(CommandHandler("vivos", lobos_vivos))

    # Callbacks menu
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))

    # Callbacks El Impostor
    app.add_handler(CallbackQueryHandler(impostor_rol_callback, pattern="^imp_rol_"))
    app.add_handler(CallbackQueryHandler(impostor_vote_callback, pattern="^imp_vote_"))

    # Callbacks Hombres Lobo - Acciones nocturnas
    app.add_handler(CallbackQueryHandler(cupido_callback, pattern="^cupido_"))
    app.add_handler(CallbackQueryHandler(protector_callback, pattern="^protector_"))
    app.add_handler(CallbackQueryHandler(lobo_callback, pattern="^lobo_"))
    app.add_handler(CallbackQueryHandler(vidente_callback, pattern="^vidente_"))
    app.add_handler(CallbackQueryHandler(bruja_callback, pattern="^bruja_"))

    # Callbacks Hombres Lobo - Votacion diurna
    app.add_handler(CallbackQueryHandler(wolf_day_vote_callback, pattern="^wolf_vote_"))

    print("Bot MultiGame iniciado...")
    app.run_polling()


if __name__ == "__main__":
    main()
