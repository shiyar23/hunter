# main.py
import os
import telebot
import logging
import random
import json
import time
from telebot import types
from googleapiclient.discovery import build
from google.oauth2 import service_account

# === Logging ===
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# === Environment Variables ===
BOT_TOKEN = os.getenv('BOT_TOKEN')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
GOOGLE_CREDENTIALS = os.getenv('GOOGLE_CREDENTIALS')

# === تحقق من المتغيرات ===
if not BOT_TOKEN:
    logger.error("BOT_TOKEN مطلوب!")
    exit(1)
if not SPREADSHEET_ID:
    logger.error("SPREADSHEET_ID مطلوب!")
    exit(1)
if not GOOGLE_CREDENTIALS:
    logger.error("GOOGLE_CREDENTIALS مطلوب كـ JSON!")
    exit(1)

logger.info("جميع المتغيرات تم تحميلها بنجاح!")

# === Bot ===
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='Markdown')

# === Google Sheets Service ===
def get_sheets_service():
    try:
        creds_info = json.loads(GOOGLE_CREDENTIALS)
        credentials = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        return build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        logger.error(f"خطأ في Google Sheets: {str(e)}")
        raise

# === Pip & Decimals ===
pip_sizes = {
    'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'USDJPY': 0.01,
    'AUDUSD': 0.0001, 'XAUUSD': 0.1, 'XAGUSD': 0.001,
}

price_decimals = {
    'EURUSD': 5, 'GBPUSD': 5, 'USDJPY': 3,
    'AUDUSD': 5, 'XAUUSD': 2, 'XAGUSD': 3,
}

# === User Data ===
user_data = {}

# === Keyboards ===
def main_menu_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD',
        'XAUUSD', 'XAGUSD',
        'بدء جديد', 'تعديل', 'رجوع',
        'حذف', 'إعادة تشغيل', 'تنظيف الدردشة', 'حساب النقاط'
    ]
    for i in range(0, len(buttons), 2):
        markup.add(buttons[i], buttons[i+1] if i+1 < len(buttons) else '')
    return markup

def buy_sell_keyboard():
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add('BUY', 'SELL')
    return markup

# === Send & Save Message ===
def send_and_save_message(chat_id, text, reply_markup=None, user_id=None):
    if reply_markup is None:
        reply_markup = types.ReplyKeyboardRemove()
    try:
        msg = bot.send_message(chat_id, text, reply_markup=reply_markup)
        if user_id and user_id in user_data:
            user_data[user_id].setdefault('bot_messages', []).append(msg.message_id)
        return msg
    except Exception as e:
        logger.error(f"فشل إرسال الرسالة: {e}")
        return None

# === Handlers ===
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_data[user_id] = {'bot_messages': []}
    text = ("*مرحباً بك في ORORA Trading Setup Generator*\n\n"
            "بوت احترافي لتوليد إعدادات تداول دقيقة ومخصصة للعملات والذهب.\n\n"
            "*ابدأ الآن*: اضغط على زر رمز للاختيار.")
    send_and_save_message(chat_id, text, main_menu_keyboard(), user_id)

