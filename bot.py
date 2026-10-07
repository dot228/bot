import os
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Update
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

BOT_TOKEN = "8870183083:AAEf4nWxxRZZmEikNp0DM5ndluk1sOmjRXY"
ADMIN_ID = 6750612015          # Ваш числовий Telegram ID (дізнатися в @userinfobot)
CHANNEL_ID = -1004464809521          # ID вашого закритого каналу

CARD_NUMBER = "4441 1110 3348 5701"  # Номер вашої картки
RECIPIENT_NAME = "Супруненко А. О."
PRICE = "288 грн"

# Публічний домен Render (значення без https://, наприклад: bot-3-lrz5.onrender.com)
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{RENDER_EXTERNAL_HOSTNAME}{WEBHOOK_PATH}"
# ================================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# --- ОБРОБНИКИ КОМАНД І КНОПОК ---

@dp.message(CommandStart())
async def start_handler(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Я оплатив(ла)", callback_data="client_paid")]
        ]
    )

    text = (
        f"👋 <b>Вітаємо!</b>\n\n"
        f"Для отримання доступу до відеоуроку <b>«Створення унікальних субтитрів»</b> "
        f"перекажіть <b>{PRICE}</b> за реквізитами:\n\n"
        f"💳 <code>{CARD_NUMBER}</code> <i>(натисніть для копіювання)</i>\n"
        f"👤 Отримувач: <b>{RECIPIENT_NAME}</b>\n\n"
        f"Після здійснення оплати натисніть кнопку нижче 👇"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query(F.data == "client_paid")
async def client_paid_handler(callback: CallbackQuery):
    user = callback.from_user
    username = f"@{user.username}" if user.username else "без юзернейма"

    # Сповіщення користувачу
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "⏳ <b>Дякуємо! Повідомлення надіслано на перевірку.</b>\n\n"
        "Очікуємо підтвердження оплати. Персональне посилання надійде сюди автоматично.",
        parse_mode="HTML"
    )
    await callback.answer()

    # Сповіщення адміністратору з кнопками
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
        # Одноразовий інвайт-лінк (ліміт: 1 вхід)
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


# --- НАЛАШТУВАННЯ ВЕБ-СЕРВЕРА ТА WEBHOOK ---

async def health_check(request):
    """Маршрут для Render та UptimeRobot, щоб підтримувати сервер активним."""
    return web.Response(text="OK", status=200)


async def on_startup(app: web.Application):
    # Встановлюємо вебхук у Telegram
    if RENDER_EXTERNAL_HOSTNAME:
        logging.info(f"Реєструємо Webhook: {WEBHOOK_URL}")
        await bot.set_webhook(
            url=WEBHOOK_URL,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"]
        )
    else:
        logging.warning("RENDER_EXTERNAL_HOSTNAME не знайдено, перевірте змінні середовища.")


async def on_shutdown(app: web.Application):
    logging.info("Зупиняємо сесію бота...")
    await bot.session.close()


def main():
    app = web.Application()

    # Health-check ендпоінт
    app.router.add_get("/", health_check)

    # Обробник вебхуків Telegram
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