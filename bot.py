import os
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta

import aiohttp
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ================= КОНФІГУРАЦІЯ =================
BOT_TOKEN = "8870183083:AAEf4nWxxRZZmEikNp0DM5ndluk1sOmjRXY"
ADMIN_ID = 6750612015
CHANNEL_ID = -1004464809521

CARD_NUMBER = "4441 1110 3348 5701"
RECIPIENT_NAME = "Супруненко А. О."
PRICE = "288 грн"

WORK_START_HOUR = 8
WORK_END_HOUR = 22
TIMEZONE = timezone(timedelta(hours=3))  # Київський літній час (UTC+3)
QUEUE_FILE = "night_queue.json"

RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{RENDER_EXTERNAL_HOSTNAME}{WEBHOOK_PATH}"
# ================================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# --- РОБОТА З НІЧНОЮ ЧЕРГОЮ ---

def load_queue() -> set:
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            logging.error(f"Помилка читання черги: {e}")
    return set()


def save_queue(queue_data: set):
    try:
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(queue_data), f)
    except Exception as e:
        logging.error(f"Помилка збереження черги: {e}")


def is_night_time() -> bool:
    current_hour = datetime.now(TIMEZONE).hour
    return current_hour >= WORK_END_HOUR or current_hour < WORK_START_HOUR


def get_payment_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Я оплатив(ла)", callback_data="client_paid")]
        ]
    )


def get_payment_text():
    return (
        f"👋 <b>Вітаємо!</b>\n\n"
        f"Для отримання доступу до відеоуроку <b>«Твоя ідеальна схема обробки»</b> "
        f"перекажіть <b>{PRICE}</b> за реквізитами:\n\n"
        f"💳 <code>{CARD_NUMBER}</code> <i>(натисніть для копіювання)</i>\n"
        f"👤 Отримувач: <b>{RECIPIENT_NAME}</b>\n\n"
        f"<i>Графік обробки заявок: щодня з 08:00 до 22:00.</i>\n\n"
        f"Після здійснення оплати натисніть кнопку нижче 👇"
    )


# --- ОБРОБНИКИ КОМАНД І КНОПОК ---

@dp.message(CommandStart())
async def start_handler(message: Message):
    if is_night_time():
        user_id = message.from_user.id
        queue = load_queue()
        queue.add(user_id)
        save_queue(queue)

        text = (
            "🌙 <b>Зараз неробочий час</b>\n\n"
            "Прийом оплат та видача доступу адміністратором відновлюється щодня о <b>08:00</b>.\n\n"
            "✅ <b>Ми зберегли ваш запит!</b> Рівно о 08:00 бот автоматично надішле вам реквізити "
            "та деталі для оплати прямо сюди."
        )
        await message.answer(text, parse_mode="HTML")
        return

    await message.answer(get_payment_text(), parse_mode="HTML", reply_markup=get_payment_keyboard())


@dp.callback_query(F.data == "client_paid")
async def client_paid_handler(callback: CallbackQuery):
    if is_night_time():
        await callback.answer(
            "🌙 Зараз неробочий час (з 22:00 до 08:00). Оплата не приймається до ранку.",
            show_alert=True
        )
        return

    user = callback.from_user
    username = f"@{user.username}" if user.username else "без юзернейма"

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "⏳ <b>Дякуємо! Повідомлення надіслано на перевірку.</b>\n\n"
        "Очікуємо підтвердження оплати. Персональне посилання надійде сюди автоматично.",
        parse_mode="HTML"
    )
    await callback.answer()

    admin_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Підтвердити доступ", callback_data=f"approve_{user.id}"),
                InlineKeyboardButton(text="❌ Відхилити", callback_data=f"reject_{user.id}")
            ]
        ]
    )

    admin_text = (
        f"🔔 <b>Нове повідомлення про оплату!</b>\n\n"
        f"👤 Покупець: <b>{user.full_name}</b> ({username})\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"💰 Очікувана сума: <b>{PRICE}</b>"
    )

    await bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_text,
        reply_markup=admin_keyboard,
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("approve_"))
async def approve_handler(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])

    try:
        invite = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            name=f"User_{user_id}"
        )

        await bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 <b>Оплату підтверджено!</b>\n\n"
                f"Ваше одноразове посилання для входу в закритий канал:\n"
                f"👉 {invite.invite_link}\n\n"
                f"<i>Посилання активне лише для одного входу.</i>"
            ),
            parse_mode="HTML"
        )

        await callback.message.edit_text(
            f"✅ <b>Доступ надано!</b> Користувачу <code>{user_id}</code> надіслано посилання.",
            parse_mode="HTML"
        )
        await callback.answer("Підтверджено!")

    except Exception as e:
        logging.error(f"Помилка створення посилання: {e}")
        await callback.answer(f"Помилка: {e}", show_alert=True)


