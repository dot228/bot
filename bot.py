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

BOT_TOKEN = "8870183083:AAFGPIe5aVHNvwNTJt51G04JRZcTKD23n0M"
CHANNEL_ID = -1004311434285          # ID вашого закритого каналу
MONO_TOKEN = "u4rfSa4RXC6e0i1Sb7kFlcxp_wG_3WMcHwWDuj4jtEoQ" # З api.monobank.ua
ACCOUNT_ID = "0"                      # "0" — основна гривнева картка
CARD_NUMBER = "4441 1111 4227 5779"  # Номер вашої картки
RECIPIENT_NAME = "Талько П.В."
BASE_PRICE = 1

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Тимчасове сховище призначених сум (у продакшені краще SQLite / Redis)
# Формат: {user_id: {"amount_cents": 24715, "timestamp": 1710000000}}
pending_payments = {}

# Лічильник унікальних копійок (від 1 до 99)
cents_counter = 1


async def check_monobank_payment(expected_amount_cents: int, since_timestamp: int) -> bool:
    """Перевіряє, чи є у виписці Monobank зарахування на потрібну суму."""
    url = f"https://api.monobank.ua/personal/statement/{ACCOUNT_ID}/{since_timestamp}"
    headers = {"X-Token": MONO_TOKEN}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    logging.warning(f"Monobank API status: {response.status}")
                    return False

                data = await response.json()
                for item in data:
                    # Поповнення у Monobank мають додатнє значення amount (у копійках)
                    if item.get("amount") == expected_amount_cents:
                        return True
        except Exception as e:
            logging.error(f"Помилка запиту до Monobank: {e}")
            return False

    return False


@dp.message(CommandStart())
async def cmd_start(message: Message):
    global cents_counter
    user_id = message.from_user.id

    # Призначаємо клієнту унікальні копійки (247.01, 247.02 тощо) для ідентифікації
    cents = cents_counter
    cents_counter = (cents_counter % 99) + 1
    total_amount_cents = BASE_PRICE * 100 + cents
    formatted_price = f"{BASE_PRICE}.{cents:02d} грн"

    # Фіксуємо платіж (шукаємо транзакції, здійснені не раніше ніж за 2 хвилини до старту)
    pending_payments[user_id] = {
        "amount_cents": total_amount_cents,
        "price_str": formatted_price,
        "timestamp": int(time.time()) - 120
    }

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Я оплатив(ла)", callback_data="check_payment")]
        ]
    )

    await message.answer(
        f"👋 <b>Доступ до відеоуроку «Створення унікальних субтитрів»</b>\n\n"
        f"Для автоматичного отримання доступу перекажіть <b>точну суму з копійками</b>:\n\n"
        f"💰 <b>Сума:</b> <code>{formatted_price}</code>\n"
        f"💳 <b>Картка:</b> <code>{CARD_NUMBER}</code>\n"
        f"👤 <b>Отримувач:</b> {RECIPIENT_NAME}\n\n"
        f"⚠️ <i>Важливо переказати саме з копійками — за ними система миттєво підтвердить ваш платіж.</i>\n\n"
        f"Після оплати натисніть кнопку нижче 👇",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "check_payment")
async def verify_payment(callback: CallbackQuery):
    user_id = callback.from_user.id
    payment_data = pending_payments.get(user_id)

    if not payment_data:
        await callback.answer("Дані платежу застаріли. Надішліть /start повторно.", show_alert=True)
        return

    await callback.answer("Перевіряємо виписку...")

    is_paid = await check_monobank_payment(
        expected_amount_cents=payment_data["amount_cents"],
        since_timestamp=payment_data["timestamp"]
    )

    if is_paid:
        try:
            # Створюємо персональне суворо одноразове посилання (member_limit=1)
            invite = await bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                member_limit=1,
                name=f"User_{user_id}"
            )

            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(
                f"🎉 <b>Оплату успішно підтверджено!</b>\n\n"
                f"Ваше особисте одноразове посилання для входу в закритий канал:\n"
                f"👉 {invite.invite_link}\n\n"
                f"<i>Посилання розраховане лише на 1 особу. У каналі заборонено пересилання та копіювання файлів.</i>",
                parse_mode="HTML"
            )
            del pending_payments[user_id]

        except Exception as e:
            logging.error(f"Помилка створення посилання: {e}")
            await callback.message.answer("Виникла технічна помилка генерації доступу. Будь ласка, зверніться до підтримки.")
    else:
        await callback.message.answer(
            f"❌ Платіж на суму <b>{payment_data['price_str']}</b> ще не надійшов.\n\n"
            f"Якщо ви щойно переказали кошти, зачекайте 1–2 хвилини на оновлення банківського шлюзу і натисніть кнопку знову.",
            parse_mode="HTML"
        )


# ================= ВЕБ-СЕРВЕР ДЛЯ RENDER =================
async def handle_ping(request):
    """Фіктивний ендпоінт, щоб Render бачив відкритий порт і статус Live."""
    return web.Response(text="Bot is running!")


async def main():
    # Отримуємо порт від Render (за замовчуванням 10000 або 8080)
    port = int(os.environ.get("PORT", 8080))

    # Створюємо міні-вебсервер
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Dummy health-check web server started on port {port}")

    # Запускаємо бота
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())