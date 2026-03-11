import asyncio
import logging
import random
import string
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    Message, ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота и ID админа
BOT_TOKEN = "8609302177:AAGmDeZXbdCPJx_7zb3ghkUEcPWk79LYThk"
ADMIN_ID = 8230314926

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Эмодзи для капчи
CAPTCHA_EMOJIS = ["🐹", "🐻", "🐻‍❄️", "🦊"]

# База данных пользователей (в реальном проекте используйте настоящую БД)
users_db: Dict[int, Dict] = {}
orders_db: Dict[str, Dict] = {}
pending_orders: Dict[str, Dict] = {}
completed_orders: Dict[str, Dict] = {}
balance_topups: Dict[str, Dict] = {}
reviews_db: List[Dict] = []

# Категории и товары с ценами
categories = {
    "Telegram": {
        "Накрутка подписчиков": 0.4,
        "Накрутка реакций": 0.5,
        "Накрутка просмотров": 0.6
    },
    "Instagram": {
        "Накрутка подписчиков": 0.4,
        "Накрутка реакций": 0.5,
        "Накрутка просмотров": 0.6
    },
    "TikTok": {
        "Накрутка подписчиков": 0.4,
        "Накрутка просмотров": 0.6
    },
    "YouTube": {
        "Накрутка подписчиков": 0.4,
        "Накрутка реакций": 0.5,
        "Накрутка комментариев": 0.8,
        "Накрутка просмотров": 0.6
    },
    "Twitch": {
        "Накрутка подписчиков": 0.4,
        "Накрутка просмотров": 0.6
    }
}

# Доступные суммы для выбора количества
AVAILABLE_AMOUNTS = [30, 50, 70, 100, 150, 200]

# Состояния FSM
class OrderStates(StatesGroup):
    waiting_for_quantity = State()
    waiting_for_link = State()
    confirming_order = State()
    waiting_for_review_text = State()

class AdminStates(StatesGroup):
    waiting_for_reject_reason = State()
    waiting_for_broadcast = State()
    waiting_for_category_add = State()
    waiting_for_service_add = State()
    waiting_for_category_delete = State()
    waiting_for_service_delete = State()
    waiting_for_balance_amount = State()
    waiting_for_balance_user = State()

# Вспомогательные функции
def generate_random_id(length: int = 8) -> str:
    """Генерация случайного ID"""
    return ''.join(random.choices(string.digits, k=length))

def generate_order_number() -> str:
    """Генерация номера заказа"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

def get_user_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Главное меню"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    builder.add(InlineKeyboardButton(text="🛍 Товары", callback_data="products"))
    builder.add(InlineKeyboardButton(text="⭐ Отзывы", callback_data="reviews"))
    builder.add(InlineKeyboardButton(text="🆘 Техподдержка", callback_data="support"))
    builder.adjust(2)
    return builder.as_markup()

def get_captcha_keyboard(correct_emoji: str = None) -> Tuple[InlineKeyboardMarkup, str]:
    """Клавиатура для капчи с перемешанными эмодзи"""
    if correct_emoji is None:
        correct_emoji = random.choice(CAPTCHA_EMOJIS)
    
    # Создаем копию списка и перемешиваем
    emojis = CAPTCHA_EMOJIS.copy()
    random.shuffle(emojis)
    
    builder = InlineKeyboardBuilder()
    for emoji in emojis:
        builder.add(InlineKeyboardButton(text=emoji, callback_data=f"captcha_{emoji}"))
    builder.adjust(2)
    
    return builder.as_markup(), correct_emoji

def get_quantity_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора количества"""
    builder = InlineKeyboardBuilder()
    
    # Создаем ряды по 2 кнопки
    for i in range(0, len(AVAILABLE_AMOUNTS), 2):
        row = []
        for j in range(2):
            if i + j < len(AVAILABLE_AMOUNTS):
                amount = AVAILABLE_AMOUNTS[i + j]
                row.append(InlineKeyboardButton(
                    text=f"{amount} шт", 
                    callback_data=f"quantity_{amount}"
                ))
        builder.row(*row)
    
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="products"))
    return builder.as_markup()

