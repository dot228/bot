import asyncio
import time
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

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
                if response.status == 429:
                    # Ліміт 1 запит на хвилину
                    return False
                if response.status != 200:
                    return False

                data = await response.json()
                for item in data:
                    # item['amount'] у Monobank повертається в копійках (додатнє значення — поповнення)
                    if item.get("amount") == expected_amount_cents:
                        return True
        except Exception:
            return False

    return False


@dp.message(CommandStart())
async def cmd_start(message: Message):
    global cents_counter
    user_id = message.from_user.id

    # Призначаємо користувачеві унікальні копійки (наприклад, 247.01, 247.02 ...)
    cents = cents_counter
    cents_counter = (cents_counter % 99) + 1
    total_amount_cents = BASE_PRICE * 100 + cents
    formatted_price = f"{BASE_PRICE}.{cents:02d} грн"

    # Фіксуємо очікувану оплату
    pending_payments[user_id] = {
        "amount_cents": total_amount_cents,
        "price_str": formatted_price,
        "timestamp": int(time.time()) - 120  # Шукаємо платежі з моменту за 2 хв до натискання
    }

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Я оплатив(ла)", callback_data="check_payment")]
        ]
    )

    await message.answer(
        f"👋 <b>Доступ до відеоуроку та бонусних гайдів</b>\n\n"
        f"Для автоматичного підтвердження перекажіть <b>точну суму з копійками</b>:\n"
        f"💰 <b>Сума:</b> <code>{formatted_price}</code>\n"
        f"💳 <b>Картка:</b> <code>{CARD_NUMBER}</code>\n"
        f"👤 <b>Отримувач:</b> {RECIPIENT_NAME}\n\n"
        f"⚠️ <i>Копійки важливі — саме за ними робот миттєво розпізнає ваш переказ.</i>\n\n"
        f"Після переказу натисніть кнопку нижче 👇",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "check_payment")
async def verify_payment(callback: CallbackQuery):
    user_id = callback.from_user.id
    payment_data = pending_payments.get(user_id)

    if not payment_data:
        await callback.answer("Дані платежу застаріли. Натисніть /start заново.", show_alert=True)
        return

    await callback.answer("Перевіряємо виписку банку...")

    is_paid = await check_monobank_payment(
        expected_amount_cents=payment_data["amount_cents"],
        since_timestamp=payment_data["timestamp"]
    )

    if is_paid:
        try:
            # Генерація суворо одноразового посилання
            invite = await bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                member_limit=1,
                name=f"User {user_id}"
            )

            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(
                f"✅ <b>Оплату успішно зараховано!</b>\n\n"
                f"Ваше персональне посилання на закритий канал:\n"
                f"👉 {invite.invite_link}\n\n"
                f"<i>Посилання діє для 1 входу. Пересилання відео та скріншоти в каналі вимкнено.</i>",
                parse_mode="HTML"
            )
            # Очищуємо стан після успішної оплати
            del pending_payments[user_id]

        except Exception as e:
            await callback.message.answer("Помилка видачі лінка. Зв'яжіться з підтримкою.")
    else:
        await callback.message.answer(
            f"❌ Платіж на суму <b>{payment_data['price_str']}</b> поки не знайдено.\n\n"
            f"Якщо ви щойно відправили кошти, зачекайте 1–2 хвилини на оновлення банківської мережі й натисніть ще раз.",
            parse_mode="HTML"
        )


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())