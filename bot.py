import os
import asyncio
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = "8870183083:AAEf4nWxxRZZmEikNp0DM5ndluk1sOmjRXY"
ADMIN_ID = 465382376          # Ваш числовий Telegram ID (дізнатися в @userinfobot)
CHANNEL_ID = -1004311434285          # ID вашого закритого каналу

CARD_NUMBER = "4441 1111 4227 5779"  # Номер вашої картки
RECIPIENT_NAME = "Талько П.В."
PRICE = "247 грн"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


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
        f"Після здійснення переказу просто натисніть кнопку нижче 👇"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query(F.data == "client_paid")
async def client_paid_handler(callback: CallbackQuery):
    user = callback.from_user
    username = f"@{user.username}" if user.username else "без юзернейма"

    # 1. Прибираємо кнопку в повідомленні користувача та інформуємо про обробку
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "⏳ <b>Дякуємо! Заявку надіслано адміністратору.</b>\n\n"
        "Очікуємо підтвердження з банку. Одразу після перевірки ваше персональне посилання "
        "надійде в цей чат автоматично.",
        parse_mode="HTML"
    )
    await callback.answer()

    # 2. Відправляємо адміну сповіщення з кнопками керування
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
        f"🆔 Telegram ID: <code>{user.id}</code>\n"
        f"💰 Очікувана сума: <b>{PRICE}</b>\n\n"
        f"<i>Перевірте виписку у своєму банку та оберіть дію:</i>"
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
        # Створюємо строго одноразове посилання (діє лише для 1 входу)
        invite = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            name=f"User_{user_id}"
        )

        # Надсилаємо посилання покупцю
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 <b>Оплату успішно підтверджено!</b>\n\n"
                f"Ваше персональне посилання для входу в закритий канал із матеріалами:\n"
                f"👉 {invite.invite_link}\n\n"
                f"<i>Зверніть увагу: посилання діє лише для одного акаунта.</i>"
            ),
            parse_mode="HTML"
        )

        # Оновлюємо картку адміна, щоб випадково не натиснути двічі
        await callback.message.edit_text(
            f"✅ <b>Доступ надано!</b>\n"
            f"Користувач ID <code>{user_id}</code> отримав одноразовий інвайт-лінк.",
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
        # Повідомляємо клієнта про відхилення
        await bot.send_message(
            chat_id=user_id,
            text=(
                "❌ <b>Оплату не знайдено у банківській виписці.</b>\n\n"
                "Будь ласка, перевірте факт списання коштів або зверніться до підтримки, "
                "якщо виникла затримка з боку вашого банку."
            ),
            parse_mode="HTML"
        )

        await callback.message.edit_text(
            f"❌ <b>Оплату відхилено.</b>\n"
            f"Користувача ID <code>{user_id}</code> сповіщено.",
            parse_mode="HTML"
        )
        await callback.answer("Відхилено!")

    except Exception as e:
        logging.error(f"Помилка: {e}")
        await callback.answer(f"Помилка: {e}", show_alert=True)


# ================= ВЕБ-СЕРВЕР ДЛЯ ВИТОКІВ RENDER =================
async def handle_ping(request):
    return web.Response(text="Bot is running!")


async def main():
    port = int(os.environ.get("PORT", 8080))

    # Створюємо фіктивний вебсервер, щоб Render бачив відкритий порт
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Health-check port started on {port}")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())