def get_balance_topup_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для пополнения баланса"""
    amounts = [("30₽", 30), ("50₽", 50), ("70₽", 70), ("100₽", 100), ("150₽", 150), ("200₽", 200)]
    builder = InlineKeyboardBuilder()
    
    for i in range(0, len(amounts), 2):
        row = []
        for j in range(2):
            if i + j < len(amounts):
                text, amount = amounts[i + j]
                row.append(InlineKeyboardButton(
                    text=text, 
                    callback_data=f"topup_{amount}"
                ))
        builder.row(*row)
    
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu"))
    return builder.as_markup()

def get_categories_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура категорий"""
    builder = InlineKeyboardBuilder()
    for category in categories.keys():
        builder.add(InlineKeyboardButton(text=category, callback_data=f"cat_{category}"))
    builder.add(InlineKeyboardButton(text="◀️ Назад", callback_data="menu"))
    builder.adjust(2)
    return builder.as_markup()

def get_services_keyboard(category: str) -> InlineKeyboardMarkup:
    """Клавиатура услуг для категории"""
    builder = InlineKeyboardBuilder()
    for service in categories[category].keys():
        builder.add(InlineKeyboardButton(text=service, callback_data=f"service_{category}_{service}"))
    builder.add(InlineKeyboardButton(text="◀️ Назад", callback_data="products"))
    builder.adjust(2)
    return builder.as_markup()

def get_review_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для оценки"""
    builder = InlineKeyboardBuilder()
    for i in range(5, 0, -1):
        stars = "⭐" * i
        builder.add(InlineKeyboardButton(text=stars, callback_data=f"review_rate_{i}"))
    builder.adjust(1)
    return builder.as_markup()

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Админ-панель"""
    builder = InlineKeyboardBuilder()
    buttons = [
        ("👥 Онлайн", "admin_online"),
        ("⏳ Ожидаемые покупки", "admin_pending"),
        ("✅ Совершенные покупки", "admin_completed"),
        ("💰 Накрутка баланса", "admin_balance"),
        ("➕ Добавить товар", "admin_add_service"),
        ("➖ Удалить товар", "admin_delete_service"),
        ("📢 Скинуть пост", "admin_broadcast")
    ]
    for text, callback in buttons:
        builder.add(InlineKeyboardButton(text=text, callback_data=callback))
    builder.adjust(2)
    return builder.as_markup()

# Команда /start
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Инициализация пользователя
    if user_id not in users_db:
        users_db[user_id] = {
            "id": generate_random_id(8),
            "username": message.from_user.full_name,
            "balance": 0.0,
            "orders_completed": 0,
            "captcha_passed": False,
            "joined_date": datetime.now().isoformat()
        }
    
    # Если капча уже пройдена
    if users_db[user_id]["captcha_passed"]:
        await message.answer(
            f"👋 С возвращением, {message.from_user.full_name}!",
            reply_markup=get_user_keyboard(user_id)
        )
        return
    
    # Отправляем капчу
    await state.update_data(captcha_attempts=0)
    
    await message.answer(
        "Добро пожаловать в бота TMT!\nПройдите капчу чтобы пользоваться ботом👇",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔓 Пройти капчу", callback_data="start_captcha")]]
        )
    )

# Обработка капчи
@dp.callback_query(F.data == "start_captcha")
async def process_captcha_start(callback: CallbackQuery, state: FSMContext):
    # Генерируем правильный эмодзи и сохраняем его
    correct_emoji = random.choice(CAPTCHA_EMOJIS)
    await state.update_data(correct_captcha_emoji=correct_emoji)
    
    # Получаем клавиатуру с перемешанными эмодзи
    keyboard, _ = get_captcha_keyboard(correct_emoji)
    
    # Показываем пользователю какой эмодзи нужно выбрать
    await callback.message.edit_text(
        f"Выберите эмодзи: {correct_emoji}\n\n(Эмодзи для выбора ниже)",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("captcha_"))
