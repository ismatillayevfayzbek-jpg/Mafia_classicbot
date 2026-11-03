
import os
import random
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, filters, MessageHandler
)

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("9205946497:AAEygnfsBTJsos5_xg7gOYizgxbEk_uO2Ww")

games = {}
started_users = set()


def get_name(user):
    return user.first_name or user.username or "O‘yinchi"


def alive_players(game):
    return [p for p in game["players"].values() if p["alive"]]


def check_winner(chat_id, game):
    alive = alive_players(game)
    mafia = sum(p["role"] == "mafia" for p in alive)
    town = len(alive) - mafia

    if mafia == 0:
        game["phase"] = "finished"
        return "🏆 TINCH AHOLI G‘ALABA QOZONDI!"
    if mafia >= town:
        game["phase"] = "finished"
        return "🔪 MAFIA G‘ALABA QOZONDI!"
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == ChatType.PRIVATE:
        started_users.add(update.effective_user.id)
        await update.message.reply_text(
            "🎭 MAFIA OLAMIGA XUSH KELIBSIZ!\n\n"
            "Endi guruhga qayting va /join buyrug‘i bilan o‘yinga qo‘shiling."
        )
    else:
        await update.message.reply_text(
            "🎭 Mafia bot ishlayapti!\n"
            "/newgame — yangi o‘yin\n"
            "/join — qo‘shilish\n"
            "/startgame — boshlash"
        )


async def newgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id in games and games[chat_id]["phase"] != "finished":
        await update.message.reply_text("⚠️ Bu guruhda allaqachon o‘yin mavjud.")
        return

    games[chat_id] = {
        "players": {},
        "phase": "lobby",
        "night_mafia": None,
        "night_doctor": None,
        "votes": {}
    }

    await update.message.reply_text(
        "🌑 MAFIA O‘YINI OCHILDI!\n\n"
        "👥 O‘yinga qo‘shilish uchun /join bosing.\n"
        "👤 Kamida 4 nafar o‘yinchi kerak.\n\n"
        "🎭 Rollar: Mafia, Doktor va Oddiy odam."
    )


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in games or games[chat_id]["phase"] != "lobby":
        await update.message.reply_text("Avval /newgame buyrug‘ini bosing.")
        return

    game = games[chat_id]

    if user.id in game["players"]:
        await update.message.reply_text("Siz allaqachon o‘yindasiz!")
        return

    if user.id not in started_users:
        await update.message.reply_text(
            f"{get_name(user)}, avval botning shaxsiy chatiga kiring "
            "va /start bosing. Keyin guruhda yana /join yuboring."
        )
        return

    game["players"][user.id] = {
        "name": get_name(user),
        "role": None,
        "alive": True
    }

    await update.message.reply_text(
        f"✅ {get_name(user)} o‘yinga qo‘shildi!\n"
        f"👥 O‘yinchilar: {len(game['players'])}"
    )


async def startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in games or games[chat_id]["phase"] != "lobby":
        await update.message.reply_text("Avval yangi o‘yin oching.")
        return

    game = games[chat_id]
    players = list(game["players"].keys())

    if len(players) < 4:
        await update.message.reply_text("❗ Boshlash uchun kamida 4 o‘yinchi kerak.")
        return

    random.shuffle(players)

    game["players"][players[0]]["role"] = "mafia"
    game["players"][players[1]]["role"] = "doctor"

    for uid in players[2:]:
        game["players"][uid]["role"] = "citizen"

    for uid in players:
        role = game["players"][uid]["role"]
        role_text = {
            "mafia": "🔪 SIZ — MAFIASIZ!",
            "doctor": "🩺 SIZ — DOKTORSIZ!",
            "citizen": "👤 SIZ — ODDIY ODAMSIZ!"
        }[role]

        try:
            await context.bot.send_message(
                uid,
                f"🎭 MAFIA O‘YINI BOSHLANDI!\n\n{role_text}\n\n"
                "🤫 ROLINGIZNI BOSHQA O‘YINCHILARGA AYTМANG."
            )
        except Exception:
            await update.message.reply_text(
                f"⚠️ {game['players'][uid]['name']} ga xabar yuborilmadi. "
                "U botni qayta ochib /start bosishi kerak."
            )
            game["phase"] = "lobby"
            for p in game["players"].values():
                p["role"] = None
            return

    game["phase"] = "night"
    await update.message.reply_text(
        "🌙 BIRINCHI TUN BOSHLANDI!\n"
        "Mafia va Doktor shaxsiy chatidagi tugmalardan foydalanadi."
    )
    await send_night_actions(chat_id, context)


