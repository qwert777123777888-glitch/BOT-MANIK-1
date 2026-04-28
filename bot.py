import telebot
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import json
import os
import schedule
import time
import threading
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import calendar
import re

# ==================== ФИКС ОШИБКИ "message is not modified" ====================
import telebot.apihelper

original_edit = telebot.apihelper.edit_message_text

def patched_edit(token, text, chat_id, message_id, *args, **kwargs):
    try:
        return original_edit(token, text, chat_id, message_id, *args, **kwargs)
    except Exception as e:
        if "message is not modified" in str(e):
            return None
        raise

telebot.apihelper.edit_message_text = patched_edit

# Импорт конфигурации
from config import (
    TOKEN, ADMIN_IDS, WORK_START_HOUR, WORK_END_HOUR,
    SERVICES, REMINDER_DAY_BEFORE, REMINDER_HOUR_BEFORE,
    WELCOME_TEXT, PORTFOLIO_TEXT, PRICE_TEXT, PORTFOLIO_PHOTO_URL
)

# ==================== ДНИ НЕДЕЛИ НА РУССКОМ ====================
DAYS_RU = {
    'Monday': 'Понедельник',
    'Tuesday': 'Вторник',
    'Wednesday': 'Среда',
    'Thursday': 'Четверг',
    'Friday': 'Пятница',
    'Saturday': 'Суббота',
    'Sunday': 'Воскресенье'
}

def get_day_ru(date_obj):
    """Получить день недели на русском"""
    day_en = date_obj.strftime("%A")
    return DAYS_RU.get(day_en, day_en)

def format_duration(duration_minutes):
    """Форматирование длительности"""
    hours = duration_minutes // 60
    minutes = duration_minutes % 60
    if hours > 0 and minutes > 0:
        return f"{hours} ч {minutes} мин"
    elif hours > 0:
        return f"{hours} ч"
    else:
        return f"{minutes} мин"

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

# ==================== ХРАНИЛИЩЕ ДАННЫХ ====================
DATA_DIR = os.getenv("DATA_DIR", "data")
os.makedirs(DATA_DIR, exist_ok=True)