async def process_captcha(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    selected_emoji = callback.data.split("_")[1]
    
    # Получаем сохраненный правильный эмодзи
    data = await state.get_data()
    correct_emoji = data.get("correct_captcha_emoji")
    attempts = data.get("captcha_attempts", 0)
    
    if not correct_emoji:
        # Если почему-то нет правильного эмодзи, начинаем заново
        await callback.message.edit_text(
            "Ошибка. Начните заново.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔓 Пройти капчу", callback_data="start_captcha")]]
            )
        )
        return
    
    logger.info(f"User {user_id} selected {selected_emoji}, correct is {correct_emoji}")
    
    if selected_emoji == correct_emoji:
        # Капча пройдена
        users_db[user_id]["captcha_passed"] = True
        await callback.message.delete()
        await callback.message.answer(
            f"✅ Капча пройдена!\n\nВаш ID: {users_db[user_id]['id']}\n\nМеню:",
            reply_markup=get_user_keyboard(user_id)
        )
        await state.clear()  # Очищаем состояние после успешной капчи
    else:
        # Неправильный выбор
        attempts += 1
        if attempts >= 3:
            await callback.message.edit_text(
                "❌ Слишком много попыток. Начните заново.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="🔓 Пройти капчу", callback_data="start_captcha")]]
                )
            )
            await state.clear()
            return
        
        await state.update_data(captcha_attempts=attempts)
        
        # Генерируем новый правильный эмодзи для следующей попытки
        new_correct_emoji = random.choice(CAPTCHA_EMOJIS)
        await state.update_data(correct_captcha_emoji=new_correct_emoji)
        
        # Получаем новую клавиатуру
        keyboard, _ = get_captcha_keyboard(new_correct_emoji)
        
        await callback.message.edit_text(
            f"❌ Вы выбрали не верный эмодзи. Попробуйте еще раз\n\n"
            f"Выберите эмодзи: {new_correct_emoji}\n\n"
            f"Попытка {attempts + 1}/3",
            reply_markup=keyboard
        )

# Профиль
@dp.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = users_db.get(user_id, {})
    
    if not user:
        await callback.answer("Ошибка: пользователь не найден", show_alert=True)
        return
    
    text = f"""
👤 {callback.from_user.full_name}, вот ваш профиль:

📝 Имя: {user.get('username', 'Не указано')}
🆔 ID: {user.get('id', 'Не указан')}
💰 Баланс: {user.get('balance', 0):.2f}₽
📊 Заказов выполнено: {user.get('orders_completed', 0)}
    """
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="balance_topup"))
    builder.add(InlineKeyboardButton(text="◀️ Назад", callback_data="menu"))
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# Пополнение баланса
@dp.callback_query(F.data == "balance_topup")
async def balance_topup(callback: CallbackQuery):
    await callback.message.edit_text(
        "💳 Выберите сумму на которую хотите пополнить баланс:",
        reply_markup=get_balance_topup_keyboard()
    )