@dp.callback_query(F.data.startswith("reject_"))
async def reject_handler(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])

    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                "❌ <b>Оплату не знайдено.</b>\n\n"
                "Перевірте факт списання у банку або зверніться до підтримки."
            ),
            parse_mode="HTML"
        )

        await callback.message.edit_text(
            f"❌ Оплату користувача <code>{user_id}</code> відхилено.",
            parse_mode="HTML"
        )
        await callback.answer("Відхилено!")

    except Exception as e:
        logging.error(f"Помилка: {e}")
        await callback.answer(f"Помилка: {e}", show_alert=True)


# --- ФОНОВІ ЗАДАЧІ: РАНКОВА РОЗСИЛКА ТА KEEP-ALIVE ---

async def morning_sender_task():
    """Перевіряє настання 08:00 за Києвом і розсилає реквізити всім, хто написав уночі."""
    has_sent_today = False

    while True:
        try:
            now = datetime.now(TIMEZONE)

            # Якщо рівно 8 ранку (проміжок 08:00 - 08:01) і розсилка ще не робилася
            if now.hour == WORK_START_HOUR and now.minute == 0 and not has_sent_today:
                queue = load_queue()
                if queue:
                    logging.info(f"08:00 — відправляємо ранкові реквізити для {len(queue)} користувачів")
                    for user_id in list(queue):
                        try:
                            morning_text = (
                                "☀️ <b>Доброго ранку!</b>\n\n"
                                "Ми відновили роботу. Ось реквізити для отримання доступу:\n\n"
                                f"{get_payment_text()}"
                            )
                            await bot.send_message(
                                chat_id=user_id,
                                text=morning_text,
                                parse_mode="HTML",
                                reply_markup=get_payment_keyboard()
                            )
                            await asyncio.sleep(0.1)  # захист від флуд-контролю Telegram
                        except Exception as e:
                            logging.error(f"Не вдалося надіслати повідомлення {user_id}: {e}")

                    # Очищаємо чергу після надсилання
                    save_queue(set())

                has_sent_today = True

            # Скидаємо прапорець о 09:00, готуючись до наступного дня
            if now.hour == WORK_START_HOUR + 1:
                has_sent_today = False

        except Exception as e:
            logging.error(f"Помилка у morning_sender_task: {e}")

        await asyncio.sleep(30)


async def keep_alive():
    """Кожні 10 хвилин робить запит на свій же сервер через інтернет, не даючи йому заснути."""
    url = f"https://{RENDER_EXTERNAL_HOSTNAME}/"
    await asyncio.sleep(30)

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                if RENDER_EXTERNAL_HOSTNAME:
                    async with session.get(url, timeout=15) as resp:
                        logging.info(f"Keep-alive ping до {url}: статус {resp.status}")
            except Exception as e:
                logging.warning(f"Keep-alive ping error: {e}")
            await asyncio.sleep(600)


async def health_check(request):
    return web.Response(text="OK", status=200)


async def on_startup(app: web.Application):
    if RENDER_EXTERNAL_HOSTNAME:
        logging.info(f"Реєструємо Webhook: {WEBHOOK_URL}")
        await bot.set_webhook(
            url=WEBHOOK_URL,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"]
        )
    # Запускаємо фонові сервіси
    app["ping_task"] = asyncio.create_task(keep_alive())
    app["morning_task"] = asyncio.create_task(morning_sender_task())


async def on_shutdown(app: web.Application):
    logging.info("Зупиняємо сесію бота...")
    if "ping_task" in app:
        app["ping_task"].cancel()
    if "morning_task" in app:
        app["morning_task"].cancel()
    await bot.session.close()


def main():
    app = web.Application()

    app.router.add_get("/", health_check)

    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    )
    webhook_handler.register(app, path=WEBHOOK_PATH)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    setup_application(app, dp, bot=bot)

    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()