APPOINTMENTS_FILE = os.path.join(DATA_DIR, "appointments.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
user_booking_data = {}

# ==================== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ====================

def save_user(user_id, username, first_name):
    """Сохранить пользователя в базу"""
    users = load_users()
    if str(user_id) not in users:
        users[str(user_id)] = {
            'user_id': user_id,
            'username': username or '',
            'first_name': first_name or '',
            'first_seen': datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        save_users(users)

def load_users():
    """Загрузка списка пользователей"""
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content.strip():
                return {}
            return json.loads(content)
    except:
        return {}

def save_users(data):
    """Сохранение списка пользователей"""
    try:
        temp_file = USERS_FILE + ".tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if os.path.exists(USERS_FILE):
            os.remove(USERS_FILE)
        os.rename(temp_file, USERS_FILE)
    except Exception as e:
        print(f"Ошибка сохранения пользователей: {e}")

def get_all_users():
    """Получить всех пользователей"""
    users = load_users()
    return list(users.values())

# ==================== РАБОТА С ФАЙЛАМИ ЗАПИСЕЙ ====================

def load_appointments():
    """Загрузка записей из файла"""
    if not os.path.exists(APPOINTMENTS_FILE):
        return {}
    try:
        with open(APPOINTMENTS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content.strip():
                return {}
            data = json.loads(content)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, PermissionError) as e:
        print(f"⚠️ Ошибка чтения файла: {e}")
        if os.path.exists(APPOINTMENTS_FILE):
            backup_name = f"{APPOINTMENTS_FILE}.backup"
            try:
                os.rename(APPOINTMENTS_FILE, backup_name)
                print(f"📁 Создана резервная копия: {backup_name}")
            except:
                pass
        return {}

def save_appointments(data):
    """Сохранение записей в файл"""
    try:
        temp_file = APPOINTMENTS_FILE + ".tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if os.path.exists(APPOINTMENTS_FILE):
            os.remove(APPOINTMENTS_FILE)
        os.rename(temp_file, APPOINTMENTS_FILE)
    except PermissionError as e:
        print(f"❌ Ошибка сохранения: {e}")
        alt_file = os.path.join(DATA_DIR, "appointments_backup.json")
        try:
            with open(alt_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ Данные сохранены в {alt_file}")
        except:
            print("❌ Не удалось сохранить данные")
    except Exception as e:
        print(f"❌ Неожиданная ошибка сохранения: {e}")

# ==================== РАБОТА С ЗАПИСЯМИ ====================

def get_appointments_for_date(date_str):
    """Получить записи на конкретную дату"""
    appointments = load_appointments()
    return appointments.get(date_str, {})

def add_appointment(date_str, time_str, user_id, username, client_name, client_phone, service_name="", duration=60):
    """Добавить запись с данными клиента и услугой"""
    appointments = load_appointments()
    if date_str not in appointments:
        appointments[date_str] = {}
    for d, times in list(appointments.items()):
        for t, data in list(times.items()):
            if data.get('user_id') == user_id:
                del appointments[d][t]
                if not appointments[d]:
                    del appointments[d]
    appointments[date_str][time_str] = {
        'user_id': user_id,
        'username': username,
        'client_name': client_name,
        'client_phone': client_phone,
        'service_name': service_name,
        'duration': duration,
        'reminded_day': False,
        'reminded_hour': False
    }
    save_appointments(appointments)

def cancel_appointment(user_id):
    """Отменить запись пользователя"""
    appointments = load_appointments()
    for date_str, times in list(appointments.items()):
        for time_str, data in list(times.items()):
            if data.get('user_id') == user_id:
                del appointments[date_str][time_str]
                if not appointments[date_str]:
                    del appointments[date_str]
                save_appointments(appointments)
                return date_str, time_str, data
    return None, None, None

def cancel_appointment_admin(date_str, time_str):
    """Отменить запись админом"""
    appointments = load_appointments()
    if date_str in appointments and time_str in appointments[date_str]:
        data = appointments[date_str][time_str]
        del appointments[date_str][time_str]
        if not appointments[date_str]:
            del appointments[date_str]
        save_appointments(appointments)
        return data
    return None

def get_user_appointment(user_id):
    """Получить запись пользователя"""
    appointments = load_appointments()
    for date_str, times in appointments.items():
        for time_str, data in times.items():
            if data.get('user_id') == user_id:
                return date_str, time_str, data
    return None, None, None

def get_all_appointments():
    """Получить все записи"""
    appointments = load_appointments()
    result = []
    for date_str in sorted(appointments.keys()):
        for time_str in sorted(appointments[date_str].keys()):
            data = appointments[date_str][time_str]
            result.append({
                'date': date_str,
                'time': time_str,
                'username': data.get('username', 'Unknown'),
                'user_id': data.get('user_id', 0),
                'client_name': data.get('client_name', 'Не указано'),
                'client_phone': data.get('client_phone', 'Не указано'),
                'service_name': data.get('service_name', ''),
                'duration': data.get('duration', 60)
            })
    return result

# ==================== ГЕНЕРАЦИЯ СЛОТОВ ====================

def get_available_slots(date_str, duration_minutes=60):
    """Получить доступные слоты на дату с учётом длительности услуги"""
    try:
        datetime.strptime(date_str, "%d.%m.%Y")
        all_slots = []
        hour = WORK_START_HOUR
        minute = 0
        while hour <= WORK_END_HOUR:
            time_str = f"{hour:02d}:{minute:02d}"
            all_slots.append(time_str)
            minute += 30
            if minute >= 60:
                minute = 0
                hour += 1
        valid_slots = []
        for slot in all_slots:
            slot_h, slot_m = map(int, slot.split(":"))
            end_minutes = slot_h * 60 + slot_m + duration_minutes
            end_h = end_minutes // 60
            if end_h < WORK_END_HOUR or (end_h == WORK_END_HOUR and end_minutes % 60 == 0):
                valid_slots.append(slot)
        appointments = get_appointments_for_date(date_str)
        busy_slots = set()
        for slot in valid_slots:
            slot_start = int(slot.split(":")[0]) * 60 + int(slot.split(":")[1])
            slot_end = slot_start + duration_minutes
            for booked_time, data in appointments.items():
                booked_h, booked_m = map(int, booked_time.split(":"))
                booked_start = booked_h * 60 + booked_m
                booked_duration = data.get('duration', 60)
                booked_end = booked_start + booked_duration
                if slot_start < booked_end and slot_end > booked_start:
                    busy_slots.add(slot)
                    break
        available = [s for s in valid_slots if s not in busy_slots]
        return available
    except:
        return []

# ==================== ВАЛИДАЦИЯ ====================

def validate_phone(phone):
    phone = re.sub(r'\D', '', phone)
    if len(phone) == 11 and (phone.startswith('7') or phone.startswith('8')):
        return True, phone
    if len(phone) == 10 and phone.startswith('9'):
        return True, '7' + phone
    return False, phone

def validate_name(name):
    name = name.strip()
    return 2 <= len(name) <= 50

def format_phone_display(phone):
    if len(phone) == 11:
        return f"+{phone[0]} ({phone[1:4]}) {phone[4:7]}-{phone[7:9]}-{phone[9:11]}"
    return phone

# ==================== КЛАВИАТУРЫ ПОЛЬЗОВАТЕЛЯ ====================

def main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        types.KeyboardButton("📅 Записаться на приём"),
        types.KeyboardButton("❌ Отменить запись"),
        types.KeyboardButton("🎨 Портфолио"),
        types.KeyboardButton("💰 Прайс-лист"),
        types.KeyboardButton("📋 Моя запись")
    )
    return keyboard

def phone_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    keyboard.add(KeyboardButton("📱 Отправить номер телефона", request_contact=True))
    keyboard.add(KeyboardButton("🔙 Отмена"))
    return keyboard

def cancel_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    keyboard.add(KeyboardButton("🔙 Отмена"))
    return keyboard

# ==================== КАЛЕНДАРЬ ДЛЯ КЛИЕНТОВ ====================

def create_calendar(year, month):
    markup = InlineKeyboardMarkup(row_width=7)
    month_names = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    markup.add(
        InlineKeyboardButton("◀️", callback_data=f"cal_nav_{prev_year}_{prev_month}"),
        InlineKeyboardButton(f"{month_names[month-1]} {year}", callback_data="cal_ignore"),
        InlineKeyboardButton("▶️", callback_data=f"cal_nav_{next_year}_{next_month}")
    )
    markup.add(*[InlineKeyboardButton(d, callback_data="cal_ignore") for d in ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]])
    cal = calendar.monthcalendar(year, month)
    today = datetime.now()
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="cal_ignore"))
            else:
                date_str = f"{day:02d}.{month:02d}.{year}"
                date_obj = datetime(year, month, day)
                if date_obj.date() < today.date():
                    row.append(InlineKeyboardButton(" · ", callback_data="cal_ignore"))
                else:
                    has_slots = False
                    for duration in SERVICES.values():
                        if get_available_slots(date_str, duration):
                            has_slots = True
                            break
                    if has_slots:
                        row.append(InlineKeyboardButton(f"📍{day}" if date_obj.date() == today.date() else str(day), callback_data=f"cal_day_{date_str}"))
                    else:
                        row.append(InlineKeyboardButton(f"🔴{day}", callback_data="cal_ignore"))
        markup.add(*row)
    markup.add(InlineKeyboardButton("🏠 В главное меню", callback_data="cal_main_menu"))
    return markup