@dp.callback_query(F.data.startswith("topup_"))
async def process_topup(callback: CallbackQuery):
    amount = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    order_id = generate_order_number()
    
    # Сохраняем запрос на пополнение
    balance_topups[order_id] = {
        "user_id": user_id,
        "amount": amount,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    
    # Ссылка на оплату
    payment_link = "https://finance.ozon.ru/apps/sbp/ozonbankpay/019c418f-ddf8-7d0f-94b5-93baedaa373b"
    
    await callback.message.edit_text(
        f"💳 Пополнение баланса на {amount}₽\n\n"
        f"Номер заказа: #{order_id}\n\n"
        f"Для оплаты перейдите по ссылке:\n{payment_link}\n\n"
        f"⚠️ После оплаты ожидайте подтверждения от администратора",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"paid_{order_id}")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="profile")]
            ]
        )
    )
    
    # Отправляем админу уведомление
    user_mention = f"<a href='tg://user?id={user_id}'>{callback.from_user.full_name}</a>"
    admin_text = f"""
🔔 Новая операция пополнения:

💰 Сумма: {amount}₽
👤 Заказал пользователь: {user_mention}
🆔 Номер заказа: #{order_id}
    """
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_confirm_topup_{order_id}"))
    builder.add(InlineKeyboardButton(text="❌ Отказать", callback_data=f"admin_reject_topup_{order_id}"))
    builder.adjust(2)
    
    await bot.send_message(ADMIN_ID, admin_text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("paid_"))
async def paid_notification(callback: CallbackQuery):
    order_id = callback.data.split("_")[1]
    await callback.answer("✅ Уведомление отправлено администратору", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)

# Товары
@dp.callback_query(F.data == "products")
async def show_categories(callback: CallbackQuery):
    await callback.message.edit_text(
        "🛍 Выберите категорию:",
        reply_markup=get_categories_keyboard()
    )

@dp.callback_query(F.data.startswith("cat_"))
async def show_services(callback: CallbackQuery):
    category = callback.data[4:]
    await callback.message.edit_text(
        f"📋 Список товаров для {category}:",
        reply_markup=get_services_keyboard(category)
    )

@dp.callback_query(F.data.startswith("service_"))
async def show_service_info(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    category = parts[1]
    service = parts[2]
    price_per_unit = categories[category][service]
    
    order_number = generate_order_number()
    
    await state.update_data(
        category=category,
        service=service,
        price_per_unit=price_per_unit,
        order_number=order_number
    )
    
    text = f"""
🛍 Товар: {service} ({category})

💰 Цена: {price_per_unit}₽ за 1 {service.lower().replace('накрутка ', '')}

Выберите количество:
    """
    
    await callback.message.edit_text(
        text,
        reply_markup=get_quantity_keyboard()
    )

@dp.callback_query(F.data.startswith("quantity_"))
async def process_quantity(callback: CallbackQuery, state: FSMContext):
    quantity = int(callback.data.split("_")[1])
    data = await state.get_data()
    
    price_per_unit = data.get('price_per_unit')
    total_price = quantity * price_per_unit
    
    await state.update_data(
        quantity=quantity,
        total_price=total_price
    )
    
    text = f"""
🛍 Товар: {data['service']} ({data['category']})

📊 Количество: {quantity} шт
💰 Цена за единицу: {price_per_unit}₽
💵 Итого к оплате: {total_price:.2f}₽
📦 Номер заказа: #{data['order_number']}
    """
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🛒 Купить", callback_data="buy_service"))
    builder.add(InlineKeyboardButton(text="◀️ Назад", callback_data=f"cat_{data['category']}"))
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "buy_service")
async def buy_service(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    
    total_price = data.get("total_price", 0)
    user_balance = users_db[user_id]["balance"]
    
    if user_balance < total_price:
        # Недостаточно средств
        await callback.message.edit_text(
            f"❌ Недостаточно средств на балансе.\n\n"
            f"Ваш баланс: {user_balance:.2f}₽\n"
            f"Сумма покупки: {total_price:.2f}₽\n\n"
            f"Пополните баланс и повторите попытку.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="balance_topup")],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="products")]
                ]
            )
        )
        return
    
    await callback.message.edit_text(
        "🔗 Скиньте ссылку на канал, пост, видео или профиль:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="products")]]
        )
    )
    await state.set_state(OrderStates.waiting_for_link)