async def send_night_actions(chat_id, context):
    game = games[chat_id]
    alive = alive_players(game)

    mafia = next((uid for uid, p in game["players"].items()
                  if p["role"] == "mafia" and p["alive"]), None)
    doctor = next((uid for uid, p in game["players"].items()
                   if p["role"] == "doctor" and p["alive"]), None)

    if mafia is None:
        await finish_game(chat_id, context)
        return

    if doctor is None:
        game["night_doctor"] = 0

    for uid, role in [(mafia, "mafia"), (doctor, "doctor")]:
        if uid is None:
            continue

        buttons = []
        for target_id, player in game["players"].items():
            if not player["alive"]:
                continue
            if role == "mafia" and target_id == uid:
                continue

            buttons.append([
                InlineKeyboardButton(
                    player["name"],
                    callback_data=f"night:{chat_id}:{target_id}"
                )
            ])

        try:
            await context.bot.send_message(
                uid,
                "🌙 Tungi tanlovingizni qiling:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception:
            pass

    await resolve_night_if_ready(chat_id, context)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    action = parts[0]
    chat_id = int(parts[1])
    target_id = int(parts[2])

    if chat_id not in games:
        await query.edit_message_text("Bu o‘yin topilmadi.")
        return

    game = games[chat_id]
    uid = query.from_user.id

    if uid not in game["players"] or not game["players"][uid]["alive"]:
        await query.edit_message_text("Siz bu amalni bajara olmaysiz.")
        return

    if action == "night":
        if game["phase"] != "night":
            return

        role = game["players"][uid]["role"]

        if role == "mafia":
            if game["players"][target_id]["role"] == "mafia":
                return
            game["night_mafia"] = target_id
            await query.edit_message_text("🔪 Tanlovingiz qabul qilindi.")
        elif role == "doctor":
            game["night_doctor"] = target_id
            await query.edit_message_text("🩺 Himoya tanlandi.")
        else:
            return

        await resolve_night_if_ready(chat_id, context)

    elif action == "vote":
        if game["phase"] != "day":
            return

        if target_id not in game["players"] or not game["players"][target_id]["alive"]:
            return

        game["votes"][uid] = target_id
        await query.edit_message_text("⚖️ Ovozingiz qabul qilindi.")
        await resolve_vote_if_ready(chat_id, context)


async def resolve_night_if_ready(chat_id, context):
    game = games[chat_id]

    if game["phase"] != "night":
        return
    if game["night_mafia"] is None or game["night_doctor"] is None:
        return

    target = game["night_mafia"]
    protected = game["night_doctor"]

    if target != protected:
        game["players"][target]["alive"] = False
        result = f"🌅 Tong otdi!\n\n🌑 {game['players'][target]['name']} o‘yindan chiqdi."
    else:
        result = "🌅 Tong otdi!\n\n🩺 Doktor himoyasi muvaffaqiyatli bo‘ldi!"

    game["night_mafia"] = None
    game["night_doctor"] = None

    winner = check_winner(chat_id, game)
    if winner:
        await context.bot.send_message(chat_id, result + "\n\n" + winner)
        return

    game["phase"] = "day"
    game["votes"] = {}

    await context.bot.send_message(chat_id, result)
    await send_vote_buttons(chat_id, context)


async def send_vote_buttons(chat_id, context):
    game = games[chat_id]
    buttons = []

    for uid, player in game["players"].items():
        if player["alive"]:
            buttons.append([
                InlineKeyboardButton(
                    f"⚖️ {player['name']}",
                    callback_data=f"vote:{chat_id}:{uid}"
                )
            ])

    await context.bot.send_message(
        chat_id,
        "☀️ KUNDUZGI MUHOKAMA!\n"
        "Kimdan shubhalanyapsiz? Ovoz bering:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def resolve_vote_if_ready(chat_id, context):
    game = games[chat_id]
    alive = alive_players(game)

    if len(game["votes"]) < len(alive):
        return

    counts = {}
    for target in game["votes"].values():
        counts[target] = counts.get(target, 0) + 1

    highest = max(counts.values())
    winners = [uid for uid, count in counts.items() if count == highest]

    if len(winners) == 1:
        eliminated = winners[0]
        game["players"][eliminated]["alive"] = False
        result = f"⚖️ {game['players'][eliminated]['name']} ovoz bilan o‘yindan chiqdi."
    else:
        result = "⚖️ Ovozlar teng bo‘ldi. Hech kim o‘yindan chiqmadi."

    winner = check_winner(chat_id, game)

    if winner:
        await context.bot.send_message(chat_id, result + "\n\n" + winner)
        return

    game["phase"] = "night"
    await context.bot.send_message(chat_id, result + "\n\n🌙 Yana tun tushdi.")
    await send_night_actions(chat_id, context)


async def finish_game(chat_id, context):
    game = games[chat_id]
    winner = check_winner(chat_id, game)
    if winner:
        await context.bot.send_message(chat_id, winner)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in games:
        await update.message.reply_text("Hozir faol o‘yin yo‘q.")
        return

    game = games[chat_id]
    players = alive_players(game)
    await update.message.reply_text(
        f"📊 O‘yin holati: {game['phase']}\n"
        f"👥 Tirik o‘yinchilar: {len(players)}"
    )


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 MAFIA QOIDALARI\n\n"
        "🔪 Mafia — tunda bir o‘yinchini tanlaydi.\n"
        "🩺 Doktor — tunda bir o‘yinchini himoya qiladi.\n"
        "👤 Oddiy odam — kunduz ovoz beradi.\n\n"
        "Maqsad: Mafia yoki tinch aholi jamoasining g‘alabasiga erishish."
    )


async def leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    uid = update.effective_user.id

    if chat_id in games and games[chat_id]["phase"] == "lobby":
        games[chat_id]["players"].pop(uid, None)
        await update.message.reply_text("🚪 Siz o‘yindan chiqdingiz.")
    else:
        await update.message.reply_text("O‘yin boshlanganidan keyin chiqib bo‘lmaydi.")


def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN muhit o‘zgaruvchisi kiritilmagan.")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newgame", newgame, filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("join", join, filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("startgame", startgame, filters=filters.ChatType.GROUPS))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("leave", leave, filters=filters.ChatType.GROUPS))
    app.add_handler(CallbackQueryHandler(callback))

    print("Mafia bot ishga tushdi!")
    app.run_polling()


if __name__ == "__main__":
    main()
          