def create_service_keyboard(date_str):
    markup = InlineKeyboardMarkup(row_width=1)
    for service_name, duration in SERVICES.items():
        markup.add(InlineKeyboardButton(f"{service_name} ({format_duration(duration)})", callback_data=f"service_{date_str}_{service_name}"))
    markup.add(InlineKeyboardButton("🔙 К календарю", callback_data="cal_back"))
    markup.add(InlineKeyboardButton("🏠 В главное меню", callback_data="cal_main_menu"))
    return markup

def create_time_slots_keyboard(date_str, duration_minutes=60):
    markup = InlineKeyboardMarkup(row_width=3)
    available_slots = get_available_slots(date_str, duration_minutes)
    if not available_slots:
        markup.add(InlineKeyboardButton("❌ Нет свободных слотов", callback_data="cal_ignore"))
    else:
        for i in range(0, len(available_slots), 3):
            row = []
            for slot in available_slots[i:i+3]:
                row.append(InlineKeyboardButton(f"🕐 {slot}", callback_data=f"slot_{date_str}_{slot}"))
            markup.add(*row)
    markup.add(InlineKeyboardButton("🔙 К выбору услуги", callback_data=f"service_back_{date_str}"))
    markup.add(InlineKeyboardButton("🏠 В главное меню", callback_data="cal_main_menu"))
    return markup

# ==================== КАЛЕНДАРЬ ДЛЯ АДМИНА ====================