@dp.message(OrderStates.waiting_for_link)
async def process_link(message: Message, state: FSMContext):
    link = message.text
    data = await state.get_data()
    
    await state.update_data(link=link)
    
    text = f"""
✅ Проверьте данные:

📦 Товар: {data['service']} ({data['category']})
📊 Количество: {data['quantity']} шт
💵 Сумма: {data['total_price']:.2f}₽
🔢 Номер заказа: #{data['order_number']}
🔗 Ссылка: {link}
    """
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_order"))
    builder.add(InlineKeyboardButton(text="✏️ Изменить ссылку", callback_data="change_link"))
    builder.add(InlineKeyboardButton(text="❌ Отменить", callback_data="products"))
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup())
    await state.set_state(OrderStates.confirming_order)

@dp.callback_query(F.data == "change_link", OrderStates.confirming_order)
async def change_link(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🔗 Скиньте новую ссылку:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="products")]]
        )
    )
    await state.set_state(OrderStates.waiting_for_link)

@dp.callback_query(F.data == "confirm_order", OrderStates.confirming_order)
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    
    # Проверяем баланс еще раз
    if users_db[user_id]["balance"] < data['total_price']:
        await callback.message.edit_text(
            "❌ Недостаточно средств. Пополните баланс.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="💳 Пополнить", callback_data="balance_topup")]]
            )
        )
        await state.clear()
        return
    
    # Списываем средства
    users_db[user_id]["balance"] -= data['total_price']
    
    # Сохраняем заказ
    order_id = data['order_number']
    orders_db[order_id] = {
        "user_id": user_id,
        "category": data['category'],
        "service": data['service'],
        "quantity": data['quantity'],
        "link": data['link'],
        "price_per_unit": data['price_per_unit'],
        "total_price": data['total_price'],
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    pending_orders[order_id] = orders_db[order_id]
    
    # Отправляем подтверждение пользователю
    await callback.message.edit_text(
        f"✅ Вы совершили покупку {data['category']} {data['service']}.\n"
        f"Количество: {data['quantity']} шт\n"
        f"Сумма: {data['total_price']:.2f}₽\n"
        f"Номер заказа - #{order_id}.\n\n"
        f"Ожидайте в скором времени мы выполним ваш заказ.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="menu")]]
        )
    )
    
    # Отправляем запрос на отзыв
    await asyncio.sleep(2)
    await callback.message.answer(
        "⭐ Поставьте отзыв по 5-бальной шкале:",
        reply_markup=get_review_keyboard()
    )
    
    # Отправляем админу уведомление
    user_mention = f"<a href='tg://user?id={user_id}'>{callback.from_user.full_name}</a>"
    admin_text = f"""
🔔 Новая операция покупки:

📁 Категория: {data['category']}
🛍 Товар: {data['service']}
📊 Количество: {data['quantity']} шт
👤 Заказал пользователь: {user_mention}
🔗 Ссылка: {data['link']}
💰 Цена за ед: {data['price_per_unit']}₽
💵 Общая сумма: {data['total_price']:.2f}₽
🆔 Номер заказа: #{order_id}
    """
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_confirm_order_{order_id}"))
    builder.add(InlineKeyboardButton(text="❌ Отказать", callback_data=f"admin_reject_order_{order_id}"))
    builder.adjust(2)
    
    await bot.send_message(ADMIN_ID, admin_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    
    await state.clear()

# Отзывы
@dp.callback_query(F.data.startswith("review_rate_"))
async def process_review_rate(callback: CallbackQuery, state: FSMContext):
    rating = int(callback.data.split("_")[2])
    await state.update_data(review_rating=rating)
    
    await callback.message.edit_text(
        f"⭐ Ваша оценка: {'⭐' * rating}\n\n"
        f"📝 Напишите текстовый отзыв:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🤐 Промолчать", callback_data="review_skip")]
            ]
        )
    )
    await state.set_state(OrderStates.waiting_for_review_text)