@bot.message_handler(func=lambda m: m.text in ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'XAUUSD', 'XAGUSD'])
def handle_symbol(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_data.setdefault(user_id, {'bot_messages': []})
    user_data[user_id]['commodity'] = message.text.upper()
    send_and_save_message(chat_id, f"*تم اختيار {message.text}*\n\nاختر نوع الصفقة:", buy_sell_keyboard(), user_id)
    bot.register_next_step_handler(message, process_trade_type)

def process_trade_type(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    trade_type = message.text.upper()
    if trade_type not in ['BUY', 'SELL']:
        send_and_save_message(chat_id, "*يرجى اختيار BUY أو SELL فقط.*", buy_sell_keyboard(), user_id)
        bot.register_next_step_handler(message, process_trade_type)
        return
    user_data[user_id]['trade_type'] = trade_type
    send_and_save_message(chat_id, f"*تم اختيار {trade_type}*\n\nأدخل سعر الدخول (✅Entry Price):", types.ReplyKeyboardRemove(), user_id)
    bot.register_next_step_handler(message, process_entry_price)

def process_entry_price(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        user_data[user_id]['entry_price'] = float(message.text)
        send_and_save_message(chat_id, "أدخل سعر وقف الخسارة (❌Stop Loss):", types.ReplyKeyboardRemove(), user_id)
        bot.register_next_step_handler(message, process_stop_loss)
    except ValueError:
        send_and_save_message(chat_id, "*سعر دخول غير صحيح. أعد الإدخال:*", types.ReplyKeyboardRemove(), user_id)
        bot.register_next_step_handler(message, process_entry_price)

def process_stop_loss(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        user_data[user_id]['stop_loss'] = float(message.text)
        generate_and_send_setup(user_id, chat_id)
    except ValueError:
        send_and_save_message(chat_id, "*سعر وقف الخسارة غير صحيح. أعد الإدخال:*", types.ReplyKeyboardRemove(), user_id)
        bot.register_next_step_handler(message, process_stop_loss)

def generate_and_send_setup(user_id, chat_id):
    data = user_data[user_id]
    commodity = data['commodity']
    entry_price = data['entry_price']
    stop_loss = data['stop_loss']
    trade_type = data.get('trade_type', 'BUY')
    direction = 1 if trade_type == 'BUY' else -1
    pip_size = pip_sizes.get(commodity, 0.0001)
    decimals = price_decimals.get(commodity, 5)

    if commodity == 'XAUUSD':
        gaps_list = [50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 200, 220, 250]
        selected_gaps = random.sample(gaps_list, 5)
        selected_gaps.sort()
        tp_units = []
        cumulative_pips = 0
        for gap in selected_gaps:
            cumulative_pips += gap
            tp_units.append(cumulative_pips)
        swing_unit = random.randint(550, 750)
    else:
        base_units = [50, 100, 160, 220, 280]
        tp_units = sorted([int(u + random.uniform(-5, 5)) for u in base_units])
        swing_unit = random.randint(550, 750)

    output = f"*Setup {commodity} {trade_type}*\n"
    output += f"Entry: `{entry_price:.{decimals}f}`\n"
    output += f"Stop Loss: `{stop_loss:.{decimals}f}` (High Risk)\n\n"

    tp_prices = []
    for i, unit in enumerate(tp_units, 1):
        tp_price = entry_price + (unit * pip_size * direction)
        tp_prices.append(tp_price)
        output += f"TP{i}: `{tp_price:.{decimals}f}` — pips: `{unit}`\n"

    swing_tp_price = entry_price + (swing_unit * pip_size * direction)
    output += f"Swing TP: `{swing_tp_price:.{decimals}f}` — pips: `{swing_unit}`\n\n"
    output += "⚠️ إخلاء مسؤولية: هذا ليس نصيحة مالية. استخدم دائمًا إدارة مخاطر مناسبة واتخذ قراراتك بناءً على استراتيجيتك الخاصة.."

    send_and_save_message(chat_id, output, main_menu_keyboard(), user_id)

    # === Save to Google Sheets ===
    try:
        sheets_service = get_sheets_service()
        values = [[
            commodity, trade_type, entry_price, stop_loss,
            tp_prices[0] if len(tp_prices) > 0 else '',
            tp_prices[1] if len(tp_prices) > 1 else '',
            tp_prices[2] if len(tp_prices) > 2 else '',
            tp_prices[3] if len(tp_prices) > 3 else '',
            swing_tp_price
        ]]
        body = {'values': values}
        sheets_service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range='Sheet1!A:I',
            valueInputOption='RAW',
            body=body
        ).execute()
        send_and_save_message(chat_id, f"*تم حفظ الإعداد في Google Sheets!*\n[رابط الجدول](https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit)", user_id=user_id)
    except Exception as e:
        logger.error(f"خطأ Google Sheets: {str(e)}")
        send_and_save_message(chat_id, f"*خطأ في حفظ البيانات:* `{str(e)}`", main_menu_keyboard(), user_id)

# === باقي الأوامر ===
@bot.message_handler(func=lambda m: m.text == 'بدء جديد')
def new_setup(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_data[user_id] = {'bot_messages': []}
    send_and_save_message(chat_id, "*إعداد جديد جاهز!*\nاختر الرمز:", main_menu_keyboard(), user_id)

@bot.message_handler(func=lambda m: m.text == 'حذف')
def delete_setup(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_data.pop(user_id, None)
    send_and_save_message(chat_id, "*تم حذف البيانات. ابدأ جديدًا!*", main_menu_keyboard(), user_id)

@bot.message_handler(func=lambda m: m.text == 'تنظيف الدردشة')
def clean_chat(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if user_id in user_data and 'bot_messages' in user_data[user_id]:
        for msg_id in user_data[user_id]['bot_messages']:
            try: bot.delete_message(chat_id, msg_id)
            except: pass
        user_data[user_id]['bot_messages'] = []
    try: bot.delete_message(chat_id, message.message_id)
    except: pass
    send_and_save_message(chat_id, "*تم تنظيف الدردشة!*\nمرحباً!", main_menu_keyboard(), user_id)

# === تشغيل البوت بـ Polling (بدون Flask أو Webhook) ===
if __name__ == "__main__":
    logger.info("البوت يعمل الآن باستخدام Polling...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            logger.error(f"خطأ في Polling: {e}")
            time.sleep(5)