def create_admin_calendar(year, month, appointments):
    markup = InlineKeyboardMarkup(row_width=7)
    month_names = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    dates_with_appointments = {}
    for app in appointments:
        d = app['date']
        if d not in dates_with_appointments:
            dates_with_appointments[d] = []
        dates_with_appointments[d].append(app)
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    markup.add(
        InlineKeyboardButton("◀️", callback_data=f"admin_nav_{prev_year}_{prev_month}"),
        InlineKeyboardButton(f"{month_names[month-1]} {year}", callback_data="admin_ignore"),
        InlineKeyboardButton("▶️", callback_data=f"admin_nav_{next_year}_{next_month}")
    )
    markup.add(*[InlineKeyboardButton(d, callback_data="admin_ignore") for d in ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]])
    cal = calendar.monthcalendar(year, month)
    today = datetime.now()
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="admin_ignore"))
            else:
                date_str = f"{day:02d}.{month:02d}.{year}"
                date_obj = datetime(year, month, day)
                if date_obj.date() < today.date():
                    row.append(InlineKeyboardButton(" · ", callback_data="admin_ignore"))
                else:
                    if date_str in dates_with_appointments:
                        row.append(InlineKeyboardButton(f"📍{day}" if date_obj.date() == today.date() else f"🔵{day}", callback_data=f"admin_day_{date_str}"))
                    else:
                        row.append(InlineKeyboardButton(f"📍{day}" if date_obj.date() == today.date() else str(day), callback_data=f"admin_day_{date_str}"))
        markup.add(*row)
    markup.add(InlineKeyboardButton("📋 Все записи списком", callback_data="admin_all_list"))
    markup.add(InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"))
    markup.add(InlineKeyboardButton("🔄 Обновить", callback_data=f"admin_refresh_{year}_{month}"))
    markup.add(InlineKeyboardButton("🚪 Закрыть админ-панель", callback_data="admin_close"))
    return markup

# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@bot.message_handler(commands=['start'])
def start_command(message):
    save_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    bot.send_message(message.chat.id, WELCOME_TEXT, reply_markup=main_keyboard(), parse_mode="Markdown")

@bot.message_handler(commands=['admin_panel'])
def admin_panel_command(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "🚫 У вас нет доступа к этой команде.")
        return
    show_admin_panel(message.chat.id)

@bot.message_handler(commands=['news'])
def news_command(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "🚫 У вас нет доступа к этой команде.")
        return
    text = message.text.replace('/news', '').strip()
    if not text:
        bot.reply_to(message, "❌ *Укажите текст рассылки*\n\nПример:\n`/news Дорогие клиенты! Акция!`", parse_mode="Markdown")
        return
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ Отправить", callback_data=f"broadcast_confirm_{message.message_id}"), InlineKeyboardButton("❌ Отмена", callback_data="broadcast_cancel"))
    user_booking_data[f"broadcast_{message.from_user.id}"] = text
    users = get_all_users()
    bot.reply_to(message, f"📢 *Подтвердите рассылку*\n\n📝 Текст:\n«{text}»\n\n👥 Получателей: *{len(users)}*\n\nОтправить?", reply_markup=markup, parse_mode="Markdown")

# ==================== ОСНОВНЫЕ КНОПКИ МЕНЮ ====================

@bot.message_handler(func=lambda msg: msg.text == "📅 Записаться на приём")
def book_appointment(message):
    save_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    user_booking_data.pop(message.from_user.id, None)
    today = datetime.now()
    bot.send_message(message.chat.id, f"📅 *Выберите дату:*\n\n🔴 — нет свободных слотов\n📍 — сегодняшняя дата\n· — прошедшая дата", reply_markup=create_calendar(today.year, today.month), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "❌ Отменить запись")
def cancel_appointment_handler(message):
    date_str, time_str, data = get_user_appointment(message.from_user.id)
    if not date_str:
        bot.send_message(message.chat.id, "❌ У вас нет активной записи.", reply_markup=main_keyboard())
        return
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ Да, отменить", callback_data="cancel_confirm"), InlineKeyboardButton("❌ Нет, оставить", callback_data="cancel_decline"))
    date_obj = datetime.strptime(date_str, "%d.%m.%Y")
    bot.send_message(message.chat.id, f"📋 *Ваша запись:*\n\n👤 Имя: *{data.get('client_name', 'Не указано')}*\n📅 Дата: *{date_str}* ({get_day_ru(date_obj)})\n🕐 Время: *{time_str}*\n\n*Вы уверены, что хотите отменить запись?*", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "🎨 Портфолио")
def portfolio(message):
    try:
        if PORTFOLIO_PHOTO_URL:
            bot.send_photo(message.chat.id, PORTFOLIO_PHOTO_URL, caption=PORTFOLIO_TEXT, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, PORTFOLIO_TEXT, parse_mode="Markdown")
        bot.send_message(message.chat.id, "Выберите действие:", reply_markup=main_keyboard())
    except Exception as e:
        print(f"Ошибка отправки фото: {e}")
        bot.send_message(message.chat.id, PORTFOLIO_TEXT, reply_markup=main_keyboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "💰 Прайс-лист")
def price_list(message):
    bot.send_message(message.chat.id, PRICE_TEXT, reply_markup=main_keyboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "📋 Моя запись")
def my_appointment(message):
    date_str, time_str, data = get_user_appointment(message.from_user.id)
    if not date_str:
        bot.send_message(message.chat.id, "❌ У вас нет активной записи.\n\nНажмите «📅 Записаться на приём».", reply_markup=main_keyboard())
        return
    date_obj = datetime.strptime(date_str, "%d.%m.%Y")
    phone_display = format_phone_display(data.get('client_phone', '')) if data.get('client_phone') else 'Не указано'
    service = data.get('service_name', '')
    duration = data.get('duration', 60)
    dur_str = format_duration(duration)
    time_parts = time_str.split(":")
    start_min = int(time_parts[0]) * 60 + int(time_parts[1])
    end_time = f"{((start_min + duration) // 60):02d}:{((start_min + duration) % 60):02d}"
    text = f"📋 *Ваша запись:*\n\n👤 Имя: *{data.get('client_name', 'Не указано')}*\n📱 Телефон: *{phone_display}*\n📅 Дата: *{date_str}* ({get_day_ru(date_obj)})\n🕐 Время: *{time_str} - {end_time}*\n"
    if service:
        text += f"💅 Услуга: *{service}* ({dur_str})\n"
    text += f"\n🔔 Напоминания:\n• За 1 день до записи\n• За 1 час до записи\n\nЕсли нужно отменить, нажмите «❌ Отменить запись»"
    bot.send_message(message.chat.id, text, reply_markup=main_keyboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "🔙 Отмена")
def cancel_booking_process(message):
    user_booking_data.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "❌ Запись отменена.", reply_markup=main_keyboard())

# ==================== ОБРАБОТЧИКИ КАЛЕНДАРЯ КЛИЕНТА ====================

@bot.callback_query_handler(func=lambda call: call.data.startswith("cal_nav_"))
def calendar_navigation(call):
    _, _, year, month = call.data.split("_")
    year, month = int(year), int(month)
    today = datetime.now()
    max_date = today + relativedelta(months=2)
    if datetime(year, month, 1) > max_date:
        bot.answer_callback_query(call.id, "📅 Можно записаться только на 2 месяца вперёд")
        return
    if datetime(year, month, 1) < datetime(today.year, today.month, 1):
        bot.answer_callback_query(call.id, "📅 Нельзя выбрать прошедший месяц")
        return
    bot.edit_message_text(f"📅 *Выберите дату:*\n\n🔴 — нет свободных слотов\n📍 — сегодняшняя дата", call.message.chat.id, call.message.message_id, reply_markup=create_calendar(year, month), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("cal_day_"))
def calendar_day_selected(call):
    date_str = call.data.replace("cal_day_", "")
    date_obj = datetime.strptime(date_str, "%d.%m.%Y")
    bot.edit_message_text(f"📅 *{date_str}* ({get_day_ru(date_obj)})\n\n💅 *Выберите услугу:*", call.message.chat.id, call.message.message_id, reply_markup=create_service_keyboard(date_str), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("service_") and not call.data.startswith("service_back_"))