@dp.callback_query(F.data == "review_skip", OrderStates.waiting_for_review_text)
async def skip_review(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    rating = data.get("review_rating", 5)
    
    await callback.message.edit_text(
        "🙏 Спасибо за ваш отзыв!",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="menu")]]
        )
    )
    
    # Отправляем в группу отзывов
    review_text = f"""
👤 Имя: {callback.from_user.full_name}
⭐ Оценка: {'⭐' * rating}
    """
    await bot.send_message(-1002241334828, review_text)  # Замените на ID вашей группы
    
    await state.clear()

@dp.message(OrderStates.waiting_for_review_text)
async def process_review_text(message: Message, state: FSMContext):
    data = await state.get_data()
    rating = data.get("review_rating", 5)
    review_text = message.text
    
    await message.answer(
        "🙏 Спасибо за ваш отзыв!",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="menu")]]
        )
    )
    
    # Отправляем в группу отзывов
    review = f"""
👤 Имя: {message.from_user.full_name}
⭐ Оценка: {'⭐' * rating}
📝 Текстовое сообщение: {review_text}
    """
    await bot.send_message(-1002241334828, review)  # Замените на ID вашей группы
    
    await state.clear()

@dp.callback_query(F.data == "reviews")
async def show_reviews(callback: CallbackQuery):
    await callback.message.edit_text(
        "📢 Наш канал с отзывами:\nhttps://t.me/+3HhfVF9qXb40OWIy",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="menu")]]
        )
    )

@dp.callback_query(F.data == "support")
async def show_support(callback: CallbackQuery):
    await callback.message.edit_text(
        "🆘 Техподдержка:\nhttp://t.me/VapePriceShop",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="menu")]]
        )
    )

@dp.callback_query(F.data == "menu")
async def back_to_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.message.edit_text(
        "📱 Главное меню:",
        reply_markup=get_user_keyboard(user_id)
    )

# Админ-панель
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    await message.answer(
        "👑 Панель администратора:",
        reply_markup=get_admin_keyboard()
    )

@dp.callback_query(F.data == "admin_online")
async def admin_online(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    online_count = len([u for u in users_db.keys() if u in [m.from_user.id for m in (await bot.get_updates())]])
    
    await callback.message.edit_text(
        f"👥 Пользователей в базе: {len(users_db)}\n"
        f"🟢 Онлайн: {online_count}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]
        )
    )

@dp.callback_query(F.data == "admin_pending")
async def admin_pending(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    if not pending_orders:
        await callback.message.edit_text(
            "📭 Нет ожидающих заказов",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]
            )
        )
        return
    
    text = "⏳ Ожидающие заказы:\n\n"
    for order_id, order in pending_orders.items():
        text += f"#{order_id} - {order['service']} - {order['quantity']} шт - {order['total_price']}₽ - {order['created_at']}\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]
        )
    )

@dp.callback_query(F.data == "admin_completed")
async def admin_completed(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    if not completed_orders:
        await callback.message.edit_text(
            "📭 Нет выполненных заказов",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]
            )
        )
        return
    
    text = "✅ Выполненные заказы:\n\n"
    for order_id, order in list(completed_orders.items())[-10:]:  # Последние 10
        text += f"#{order_id} - {order['service']} - {order['quantity']} шт - {order['total_price']}₽\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]]
        )
    )

@dp.callback_query(F.data == "admin_balance")
async def admin_balance(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    
    await callback.message.edit_text(
        "💰 Введите ID пользователя и сумму через пробел\n"
        "Пример: 12345678 1000",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_back")]]
        )
    )
    await state.set_state(AdminStates.waiting_for_balance_amount)

