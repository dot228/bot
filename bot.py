import os
import time
import asyncio
import logging
import aiohttp
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
    text = (
        f"👋 <b>Вітаємо!</b>\n\n"
        f"Для отримання доступу до відеоуроку <b>«Створення унікальних субтитрів»</b> "
        f"та гайду перекажіть <b>{PRICE}</b> на картку:\n\n"
        f"💳 <code>{CARD_NUMBER}</code> <i>(натисніть, щоб скопіювати)</i>\n"
        f"👤 Отримувач: <b>{RECIPIENT_NAME}</b>\n\n"
        f"📸 <b>Після оплати просто надішліть сюди скріншот або PDF квитанції.</b>"
    )
    await message.answer(text, parse_mode="HTML")


@dp.message(F.photo | F.document)
async def receipt_handler(message: Message):
    # Якщо сам адмін щось шле в бота — не реагуємо як на чек
    if message.from_user.id == ADMIN_ID:
        return

    # Відповідаємо клієнту
    await message.answer(
        "⏳ <b>Квитанцію отримано!</b>\n"
        "Перевіряємо зарахування. Ваше персональне посилання надійде сюди одразу після підтвердження.",
        parse_mode="HTML"
    )

    # Сповіщення адміністратору
    user = message.from_user
    username = f"@{user.username}" if user.username else "без username"
    caption_text = (
        f"📥 <b>Нова оплата на перевірці!</b>\n\n"
        f"👤 Користувач: {user.full_name} ({username})\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"💰 Очікувана сума: {PRICE}"
    )

    admin_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Підтвердити доступ", callback_data=f"approve_{user.id}"),
                InlineKeyboardButton(text="❌ Відхилити", callback_data=f"reject_{user.id}")
            ]
        ]
    )

    if message.photo:
        await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=message.photo[-1].file_id,
            caption=caption_text,
            reply_markup=admin_keyboard,
            parse_mode="HTML"
        )
    elif message.document:
        await bot.send_document(
            chat_id=ADMIN_ID,
            document=message.document.file_id,
            caption=caption_text,
            reply_markup=admin_keyboard,
            parse_mode="HTML"
        )


@dp.callback_query(F.data.startswith("approve_"))
async def approve_payment(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])

    try:
        # Створюємо СУВОРО ОДНОРАЗОВЕ посилання (member_limit=1)
        invite = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            name=f"User_{user_id}"
        )

        # Відправляємо персональне посилання покупцю
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 <b>Оплату успішно підтверджено!</b>\n\n"
                f"Ваше персональне одноразове посилання для входу в закритий канал:\n"
                f"👉 {invite.invite_link}\n\n"
                f"<i>Посилання діє для 1 входу. Пересилання відео та скріншоти в каналі вимкнено.</i>"
            ),
            parse_mode="HTML"
        )

        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(f"✅ Доступ успішно відправлено користувачу <code>{user_id}</code>!")
        await callback.answer("Підтверджено!")

    except Exception as e:
        logging.error(f"Помилка створення посилання: {e}")
        await callback.answer(f"Помилка: {e}", show_alert=True)


@dp.callback_query(F.data.startswith("reject_"))
async def reject_payment(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])

    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                "❌ <b>Квитанцію відхилено або платіж не знайдено.</b>\n\n"
                "Будь ласка, перевірте виписку у своєму банку або надішліть коректний чек повторно."
            ),
            parse_mode="HTML"
        )

        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(f"❌ Платіж користувача <code>{user_id}</code> відхилено.")
        await callback.answer("Відхилено!")

    except Exception as e:
        logging.error(f"Помилка: {e}")
        await callback.answer(f"Помилка: {e}", show_alert=True)


# ================= ВЕБ-СЕРВЕР ДЛЯ RENDER =================
async def handle_ping(request):
    return web.Response(text="Bot is running!")


async def main():
    port = int(os.environ.get("PORT", 8080))

    # Створюємо фіктивний вебсервер для Render (щоб не було таймаутів)
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