def service_selected(call):
    parts = call.data.split("_", 2)
    date_str = parts[1]
    service_name = parts[2]
    duration = SERVICES.get(service_name, 60)
    user_booking_data[call.from_user.id] = {'date': date_str, 'service': service_name, 'duration': duration}
    available_slots = get_available_slots(date_str, duration)
    date_obj = datetime.strptime(date_str, "%d.%m.%Y")
    bot.edit_message_text(f"📅 *{date_str}* ({get_day_ru(date_obj)})\n💅 *{service_name}* ({format_duration(duration)})\n\n🕐 *Выберите время:*\nДоступно слотов: {len(available_slots)}", call.message.chat.id, call.message.message_id, reply_markup=create_time_slots_keyboard(date_str, duration), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("service_back_"))
def service_back(call):
    date_str = call.data.replace("service_back_", "")
    date_obj = datetime.strptime(date_str, "%d.%m.%Y")
    bot.edit_message_text(f"📅 *{date_str}* ({get_day_ru(date_obj)})\n\n💅 *Выберите услугу:*", call.message.chat.id, call.message.message_id, reply_markup=create_service_keyboard(date_str), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("slot_"))
def time_slot_selected(call):
    _, date_str, time_str = call.data.split("_", 2)
    booking = user_booking_data.get(call.from_user.id, {})
    duration = booking.get('duration', 60)
    service = booking.get('service', '')
    available_slots = get_available_slots(date_str, duration)
    if time_str not in available_slots:
        bot.answer_callback_query(call.id, "❌ Это время уже занято. Выберите другое.")
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_time_slots_keyboard(date_str, duration))
        except:
            pass
        return
    user_booking_data[call.from_user.id] = {'date': date_str, 'time': time_str, 'service': service, 'duration': duration}
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    msg = bot.send_message(call.message.chat.id, "📝 *Введите ваше имя:*\n\nНапример: Анна", reply_markup=cancel_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_name)

# ==================== ПРОЦЕСС ЗАПИСИ ====================

def process_name(message):
    user_id = message.from_user.id
    if message.text == "🔙 Отмена":
        user_booking_data.pop(user_id, None)
        bot.send_message(message.chat.id, "❌ Запись отменена.", reply_markup=main_keyboard())
        return
    if not validate_name(message.text):
        msg = bot.send_message(message.chat.id, "❌ Имя должно содержать от 2 до 50 символов.\nПожалуйста, введите корректное имя:", reply_markup=cancel_keyboard())
        bot.register_next_step_handler(msg, process_name)
        return
    user_booking_data[user_id]['name'] = message.text.strip()
    msg = bot.send_message(message.chat.id, "📱 *Введите номер телефона:*\n\nВ формате: +7 (999) 123-45-67\nИли нажмите кнопку ниже", reply_markup=phone_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_phone)

def process_phone(message):
    user_id = message.from_user.id
    if message.text == "🔙 Отмена":
        user_booking_data.pop(user_id, None)
        bot.send_message(message.chat.id, "❌ Запись отменена.", reply_markup=main_keyboard())
        return
    phone = message.contact.phone_number if message.contact else message.text.strip()
    is_valid, formatted_phone = validate_phone(phone)
    if not is_valid:
        msg = bot.send_message(message.chat.id, "❌ Некорректный номер телефона.\nПожалуйста, введите в формате: +7 (999) 123-45-67\nИли нажмите кнопку «📱 Отправить номер телефона»", reply_markup=phone_keyboard())
        bot.register_next_step_handler(msg, process_phone)
        return
    user_booking_data[user_id]['phone'] = formatted_phone
    confirm_booking(message)

def confirm_booking(message):
    user_id = message.from_user.id
    booking = user_booking_data.get(user_id)
    if not booking:
        bot.send_message(message.chat.id, "❌ Ошибка. Начните запись заново.", reply_markup=main_keyboard())
        return
    date_str = booking['date']
    time_str = booking['time']
    name = booking['name']
    phone = booking['phone']
    service = booking.get('service', '')
    duration = booking.get('duration', 60)
    username = message.from_user.username or message.from_user.first_name
    try:
        add_appointment(date_str, time_str, user_id, username, name, phone, service, duration)
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка при создании записи.", reply_markup=main_keyboard())
        print(f"Ошибка записи: {e}")
        return
    user_booking_data.pop(user_id, None)
    date_obj = datetime.strptime(date_str, "%d.%m.%Y")
    phone_display = format_phone_display(phone)
    dur_str = format_duration(duration)
    time_parts = time_str.split(":")
    start_min = int(time_parts[0]) * 60 + int(time_parts[1])
    end_time = f"{((start_min + duration) // 60):02d}:{((start_min + duration) % 60):02d}"
    bot.send_message(message.chat.id, f"✅ *Запись подтверждена!*\n\n👤 Имя: *{name}*\n📱 Телефон: *{phone_display}*\n💅 Услуга: *{service}*\n⏱ Длительность: *{dur_str}*\n📅 Дата: *{date_str}* ({get_day_ru(date_obj)})\n🕐 Время: *{time_str} - {end_time}*\n\n🔔 Напоминания:\n• За 1 день до записи\n• За 1 час до записи\n\n📍 *ул. Примерная, д. 123*", reply_markup=main_keyboard(), parse_mode="Markdown")
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, f"📋 *Новая запись!*\n\n👤 Имя: *{name}*\n📱 Телефон: *{phone_display}*\n💅 Услуга: *{service}* ({dur_str})\n💬 Telegram: @{username}\n📅 Дата: *{date_str}* ({get_day_ru(date_obj)})\n🕐 Время: *{time_str} - {end_time}*", parse_mode="Markdown")
        except:
            pass