@dp.message(AdminStates.waiting_for_balance_amount)
async def process_balance_add(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        user_id_str, amount_str = message.text.split()
        amount = float(amount_str)
        
        # Ищем пользователя по его ID в нашей базе
        target_user_id = None
        for uid, data in users_db.items():
            if data.get('id') == user_id_str:
                target_user_id = uid
                break
        
        if not target_user_id:
            await message.answer("❌ Пользователь с таким ID не найден")
            await state.clear()
            return
        
        # Начисляем баланс
        users_db[target_user_id]["balance"] += amount
        
        await message.answer(
            f"✅ Баланс пользователя {users_db[target_user_id]['username']} пополнен на {amount}₽",
            reply_markup=get_admin_keyboard()
        )
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                target_user_id,
                f"💰 Ваш баланс был пополнен на {amount}₽ администратором."
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке пользователю: {e}")
        
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: ID_пользователя сумма")
    finally:
        await state.clear()

@dp.callback_query(F.data.startswith("admin_confirm_topup_"))
async def admin_confirm_topup(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    
    order_id = callback.data.split("_")[3]
    topup = balance_topups.get(order_id)
    
    if not topup:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    
    user_id = topup['user_id']
    amount = topup['amount']
    
    # Начисляем баланс
    if user_id in users_db:
        users_db[user_id]["balance"] += amount
        topup['status'] = 'completed'
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"✅ Вы успешно пополнили баланс на {amount}₽. Покупайте товары прямо сейчас!",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🛍 Купить", callback_data="products")]
                    ]
                )
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке пользователю: {e}")
        
        await callback.message.edit_text(
            f"✅ Пополнение #{order_id} подтверждено",
            reply_markup=get_admin_keyboard()
        )
    else:
        await callback.message.edit_text(
            "❌ Пользователь не найден",
            reply_markup=get_admin_keyboard()
        )

@dp.callback_query(F.data.startswith("admin_reject_topup_"))
async def admin_reject_topup(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    
    order_id = callback.data.split("_")[3]
    await state.update_data(reject_order_id=order_id, reject_type='topup')
    
    await callback.message.edit_text(
        "❓ По какой причине вы отказали?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_back")]]
        )
    )
    await state.set_state(AdminStates.waiting_for_reject_reason)

@dp.callback_query(F.data.startswith("admin_confirm_order_"))
async def admin_confirm_order(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    order_id = callback.data.split("_")[3]
    order = orders_db.get(order_id)
    
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    
    # Обновляем статус
    order['status'] = 'completed'
    if order_id in pending_orders:
        del pending_orders[order_id]
    completed_orders[order_id] = order
    
    # Увеличиваем счетчик выполненных заказов пользователя
    user_id = order['user_id']
    if user_id in users_db:
        users_db[user_id]['orders_completed'] += 1
    
    # Уведомляем пользователя
    try:
        await bot.send_message(
            user_id,
            f"✅ Ваш заказ #{order_id} выполнен!\n\nСпасибо за покупку!"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке пользователю: {e}")
    
    await callback.message.edit_text(
        f"✅ Заказ #{order_id} подтвержден",
        reply_markup=get_admin_keyboard()
    )

@dp.callback_query(F.data.startswith("admin_reject_order_"))
async def admin_reject_order(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    
    order_id = callback.data.split("_")[3]
    await state.update_data(reject_order_id=order_id, reject_type='order')
    
    await callback.message.edit_text(
        "❓ По какой причине вы отказали?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_back")]]
        )
    )
    await state.set_state(AdminStates.waiting_for_reject_reason)

@dp.message(AdminStates.waiting_for_reject_reason)
async def process_reject_reason(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    data = await state.get_data()
    order_id = data.get('reject_order_id')
    reject_type = data.get('reject_type')
    reason = message.text
    
    if reject_type == 'topup':
        topup = balance_topups.get(order_id)
        if topup:
            user_id = topup['user_id']
            topup['status'] = 'rejected'
            
            try:
                await bot.send_message(
                    user_id,
                    f"❌ Отказ по пополнению баланса #{order_id}\n\nПричина: {reason}"
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке пользователю: {e}")
            
            await message.answer(
                f"✅ Отказ отправлен пользователю",
                reply_markup=get_admin_keyboard()
            )
    
    elif reject_type == 'order':
        order = orders_db.get(order_id)
        if order:
            user_id = order['user_id']
            
            # Возвращаем средства
            if user_id in users_db:
                users_db[user_id]['balance'] += order['total_price']
            
            try:
                await bot.send_message(
                    user_id,
                    f"❌ Отказ по заказу #{order_id}\n\nПричина: {reason}\n\nСредства возвращены на баланс."
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке пользователю: {e}")
            
            await message.answer(
                f"✅ Отказ отправлен пользователю, средства возвращены",
                reply_markup=get_admin_keyboard()
            )
    
    await state.clear()

@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    await callback.message.edit_text(
        "👑 Панель администратора:",
        reply_markup=get_admin_keyboard()
    )

# Добавление/удаление товаров (админка)
@dp.callback_query(F.data == "admin_add_service")
async def admin_add_service(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    
    categories_list = "\n".join(categories.keys())
    await callback.message.edit_text(
        f"📝 Введите категорию, название товара и цену через запятую\n"
        f"Пример: Telegram,Накрутка подписчиков,0.4\n\n"
        f"Доступные категории:\n{categories_list}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_back")]]
        )
    )
    await state.set_state(AdminStates.waiting_for_service_add)

@dp.message(AdminStates.waiting_for_service_add)
async def process_service_add(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        category, service, price = message.text.split(',')
        price = float(price.strip())
        category = category.strip()
        service = service.strip()
        
        if category not in categories:
            await message.answer("❌ Категория не найдена")
            return
        
        categories[category][service] = price
        
        await message.answer(
            f"✅ Товар добавлен:\nКатегория: {category}\nТовар: {service}\nЦена: {price}₽",
            reply_markup=get_admin_keyboard()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        await state.clear()

@dp.callback_query(F.data == "admin_delete_service")
async def admin_delete_service(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    
    categories_list = "\n".join(categories.keys())
    await callback.message.edit_text(
        f"📝 Введите категорию и название товара через запятую для удаления\n"
        f"Пример: Telegram,Накрутка подписчиков\n\n"
        f"Доступные категории:\n{categories_list}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_back")]]
        )
    )
    await state.set_state(AdminStates.waiting_for_service_delete)

@dp.message(AdminStates.waiting_for_service_delete)
async def process_service_delete(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        category, service = message.text.split(',')
        category = category.strip()
        service = service.strip()
        
        if category not in categories:
            await message.answer("❌ Категория не найдена")
            return
        
        if service not in categories[category]:
            await message.answer("❌ Товар не найден в этой категории")
            return
        
        del categories[category][service]
        
        await message.answer(
            f"✅ Товар удален:\nКатегория: {category}\nТовар: {service}",
            reply_markup=get_admin_keyboard()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        await state.clear()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    
    await callback.message.edit_text(
        "📢 Введите сообщение для рассылки всем пользователям:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_back")]]
        )
    )
    await state.set_state(AdminStates.waiting_for_broadcast)

@dp.message(AdminStates.waiting_for_broadcast)
async def process_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    text = message.text
    sent = 0
    failed = 0
    
    for user_id in users_db.keys():
        try:
            await bot.send_message(user_id, f"📢 Рассылка:\n\n{text}")
            sent += 1
            await asyncio.sleep(0.05)  # Чтобы не флудить
        except Exception as e:
            failed += 1
            logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
    
    await message.answer(
        f"✅ Рассылка завершена\n"
        f"📨 Отправлено: {sent}\n"
        f"❌ Не доставлено: {failed}",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()

# Обработка неизвестных команд
@dp.message()
async def handle_unknown(message: Message):
    user_id = message.from_user.id
    
    if user_id in users_db and users_db[user_id]["captcha_passed"]:
        await message.answer(
            "Используйте кнопки меню для навигации",
            reply_markup=get_user_keyboard(user_id)
        )
    else:
        await cmd_start(message, FSMContext())

# Запуск бота
async def main():
    try:
        print("Бот запущен...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