# ==================== ОБЩИЕ ОБРАБОТЧИКИ КАЛЕНДАРЯ ====================

@bot.callback_query_handler(func=lambda call: call.data == "cal_back")
def calendar_back(call):
    today = datetime.now()
    bot.edit_message_text(f"📅 *Выберите дату:*\n\n🔴 — нет свободных слотов\n📍 — сегодняшняя дата", call.message.chat.id, call.message.message_id, reply_markup=create_calendar(today.year, today.month), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "cal_main_menu")
def calendar_main_menu(call):
    user_booking_data.pop(call.from_user.id, None)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    bot.send_message(call.message.chat.id, "Выберите действие:", reply_markup=main_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "cal_ignore")
def calendar_ignore(call):
    bot.answer_callback_query(call.id)

# ==================== ОБРАБОТЧИКИ ОТМЕНЫ ЗАПИСИ ====================

@bot.callback_query_handler(func=lambda call: call.data == "cancel_confirm")
def cancel_confirm(call):
    date_str, time_str, data = cancel_appointment(call.from_user.id)
    if date_str:
        bot.edit_message_text(f"✅ *Запись отменена*\n\n👤 {data.get('client_name', 'Не указано')}\n📅 {date_str} в {time_str} — освободилось.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        bot.send_message(call.message.chat.id, "Выберите действие:", reply_markup=main_keyboard())
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(admin_id, f"❌ *Запись отменена клиентом!*\n\n👤 Имя: *{data.get('client_name', 'Не указано')}*\n📅 Дата: *{date_str}*\n🕐 Время: *{time_str}*", parse_mode="Markdown")
            except:
                pass
    else:
        bot.edit_message_text("❌ Не удалось отменить запись.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_decline")
def cancel_decline(call):
    bot.edit_message_text("✅ Запись сохранена.", call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, "Выберите действие:", reply_markup=main_keyboard())

# ==================== АДМИН-ПАНЕЛЬ ====================

def show_admin_panel(chat_id, year=None, month=None):
    if year is None:
        today = datetime.now()
        year, month = today.year, today.month
    appointments = get_all_appointments()
    total = len(appointments)
    users = len(get_all_users())
    bot.send_message(chat_id, f"📊 *АДМИН-ПАНЕЛЬ*\n\n📅 Выберите дату\n📈 Активных записей: *{total}*\n👥 Пользователей: *{users}*\n\n🔵 — есть записи\n⚪ — нет записей", reply_markup=create_admin_calendar(year, month, appointments), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_nav_"))
def admin_calendar_navigation(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "🚫 Доступ запрещён"); return
    _, _, year, month = call.data.split("_")
    year, month = int(year), int(month)
    appointments = get_all_appointments()
    total = len(appointments)
    users = len(get_all_users())
    bot.edit_message_text(f"📊 *АДМИН-ПАНЕЛЬ*\n\n📅 Выберите дату\n📈 Активных записей: *{total}*\n👥 Пользователей: *{users}*\n\n🔵 — есть записи\n⚪ — нет записей", call.message.chat.id, call.message.message_id, reply_markup=create_admin_calendar(year, month, appointments), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_day_"))
def admin_day_selected(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "🚫 Доступ запрещён"); return
    date_str = call.data.replace("admin_day_", "")
    appointments = get_all_appointments()
    day_appointments = [a for a in appointments if a['date'] == date_str]
    date_obj = datetime.strptime(date_str, "%d.%m.%Y")
    if not day_appointments:
        text = f"📅 *{date_str}* ({get_day_ru(date_obj)})\n\n❌ Записей нет."
    else:
        text = f"📅 *{date_str}* ({get_day_ru(date_obj)})\n\n*Записи:*\n\n"
        for i, app in enumerate(day_appointments, 1):
            phone = format_phone_display(app['client_phone']) if app['client_phone'] != 'Не указано' else 'Не указано'
            dur = format_duration(app.get('duration', 60))
            service = app.get('service_name', '')
            time_parts = app['time'].split(":")
            start_min = int(time_parts[0]) * 60 + int(time_parts[1])
            end_time = f"{((start_min + app.get('duration', 60)) // 60):02d}:{((start_min + app.get('duration', 60)) % 60):02d}"
            text += f"*{i}.* 🕐 *{app['time']} - {end_time}*\n   👤 {app['client_name']}\n   📱 {phone}\n"
            if service:
                text += f"   💅 {service} ({dur})\n"
            text += f"   💬 @{app['username']}\n   ID: `{app['user_id']}`\n\n"
    markup = InlineKeyboardMarkup()
    if day_appointments:
        for app in day_appointments:
            markup.add(InlineKeyboardButton(f"❌ Отменить: {app['time']} - {app['client_name']}", callback_data=f"admin_cancel_{app['date']}_{app['time']}"))
    markup.add(InlineKeyboardButton("🔙 К календарю", callback_data="admin_back_to_calendar"), InlineKeyboardButton("📋 Все записи", callback_data="admin_all_list"))
    markup.add(InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"), InlineKeyboardButton("🚪 Закрыть", callback_data="admin_close"))
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    except:
        bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_cancel_"))
def admin_cancel_appointment(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "🚫 Доступ запрещён"); return
    parts = call.data.split("_", 2)
    date_time = parts[2].rsplit("_", 1)
    if len(date_time) != 2:
        bot.answer_callback_query(call.id, "❌ Ошибка данных"); return
    date_str, time_str = date_time[0], date_time[1]
    data = cancel_appointment_admin(date_str, time_str)
    if data:
        try:
            bot.send_message(data['user_id'], f"❌ *Запись отменена администратором*\n\n📅 {date_str} в {time_str}", parse_mode="Markdown")
        except:
            pass
        bot.answer_callback_query(call.id, f"✅ Запись отменена")
        admin_day_selected(call)
    else:
        bot.answer_callback_query(call.id, "❌ Запись не существует")

@bot.callback_query_handler(func=lambda call: call.data == "admin_back_to_calendar")
def admin_back_to_calendar(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "🚫 Доступ запрещён"); return
    today = datetime.now()
    appointments = get_all_appointments()
    total = len(appointments)
    users = len(get_all_users())
    bot.edit_message_text(f"📊 *АДМИН-ПАНЕЛЬ*\n\n📅 Выберите дату\n📈 Активных записей: *{total}*\n👥 Пользователей: *{users}*\n\n🔵 — есть записи\n⚪ — нет записей", call.message.chat.id, call.message.message_id, reply_markup=create_admin_calendar(today.year, today.month, appointments), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_refresh_"))
def admin_refresh(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "🚫 Доступ запрещён"); return
    _, _, year, month = call.data.split("_")
    year, month = int(year), int(month)
    appointments = get_all_appointments()
    total = len(appointments)
    users = len(get_all_users())
    bot.edit_message_text(f"📊 *АДМИН-ПАНЕЛЬ*\n\n📅 Выберите дату\n📈 Активных записей: *{total}*\n👥 Пользователей: *{users}*\n\n🔵 — есть записи\n⚪ — нет записей", call.message.chat.id, call.message.message_id, reply_markup=create_admin_calendar(year, month, appointments), parse_mode="Markdown")
    bot.answer_callback_query(call.id, "✅ Обновлено")

@bot.callback_query_handler(func=lambda call: call.data == "admin_all_list")
def admin_all_list(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "🚫 Доступ запрещён"); return
    appointments = get_all_appointments()
    if not appointments:
        text = "📋 Нет активных записей."
    else:
        text = "📊 *ВСЕ ЗАПИСИ*\n\n"
        for i, app in enumerate(appointments, 1):
            try:
                d_obj = datetime.strptime(app['date'], "%d.%m.%Y")
                text += f"{i}. 📅 *{app['date']}* ({get_day_ru(d_obj)})\n"
            except:
                text += f"{i}. 📅 *{app['date']}*\n"
            phone = format_phone_display(app['client_phone']) if app['client_phone'] != 'Не указано' else 'Не указано'
            text += f"   🕐 {app['time']} | 👤 {app['client_name']}\n   📱 {phone} | 💬 @{app['username']}\n\n"
        text += f"📈 *Всего:* {len(appointments)}"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 К календарю", callback_data="admin_back_to_calendar"), InlineKeyboardButton("🚪 Закрыть", callback_data="admin_close"))
    if len(text) > 4000:
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        for part in [text[i:i+4000] for i in range(0, len(text), 4000)]:
            bot.send_message(call.message.chat.id, part, parse_mode="Markdown")
        bot.send_message(call.message.chat.id, "Действия:", reply_markup=markup)
    else:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

# ==================== РАССЫЛКА ====================

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
def admin_broadcast_button(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "🚫 Доступ запрещён"); return
    msg = bot.send_message(call.message.chat.id, "📢 *Введите текст рассылки:*\n\nДля отмены нажмите кнопку.", reply_markup=cancel_keyboard(), parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_broadcast_text)

def process_broadcast_text(message):
    if message.from_user.id not in ADMIN_IDS: return
    if message.text == "🔙 Отмена":
        bot.send_message(message.chat.id, "❌ Рассылка отменена.", reply_markup=main_keyboard()); return
    text = message.text.strip()
    if not text:
        msg = bot.send_message(message.chat.id, "❌ Текст не может быть пустым:", reply_markup=cancel_keyboard())
        bot.register_next_step_handler(msg, process_broadcast_text); return
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ Отправить", callback_data="broadcast_confirm_text"), InlineKeyboardButton("❌ Отмена", callback_data="broadcast_cancel"))
    user_booking_data[f"broadcast_text_{message.from_user.id}"] = text
    users = get_all_users()
    bot.send_message(message.chat.id, f"📢 *Подтвердите*\n\n📝 Текст:\n«{text[:200]}{'...' if len(text) > 200 else ''}»\n\n👥 Получателей: *{len(users)}*\n\nОтправить?", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("broadcast_confirm"))
def broadcast_confirm(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "🚫 Доступ запрещён"); return
    text = user_booking_data.pop(f"broadcast_text_{call.from_user.id}", None) or user_booking_data.pop(f"broadcast_{call.from_user.id}", None)
    if not text:
        bot.answer_callback_query(call.id, "❌ Текст не найден"); return
    users = get_all_users()
    total = len(users)
    success = 0
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    for user in users:
        try:
            bot.send_message(user['user_id'], f"📢 *Рассылка*\n\n{text}", parse_mode="Markdown")
            success += 1
        except:
            pass
        time.sleep(0.05)
    bot.send_message(call.message.chat.id, f"✅ *Рассылка завершена!*\n\n📊 Отправлено: *{success}*\n❌ Ошибок: *{total - success}*\n👥 Всего: *{total}*", reply_markup=main_keyboard(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "broadcast_cancel")
def broadcast_cancel(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "🚫 Доступ запрещён"); return
    user_booking_data.pop(f"broadcast_{call.from_user.id}", None)
    user_booking_data.pop(f"broadcast_text_{call.from_user.id}", None)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    bot.send_message(call.message.chat.id, "❌ Рассылка отменена.", reply_markup=main_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "admin_close")
def admin_close(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "🚫 Доступ запрещён"); return
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    bot.send_message(call.message.chat.id, "✅ Админ-панель закрыта.", reply_markup=main_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "admin_ignore")
def admin_ignore(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "🚫 Доступ запрещён"); return
    bot.answer_callback_query(call.id)

# ==================== ОБРАБОТЧИК КОНТАКТОВ ====================

@bot.message_handler(content_types=['contact'])
def contact_received(message):
    pass

# ==================== АВТОУДАЛЕНИЕ СТАРЫХ ЗАПИСЕЙ ====================

def cleanup_old_appointments():
    now = datetime.now()
    appointments = load_appointments()
    modified = False
    for date_str in list(appointments.keys()):
        for time_str in list(appointments[date_str].keys()):
            try:
                app_datetime = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
                data = appointments[date_str][time_str]
                duration = data.get('duration', 60)
                # Удаляем через 20 минут после ОКОНЧАНИЯ услуги
                if now > app_datetime + timedelta(minutes=duration + 20):
                    print(f"🗑 Автоудаление: {date_str} {time_str} - {data.get('client_name', '?')}")
                    del appointments[date_str][time_str]
                    if not appointments[date_str]:
                        del appointments[date_str]
                    modified = True
            except:
                continue
    if modified:
        save_appointments(appointments)

# ==================== СИСТЕМА НАПОМИНАНИЙ ====================

def check_reminders():
    now = datetime.now()
    appointments = load_appointments()
    modified = False
    for date_str in list(appointments.keys()):
        for time_str in list(appointments[date_str].keys()):
            data = appointments[date_str][time_str]
            try:
                app_datetime = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
            except:
                continue
            time_diff = app_datetime - now
            client_name = data.get('client_name', 'Клиент')
            if REMINDER_DAY_BEFORE and not data.get('reminded_day'):
                if timedelta(hours=23, minutes=55) <= time_diff <= timedelta(hours=24, minutes=5):
                    for uid in [data['user_id']] + ADMIN_IDS:
                        try:
                            bot.send_message(uid, f"🔔 *Напоминание!*\n\n👤 {client_name}, у вас запись на *завтра*:\n📅 *{date_str}*\n🕐 *{time_str}*\n\n📍 ул. Примерная, д. 123", parse_mode="Markdown")
                        except:
                            pass
                    data['reminded_day'] = True
                    modified = True
            if REMINDER_HOUR_BEFORE and not data.get('reminded_hour'):
                if timedelta(minutes=55) <= time_diff <= timedelta(minutes=65):
                    for uid in [data['user_id']] + ADMIN_IDS:
                        try:
                            bot.send_message(uid, f"⏰ *Напоминание!*\n\n👤 {client_name}, до записи остался *1 час*:\n📅 *{date_str}*\n🕐 *{time_str}*\n\n📍 ул. Примерная, д. 123", parse_mode="Markdown")
                        except:
                            pass
                    data['reminded_hour'] = True
                    modified = True
    if modified:
        save_appointments(appointments)

def run_scheduler():
    schedule.every(1).minutes.do(check_reminders)
    schedule.every(5).minutes.do(cleanup_old_appointments)
    print("🔔 Система запущена")
    while True:
        schedule.run_pending()
        time.sleep(30)

# ==================== ЗАПУСК БОТА ====================

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 БОТ ЗАПУСКАЕТСЯ...")
    print(f"🕐 Часы работы: {WORK_START_HOUR}:00 - {WORK_END_HOUR}:00")
    print(f"👑 Админы: {ADMIN_IDS}")
    print("=" * 50)
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        for fp in [APPOINTMENTS_FILE, USERS_FILE]:
            if not os.path.exists(fp):
                with open(fp, 'w', encoding='utf-8') as f:
                    json.dump({}, f)
        print("✅ Файлы готовы")
    except:
        pass
    try:
        appointments = load_appointments()
        today = datetime.now().strftime("%d.%m.%Y")
        for ds in list(appointments.keys()):
            if ds < today:
                del appointments[ds]
        save_appointments(appointments)
    except:
        pass
    threading.Thread(target=run_scheduler, daemon=True).start()
    print("🚀 Запуск бота...")
    while True:
        try:
            bot.polling(none_stop=False, timeout=30, long_polling_timeout=10)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)