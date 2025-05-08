import sqlite3
import asyncio
import random
import re
import string
import pytz
from datetime import datetime
from urllib.parse import unquote
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
    ContextTypes,
    CallbackContext
)
from telegram.error import NetworkError, TelegramError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta


# إعداد سجل الأخطاء
import logging

logging.basicConfig(
    filename='errors.log',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.ERROR
)

logger = logging.getLogger(__name__)

# متغير عالمي لتخزين الطلبات إن لزم
user_orders = {}




# ✅ إنشاء جداول المحافظات والمدن أولًا
def setup_database():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # جدول بيانات المستخدمين
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_data (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            phone TEXT,
            province TEXT,
            city TEXT,
            location_image TEXT,
            location_text TEXT,
            latitude REAL,
            longitude REAL
        )
    """)

    # جدول عداد الطلبات للمطاعم
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS restaurant_order_counter (
            restaurant TEXT PRIMARY KEY,
            last_order_number INTEGER
        )
    """)

    # جدول الطلبات
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_orders (
            order_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            restaurant TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # جدول تقييمات المطاعم
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS restaurant_ratings (
            restaurant TEXT PRIMARY KEY,
            total_ratings INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0
        )
    """)

    # ✅ جدول المطاعم (مطابق لبوت الإدارة)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            city_id INTEGER NOT NULL,
            channel TEXT NOT NULL,
            open_hour REAL NOT NULL,
            close_hour REAL NOT NULL,
            is_frozen INTEGER DEFAULT 0,
            FOREIGN KEY (city_id) REFERENCES cities(id)
        )
    """)

    # ✅ جدول الإعلانات
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS advertisements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            region_type TEXT NOT NULL,
            region_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    return conn


def setup_menu_tables():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # جدول الفئات والمطاعم كما في السابق...

    # جدول الوجبات
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER,
            category_id INTEGER NOT NULL,
            caption TEXT,
            image_file_id TEXT,
            size_options TEXT,
            unique_id TEXT UNIQUE,
            image_message_id INTEGER,
            UNIQUE(name, category_id),
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )
    """)

    # ✅ تحقق من وجود الأعمدة
    cursor.execute("PRAGMA table_info(meals)")
    meal_columns = [col[1] for col in cursor.fetchall()]
    if "caption" not in meal_columns:
        cursor.execute("ALTER TABLE meals ADD COLUMN caption TEXT")
    if "image_file_id" not in meal_columns:
        cursor.execute("ALTER TABLE meals ADD COLUMN image_file_id TEXT")
    if "size_options" not in meal_columns:
        cursor.execute("ALTER TABLE meals ADD COLUMN size_options TEXT")
    if "unique_id" not in meal_columns:
        cursor.execute("ALTER TABLE meals ADD COLUMN unique_id TEXT UNIQUE")
    if "image_message_id" not in meal_columns:
        cursor.execute("ALTER TABLE meals ADD COLUMN image_message_id INTEGER")

    conn.commit()
    conn.close()

db_conn = setup_database()
setup_menu_tables()



ASK_INFO, ASK_NAME, ASK_PHONE, ASK_PHONE_VERIFICATION, ASK_PROVINCE, ASK_CITY, ASK_LOCATION_IMAGE, ASK_LOCATION_TEXT, CONFIRM_INFO, MAIN_MENU, ORDER_CATEGORY, ORDER_MEAL, CONFIRM_ORDER, SELECT_RESTAURANT, ASK_ORDER_LOCATION, CONFIRM_FINAL_ORDER, ASK_NEW_LOCATION_IMAGE, ASK_NEW_LOCATION_TEXT, CANCEL_ORDER_OPTIONS, ASK_CUSTOM_CITY, ASK_NEW_RESTAURANT_NAME, ASK_ORDER_NOTES, ASK_RATING, ASK_RATING_COMMENT, ASK_REPORT_REASON   = range(25)



ADMIN_MEDIA_CHANNEL = -1002659459294  
AD_MEDIA_CHANNEL = -1002315567913  # معرف القناة الوسيطة الإعلانية (بالسالب)
ERRORS_CHANNEL = -1001234567890  # استبدله بمعرف قناتك



# دالة حساب السعر الإجمالي
def calculate_total_price(orders, prices):
    total = 0
    for item, count in orders.items():
        found = False
        for category, items in prices.items():
            if item in items:
                total += count * items[item]
                found = True
                break
        if not found:
            logging.warning(f"العنصر '{item}' غير موجود في قائمة أسعار المطعم.")
    return total

def get_fast_order_cooldown(cancel_times: list) -> tuple[int, str]:
    now = datetime.now()
    count_17 = sum((now - t).total_seconds() <= 1020 for t in cancel_times)
    count_22 = sum((now - t).total_seconds() <= 1320 for t in cancel_times)
    count_40 = sum((now - t).total_seconds() <= 2400 for t in cancel_times)

    if count_40 >= 5:
        return 2 * 24 * 60 * 60, (
            "🚫 تم حظرك من استخدام (اطلب عالسريع) لمدة يومين.\n"
            "استخدامك المتكرر للإلغاء يُعتبر سلوكًا عبثيًا بالخدمة.\n"
            "للاستفسار: @Support"
        )
    elif count_22 >= 4:
        return 10 * 60, (
            "⚠️ تم حظرك من (اطلب عالسريع) لمدة 10 دقائق بسبب تكرار الإلغاء.\n"
            "نرجو الالتزام بالاستخدام المنطقي للخدمة."
        )
    elif count_17 >= 3:
        return 5 * 60, (
            "⚠️ تم إيقاف زر (اطلب عالسريع) مؤقتًا لمدة 5 دقائق بسبب الإلغاء المتكرر.\n"
            "إذا تكرر ذلك سيتم حظرك مؤقتًا."
        )

    return 0, ""




def generate_order_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=15))  # 15 حرف ورقم عشوائي

# عند تأكيد الطلب، قم بإنشاء معرف الطلب مرة واحدة فقط
order_id = generate_order_id()

def get_main_menu():
    return ReplyKeyboardMarkup([
        ["اطلب عالسريع 🔥"],
        ["تعديل معلوماتي 🖊", "التواصل مع الدعم 🎧"],
        ["من نحن 🏢", "أسئلة متكررة ❓"]
    ], resize_keyboard=True)

# الوظائف
from urllib.parse import unquote

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    user_id = update.effective_user.id

    # ✅ حماية من إجراء جارٍ (تذكير/إلغاء)
    if context.user_data.get("pending_action") in ["awaiting_reminder_confirm", "awaiting_cancel_confirm"]:
        await update.message.reply_text("🚫 لديك إجراء جارٍ قيد التنفيذ. أتمه أو ألغِه قبل فتح عروض جديدة.")
        return ConversationHandler.END

    # ✅ حماية من الضغط المتكرر
    if context.user_data.get("ad_click_lock"):
        return ConversationHandler.END
    context.user_data["ad_click_lock"] = True
    await asyncio.sleep(1)
    context.user_data["ad_click_lock"] = False

    # ✅ إذا دخل من إعلان عادي
    if args and args[0].startswith("go_"):
        await update.message.reply_text(
            "📢 *يالله عالسرييع 🔥*\n\n"
            "وصلت من إعلان، لتكمل:\n"
            "➤ اضغط على زر *اطلب عالسريع 🔥* في الأسفل\n"
            "➤ ثم اختر المطعم اللي شفته\n\n"
            "👇 وبلّش شوف العروض 👇",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # ✅ إذا دخل من إعلان VIP
    if args and args[0].startswith("vip_"):
        return await handle_vip_start(update, context)

    # ✅ الدخول العادي (بدون إعلان)
    reply_markup = ReplyKeyboardMarkup([
        ["تفاصيل عن الأسئلة وما الغاية منها"],
        ["املأ بياناتي"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        "أهلا وسهلا 🌹\n"
        "بدنا نسألك كم سؤال لتسجيل معلوماتك لأول مرة 😄\n"
        "غايتنا نخدمك بأفضل طريقة 👌",
        reply_markup=reply_markup
    )
    return ASK_INFO




async def ask_info_details(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        "عزيزي/عزيزتي\n\n"
        "نشكرك على تواصلك معنا. نود أن نؤكد لك أن المعلومات التي نطلبها هي لغاية تقديم خدمة أفضل لك. "
        "جميع البيانات التي نجمعها محفوطة بشكل آمن ولن يتم مشاركتها مع أي جهة أخرى، باستثناء مصدر الخدمة المحدد كالمطعم أو خدمة التوصيل.\n\n"
        "إذا كان هناك أي تغيير في المعلومات أو إذا رغبت في تعديلها، يمكنك ببساطة الضغط على خيار 'تعديل معلوماتي' وسنقوم بحذف المعلومات السابقة لبدء عملية جديدة.\n\n"
        "نحن هنا لخدمتك، وشكرًا لتفهمك!\n\n"
        "مع أطيب التحيات."
    )
    return ASK_INFO

async def ask_name(update: Update, context: CallbackContext) -> int:
    reply_markup = ReplyKeyboardMarkup([
        ["عودة ⬅️"]
    ], resize_keyboard=True)
    await update.message.reply_text("ما اسمك الكامل؟", reply_markup=reply_markup)
    return ASK_NAME

async def handle_back_to_info(update: Update, context: CallbackContext) -> int:
    """
    معالجة خيار العودة من مرحلة الاسم إلى المرحلة الأولى.
    """
    reply_markup = ReplyKeyboardMarkup([
        ["تفاصيل عن الأسئلة وما الغاية منها"],
        ["املأ بياناتي"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        "تم الرجوع إلى البداية. يمكنك الآن اختيار أحد الخيارات التالية:",
        reply_markup=reply_markup
    )
    return ASK_INFO


async def ask_phone(update: Update, context: CallbackContext) -> int:
    # العودة للخطوة السابقة إذا اختار المستخدم "عودة"
    if update.message.text == "عودة ⬅️":
        return await start(update, context)

    # حفظ اسم المستخدم
    context.user_data['name'] = update.message.text

    # طلب رقم الهاتف
    reply_markup = ReplyKeyboardMarkup([
        ["عودة ⬅️"]
    ], resize_keyboard=True)
    await update.message.reply_text("رقم الهاتف (سيتم إرسال كود على الرقم الذي تضيفه):", reply_markup=reply_markup)
    return ASK_PHONE


async def send_verification_code(update: Update, context: CallbackContext) -> int:
    # العودة للخطوة السابقة إذا اختار المستخدم "عودة"
    if update.message.text == "عودة ⬅️":
        context.user_data.pop('phone', None)
        return await ask_phone(update, context)

    # حفظ رقم الهاتف
    phone = update.message.text

    # التحقق من الشروط: أن يكون الرقم مكونًا من 10 أرقام ويبدأ بـ 09
    if not (phone.isdigit() and len(phone) == 10 and phone.startswith("09")):
        await update.message.reply_text(
            "❌ يرجى إدخال رقم هاتف صحيح يتكون من 10 أرقام ويبدأ بـ 09."
        )
        return ASK_PHONE

    # التحقق من أن الرقم غير محظور
    cursor = db_conn.cursor()
    cursor.execute("SELECT phone FROM blacklisted_numbers WHERE phone = ?", (phone,))
    if cursor.fetchone():
        await update.message.reply_text(
            "❌ عذراً، رقمك محظور من قبل إدارة البوت بسبب سلوك سابق.\n"
            "يرجى التواصل مع الدعم للمزيد من التفاصيل:\n"
            "📞 0912345678 - 0998765432"
        )
        return ASK_PHONE  # إعادة المستخدم لإدخال رقم جديد

    # إنشاء كود التحقق
    verification_code = random.randint(10000, 99999)  # إنشاء كود عشوائي من 5 أرقام
    context.user_data['phone'] = phone
    context.user_data['verification_code'] = verification_code

    # إرسال الكود والبيانات إلى قناة التحقق الخاصة
    try:
        name = context.user_data['name']
        verification_message = (
            f"عزيزي/عزيزتي {name} 😄\n"
            f"صاحب الرقم {phone} 🌝\n"
            f"إن كود التحقق حتى تطلب عالسريع هو {verification_code} 🤗\n"
            f"مستعدون لخدمتكم عالسريع 🔥"
        )

        # إرسال الرسالة إلى القناة المخصصة
        await context.bot.send_message(
            chat_id="@verifycode12345",  # معرف القناة التي سيتم إرسال الرسالة إليها
            text=verification_message
        )

        # طلب إدخال الكود من المستخدم
        reply_markup = ReplyKeyboardMarkup([
            ["عودة ⬅️"]
        ], resize_keyboard=True)
        await update.message.reply_text(
            "📩 تم إرسال كود التحقق الخاص بك. يرجى إدخاله هنا لتأكيد الرقم ✅.\n"
            "إذا لم يصلك الكود، يمكنك اختيار 'عودة' لتغيير الرقم.",
            reply_markup=reply_markup
        )
        return ASK_PHONE_VERIFICATION
    except Exception as e:
        # في حال حدوث خطأ في إرسال الرسالة
        await update.message.reply_text("❌ حدث خطأ أثناء إرسال الكود. يرجى المحاولة مرة أخرى.")
        context.user_data.pop('phone', None)
        return await ask_phone(update, context)




async def verify_code(update: Update, context: CallbackContext) -> int:
    if update.message.text == "عودة ⬅️":
        context.user_data.pop('phone', None)
        context.user_data.pop('verification_code', None)
        return await ask_phone(update, context)

    entered_code = update.message.text
    if entered_code == str(context.user_data['verification_code']):
        await update.message.reply_text("✅ تم التحقق من الرقم بنجاح.")

        # حفظ البيانات في قاعدة البيانات
        user_id = update.effective_user.id
        name = context.user_data['name']
        phone = context.user_data['phone']

        cursor = db_conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO user_data (user_id, name, phone) VALUES (?, ?, ?)",
                       (user_id, name, phone))
        db_conn.commit()

        # ✅ سحب المحافظات من قاعدة البيانات
        cursor.execute("SELECT name FROM provinces")
        provinces = [row[0] for row in cursor.fetchall()]
        provinces.append("عودة ➡️")

        # ✅ عرض المحافظات للمستخدم
        reply_markup = ReplyKeyboardMarkup(
            [[p for p in provinces[i:i+3]] for i in range(0, len(provinces), 3)],
            resize_keyboard=True
        )
        await update.message.reply_text("يرجى اختيار المحافظة:", reply_markup=reply_markup)
        return ASK_PROVINCE

    else:
        await update.message.reply_text(
            "❌ الكود الذي أدخلته غير صحيح. يرجى المحاولة مجددًا."
        )
        return ASK_PHONE_VERIFICATION




async def handle_province(update: Update, context: CallbackContext) -> int:
    province = update.message.text

    if province == "عودة ➡️":
        context.user_data.pop('phone', None)
        return await ask_phone(update, context)

    # حفظ اسم المحافظة
    context.user_data['province'] = province

    # سحب المدن المرتبطة بالمحافظة من قاعدة البيانات
    cursor = db_conn.cursor()
    cursor.execute("SELECT id FROM provinces WHERE name = ?", (province,))
    result = cursor.fetchone()

    if not result:
        await update.message.reply_text("⚠️ حدث خطأ أثناء جلب المدن. حاول مرة أخرى.")
        return ASK_PROVINCE

    province_id = result[0]

    # استخراج المدن المرتبطة
    cursor.execute("SELECT name FROM cities WHERE province_id = ?", (province_id,))
    cities = [row[0] for row in cursor.fetchall()]

    # إضافة خيارات إضافية
    cities += ["لم تذكر مدينتي ؟ 😕", "عودة ➡️"]

    reply_markup = ReplyKeyboardMarkup([[city] for city in cities], resize_keyboard=True)
    await update.message.reply_text("يرجى اختيار المدينة:", reply_markup=reply_markup)

    return ASK_CITY



async def handle_city(update: Update, context: CallbackContext) -> int:
    city = update.message.text

    if city == "عودة ➡️":
        context.user_data.pop('province', None)

        # جلب المحافظات من قاعدة البيانات
        cursor = db_conn.cursor()
        cursor.execute("SELECT name FROM provinces")
        provinces = [row[0] for row in cursor.fetchall()]

        reply_markup = ReplyKeyboardMarkup(
            [[p for p in provinces[i:i+3]] for i in range(0, len(provinces), 3)],
            resize_keyboard=True
        )
        await update.message.reply_text("🔙 تم الرجوع إلى السؤال السابق. يرجى اختيار المحافظة مجددًا:", reply_markup=reply_markup)
        return ASK_PROVINCE

    elif city == "لم تذكر مدينتي ؟ 😕":
        reply_markup = ReplyKeyboardMarkup([["عودة ➡️"]], resize_keyboard=True)
        await update.message.reply_text(
            "❓ نرجو منك كتابة اسم مدينتك.\n"
            "يسعدنا أن نخدمك في مدينتك قريبًا بإذن الله! 🙏",
            reply_markup=reply_markup
        )
        return ASK_CUSTOM_CITY

    context.user_data['city'] = city

    location_button = KeyboardButton("📍 إرسال موقعي", request_location=True)
    reply_markup = ReplyKeyboardMarkup([[location_button], ["عودة ➡️"]], resize_keyboard=True)

    await update.message.reply_text(
        "🔍 يرجى إرسال موقعك الجغرافي باستخدام الزر أدناه لتحديد مكان التوصيل.\n\n"
        "📌 تأكد من تفعيل خدمة GPS على جهازك لتحديد الموقع بدقة.",
        reply_markup=reply_markup
    )
    return ASK_LOCATION_IMAGE





async def handle_custom_city(update: Update, context: CallbackContext) -> int:
    city_name = update.message.text

    if city_name == "عودة ➡️":
        # ✅ العودة إلى اختيار المدينة (جلب المدن من قاعدة البيانات)
        province = context.user_data.get('province', '')
        cursor = db_conn.cursor()

        # جلب معرف المحافظة
        cursor.execute("SELECT id FROM provinces WHERE name = ?", (province,))
        result = cursor.fetchone()
        if not result:
            await update.message.reply_text("⚠️ لم يتم العثور على المحافظة. يرجى اختيارها مجددًا.")
            return ASK_PROVINCE

        province_id = result[0]

        # جلب المدن من قاعدة البيانات
        cursor.execute("SELECT name FROM cities WHERE province_id = ?", (province_id,))
        cities = [row[0] for row in cursor.fetchall()]

        # إضافة الخيارات الإضافية
        city_options = cities + ["لم تذكر مدينتي ؟ 😕", "عودة ➡️"]
        reply_markup = ReplyKeyboardMarkup(
            [[city] for city in city_options],
            resize_keyboard=True
        )
        await update.message.reply_text("🔙 اختر المدينة التي تريدها:", reply_markup=reply_markup)
        return ASK_CITY

    # ✅ إرسال المدينة المقترحة إلى قناة الدعم
    province = context.user_data.get('province', 'غير متوفر')
    custom_city_channel = "@Lamtozkar"  # ← غيّره إن أردت

    await context.bot.send_message(
        chat_id=custom_city_channel,
        text=f"📢 مدينة جديدة تم اقتراحها من أحد المستخدمين:\n\n"
             f"🌍 المحافظة: {province}\n"
             f"🏙️ المدينة: {city_name}\n"
             f"👤 المستخدم: @{update.effective_user.username or 'غير متوفر'}"
    )

    await update.message.reply_text(
        "✅ تم استلام مدينتك! نأمل أن نتمكن من خدمتك قريبًا 🙏.\n"
        "يرجى اختيار المدينة من القائمة:",
    )

    # ✅ إعادة المستخدم لاختيار المدينة من قاعدة البيانات
    cursor = db_conn.cursor()
    cursor.execute("SELECT id FROM provinces WHERE name = ?", (province,))
    result = cursor.fetchone()
    if not result:
        await update.message.reply_text("⚠️ لم يتم العثور على المحافظة. يرجى اختيارها مجددًا.")
        return ASK_PROVINCE

    province_id = result[0]
    cursor.execute("SELECT name FROM cities WHERE province_id = ?", (province_id,))
    cities = [row[0] for row in cursor.fetchall()]
    city_options = cities + ["لم تذكر مدينتي ؟ 😕", "عودة ➡️"]

    reply_markup = ReplyKeyboardMarkup([[city] for city in city_options], resize_keyboard=True)
    await update.message.reply_text("🔙 اختر المدينة التي تريدها:", reply_markup=reply_markup)
    return ASK_CITY



async def ask_location(update: Update, context: CallbackContext) -> int:
    """
    طلب الموقع الجغرافي من المستخدم باستخدام ميزة إرسال الموقع في Telegram.
    """
    reply_markup = ReplyKeyboardMarkup([
        ["إرسال موقعي 📍"],
        ["عودة ➡️"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        "🔍 يرجى إرسال موقعك الجغرافي باستخدام الزر أدناه لتحديد مكان التوصيل.\n\n"
        "📌 تفعيل خدمة GPS على جهازك يساعدنا في تحديد موقعك بدقة.\n"
        "🗺️ بعد إرسال الموقع، يمكننا التأكد من العنوان وتقديم خدمة أسرع.",
        reply_markup=reply_markup
    )
    return ASK_LOCATION_IMAGE



# الدالة التي تتعامل مع إرسال الموقع من الزبون
async def handle_location(update: Update, context: CallbackContext) -> int:
    if update.message.location:
        latitude = update.message.location.latitude
        longitude = update.message.location.longitude

        # حفظ الموقع الأساسي في بيانات المستخدم
        context.user_data['location_coords'] = {'latitude': latitude, 'longitude': longitude}

        # طلب الموقع الكتابي
        reply_markup = ReplyKeyboardMarkup([["عودة ➡️"]], resize_keyboard=True)
        await update.message.reply_text(
            "✅ تم استلام الموقع. يرجى الآن كتابة وصف موقعك (مثل الشارع، العلامة القريبة).",
            reply_markup=reply_markup
        )
        return ASK_LOCATION_TEXT
    else:
        await update.message.reply_text("❌ يرجى إرسال موقعك باستخدام ميزة Telegram.")
        return ASK_LOCATION_IMAGE





async def handle_location_text(update: Update, context: CallbackContext) -> int:
    user_location_text = update.message.text

    # ⬅️ تحقق مما إذا كانت الرسالة "عودة"
    if user_location_text == "عودة ➡️":
        # احذف الإحداثيات المسجلة
        context.user_data.pop("location_coords", None)

        # ارجع إلى خيار إرسال الموقع من جديد
        location_button = KeyboardButton("📍 إرسال موقعي", request_location=True)
        reply_markup = ReplyKeyboardMarkup([[location_button], ["عودة ➡️"]], resize_keyboard=True)
        await update.message.reply_text(
            "🔙 تم الرجوع خطوة للخلف. أرسل موقعك باستخدام الزر أدناه.",
            reply_markup=reply_markup
        )
        return ASK_LOCATION_IMAGE

    # 🟢 متابعة حفظ الموقع الكتابي
    context.user_data['location_text'] = user_location_text

    await update.message.reply_text(f"تم استلام موقعك الكتابي: {user_location_text}")

    reply_markup = ReplyKeyboardMarkup([
        ["اطلب عالسريع 🔥"],
        ["تعديل معلوماتي 🖊", "التواصل مع الدعم 🎧"],
        ["من نحن 🏢", "أسئلة متكررة ❓"]
    ], resize_keyboard=True)
    await update.message.reply_text(
        "الآن يمكنك متابعة طلبك أو تعديل معلوماتك.",
        reply_markup=reply_markup
    )

    return MAIN_MENU








async def ask_location_text(update: Update, context: CallbackContext) -> int:
    """
    طلب وصف الموقع أو الموقع الجغرافي من المستخدم باستخدام ميزة GPS.
    """
    if update.message.text == "عودة ➡️":
        # العودة إلى اختيار المدينة
        context.user_data.pop('city', None)  # حذف الإجابة السابقة
        cities = {
            "دمشق": ["مدينة دمشق", "معضمية الشام", "جرمانا"],
            "حلب": ["مدينة حلب", "السفيرة", "اعزاز"],
            "اللاذقية": ["مدينة اللاذقية", "جبلة", "القرداحة"],
            "حمص": ["مدينة حمص", "الرستن", "تلكلخ"],
            "طرطوس": ["مدينة طرطوس", "بانياس", "صافيتا"],
            "حماة": ["مدينة حماة", "مصياف", "السلمية"]
        }
        reply_markup = ReplyKeyboardMarkup(
            [[city] for city in cities.get(context.user_data.get('province', ''), [])] + [["عودة ➡️"]],
            resize_keyboard=True
        )
        await update.message.reply_text(
            "🔙 تم الرجوع إلى السؤال السابق. يرجى اختيار المدينة مجددًا:",
            reply_markup=reply_markup
        )
        return ASK_CITY

    # إعداد زر طلب الموقع الجغرافي
    location_button = KeyboardButton("إرسال موقعي 📍", request_location=True)
    reply_markup = ReplyKeyboardMarkup([[location_button], ["عودة ➡️"]], resize_keyboard=True)

    # طلب الموقع من المستخدم
    await update.message.reply_text(
        "📍 يرجى إرسال موقعك باستخدام GPS عبر الزر أدناه.\n"
        "بعد تحديد الموقع، نرجو كتابة وصف إضافي (مثل الحي، الشارع، معلم قريب):",
        reply_markup=reply_markup
    )
    return ASK_LOCATION_IMAGE



async def confirm_info(update: Update, context: CallbackContext) -> int:
    """
    عرض ملخص المعلومات للزبون مع بطاقة الموقع وخيارات تأكيد أو تعديل المعلومات.
    """
    if update.message.text == "عودة ➡️":
        # حذف البيانات المؤقتة والرجوع للسؤال السابق
        context.user_data.pop('location_coords', None)
        reply_markup = ReplyKeyboardMarkup([
            ["📍 إرسال موقعي", "عودة ➡️"]
        ], resize_keyboard=True)
        await update.message.reply_text("🔙 تم الرجوع إلى السؤال السابق. يرجى إرسال موقعك مجددًا:", reply_markup=reply_markup)
        return ASK_NEW_LOCATION_IMAGE

    # تخزين الوصف الكتابي للموقع
    context.user_data['location_text'] = update.message.text

    # استرجاع بيانات الزبون
    name = context.user_data.get('name', 'غير متوفر')
    phone = context.user_data.get('phone', 'غير متوفر')
    province = context.user_data.get('province', 'غير متوفر')
    city = context.user_data.get('city', 'غير متوفر')
    location_text = context.user_data.get('location_text', 'غير متوفر')
    location_coords = context.user_data.get('location_coords', None)

    # إعداد الرسالة
    info_message = (
        f"🔹 الاسم: {name}\n"
        f"🔹 رقم الهاتف: {phone}\n"
        f"🔹 المحافظة: {province}\n"
        f"🔹 المدينة: {city}\n"
        f"🔹 الوصف الكتابي للموقع: {location_text}\n"
    )

    reply_markup = ReplyKeyboardMarkup([
        ["نعم متأكد ✅"],
        ["تعديل معلوماتي 🖊"]
    ], resize_keyboard=True)

    try:
        # إذا كان الموقع متاحًا كإحداثيات، أرسل بطاقة الموقع
        if location_coords:
            latitude = location_coords.get('latitude')
            longitude = location_coords.get('longitude')
            await update.message.reply_location(
                latitude=latitude,
                longitude=longitude
            )
        # إرسال ملخص المعلومات
        await update.message.reply_text(
            f"{info_message}\n\n🔴 هل أنت متأكد من المعلومات التي سجلتها؟",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Error sending location: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء عرض المعلومات. يرجى المحاولة لاحقًا.")
        return MAIN_MENU

    return CONFIRM_INFO





async def handle_confirmation(update: Update, context: CallbackContext) -> int:
    choice = update.message.text

    if choice == "نعم متأكد ✅":
        try:
            # استرجاع بيانات المستخدم
            user_id = update.effective_user.id
            name = context.user_data['name']
            phone = context.user_data['phone']
            province = context.user_data['province']
            city = context.user_data['city']
            location_text = context.user_data['location_text']
            location_coords = context.user_data.get('location_coords', {})
            latitude = location_coords.get('latitude')
            longitude = location_coords.get('longitude')

            # حفظ البيانات في قاعدة البيانات
            cursor = db_conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO user_data 
                (user_id, name, phone, province, city, location_text, latitude, longitude) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, name, phone, province, city, location_text, latitude, longitude))
            db_conn.commit()

            # ✅ محاولة الحصول على معرف قناة الإعلانات للمدينة
            cursor.execute("SELECT ads_channel FROM cities WHERE name = ?", (city,))
            result = cursor.fetchone()
            ads_channel = result[0] if result and result[0] else None

            # بناء الكيبورد الأساسي
            reply_markup = ReplyKeyboardMarkup([
                ["اطلب عالسريع 🔥"],
                ["تعديل معلوماتي 🖊", "التواصل مع الدعم 🎧"],
                ["من نحن 🏢", "أسئلة متكررة ❓"]
            ], resize_keyboard=True)

            await update.message.reply_text(
                "✅ تم حفظ معلوماتك بنجاح.\n"
                "الآن يمكنك تقديم طلبك بسهولة ☺️.",
                reply_markup=reply_markup
            )

            # ✅ إذا كان هناك قناة إعلانات، أرسل دعوة للمستخدم
            if ads_channel:
                invite_keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("📢 لا تفوّت العروض! انضم لقناتنا", url=f"https://t.me/{ads_channel.lstrip('@')}")
                ]])
                await update.message.reply_text(
                    f"🎉 مفاجآت وعروض يومية مخصصة لأهل مدينة {city}!\n\n"
                    "🌟 لا تفوّت الخصومات الحصرية.\n"
                    "📢 كن أول من يعرف بالعروض الجديدة.\n\n"
                    "انضم الآن لقناتنا الإعلانية لتبقى على اطلاع دائم 🔥",
                    reply_markup=invite_keyboard
                )

            return MAIN_MENU

        except Exception as e:
            logging.error(f"Error saving user data: {e}")
            await update.message.reply_text("❌ حدث خطأ أثناء معالجة طلبك. يرجى المحاولة لاحقًا.")
            return MAIN_MENU

    elif choice == "تعديل معلوماتي 🖊":
        await update.message.reply_text("تم حذف بياناتك. سنبدأ من جديد 😊.")
        return await start(update, context)

    else:
        await update.message.reply_text("❌ يرجى اختيار أحد الخيارات المتاحة.")
        return CONFIRM_INFO



async def main_menu(update: Update, context: CallbackContext) -> int:
    choice = update.message.text
    user_id = update.effective_user.id
    cursor = db_conn.cursor()

    if choice == "تعديل معلوماتي 🖊":
        cursor.execute("DELETE FROM user_data WHERE user_id = ?", (user_id,))
        db_conn.commit()
        await update.message.reply_text("تم حذف بياناتك. سنبدأ من جديد 😊.")
        return await start(update, context)

    elif choice == "التواصل مع الدعم 🎧":
        await update.message.reply_text("للتواصل مع الدعم: @Support")
        return MAIN_MENU

    elif choice == "من نحن 🏢":
        await update.message.reply_text(
            "✅ بوتنا مرخص قانونياً لدى الدولة ويهدف إلى تحسين تجربة الطلبات.\n"
            "👨‍💻 لدينا فريق عمل جاهز للاستماع لنصائحكم دائماً لنتطور ونحسن لكم الخدمة.\n"
            "📲 مواقع التواصل الاجتماعي:\n"
            "- 📞 واتساب: 0912345678\n"
            "- 📧 بريد إلكتروني: support@bot.com\n"
            "- 🌐 موقعنا الإلكتروني: www.bot.com"
        )
        return MAIN_MENU

    elif choice == "أسئلة متكررة ❓":
        await update.message.reply_text(
            "📋 *الأسئلة المتكررة:*\n"
            "- *ما هي فوائد البوت؟*\n"
            "  🔹 تسهيل الطلبات، تحسين التنظيم، وتقليل الأخطاء.\n\n"
            "- *ماذا يحدث إذا عبثت مع المطاعم بإلغاء الطلبات أو عدم التواجد عند وصول الديلفري؟*\n"
            "  ❌ سيتم ملاحقتك قانونياً لضمان حق المطاعم.\n\n"
            "- *هل يتم حفظ بياناتي؟*\n"
            "  ✅ نعم، يتم حفظ البيانات لضمان تجربة أفضل عند الطلب مجدداً.",
            parse_mode="Markdown"
        )
        return MAIN_MENU

    elif choice == "اطلب عالسريع 🔥":
        now = datetime.now()
        cancel_times = context.user_data.get("cancel_history", [])
        cooldown, reason_msg = get_fast_order_cooldown(cancel_times)

        last_try = context.user_data.get("last_fast_order_time")
        if last_try and (now - last_try).total_seconds() < cooldown:
            remaining = int(cooldown - (now - last_try).total_seconds())
            minutes = max(1, remaining // 60)
            await update.message.reply_text(
                f"{reason_msg}\n⏳ الرجاء الانتظار {minutes} دقيقة قبل إعادة المحاولة.",
                reply_markup=ReplyKeyboardMarkup([
                    ["القائمة الرئيسية 🪧"]
                ], resize_keyboard=True)
            )
            return MAIN_MENU

        context.user_data["last_fast_order_time"] = now

        # 🧱 حذف البيانات المؤقتة
        for key in ['temporary_location_text', 'temporary_location_coords', 'temporary_total_price',
                    'orders', 'order_confirmed', 'selected_restaurant']:
            context.user_data.pop(key, None)

        # ✅ التحقق من الرقم المحفوظ
        cursor.execute("SELECT phone FROM user_data WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if not result:
            await update.message.reply_text("❌ لم يتم العثور على رقم هاتفك. يرجى إعادة التسجيل.")
            return await start(update, context)

        phone = result[0]

        # ✅ التحقق مما إذا كان الرقم محظورًا
        cursor.execute("SELECT 1 FROM blacklisted_numbers WHERE phone = ?", (phone,))
        if cursor.fetchone():
            await update.message.reply_text(
                "❌ عذرًا، رقمك محظور مؤقتاً من استخدام الخدمة.\n"
                "للاستفسار ورفع الحظر، يرجى التواصل مع فريق الدعم: @Support"
            )
            return MAIN_MENU

        # ✅ جلب اسم المدينة من user_data
        cursor.execute("SELECT city FROM user_data WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            await update.message.reply_text("❌ لم يتم العثور على مدينة مسجلة. يرجى تسجيل بياناتك أولاً.")
            return await start(update, context)

        city_name = row[0]

        # ✅ جلب معرف المدينة
        cursor.execute("SELECT id FROM cities WHERE name = ?", (city_name,))
        city_row = cursor.fetchone()
        if not city_row:
            await update.message.reply_text("❌ لم يتم العثور على معرف المدينة. يرجى إعادة التسجيل.")
            return await start(update, context)

        city_id = city_row[0]

        # ✅ استعلام عن المطاعم في المدينة باستخدام city_id
        cursor.execute("SELECT id, name, is_frozen FROM restaurants WHERE city_id = ?", (city_id,))
        rows = cursor.fetchall()

        restaurants = []
        restaurant_map = {}
        for restaurant_id, name, is_frozen in rows:
            if is_frozen:
                continue

            cursor.execute("SELECT total_ratings, total_score FROM restaurant_ratings WHERE restaurant = ?", (name,))
            rating_data = cursor.fetchone()
            if rating_data and rating_data[0] > 0:
                average = round(rating_data[1] / rating_data[0], 1)
                display_name = f"{name} ⭐ ({average})"
            else:
                display_name = f"{name} ⭐ (0)"

            restaurants.append(display_name)
            restaurant_map[display_name] = name

        restaurants += ["لم يذكر مطعمي؟ 😕", "القائمة الرئيسية 🪧"]
        context.user_data['restaurant_map'] = restaurant_map

        reply_markup = ReplyKeyboardMarkup([[r] for r in restaurants], resize_keyboard=True)
        await update.message.reply_text("🔽 اختر المطعم الذي ترغب بالطلب منه:", reply_markup=reply_markup)
        return SELECT_RESTAURANT










async def about_us(update: Update, context: CallbackContext) -> int:
    """عرض رسالة من نحن."""
    reply_markup = ReplyKeyboardMarkup([
        ["اطلب عالسريع 🔥"],
        ["تعديل معلوماتي 🖊"],
        ["التواصل مع الدعم 🎧"],
        ["من نحن 🛡️"],
        ["أسئلة متكررة ❓"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        "بوتنا مرخص قانونياً لدى الدولة، ولدينا فريق جاهز للاستماع لنصائحكم لتحسين الخدمة.\n"
        "📞 أرقام التواصل:\n"
        " - 0912345678\n"
        " - 0998765432\n"
        "📧 البريد الإلكتروني: support@example.com",
        reply_markup=reply_markup
    )
    return MAIN_MENU


async def faq(update: Update, context: CallbackContext) -> int:
    """عرض رسالة الأسئلة المتكررة."""
    reply_markup = ReplyKeyboardMarkup([
        ["اطلب عالسريع 🔥"],
        ["تعديل معلوماتي 🖊"],
        ["التواصل مع الدعم 🎧"],
        ["من نحن 🛡️"],
        ["أسئلة متكررة ❓"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        "🤔 الأسئلة المتكررة:\n"
        "1️⃣ ماذا يحدث إذا ألغيت الطلب أو لم أكن في الموقع؟ سيتم حظرك من الخدمة بعد المراجعة.\n"
        "2️⃣ ما فوائد استخدام البوت؟ الطلب السريع والمنظم دون عناء الاتصال.\n"
        "3️⃣ كيف يمكنني تعديل معلوماتي؟ اختر 'تعديل معلوماتي' من القائمة الرئيسية.\n"
        "📞 لمزيد من الاستفسارات، تواصل معنا: @Support",
        reply_markup=reply_markup
    )
    return MAIN_MENU




async def handle_restaurant_selection(update: Update, context: CallbackContext) -> int:
    selected_option = update.message.text
    restaurant_map = context.user_data.get('restaurant_map', {})

    # ✅ التحقق من الخيارات الإضافية
    if selected_option == "لم يذكر مطعمي؟ 😕":
        reply_markup = ReplyKeyboardMarkup([
            ["عودة ➡️"]
        ], resize_keyboard=True)
        await update.message.reply_text(
            "📋 ما اسم المطعم الذي ترغب بإضافته؟\n"
            "📝 سنقوم بالتواصل مع المطعم لإضافته قريباً! 😄",
            reply_markup=reply_markup
        )
        return ASK_NEW_RESTAURANT_NAME

    elif selected_option == "القائمة الرئيسية 🪧":
        reply_markup = ReplyKeyboardMarkup([
            ["اطلب عالسريع 🔥"],
            ["تعديل معلوماتي 🖊", "التواصل مع الدعم 🎧"],
            ["من نحن 🏢", "أسئلة متكررة ❓"]
        ], resize_keyboard=True)
        await update.message.reply_text("تم العودة إلى القائمة الرئيسية.", reply_markup=reply_markup)
        return MAIN_MENU

    # ✅ التحقق من المطعم المختار
    restaurant_name = restaurant_map.get(selected_option)
    if not restaurant_name:
        await update.message.reply_text("❌ المطعم الذي اخترته غير موجود. يرجى اختيار مطعم آخر.")
        return SELECT_RESTAURANT

    # ✅ التحقق من إذا كان المطعم مجمد
    cursor = db_conn.cursor()
    cursor.execute("SELECT is_frozen FROM restaurants WHERE name = ?", (restaurant_name,))
    result = cursor.fetchone()

    if not result:
        await update.message.reply_text("❌ حدث خطأ في جلب حالة المطعم. يرجى المحاولة لاحقًا.")
        return SELECT_RESTAURANT

    is_frozen = result[0]
    if is_frozen:
        await update.message.reply_text(
            f"❌ عذرًا، المطعم {restaurant_name} خارج الخدمة حاليًا بسبب التوقف المؤقت.\n"
            "🔄 يرجى اختيار مطعم آخر."
        )
        return SELECT_RESTAURANT

    # ✅ التحقق من وقت العمل
    is_open = await check_restaurant_availability(restaurant_name)
    if not is_open:
        # جلب وقت العمل
        cursor.execute("SELECT open_hour, close_hour FROM restaurants WHERE name = ?", (restaurant_name,))
        result = cursor.fetchone()

        if result:
            open_hour, close_hour = result

            def format_hour_12(hour_float):
                import math
                hour = int(hour_float)
                minutes = int(round((hour_float - hour) * 60))
                suffix = "صباحًا" if hour < 12 else "مساءً" if hour >= 18 else "ظهرًا"
                hour_12 = hour % 12
                hour_12 = 12 if hour_12 == 0 else hour_12
                time_str = f"{hour_12}:{minutes:02d}" if minutes else f"{hour_12}"
                return f"{time_str} {suffix}"

            open_str = format_hour_12(open_hour)
            close_str = format_hour_12(close_hour)

            await update.message.reply_text(
                f"❌ منعتذر، {restaurant_name} مسكر حاليًا.\n"
                f"⏰ أوقات الدوام: من {open_str} إلى {close_str}\n"
                "🔙 اختر مطعماً آخر أو حاول مرة أخرى لاحقاً."
            )
        else:
            await update.message.reply_text("❌ لا يمكن جلب أوقات عمل المطعم حالياً.")
        return SELECT_RESTAURANT

    # ✅ إذا كل شيء تمام، انتقل لعرض الفئات
    context.user_data['selected_restaurant'] = restaurant_name

    cursor.execute("""
        SELECT c.name FROM categories c
        JOIN restaurants r ON c.restaurant_id = r.id
        WHERE r.name = ?
        ORDER BY c.name
    """, (restaurant_name,))
    categories = [row[0] for row in cursor.fetchall()]
    categories.append("القائمة الرئيسية 🪧")

    reply_markup = ReplyKeyboardMarkup([[category] for category in categories], resize_keyboard=True)
    await update.message.reply_text(
        "🔽 اختر الفئة التي تريد الطلب منها:",
        reply_markup=reply_markup
    )
    return ORDER_CATEGORY







async def check_restaurant_availability(restaurant_name: str) -> bool:
    try:
        damascus_time = datetime.now(pytz.timezone("Asia/Damascus"))
        now_hour = damascus_time.hour + damascus_time.minute / 60

        cursor = db_conn.cursor()
        cursor.execute("SELECT open_hour, close_hour, is_frozen FROM restaurants WHERE name = ?", (restaurant_name,))
        result = cursor.fetchone()

        if not result:
            logger.warning(f"⚠️ لم يتم العثور على المطعم: {restaurant_name}")
            return False

        open_hour, close_hour, is_frozen = result

        if is_frozen:
            logger.info(f"🚫 المطعم {restaurant_name} مجمد حالياً.")
            return False

        available = open_hour <= now_hour < close_hour
        logger.debug(f"🕒 المطعم {restaurant_name} مفتوح الآن؟ {available} (الساعة الحالية: {now_hour})")
        return available

    except Exception as e:
        logger.exception(f"❌ خطأ أثناء التحقق من توفر المطعم {restaurant_name}: {e}")
        return False



async def show_restaurant_categories(update: Update, context: ContextTypes.DEFAULT_TYPE, from_ad=False):
    restaurant_id = context.user_data.get("selected_restaurant_id")

    if not restaurant_id:
        await update.message.reply_text("❌ لم يتم تحديد المطعم.")
        return

    # جلب اسم المطعم والفئات من قاعدة البيانات
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM restaurants WHERE id = ?", (restaurant_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        await update.message.reply_text("❌ لم يتم العثور على المطعم.")
        return

    restaurant_name = row[0]
    context.user_data["current_cart_restaurant"] = restaurant_name

    cursor.execute("""
        SELECT name FROM categories
        WHERE restaurant_id = ?
        ORDER BY name
    """, (restaurant_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("❌ لا توجد فئات مسجلة لهذا المطعم حالياً.")
        return

    keyboard = [[KeyboardButton(name[0])] for name in rows]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    if from_ad:
        await update.message.reply_text(
            f"✨ عروض من {restaurant_name} وصلت حديثًا!\n"
            f"👇 اختر الفئة وشوف العروض عالسريع!",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            f"📋 اختر الفئة من مطعم {restaurant_name}:",
            reply_markup=reply_markup
        )



def has_active_order(user_id: int) -> bool:
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return False

    return row[0] in ["قيد التوصيل", "بانتظار الكاشير", "جاري المعالجة"]

def has_active_order(user_id: int) -> bool:
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # تفترض أن جدول الطلبات فيه عمود status وقيم مثل: pending, in_progress, delivered, cancelled
    cursor.execute("""
        SELECT COUNT(*) FROM orders
        WHERE user_id = ? AND status IN ('pending', 'in_progress')
    """, (user_id,))

    count = cursor.fetchone()[0]
    conn.close()

    return count > 0





async def handle_missing_restaurant(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    cursor = db_conn.cursor()

    # التحقق من أن المستخدم اختار "عودة"
    if update.message.text == "عودة ➡️":
        # استرجاع اسم المدينة للمستخدم
        cursor.execute("SELECT city FROM user_data WHERE user_id = ?", (user_id,))
        city_row = cursor.fetchone()
        if not city_row:
            await update.message.reply_text("❌ لم يتم العثور على مدينة مسجلة. يرجى تسجيل بياناتك أولاً.")
            return await start(update, context)

        city_name = city_row[0]

        # جلب معرف المدينة
        cursor.execute("SELECT id FROM cities WHERE name = ?", (city_name,))
        city_id_row = cursor.fetchone()
        if not city_id_row:
            await update.message.reply_text("❌ لم يتم العثور على معرف المدينة.")
            return await start(update, context)

        city_id = city_id_row[0]

        # جلب المطاعم من المدينة عبر city_id
        cursor.execute("SELECT name, is_frozen FROM restaurants WHERE city_id = ?", (city_id,))
        rows = cursor.fetchall()

        restaurants = []
        restaurant_map = {}
        for name, is_frozen in rows:
            if is_frozen:
                continue

            cursor.execute("""
                SELECT total_ratings, total_score FROM restaurant_ratings WHERE restaurant = ?
            """, (name,))
            rating_data = cursor.fetchone()

            if rating_data and rating_data[0] > 0:
                average_rating = round(rating_data[1] / rating_data[0], 1)
                display_name = f"{name} ⭐ ({average_rating})"
            else:
                display_name = f"{name} ⭐ (0)"

            restaurants.append(display_name)
            restaurant_map[display_name] = name

        restaurants += ["القائمة الرئيسية 🪧", "لم يذكر مطعمي؟ 😕"]
        context.user_data['restaurant_map'] = restaurant_map

        reply_markup = ReplyKeyboardMarkup([[r] for r in restaurants], resize_keyboard=True)
        await update.message.reply_text("🔙 اختر المطعم الذي ترغب بالطلب منه:", reply_markup=reply_markup)
        return SELECT_RESTAURANT

    # إذا كتب المستخدم اسم مطعم جديد
    missing_restaurant_name = update.message.text
    missing_restaurant_channel = "@Lamtozkar"  # ضع معرف القناة الصحيح هنا

    # جلب اسم المدينة والمحافظة من user_data
    cursor.execute("SELECT city, province FROM user_data WHERE user_id = ?", (user_id,))
    location_row = cursor.fetchone()
    city_name = location_row[0] if location_row else "غير معروفة"
    province_name = location_row[1] if location_row else "غير معروفة"

    try:
        await context.bot.send_message(
            chat_id=missing_restaurant_channel,
            text=f"📢 زبون جديد اقترح إضافة مطعم:\n\n"
                 f"🏪 اسم المطعم: {missing_restaurant_name}\n"
                 f"🌍 المدينة: {city_name}\n"
                 f"📍 المحافظة: {province_name}\n\n"
                 f"👤 المستخدم: @{update.effective_user.username or 'غير متوفر'}"
        )
        await update.message.reply_text("✅ تم إرسال اسم المطعم بنجاح. سنقوم بالتواصل معه قريباً! 🙏")
    except Exception as e:
        logging.error(f"خطأ أثناء إرسال اسم المطعم إلى القناة: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء إرسال اسم المطعم. يرجى المحاولة لاحقاً.")

    # إعادة عرض المطاعم
    cursor.execute("SELECT id FROM cities WHERE name = ?", (city_name,))
    city_id_row = cursor.fetchone()
    if not city_id_row:
        await update.message.reply_text("❌ لم يتم العثور على معرف المدينة.")
        return await start(update, context)

    city_id = city_id_row[0]

    cursor.execute("SELECT name, is_frozen FROM restaurants WHERE city_id = ?", (city_id,))
    rows = cursor.fetchall()

    restaurants = []
    restaurant_map = {}
    for name, is_frozen in rows:
        if is_frozen:
            continue

        cursor.execute("""
            SELECT total_ratings, total_score FROM restaurant_ratings WHERE restaurant = ?
        """, (name,))
        rating_data = cursor.fetchone()

        if rating_data and rating_data[0] > 0:
            average_rating = round(rating_data[1] / rating_data[0], 1)
            display_name = f"{name} ⭐ ({average_rating})"
        else:
            display_name = f"{name} ⭐ (0)"

        restaurants.append(display_name)
        restaurant_map[display_name] = name

    restaurants += ["القائمة الرئيسية 🪧", "لم يذكر مطعمي؟ 😕"]
    context.user_data['restaurant_map'] = restaurant_map

    reply_markup = ReplyKeyboardMarkup([[r] for r in restaurants], resize_keyboard=True)
    await update.message.reply_text("🔙 اختر المطعم الذي ترغب بالطلب منه:", reply_markup=reply_markup)
    return SELECT_RESTAURANT








async def handle_order_category(update: Update, context: CallbackContext) -> int:
    category = update.message.text
    selected_restaurant = context.user_data.get('selected_restaurant')

    if not selected_restaurant:
        await update.message.reply_text("❌ يرجى اختيار المطعم أولاً.")
        return SELECT_RESTAURANT

    if category == "القائمة الرئيسية 🪧":
        reply_markup = ReplyKeyboardMarkup([
            ["اطلب عالسريع 🔥"],
            ["تعديل معلوماتي 🖊", "التواصل مع الدعم 🎧"],
            ["من نحن 🏢", "أسئلة متكررة ❓"]
        ], resize_keyboard=True)
        await update.message.reply_text("تم العودة إلى القائمة الرئيسية.", reply_markup=reply_markup)
        return MAIN_MENU

    context.user_data['selected_category'] = category

    # 🧹 حذف رسائل الوجبات السابقة
    previous_meal_msgs = context.user_data.get("current_meal_messages", [])
    if previous_meal_msgs:
        for msg_id in previous_meal_msgs:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except:
                pass
    context.user_data["current_meal_messages"] = []

    # 🥘 جلب وجبات الفئة
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT m.id, m.name, m.caption, m.image_message_id, m.size_options
        FROM meals m
        JOIN categories c ON m.category_id = c.id
        JOIN restaurants r ON c.restaurant_id = r.id
        WHERE c.name = ? AND r.name = ?
    """, (category, selected_restaurant))
    meals = cursor.fetchall()

    if not meals:
        await update.message.reply_text("❌ لا توجد وجبات حالياً في هذه الفئة.")
        return ORDER_CATEGORY

    for meal_id, name, caption, image_message_id, size_options_json in meals:
        try:
            size_options = json.loads(size_options_json or "[]")
        except json.JSONDecodeError:
            size_options = []

        buttons = []
        if size_options:
            size_buttons = []
            for opt in size_options:
                size_name = opt.get("name")
                price = opt.get("price")
                size_buttons.append(
                    InlineKeyboardButton(
                        f"{size_name}\n{price}",
                        callback_data=f"add_meal_with_size:{meal_id}:{size_name}"
                    )
                )
            buttons.append(size_buttons)
            buttons.append([
                InlineKeyboardButton("❌ حذف اللمسة الأخيرة", callback_data="remove_last_meal")
            ])
        else:
            buttons.append([
                InlineKeyboardButton("🛒 أضف إلى السلة", callback_data=f"add_meal_with_size:{meal_id}:default"),
                InlineKeyboardButton("❌ حذف اللمسة الأخيرة", callback_data="remove_last_meal")
            ])

        try:
            if image_message_id:
                photo_msg = await context.bot.copy_message(
                    chat_id=update.effective_chat.id,
                    from_chat_id=ADMIN_MEDIA_CHANNEL,
                    message_id=int(image_message_id)
                )
                context.user_data["current_meal_messages"].append(photo_msg.message_id)

                text = f"🍽️ {name}\n\n{caption}" if caption else name
                details_msg = await update.message.reply_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                context.user_data["current_meal_messages"].append(details_msg.message_id)
            else:
                raise ValueError("image_message_id مفقود.")
        except Exception as e:
            logger.error(f"❌ فشل عرض صورة الوجبة '{name}': {e}")
            text = f"🍽️ {name}\n\n{caption}" if caption else name
            msg = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            context.user_data["current_meal_messages"].append(msg.message_id)

    # ✅ عرض الفئات من جديد
    cursor.execute("""
        SELECT c.name FROM categories c
        JOIN restaurants r ON c.restaurant_id = r.id
        WHERE r.name = ?
        ORDER BY c.name
    """, (selected_restaurant,))
    categories = [row[0] for row in cursor.fetchall()]
    categories.append("تم ✅")

    reply_markup = ReplyKeyboardMarkup([[cat] for cat in categories], resize_keyboard=True)
    await update.message.reply_text("🔽 يمكنك اختيار فئة أخرى أو الضغط على 'تم ✅' عند الانتهاء:", reply_markup=reply_markup)

    return ORDER_MEAL














# 📸 دالة لاختبار نسخ صورة من القناة
async def test_copy_image(update: Update, context: CallbackContext):
    try:
        await context.bot.copy_message(
            chat_id=update.effective_chat.id,
            from_chat_id=ADMIN_MEDIA_CHANNEL,  # يجب أن يكون رقماً مثل -1001234567890
            message_id=123  # غيّر هذا إلى message_id الفعلي الموجود في القناة
        )
        await update.message.reply_text("✅ تم نسخ الصورة بنجاح.")
    except Exception as e:
        await update.message.reply_text(f"❌ فشل نسخ الصورة: {e}")







async def handle_add_meal_with_size(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    # 🧹 حذف رسالة المستجدات السابقة
    last_summary_msg_id = context.user_data.get("summary_msg_id")
    if last_summary_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_summary_msg_id)
        except:
            pass

    try:
        data = query.data.replace("add_meal_with_size:", "")
        meal_id, size = data.split(":", 1)
    except Exception:
        await query.message.reply_text("❌ حدث خطأ في إضافة الطلب. يرجى المحاولة مجددًا.")
        return ORDER_MEAL

    selected_restaurant = context.user_data.get("selected_restaurant")
    selected_category = context.user_data.get("selected_category")

    cursor = db_conn.cursor()
    cursor.execute("SELECT name, price, size_options FROM meals WHERE id = ?", (meal_id,))
    result = cursor.fetchone()

    if not result:
        await query.message.reply_text("❌ لم يتم العثور على هذه الوجبة.")
        return ORDER_MEAL

    meal_name, base_price, size_options_json = result

    price = base_price
    if size != "default" and size_options_json:
        try:
            size_options = json.loads(size_options_json)
            for opt in size_options:
                if opt["name"] == size:
                    price = opt["price"]
                    break
        except:
            pass

    key = f"{meal_name} ({size})"
    orders = context.user_data.setdefault('orders', {})
    orders[key] = orders.get(key, 0) + 1
    context.user_data['orders'] = orders

    context.user_data['temporary_total_price'] = context.user_data.get('temporary_total_price', 0) + price

    # 🔢 إعداد ملخص الطلب
    summary = "\n".join([f"{k} × {v}" for k, v in orders.items()])
    total = context.user_data['temporary_total_price']

    text = (
        f"✅ تمت إضافة: {meal_name} ({size}) بسعر {price}\n\n"
        f"🛒 طلبك حتى الآن:\n{summary}\n\n"
        f"💰 المجموع: {total}\n"
        f"عندما تنتهي اختر ✅ تم من الأسفل"
    )

    msg = await query.message.reply_text(text)
    context.user_data["summary_msg_id"] = msg.message_id

    return ORDER_MEAL


async def handle_remove_last_meal(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    # 🧹 حذف رسالة المستجدات السابقة
    last_summary_msg_id = context.user_data.get("summary_msg_id")
    if last_summary_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_summary_msg_id)
        except:
            pass

    data = query.message.text
    if not data:
        await query.message.reply_text("❌ لم يتم تحديد اسم الوجبة.")
        return ORDER_MEAL

    meal_name = data.split("\n")[0].replace("🍽️ ", "").strip()
    orders = context.user_data.get("orders", {})
    if not orders:
        await query.message.reply_text("❌ لا يوجد أي طلب لحذفه.")
        return ORDER_MEAL

    last_key = None
    for key in reversed(list(orders.keys())):
        if key.startswith(f"{meal_name} ("):
            last_key = key
            break

    if not last_key:
        await query.message.reply_text("❌ لم تقم بإضافة شيء من هذه الوجبة بعد.")
        return ORDER_MEAL

    if orders[last_key] > 1:
        orders[last_key] -= 1
    else:
        orders.pop(last_key)

    size = last_key.split("(", 1)[1].replace(")", "")
    cursor = db_conn.cursor()
    cursor.execute("SELECT price, size_options FROM meals WHERE name = ?", (meal_name,))
    result = cursor.fetchone()

    price = 0
    if result:
        base_price, size_options_json = result
        if size != "default" and size_options_json:
            try:
                size_options = json.loads(size_options_json)
                for opt in size_options:
                    if opt["name"] == size:
                        price = opt["price"]
                        break
            except:
                price = base_price or 0
        else:
            price = base_price or 0

    context.user_data['temporary_total_price'] = max(
        context.user_data.get('temporary_total_price', 0) - price, 0
    )

    # 🔢 إعداد ملخص الطلب
    summary = "\n".join([f"{k} × {v}" for k, v in orders.items()])
    total = context.user_data['temporary_total_price']

    text = (
        f"❌ تم حذف: {last_key} وقيمته {price}\n\n"
        f"🛒 طلبك حتى الآن:\n{summary}\n\n"
        f"💰 المجموع: {total}\n"
        f"عندما تنتهي اختر ✅ تم من الأسفل"
    )

    msg = await query.message.reply_text(text)
    context.user_data["summary_msg_id"] = msg.message_id

    return ORDER_MEAL





def get_meal_names_in_category(category: str, restaurant: str) -> list:
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT m.name FROM meals m
        JOIN categories c ON m.category_id = c.id
        JOIN restaurants r ON c.restaurant_id = r.id
        WHERE c.name = ? AND r.name = ?
    """, (category, restaurant))
    return [row[0] for row in cursor.fetchall()]




async def show_meals_in_category(update: Update, context: CallbackContext):
    selected_restaurant = context.user_data.get("selected_restaurant")
    selected_category = context.user_data.get("selected_category")

    if not selected_restaurant or not selected_category:
        await update.message.reply_text("❌ حدث خطأ: لم يتم تحديد المطعم أو الفئة.")
        return

    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT m.name, m.caption, m.image_file_id, m.size_options
        FROM meals m
        JOIN categories c ON m.category_id = c.id
        JOIN restaurants r ON c.restaurant_id = r.id
        WHERE c.name = ? AND r.name = ?
    """, (selected_category, selected_restaurant))
    meals = cursor.fetchall()

    if not meals:
        await update.message.reply_text("❌ لا توجد وجبات في هذه الفئة.")
        return

    for meal in meals:
        meal_name, caption, image_file_id, size_options_json = meal
        try:
            sizes = json.loads(size_options_json) if size_options_json else []
        except json.JSONDecodeError:
            sizes = []

        # تجهيز الأزرار
        buttons = []
        if sizes:
            size_buttons = []
            for size in sizes:
                size_buttons.append(
                    InlineKeyboardButton(
                        f"{size['name']} - {size['price']} ل.س",
                        callback_data=f"add_meal_with_size:{meal_name}:{size['name']}"
                    )
                )
            buttons.append(size_buttons)
            buttons.append([
                InlineKeyboardButton("❌ حذف اللمسة الأخيرة", callback_data="remove_last_meal"),
                InlineKeyboardButton("✅ تم", callback_data="done_adding_meals")
            ])
        else:
            buttons.append([
                InlineKeyboardButton("➕ أضف للسلة", callback_data=f"add_meal_with_size:{meal_name}:default"),
                InlineKeyboardButton("❌ حذف اللمسة الأخيرة", callback_data="remove_last_meal")
            ])
            buttons.append([
                InlineKeyboardButton("✅ تم", callback_data="done_adding_meals")
            ])

        reply_markup = InlineKeyboardMarkup(buttons)

        # إرسال الصورة أو النص فقط
        if image_file_id:
            await update.message.reply_photo(
                photo=image_file_id,
                caption=f"{meal_name}\n\n{caption}" if caption else meal_name,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                f"{meal_name}\n\n{caption}" if caption else meal_name,
                reply_markup=reply_markup
            )





async def handle_done_adding_meals(update: Update, context: CallbackContext) -> int:
    orders = context.user_data.get("orders", {})
    if not isinstance(orders, dict) or not orders:
        await update.message.reply_text("❌ لم تقم بإضافة أي وجبة بعد.")
        return ORDER_MEAL

    total_price = context.user_data.get("temporary_total_price", 0)

    summary_lines = []
    for item_key, count in orders.items():
        summary_lines.append(f"{count} × {item_key}")

    summary_text = "\n".join(summary_lines)

    keyboard = [
        [KeyboardButton("تخطي ➡️")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        f"🛒 *ملخص طلبك:*\n{summary_text}\n\n"
        f"💰 *المجموع:* {total_price} ل.س\n\n"
        "هل لديك ملاحظات على الطلب (مثل: زيادة جبنة، بلا بصل...)?\n"
        "يمكنك إرسال الملاحظة الآن أو الضغط على 'تخطي ➡️'.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return ASK_ORDER_NOTES






async def return_to_main_menu(update: Update, context: CallbackContext) -> int:
    # إعداد خيارات القائمة الرئيسية
    reply_markup = ReplyKeyboardMarkup([
        ["اطلب عالسريع 🔥"],
        ["تعديل معلوماتي 🖊", "التواصل مع الدعم 🎧"],
        ["من نحن 🏢", "أسئلة متكررة ❓"]
    ], resize_keyboard=True)

    # إرسال رسالة للمستخدم
    await update.message.reply_text("تمت العودة إلى القائمة الرئيسية.", reply_markup=reply_markup)

    # العودة إلى الحالة الرئيسية
    return MAIN_MENU




async def handle_order_notes(update: Update, context: CallbackContext) -> int:
    notes = update.message.text

    if notes == "تخطي ➡️":
        context.user_data['order_notes'] = "لا توجد ملاحظات."
    else:
        context.user_data['order_notes'] = notes

    reply_markup = ReplyKeyboardMarkup([
        ["لا لم يتغير أنا في موقعي الأساسي 😄"],
        ["نعم انا في موقع آخر 🙄"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        "✅ تم تسجيل ملاحظاتك.\n"
        "هل تريد توصيل الطلب إلى موقعك الأساسي المسجل لدينا أم أنك في موقع آخر؟",
        reply_markup=reply_markup
    )
    return ASK_ORDER_LOCATION





async def ask_order_location(update: Update, context: CallbackContext) -> int:
    choice = update.message.text
    orders = context.user_data.get('orders', [])
    selected_restaurant = context.user_data.get('selected_restaurant')

    # ✅ تصحيح الطلبات إذا كانت dict قديمة (مثل {"بيتزا (وسط)": 2})
    if isinstance(orders, dict):
        orders = fixed_orders_from_legacy_dict(orders, db_conn)
        context.user_data["orders"] = orders

    if choice == "لا لم يتغير أنا في موقعي الأساسي 😄":
        if not orders or not selected_restaurant:
            await update.message.reply_text("❌ حدث خطأ في استرجاع تفاصيل الطلب.")
            return MAIN_MENU

        total_price = sum(item.get("price", 0) for item in orders)
        context.user_data['temporary_total_price'] = total_price

        summary_lines = [
            f"- {item['name']} ({item['size']}) - {item['price']} ل.س"
            for item in orders
        ]
        summary_text = "\n".join(summary_lines)

        reply_markup = ReplyKeyboardMarkup([
            ["يالله عالسريع 🔥"],
            ["لا ماني متأكد 😐"]
        ], resize_keyboard=True)

        await update.message.reply_text(
            f"📋 ملخص طلبك:\n{summary_text}\n\n"
            f"💰 المجموع الكلي: {total_price} ل.س\n\n"
            "شو حابب نعمل؟",
            reply_markup=reply_markup
        )
        return CONFIRM_FINAL_ORDER

    elif choice == "نعم انا في موقع آخر 🙄":
        location_button = KeyboardButton("📍 إرسال موقعي", request_location=True)
        reply_markup = ReplyKeyboardMarkup([[location_button], ["عودة ➡️"]], resize_keyboard=True)

        await update.message.reply_text(
            "🔍 أرسل موقعك الجغرافي من خلال الزر أدناه.",
            reply_markup=reply_markup
        )
        return ASK_NEW_LOCATION_IMAGE

    else:
        await update.message.reply_text("❌ يرجى اختيار أحد الخيارات.")
        return ASK_ORDER_LOCATION

def fixed_orders_from_legacy_dict(orders_dict, db_conn):
    fixed_orders = []
    cursor = db_conn.cursor()

    for key, count in orders_dict.items():
        try:
            name, size = key.rsplit(" (", 1)
            size = size.rstrip(")")
        except:
            name, size = key, "default"

        cursor.execute("SELECT price, size_options FROM meals WHERE name = ?", (name.strip(),))
        result = cursor.fetchone()

        price = 0
        if result:
            base_price, size_options_json = result
            if size != "default" and size_options_json:
                try:
                    size_options = json.loads(size_options_json)
                    for opt in size_options:
                        if opt["name"] == size:
                            price = opt["price"]
                            break
                except:
                    price = base_price or 0
            else:
                price = base_price or 0

        for _ in range(count):
            fixed_orders.append({
                "name": name.strip(),
                "size": size.strip(),
                "price": price
            })

    return fixed_orders








async def handle_new_location_image(update: Update, context: CallbackContext) -> int:
    if update.message.location:
        latitude = update.message.location.latitude
        longitude = update.message.location.longitude

        # حفظ الموقع المؤقت
        context.user_data['temporary_location_coords'] = {'latitude': latitude, 'longitude': longitude}

        # طلب الموقع النصي المؤقت
        reply_markup = ReplyKeyboardMarkup([["عودة ➡️"]], resize_keyboard=True)
        await update.message.reply_text(
            "🔍 يرجى كتابة وصف لموقعك الجديد (مثل اسم الحي، الشارع، أو معلم قريب):",
            reply_markup=reply_markup
        )
        return ASK_NEW_LOCATION_TEXT

    await update.message.reply_text("❌ لم يتم استلام موقع صالح. يرجى استخدام ميزة Telegram.")
    return ASK_NEW_LOCATION_IMAGE



async def handle_new_location_text(update: Update, context: CallbackContext) -> int:
    context.user_data['temporary_location_text'] = update.message.text
    return await show_order_summary(update, context, is_new_location=True)





async def ask_new_location(update: Update, context: CallbackContext) -> int:
    """
    معالجة خيار 'نعم لقد تغير موقعي'، وطلب الموقع الجغرافي الجديد.
    """
    location_button = KeyboardButton("📍 إرسال موقعي", request_location=True)
    reply_markup = ReplyKeyboardMarkup([[location_button], ["عودة ⬅️"]], resize_keyboard=True)

    await update.message.reply_text(
        "🔍 يرجى إرسال موقعك الجغرافي باستخدام الزر أدناه لتحديد مكان التوصيل.\n\n"
        "📌 تأكد من تفعيل خدمة GPS على جهازك لتحديد الموقع بدقة.",
        reply_markup=reply_markup
    )
    return ASK_NEW_LOCATION_IMAGE


async def handle_new_location(update: Update, context: CallbackContext) -> int:
    """
    معالجة الموقع الجغرافي الجديد وإعداد المرحلة التالية لطلب وصف الموقع.
    """
    if update.message.location:
        latitude = update.message.location.latitude
        longitude = update.message.location.longitude

        # تخزين الموقع الجغرافي مؤقتًا
        context.user_data['temporary_location_coords'] = {'latitude': latitude, 'longitude': longitude}

        reply_markup = ReplyKeyboardMarkup([["عودة ⬅️"]], resize_keyboard=True)
        await update.message.reply_text(
            "✅ تم استلام موقعك الجديد.\n\n"
            "🔍 يرجى كتابة وصف لموقعك الجديد (مثل اسم الحي، الشارع، أو معلم قريب):",
            reply_markup=reply_markup
        )
        return ASK_NEW_LOCATION_TEXT

    else:
        await update.message.reply_text("❌ لم يتم استلام موقع صالح. يرجى استخدام الزر لإرسال موقعك.")
        return ASK_NEW_LOCATION_IMAGE

async def handle_new_location_description(update: Update, context: CallbackContext) -> int:
    context.user_data['temporary_location_text'] = update.message.text
    return await show_order_summary(update, context, is_new_location=True)




async def ask_new_location_text(update: Update, context: CallbackContext) -> int:
    if update.message.text == "عودة ➡️":
        return await ask_order_location(update, context)

    context.user_data['temporary_location_text'] = update.message.text
    return await show_order_summary(update, context, is_new_location=True)



async def show_order_summary(update: Update, context: CallbackContext, is_new_location=False) -> int:
    orders = context.user_data.get("orders", [])
    if isinstance(orders, dict):
        # تحويل الصيغة القديمة
        orders_list = []
        for name_size, count in orders.items():
            name, size = name_size.rsplit(" (", 1)
            size = size.rstrip(")")
            price = context.user_data.get('temporary_total_price', 0) // sum(orders.values())
            for _ in range(count):
                orders_list.append({"name": name, "size": size, "price": price})
        orders = orders_list
        context.user_data["orders"] = orders

    total_price = sum(item['price'] for item in orders)
    context.user_data['temporary_total_price'] = total_price

    summary = "\n".join([f"{item['name']} ({item['size']}) - {item['price']} ل.س" for item in orders])

    location_text = context.user_data.get("temporary_location_text", "") if is_new_location else "الموقع الأساسي"

    reply_markup = ReplyKeyboardMarkup([
        ["يالله عالسريع 🔥"],
        ["لا ماني متأكد 😐"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        f"📋 ملخص الطلب:\n{summary}\n\n"
        f"📍 الموقع: {location_text}\n"
        f"💰 المجموع الكلي: {total_price} ل.س\n\n"
        "شو حابب نعمل؟",
        reply_markup=reply_markup
    )
    return CONFIRM_FINAL_ORDER






async def handle_confirm_final_order(update: Update, context: CallbackContext) -> int:
    choice = update.message.text

    if choice == "يالله عالسريع 🔥":
        import random, string
        from datetime import datetime

        order_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=15))

        user_id = update.effective_user.id
        name = context.user_data.get('name', 'غير متوفر')
        phone = context.user_data.get('phone', 'غير متوفر')
        location_coords = context.user_data.get('temporary_location_coords', context.user_data.get('location_coords'))
        location_text = context.user_data.get('temporary_location_text', context.user_data.get('location_text', 'غير متوفر'))
        orders = context.user_data.get('orders', [])

        # ✅ إصلاح الخطأ: إذا كانت الطلبات dict (النظام القديم) نحولها إلى list of dicts
        if isinstance(orders, dict):
            converted_orders = []
            for name_size, count in orders.items():
                try:
                    name, size = name_size.rsplit(" (", 1)
                    size = size.rstrip(")")
                except Exception:
                    name = name_size
                    size = "default"
                price = context.user_data.get('temporary_total_price', 0) // sum(orders.values())
                for _ in range(count):
                    converted_orders.append({"name": name, "size": size, "price": price})
            orders = converted_orders
            context.user_data["orders"] = orders

        selected_restaurant = context.user_data.get('selected_restaurant', 'غير متوفر')

        if not orders or not selected_restaurant:
            await update.message.reply_text("❌ لا يمكن العثور على تفاصيل الطلب. يرجى التأكد من أنك قمت بتأكيد الطلب مسبقًا.")
            return MAIN_MENU

        total_price = sum(item["price"] for item in orders)
        context.user_data["temporary_total_price"] = total_price

        order_summary = "\n".join([
            f"- {item['name']}" + (f" ({item['size']})" if item.get('size') != "default" else "") + f": {item['price']} ل.س"
            for item in orders
        ])

        cursor = db_conn.cursor()

        # جلب رقم الطلب المتسلسل
        cursor.execute("SELECT last_order_number FROM restaurant_order_counter WHERE restaurant = ?", (selected_restaurant,))
        result = cursor.fetchone()
        if result:
            last_order_number = result[0]
        else:
            last_order_number = 0
            cursor.execute("INSERT INTO restaurant_order_counter (restaurant, last_order_number) VALUES (?, ?)", (selected_restaurant, 0))

        order_number = last_order_number + 1
        cursor.execute("UPDATE restaurant_order_counter SET last_order_number = ? WHERE restaurant = ?", (order_number, selected_restaurant))

        # جلب قناة المطعم
        cursor.execute("SELECT channel FROM restaurants WHERE name = ?", (selected_restaurant,))
        result = cursor.fetchone()
        restaurant_channel = result[0] if result else None

        if not restaurant_channel:
            await update.message.reply_text("❌ حدث خطأ: لم يتم العثور على القناة المخصصة لهذا المطعم.")
            return MAIN_MENU

        db_conn.commit()

        order_message = (
            f"🔔 *طلب جديد - معرف الطلب:* `{order_id}` 🔔\n"
            f"📌 *رقم الطلب:* `{order_number}`\n\n"
            f"👤 *الزبون:*\n"
            f" - الاسم: {name}\n"
            f" - رقم الهاتف: {phone}\n"
            f" - معرف التلغرام: @{update.effective_user.username if update.effective_user.username else 'غير متوفر'}\n"
            f" - رقم التلغرام: {user_id}\n\n"
            f"🛒 *الطلب:*\n"
            f"{order_summary}\n\n"
            f"📋 *ملاحظات:*\n{context.user_data.get('order_notes', 'لا توجد ملاحظات.')}\n\n"
            f"💰 *المجموع الكلي:* {total_price} ل.س\n\n"
            f"📍 *العنوان الكتابي:*\n{location_text}"
        )

        try:
            if location_coords:
                location_message = await context.bot.send_location(
                    chat_id=restaurant_channel,
                    latitude=location_coords.get('latitude'),
                    longitude=location_coords.get('longitude')
                )

                context.bot_data[location_message.message_id] = {
                    "user_id": user_id,
                    "order_id": order_id,
                    "selected_restaurant": selected_restaurant,
                    "timestamp": datetime.now()
                }

            sent_message = await context.bot.send_message(
                chat_id=restaurant_channel,
                text=order_message,
                parse_mode="Markdown"
            )

            context.bot_data[sent_message.message_id] = {
                "user_id": user_id,
                "order_id": order_id,
                "selected_restaurant": selected_restaurant,
                "timestamp": datetime.now()
            }

            cursor.execute("INSERT INTO user_orders (order_id, user_id, restaurant) VALUES (?, ?, ?)",
                           (order_id, user_id, selected_restaurant))
            db_conn.commit()
            user_orders[order_id] = user_id

            await update.message.reply_text("✅ تم إرسال طلبك إلى المطعم بنجاح. سيتم إخطارك عند بدء التحضير.")

        except Exception as e:
            logger.error(f"❌ خطأ أثناء إرسال الطلب إلى القناة: {e}")
            await update.message.reply_text("❌ حدث خطأ أثناء إرسال الطلب. يرجى المحاولة مرة أخرى.")
            return MAIN_MENU

        context.user_data["order_data"] = {
            "order_id": order_id,
            "order_number": order_number,
            "selected_restaurant": selected_restaurant,
            "timestamp": datetime.now()
        }

        reply_markup = ReplyKeyboardMarkup([
            ["إلغاء ❌ أريد تعديل الطلب"],
            ["لم تصل رسالة أنو بلشو بطلبي! 🤔"]
        ], resize_keyboard=True)

        await update.message.reply_text(
            f"✅ *تم تأكيد طلبك بنجاح.*\n"
            f"🔖 *معرف الطلب:* `{order_id}`\n"
            "شكراً لتعاملك معنا! 🍽️\n\n"
            "يرجى اختيار أحد الخيارات إذا دعت الحاجة:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return MAIN_MENU

    elif choice == "لا ماني متأكد 😐":
        reply_markup = ReplyKeyboardMarkup([
            ["اطلب عالسريع 🔥"],
            ["تعديل معلوماتي 🖊", "التواصل مع الدعم 🎧"],
            ["من نحن 🏢", "أسئلة متكررة ❓"]
        ], resize_keyboard=True)

        await update.message.reply_text(
            "🔙 تم الرجوع. يمكنك تعديل الطلب أو معلوماتك إذا رغبت قبل التأكيد.",
            reply_markup=reply_markup
        )
        return MAIN_MENU

    else:
        await update.message.reply_text("❌ يرجى اختيار أحد الخيارات المتاحة.")
        return CONFIRM_FINAL_ORDER











async def handle_cashier_interaction(update: Update, context: CallbackContext) -> None:
    """ 📩 يلتقط رد الكاشير من القناة ويحدد المستخدم صاحب الطلب لإرسال الإشعار إليه """

    channel_post = update.channel_post
    if not channel_post or not channel_post.text:
        return

    text = channel_post.text
    logger.info(f"📩 استلمنا رسالة جديدة من القناة: {text}")

    # ✅ استخراج معرف الطلب
    match = re.search(r"معرف الطلب:\s*([\w\d]+)", text)
    if not match:
        logger.warning("⚠️ لم يتم العثور على معرف الطلب في الرسالة!")
        return

    order_id = match.group(1)
    logger.info(f"🔍 البحث عن الطلب ID: {order_id}")

    # ✅ البحث عن المستخدم
    cursor = db_conn.cursor()
    cursor.execute("SELECT user_id FROM user_orders WHERE order_id = ?", (order_id,))
    user_result = cursor.fetchone()

    if not user_result:
        logger.warning(f"⚠️ لم يتم العثور على مستخدم لهذا الطلب: {order_id}")
        return

    user_id = user_result[0]
    logger.info(f"📩 سيتم إرسال رسالة إلى المستخدم: {user_id}")

    # ✅ إعداد الرسالة والخيارات بناءً على نوع الإشعار
    if "تم رفض الطلب" in text:
        message_text = (
            "❌ *نعتذر، لم يتم قبول طلبك.*\n\n"
            "📍 السبب: قد تكون معلوماتك غير مكتملة أو منطقتك خارج نطاق التوصيل.\n"
            "يمكنك تعديل معلوماتك أو المحاولة من مطعم آخر.\n\n"
            "📌 *معرف الطلب:* `" + order_id + "`"
        )

        # ✅ إظهار القائمة الرئيسية
        reply_markup = ReplyKeyboardMarkup([
            ["اطلب عالسريع 🔥"],
            ["تعديل معلوماتي 🖊", "التواصل مع الدعم 🎧"],
            ["من نحن 🏢", "أسئلة متكررة ❓"]
        ], resize_keyboard=True)

    elif "صار عالنار بالمطبخ" in text:
        message_text = f"🔥 *تم بدء تحضير طلبك!*\n\n📌 معرف الطلب: `{order_id}`\n🍽️ سيتم تحضيره خلال الوقت المحدد.\n\nشكراً لاختيارك مطعمنا! 🙏"
        reply_markup = ReplyKeyboardMarkup([
            ["وصل طلبي شكرا لكم 🙏"],
            ["إلغاء الطلب بسبب مشكلة 🫢"]
        ], resize_keyboard=True)
    else:
        message_text = f"🍽️ *تحديث عن طلبك!*\n\n{text}"
        reply_markup = ReplyKeyboardMarkup([
            ["وصل طلبي شكرا لكم 🙏"],
            ["إلغاء الطلب بسبب مشكلة 🫢"]
        ], resize_keyboard=True)

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=message_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        logger.info(f"📩 تم إرسال إشعار إلى المستخدم {user_id} - معرف الطلب: {order_id}")
    except Exception as e:
        logger.error(f"❌ خطأ أثناء إرسال الإشعار إلى المستخدم {user_id}: {e}")









async def handle_order_received(update: Update, context: CallbackContext) -> int:
    """
    عند اختيار 'وصل طلبي شكرا لكم 🙏' يتم حذف بيانات الطلب فقط للتمكن من بدء طلب جديد،
    ثم تظهر خيارات التقييم باستخدام رموز النجوم فقط.
    """
    # حذف بيانات الطلب فقط
    keys_to_remove = ['order_data', 'orders', 'selected_restaurant']
    for key in keys_to_remove:
        context.user_data.pop(key, None)

    # رسالة شكر
    await update.message.reply_text(
        "شكراً لك! ❤️ سعيدون بخدمتك ☺️.\n"
        "نأمل أن تستمتع بطلبك ونتطلع لخدمتك مجددًا!"
    )

    # عرض خيارات التقييم باستخدام رموز النجوم فقط
    reply_markup = ReplyKeyboardMarkup([
        ["⭐"], ["⭐⭐"], ["⭐⭐⭐"], ["⭐⭐⭐⭐"], ["⭐⭐⭐⭐⭐"]
    ], resize_keyboard=True)
    await update.message.reply_text(
        "كيف كانت تجربتك مع هذا المطعم؟ اختر عدد النجوم للتقييم:",
        reply_markup=reply_markup
    )

    return ASK_RATING






async def handle_order_cancellation(update: Update, context: CallbackContext) -> int:
    order_data = context.user_data.get("order_data")
    if not order_data:
        await update.message.reply_text("❌ لا يمكن العثور على تفاصيل الطلب.")
        return MAIN_MENU

    order_timestamp = order_data.get("timestamp", datetime.now())
    time_elapsed = (datetime.now() - order_timestamp).total_seconds() / 60  # بالدقائق

    if time_elapsed > 10:
        await update.message.reply_text(
            "😅 عذرًا، لقد مر أكثر من 10 دقائق على طلبك وبدأ تحضيره بالفعل. لا يمكنك إلغاء الطلب الآن."
        )
        return MAIN_MENU

    reply_markup = ReplyKeyboardMarkup([
        ["تأكيد الإلغاء ❌"],
        ["العودة والانتظار رسالة بدأ التحضير 😃"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        "هل أنت متأكد أنك تريد إلغاء الطلب؟\n"
        "اختر أحد الخيارات:",
        reply_markup=reply_markup
    )

    return CANCEL_ORDER_OPTIONS


async def handle_confirm_cancellation(update: Update, context: CallbackContext) -> int:
    choice = update.message.text
    order_data = context.user_data.get("order_data")

    if not order_data:
        await update.message.reply_text("❌ لم يتم العثور على تفاصيل الطلب. يمكنك البدء بطلب جديد.")
        return MAIN_MENU

    if choice == "تأكيد الإلغاء ❌":
        now = datetime.now()

        # ✅ سجل وقت الإلغاء مع تنظيف الإدخالات الأقدم من ساعة
        if "cancel_history" not in context.user_data:
            context.user_data["cancel_history"] = []

        context.user_data["cancel_history"] = [
            t for t in context.user_data["cancel_history"]
            if (now - t).total_seconds() <= 3600
        ]
        context.user_data["cancel_history"].append(now)

    elif choice == "العودة والانتظار رسالة بدأ التحضير 😃":
        reply_markup = ReplyKeyboardMarkup([
            ["إلغاء ❌ أريد تعديل الطلب"],
            ["لم تصل رسالة أنو بلشو بطلبي! 🤔"]
        ], resize_keyboard=True)
        await update.message.reply_text(
            "👌 تم الرجوع إلى الخيارات السابقة. اختر ما تريد:",
            reply_markup=reply_markup
        )
        return CANCEL_ORDER_OPTIONS

    else:
        await update.message.reply_text("❌ يرجى اختيار أحد الخيارات المتاحة.")
        return CANCEL_ORDER_OPTIONS



async def handle_cancellation_reason(update: Update, context: CallbackContext) -> int:
    if context.user_data.get("cancel_step") != "awaiting_cancellation_reason":
        await update.message.reply_text("❌ لم يتم تحديد طلب لإلغائه.")
        return MAIN_MENU

    # 🟢 احفظ سبب الإلغاء
    cancel_reason = update.message.text
    context.user_data["cancel_reason"] = cancel_reason
    context.user_data["cancel_step"] = None

    order_data = context.user_data.get("order_data")
    if not order_data:
        await update.message.reply_text("❌ لم يتم العثور على تفاصيل الطلب.")
        return MAIN_MENU

    order_number = order_data.get("order_number", "غير متوفر")
    order_id = order_data.get("order_id", None)
    selected_restaurant = order_data.get("selected_restaurant", "غير متوفر")

    cursor = db_conn.cursor()

    # ✅ تأكد من وجود المطعم في جدول العدادات
    cursor.execute("SELECT last_order_number FROM restaurant_order_counter WHERE restaurant = ?", (selected_restaurant,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO restaurant_order_counter (restaurant, last_order_number) VALUES (?, ?)", (selected_restaurant, 0))
        db_conn.commit()

    # ✅ جلب قناة المطعم
    cursor.execute("SELECT channel FROM restaurants WHERE name = ?", (selected_restaurant,))
    result = cursor.fetchone()
    restaurant_channel = result[0] if result else None

    if not restaurant_channel:
        await update.message.reply_text("❌ لم يتم العثور على القناة المرتبطة بالمطعم.")
        return MAIN_MENU

    try:
        cancellation_text = (
            f"🚫 تم إلغاء الطلب رقم {order_number}\n"
            f"📌 معرف الطلب: `{order_id}`\n"
            f"📍 السبب: {cancel_reason}"
        )
        await context.bot.send_message(
            chat_id=restaurant_channel,
            text=cancellation_text,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"❌ فشل إرسال رسالة الإلغاء إلى القناة: {e}")

    keys_to_remove = ['orders', 'selected_restaurant', 'order_data']
    for key in keys_to_remove:
        context.user_data.pop(key, None)

    reply_markup = ReplyKeyboardMarkup([
        ["اطلب عالسريع 🔥"],
        ["تعديل معلوماتي 🖊", "التواصل مع الدعم 🎧"],
        ["من نحن 🏢", "أسئلة متكررة ❓"]
    ], resize_keyboard=True)
    await update.message.reply_text(
        "✅ تم إلغاء طلبك بنجاح. يمكنك الآن البدء بطلب جديد.",
        reply_markup=reply_markup
    )
    return MAIN_MENU






async def handle_no_confirmation(update: Update, context: CallbackContext) -> int:
    # التحقق من بيانات الطلب
    order_data = context.user_data.get("order_data", None)
    if not order_data:
        await update.message.reply_text("❌ لا يمكن العثور على تفاصيل الطلب. يرجى التأكد من أنك قمت بتأكيد الطلب مسبقًا.")
        return MAIN_MENU

    # التحقق من مرور الوقت منذ تأكيد الطلب
    order_timestamp = order_data.get("timestamp", datetime.now())
    time_elapsed = (datetime.now() - order_timestamp).total_seconds() / 60  # بالدقائق

    if time_elapsed < 5:
        reply_markup = ReplyKeyboardMarkup([
            ["إلغاء ❌ أريد تعديل الطلب"],
            ["لم تصل رسالة أنو بلشو بطلبي! 🤔"]
        ], resize_keyboard=True)
        await update.message.reply_text(
            "نعتذر منك عليك الانتظار 5 دقائق 🙏🏻\n"
            "طلبك وصل مباشرة إلى المطعم لكن قد يكون هناك طلبات سابقة 😶",
            reply_markup=reply_markup
        )
        return MAIN_MENU

    # إذا مر أكثر من 5 دقائق
    reply_markup = ReplyKeyboardMarkup([
        ["تذكير المطعم 🫡"],
        ["إلغاء الطلب لقد تأخروا بالرد ❌"],
    ], resize_keyboard=True)
    await update.message.reply_text(
        "لقد مر أكثر من 5 دقائق.\n"
        "اختر أحد الخيارات التالية:",
        reply_markup=reply_markup
    )
    return CANCEL_ORDER_OPTIONS



async def handle_reminder(update: Update, context: CallbackContext) -> int:
    order_data = context.user_data.get("order_data")
    if not order_data:
        await update.message.reply_text("❌ لا يمكن العثور على تفاصيل الطلب.")
        return MAIN_MENU

    if context.user_data.get("reminder_sent", False):
        await update.message.reply_text(
            "❌ لقد قمت بالفعل بإرسال تذكير للمطعم. لا يمكنك إرسال تذكير آخر الآن."
        )
        return MAIN_MENU

    context.user_data["reminder_sent"] = True

    order_id = order_data.get("order_id")
    order_number = order_data.get("order_number")
    selected_restaurant = order_data.get("selected_restaurant")

    cursor = db_conn.cursor()

    # ✅ تأكد من وجود المطعم في جدول العدادات
    cursor.execute("SELECT last_order_number FROM restaurant_order_counter WHERE restaurant = ?", (selected_restaurant,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO restaurant_order_counter (restaurant, last_order_number) VALUES (?, ?)", (selected_restaurant, 0))
        db_conn.commit()

    # ✅ جلب قناة المطعم
    cursor.execute("SELECT channel FROM restaurants WHERE name = ?", (selected_restaurant,))
    result = cursor.fetchone()
    restaurant_channel = result[0] if result else None

    if restaurant_channel and order_number:
        await context.bot.send_message(
            chat_id=restaurant_channel,
            text=f"🔔 تذكير من الزبون: الطلب رقم {order_number} قيد الانتظار. نرجو الاستعجال في التحضير 🙏.",
        )
        await update.message.reply_text("✅ تم إرسال التذكير للمطعم بنجاح!")
    else:
        await update.message.reply_text("❌ لم يتم العثور على قناة المطعم أو رقم الطلب.")

    return MAIN_MENU








async def handle_final_cancellation(update: Update, context: CallbackContext) -> int:
    choice = update.message.text

    if choice == "إلغاء الطلب لقد تأخروا بالرد ❌":
        reply_markup = ReplyKeyboardMarkup([
            ["تأكيد الإلغاء ❌"],
            ["العودة وانتظار رسالة بدأ التحضير 😃"]
        ], resize_keyboard=True)
        await update.message.reply_text(
            "هل أنت متأكد أنك تريد إلغاء الطلب؟ اختر أحد الخيارات:",
            reply_markup=reply_markup
        )
        return CANCEL_ORDER_OPTIONS

    elif choice == "تأكيد الإلغاء ❌":
        order_data = context.user_data.get("order_data")
        if not order_data:
            await update.message.reply_text("❌ لا يمكن العثور على تفاصيل الطلب.")
            return MAIN_MENU

        context.user_data.pop("order_data", None)

        selected_restaurant = order_data.get("selected_restaurant")
        order_number = order_data.get("order_number")
        cursor = db_conn.cursor()
        cursor.execute("SELECT channel FROM restaurants WHERE name = ?", (selected_restaurant,))
        result = cursor.fetchone()
        restaurant_channel = result[0] if result else None

        if restaurant_channel:
            await context.bot.send_message(
                chat_id=restaurant_channel,
                text=f"🚫 تم إلغاء الطلب رقم: {order_number} من قبل الزبون."
            )
            await update.message.reply_text("✅ تم إلغاء طلبك بنجاح!")
        else:
            await update.message.reply_text("❌ لم يتم العثور على قناة المطعم.")

        return MAIN_MENU

    elif choice == "العودة وانتظار رسالة بدأ التحضير 😃":
        reply_markup = ReplyKeyboardMarkup([
            ["إلغاء ❌ أريد تعديل الطلب"],
            ["لم تصل رسالة أنو بلشو بطلبي! 🤔"]
        ], resize_keyboard=True)
        await update.message.reply_text(
            "👌 تم الرجوع إلى الخيارات السابقة. اختر ما تريد:",
            reply_markup=reply_markup
        )
        return MAIN_MENU

    else:
        await update.message.reply_text("❌ يرجى اختيار أحد الخيارات المتاحة.")
        return CANCEL_ORDER_OPTIONS






async def handle_order_issue(update: Update, context: CallbackContext) -> int:
    warning_message = (
        "🛑 *هام جدا*:\n\n"
        "عند إلغاء الطلب يجب أن تكون متأكد أن السبب كان من المطعم (تأخير أو أي شيء آخر..). "
        "وفي هذه الحالة، سيصلنا تقرير مباشرة يحتوي على جميع المعلومات: ماذا طلبت، متى طلبت، ومتى ألغيت، وما المطعم الذي تم الطلب منه.\n\n"
        "🛑 إذا كان الإلغاء من باب العبث أو المتعة وتم إثبات ذلك، سيتم حظرك نهائياً من البوت وملاحقتك قانونياً.\n\n"
        "إجراءاتنا دائماً تهدف لخدمتك عزيزي/عزيزتي، وشكراً لتفهمك ❤️"
    )

    reply_markup = ReplyKeyboardMarkup([
        ["تذكير المطعم بطلبي 👋", "كم يتبقى لطلبي"],
        ["إلغاء وإرسال تقرير ❌", "العودة والانتظار 🙃"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        warning_message,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return CANCEL_ORDER_OPTIONS





async def handle_report_issue(update: Update, context: CallbackContext) -> int:
    now = datetime.now()
    order_data = context.user_data.get("order_data")

    if not order_data:
        await update.message.reply_text("❌ لا يمكن العثور على تفاصيل الطلب. يرجى التأكد من أنك قمت بتأكيد الطلب مسبقًا.")
        return MAIN_MENU

    order_timestamp = order_data.get("timestamp", now)
    time_elapsed = (now - order_timestamp).total_seconds() / 60

    if time_elapsed < 29:
        remaining_time = int(30 - time_elapsed)
        await update.message.reply_text(
            f"⏳ لا يمكنك إرسال تقرير إلا بعد مرور نصف ساعة على الطلب.\n"
            f"يرجى المحاولة بعد {remaining_time} دقيقة."
        )
        return CANCEL_ORDER_OPTIONS

    reply_markup = ReplyKeyboardMarkup([
        ["إلغاء وإنشاء تقرير ❌"],
        ["منرجع ومننطر 🙃"]
    ], resize_keyboard=True)
    await update.message.reply_text(
        "⚠️ سيتم إرسال تقرير بكل تفاصيل الطلب:\n\n"
        "1️⃣ رقم الطلب.\n"
        "2️⃣ وقت الطلب ووقت الإلغاء.\n"
        "3️⃣ تفاصيل الطلب وبيانات الزبون.\n\n"
        "📄 سيتم إرسال التقرير إلى فريق الدعم لاتخاذ الإجراءات اللازمة.\n\n"
        "اختر أحد الخيارات:",
        reply_markup=reply_markup
    )
    return CANCEL_ORDER_OPTIONS





async def handle_report_cancellation(update: Update, context: CallbackContext) -> int:
    from datetime import datetime
    order_data = context.user_data.get("order_data")
    if not order_data:
        await update.message.reply_text("❌ لا يمكن العثور على تفاصيل الطلب.")
        return MAIN_MENU

    reason = update.message.text
    context.user_data["cancel_step"] = None  # تنظيف المرحلة

    user_id = update.effective_user.id
    name = context.user_data.get("name", "غير متوفر")
    phone = context.user_data.get("phone", "غير متوفر")
    order_number = order_data.get("order_number", "غير متوفر")
    order_id = order_data.get("order_id", "غير متوفر")
    selected_restaurant = order_data.get("selected_restaurant", "غير متوفر")
    order_time = order_data.get("timestamp", datetime.now())
    cancel_time = datetime.now()

    # إرسال تقرير للإدارة
    report_message = (
        f"📝 تقرير إلغاء طلب:\n\n"
        f"👤 الزبون:\n"
        f" - الاسم: {name}\n"
        f" - رقم الهاتف: {phone}\n"
        f" - رقم التلغرام: {user_id}\n\n"
        f"🛒 الطلب:\n"
        f"رقم الطلب: {order_number}\n"
        f"معرف الطلب: {order_id}\n"
        f"المطعم: {selected_restaurant}\n"
        f"⏱️ وقت الطلب: {order_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⏱️ وقت الإلغاء: {cancel_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"💬 سبب الإلغاء:\n{reason}"
    )

    await context.bot.send_message(chat_id="@reports_cancel", text=report_message)

    # إشعار المطعم
    cursor = db_conn.cursor()
    cursor.execute("SELECT channel FROM restaurants WHERE name = ?", (selected_restaurant,))
    result = cursor.fetchone()
    restaurant_channel = result[0] if result else None
    if restaurant_channel:
        await context.bot.send_message(
            chat_id=restaurant_channel,
            text=(
                f"🚫 تم إلغاء الطلب رقم: {order_number}\n"
                f"📌 معرف الطلب: `{order_id}`\n"
                "📍 السبب: تم إنشاء تقرير بالإلغاء وسنراجع الملاحظات مع الزبون.\n"
                "يرجى التواصل معه مباشرة إذا لزم الأمر."
            ),
            parse_mode="Markdown"
        )

    for key in ["order_data", "orders", "selected_restaurant"]:
        context.user_data.pop(key, None)

    reply_markup = ReplyKeyboardMarkup([
        ["اطلب عالسريع 🔥"],
        ["تعديل معلوماتي 🖊", "التواصل مع الدعم 🎧"],
        ["من نحن 🏢", "أسئلة متكررة ❓"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        "✅ تم إلغاء طلبك وإرسال تقرير بالمشكلة. شكراً لتفهمك ❤️.",
        reply_markup=reply_markup
    )
    return MAIN_MENU


async def ask_report_reason(update: Update, context: CallbackContext) -> int:
    context.user_data["cancel_step"] = "awaiting_report_reason"
    await update.message.reply_text(
        "❓ ما الذي جعلك تلغي الطلب؟\n"
        "نقدّر ملاحظتك وسنرسلها مع التقرير إلى فريق الدعم."
    )
    return ASK_REPORT_REASON



async def handle_return_and_wait(update: Update, context: CallbackContext) -> int:
    """
    إعادة عرض الخيارات "تذكير المطعم بطلبي 👋" و"إلغاء وإرسال تقرير ❌".
    """
    await update.message.reply_text(
        "👌 عدنا إلى الخيارات السابقة. اختر ما تريد:",
        reply_markup = ReplyKeyboardMarkup([
            ["تذكير المطعم بطلبي 👋", "كم يتبقى لطلبي"],
            ["إلغاء وإرسال تقرير ❌", "العودة والانتظار 🙃"]
        ], resize_keyboard=True)
    )
    return CANCEL_ORDER_OPTIONS

async def handle_order_cancellation_open(update: Update, context: CallbackContext) -> int:
        """
        عرض خيارات الإلغاء المفتوح (إلغاء الطلب لقد تأخروا بالرد ❌) مع إضافة خيار مننطر اسا شوي 🤷.
        """
        choice = update.message.text

        if choice == "إلغاء الطلب لقد تأخروا بالرد ❌":
            # عرض خيارات التأكيد أو الانتظار
            reply_markup = ReplyKeyboardMarkup([
                ["تأكيد الإلغاء ❌"],
                ["مننطر اسا شوي 🤷"]
            ], resize_keyboard=True)
            await update.message.reply_text(
                "⚠️ هل تريد تأكيد إلغاء الطلب؟ أم الانتظار قليلاً؟",
                reply_markup=reply_markup
            )
            return CANCEL_ORDER_OPTIONS

        elif choice == "تأكيد الإلغاء ❌":
            # تنفيذ عملية الإلغاء
            order_data = context.user_data.get("order_data")
            if not order_data:
                await update.message.reply_text("❌ لا يمكن العثور على تفاصيل الطلب.")
                return MAIN_MENU

            # حذف بيانات الطلب
            context.user_data.pop("order_data", None)

            # إرسال رسالة إلغاء إلى المطعم
            selected_restaurant = order_data.get("selected_restaurant")
            order_number = order_data.get("order_number")
            cursor = db_conn.cursor()
            cursor.execute("SELECT channel FROM restaurants WHERE name = ?", (selected_restaurant,))
            result = cursor.fetchone()
            restaurant_channel = result[0] if result else None

            if restaurant_channel:
                await context.bot.send_message(
                    chat_id=restaurant_channel,
                    text=f"🚫 تم إلغاء الطلب رقم: {order_number} من قبل الزبون."
                )
                await update.message.reply_text("✅ تم إلغاء طلبك بنجاح!")
            else:
                await update.message.reply_text("❌ لم يتم العثور على قناة المطعم.")

            return MAIN_MENU

        elif choice == "مننطر اسا شوي 🤷":
            # إعادة عرض الخيارات السابقة
            reply_markup = ReplyKeyboardMarkup([
                ["تذكير المطعم 🫡"],
                ["إلغاء الطلب لقد تأخروا بالرد ❌"]
            ], resize_keyboard=True)
            await update.message.reply_text(
                "👌 عدنا إلى الخيارات السابقة. اختر ما تريد:",
                reply_markup=reply_markup
            )
            return CANCEL_ORDER_OPTIONS

        else:
            await update.message.reply_text("❌ يرجى اختيار أحد الخيارات المتاحة.")
            return CANCEL_ORDER_OPTIONS

async def handle_reminder_order_request(update: Update, context: CallbackContext) -> int:
    """
    معالجة خيار 'تذكير المطعم بطلبي 👋' مع التأكد من إبقاء الخيارات الأخرى فعالة.
    """
    # التحقق من بيانات الطلب
    order_data = context.user_data.get("order_data")

    # إضافة سجل للتحقق من البيانات
    logging.info(f"user_data: {context.user_data}")

    if not order_data:
        await update.message.reply_text("❌ لا يمكن العثور على تفاصيل الطلب. يرجى التأكد من أنك قمت بتأكيد الطلب مسبقًا.")
        return CANCEL_ORDER_OPTIONS

    # التحقق من مرور وقت كافٍ للتذكير (15 دقيقة)
    now = datetime.now()
    last_reminder_request_time = context.user_data.get("last_reminder_request_time")

    if last_reminder_request_time:
        time_elapsed = (now - last_reminder_request_time).total_seconds() / 60  # بالدقائق
        if time_elapsed < 15:
            await update.message.reply_text(
                f"❌ لا يمكنك تذكير المطعم إلا مرة واحدة كل 15 دقيقة. "
                f"يرجى المحاولة بعد {15 - int(time_elapsed)} دقيقة."
            )
            return CANCEL_ORDER_OPTIONS

    # تحديث وقت آخر تذكير
    context.user_data["last_reminder_request_time"] = now

    # إرسال رسالة التذكير إلى المطعم
    order_number = order_data.get("order_number")
    selected_restaurant = order_data.get("selected_restaurant")
    cursor = db_conn.cursor()
    cursor.execute("SELECT channel FROM restaurants WHERE name = ?", (selected_restaurant,))
    result = cursor.fetchone()
    restaurant_channel = result[0] if result else None

    if restaurant_channel:
        try:
            await context.bot.send_message(
                chat_id=restaurant_channel,
                text=f"🔔 تذكير من الزبون: الطلب رقم {order_number} قيد الانتظار. "
                     f"نرجو الاستعجال في التحضير 🙏."
            )
            await update.message.reply_text("✅ تم إرسال التذكير للمطعم بنجاح! شكراً لتواصلك معنا.")
        except Exception as e:
            logging.error(f"خطأ أثناء إرسال رسالة التذكير: {e}")
            await update.message.reply_text("❌ حدث خطأ أثناء إرسال التذكير. يرجى المحاولة مرة أخرى.")
    else:
        await update.message.reply_text("❌ لم يتم العثور على قناة المطعم.")
        logging.error(f"القناة غير موجودة للمطعم: {selected_restaurant}")

    # إعادة عرض الخيارات للمستخدم
    reply_markup = ReplyKeyboardMarkup([
        ["تذكير المطعم بطلبي 👋", "كم يتبقى لطلبي"],
        ["إلغاء وإرسال تقرير ❌", "العودة والانتظار 🙃"]
    ], resize_keyboard=True)
    await update.message.reply_text(
        "🔄 اختر أحد الخيارات المتاحة:",
        reply_markup=reply_markup
    )

    # الإبقاء على نفس الحالة لتفعيل الخيارات
    return CANCEL_ORDER_OPTIONS



async def handle_back_and_wait(update: Update, context: CallbackContext) -> int:
    """
    معالجة خيار العودة والانتظار 🙃 وإعادة المستخدم إلى الخيارات الأساسية في الإلغاء.
    """
    reply_markup = ReplyKeyboardMarkup([
        ["وصل طلبي شكرا لكم 🙏"],
        ["إلغاء الطلب بسبب مشكلة 🫢"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        "👌 عدنا إلى الخيارات الأساسية. اختر ما يناسبك:",
        reply_markup=reply_markup
    )
    return MAIN_MENU


import asyncio

async def ask_remaining_time(update: Update, context: CallbackContext) -> int:
    """إرسال طلب إلى قناة المطعم لمعرفة مدة تحضير الطلب."""
    user_id = update.effective_user.id
    order_data = context.user_data.get("order_data")

    if not order_data:
        await update.message.reply_text("❌ لا يمكن العثور على تفاصيل الطلب.")
        return CANCEL_ORDER_OPTIONS

    order_number = order_data.get("order_number")
    selected_restaurant = order_data.get("selected_restaurant")

    cursor = db_conn.cursor()
    cursor.execute("SELECT channel FROM restaurants WHERE name = ?", (selected_restaurant,))
    result = cursor.fetchone()
    restaurant_channel = result[0] if result else None

    if not restaurant_channel:
        await update.message.reply_text("❌ لم يتم العثور على قناة المطعم.")
        return CANCEL_ORDER_OPTIONS

    # إرسال طلب إلى قناة المطعم
    message = await context.bot.send_message(
        chat_id=restaurant_channel,
        text=f"🔔 كم يتبقى لتحضير الطلب رقم {order_number}؟"
    )

    # حفظ معرف الرسالة لربط رد الكاشير بالمستخدم
    context.bot_data[message.message_id] = {
        "user_id": user_id,
        "order_number": order_number,
        "selected_restaurant": selected_restaurant,
    }

    # بدء تذكير تلقائي بعد 5 دقائق
    asyncio.create_task(remind_cashier_after_delay(context, message.message_id, restaurant_channel))

    await update.message.reply_text("✅ تم إرسال طلب معرفة الوقت إلى المطعم. سيتم إبلاغك عند الرد.")
    return CANCEL_ORDER_OPTIONS






async def handle_cashier_reply(update: Update, context: CallbackContext) -> None:
    channel_post = update.channel_post
    if not channel_post or not channel_post.reply_to_message:
        logging.warning("Received a message that is not a reply.")
        return

    reply_to_message_id = channel_post.reply_to_message.message_id
    logging.info(f"Reply to message ID: {reply_to_message_id}")

    # التحقق من أن الرسالة الأصلية موجودة في bot_data
    order_data = context.bot_data.get(reply_to_message_id)
    if not order_data:
        logging.warning(f"No order data found for reply_to_message_id: {reply_to_message_id}")
        return

    # استخراج المستخدم ورقم الطلب
    user_id = order_data["user_id"]
    order_number = order_data["order_number"]

    # محاولة استخراج الرقم من رد الكاشير
    try:
        remaining_time = int(''.join(filter(str.isdigit, channel_post.text)))
        if remaining_time < 0 or remaining_time > 150:  # تحقق من النطاق المقبول
            await channel_post.reply_text("❌ يرجى إدخال رقم بين 0 و150 دقيقة.")
            logging.warning(f"Invalid remaining time provided: {remaining_time}")
            return
    except ValueError:
        await channel_post.reply_text("❌ يرجى الرد برقم صحيح فقط.")
        logging.error("Failed to extract a valid number from the cashier's reply.")
        return

    # إرسال الرسالة للمستخدم
    await context.bot.send_message(
        chat_id=user_id,
        text=f"⏳ متبقي لطلبك حوالي {remaining_time} دقيقة. شكراً لانتظارك!"
    )
    logging.info(f"Extracted remaining time: {remaining_time} for order {order_number}. Notified user {user_id}.")






async def remind_cashier_after_delay(context: CallbackContext, message_id: int, restaurant_channel: str) -> None:
    """تذكير المطعم تلقائيًا بعد 5 دقائق إذا لم يتم الرد."""
    await asyncio.sleep(300)  # الانتظار 5 دقائق
    order_data = context.bot_data.get(message_id)

    if order_data:  # إذا لم يتم الرد على الرسالة
        order_number = order_data.get("order_number")
        await context.bot.send_message(
            chat_id=restaurant_channel,
            text=f"⏰ تذكير: لم يتم الرد على طلب الزبون لمعرفة مدة التحضير للطلب رقم {order_number}. يرجى الرد."
        )

async def handle_remaining_time_for_order(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    order_number = context.user_data.get("order_data", {}).get("order_number", None)

    if not order_number:
        await update.message.reply_text("❌ لا يمكن العثور على رقم الطلب. يرجى المحاولة مرة أخرى.")
        return MAIN_MENU

    restaurant_channel = restaurant_channels.get(context.user_data.get("selected_restaurant", None))
    if not restaurant_channel:
        await update.message.reply_text("❌ حدث خطأ: لا يمكن العثور على قناة المطعم.")
        return MAIN_MENU

    # إرسال طلب "كم يتبقى لطلبي" إلى قناة المطعم
    message_text = f"كم يتبقى لتحضير الطلب رقم {order_number}؟"
    sent_message = await context.bot.send_message(
        chat_id=restaurant_channel,
        text=message_text
    )

    # تسجيل البيانات لربط الرد بالمستخدم
    context.bot_data[sent_message.message_id] = {
        "user_id": user_id,
        "order_number": order_number
    }
    logging.info(f"Sent 'remaining time' request for order {order_number} to channel. Message ID: {sent_message.message_id}")

    await update.message.reply_text("✅ تم إرسال طلبك لمعرفة المدة المتبقية لتحضير الطلب.")
    return CANCEL_ORDER_OPTIONS











async def show_relevant_ads(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    cursor = db_conn.cursor()
    cursor.execute("SELECT city, province FROM user_data WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()

    if not user_info:
        return

    city, province = user_info
    cursor.execute("""
    SELECT content FROM advertisements
    WHERE region_type = 'all'
       OR (region_type = 'city' AND region_name = ?)
       OR (region_type = 'province' AND region_name = ?)
    """, (city, province))
    ads = cursor.fetchall()

    for ad in ads:
        await update.message.reply_text(ad[0])

async def ask_rating(update: Update, context: CallbackContext) -> int:
    selected_restaurant = context.user_data.get('selected_restaurant', 'غير متوفر')
    order_data = context.user_data.get("order_data", {})

    if not selected_restaurant or "order_number" not in order_data:
        await update.message.reply_text("❌ حدث خطأ في جلب معلومات الطلب.")
        return MAIN_MENU

    # حفظ رقم الطلب لربطه بالتقييم لاحقًا
    context.user_data["delivered_order_number"] = order_data["order_number"]

    reply_markup = ReplyKeyboardMarkup([
        ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"],
        ["تخطي ⏭️"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        f"كيف كانت تجربتك مع *{selected_restaurant}*؟\n"
        "يرجى اختيار تقييمك:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return ASK_RATING


async def handle_rating(update: Update, context: CallbackContext) -> int:
    user_rating_text = update.message.text

    if user_rating_text == "تخطي ⏭️":
        await update.message.reply_text("تم تخطي التقييم. شكراً لك! 😊")
        return MAIN_MENU

    # ✅ حساب عدد النجوم
    user_rating = user_rating_text.count("⭐")

    # ✅ استرجاع معلومات الطلب والمطعم
    selected_restaurant = context.user_data.get('selected_restaurant')
    order_number = context.user_data.get("delivered_order_number")
    order_data = context.user_data.get("order_data", {})
    order_id = order_data.get("order_id")  # هذا هو المعرف الأساسي المطلوب
    cursor = db_conn.cursor()
    cursor.execute("SELECT channel FROM restaurants WHERE name = ?", (selected_restaurant,))
    result = cursor.fetchone()
    restaurant_channel = result[0] if result else None

    if not selected_restaurant or not order_number or not order_id or not restaurant_channel:
        await update.message.reply_text("❌ حدث خطأ أثناء حفظ التقييم.")
        return MAIN_MENU

    # ✅ تحديث قاعدة بيانات التقييمات
    cursor.execute("""
        UPDATE restaurant_ratings
        SET total_ratings = total_ratings + 1, total_score = total_score + ?
        WHERE restaurant = ?
    """, (user_rating, selected_restaurant))
    db_conn.commit()

    # ✅ حفظ المعلومات مؤقتًا لإرسالها لاحقًا مع التعليق (إن وُجد)
    context.user_data["user_rating_text"] = user_rating_text
    context.user_data["delivered_order_number"] = order_number
    context.user_data["user_rating_order_id"] = order_id
    context.user_data["user_rating_channel"] = restaurant_channel

    # ✅ ننتقل لسؤال المستخدم عن التعليق
    await update.message.reply_text(
        "✍️ هل تحب ترك تعليق للمطعم؟\n"
        "مثل: 'الطلب كان بيوصل سخن' أو 'الدليفري تأخر شوية'\n"
        "أو اضغط 'تخطي ⏭️'",
        reply_markup=ReplyKeyboardMarkup([["تخطي ⏭️"]], resize_keyboard=True)
    )
    return ASK_RATING_COMMENT



async def handle_rating_comment(update: Update, context: CallbackContext) -> int:
    comment = update.message.text

    if comment == "تخطي ⏭️":
        context.user_data["user_rating_comment"] = None
    else:
        context.user_data["user_rating_comment"] = comment

    # استرجاع البيانات المطلوبة
    order_data = context.user_data.get("order_data", {})
    order_number = order_data.get("order_number", "غير متوفر")
    order_id = order_data.get("order_id", "غير معروف")
    selected_restaurant = context.user_data.get("selected_restaurant", "غير معروف")
    restaurant_channel = get_restaurant_channel(selected_restaurant)  # استخدم دالتك الحالية

    rating = context.user_data.get("user_rating_text", "غير محدد")
    comment_text = context.user_data.get("user_rating_comment")

    msg = (
        f"⭐ تقييم جديد من الزبون:\n"
        f"رقم الطلب: {order_number}\n"
        f"معرف الطلب: {order_id}\n"
        f"التقييم: {rating}"
    )
    if comment_text:
        msg += f"\n💬 التعليق: {comment_text}"

    try:
        await context.bot.send_message(
            chat_id=restaurant_channel,
            text=msg
        )
    except Exception as e:
        logger.error(f"فشل إرسال التقييم إلى قناة المطعم: {e}")

    await update.message.reply_text("✅ شكرًا لتقييمك. سعدنا بخدمتك!")

    # إنهاء الجلسة والعودة للقائمة
    reply_markup = ReplyKeyboardMarkup([
        ["اطلب عالسريع 🔥"],
        ["تعديل معلوماتي 🖊", "التواصل مع الدعم 🎧"],
        ["من نحن 🏢", "أسئلة متكررة ❓"]
    ], resize_keyboard=True)

    await update.message.reply_text("💡 يمكنك الآن بدء طلب جديد أو استكشاف المزيد:", reply_markup=reply_markup)
    return MAIN_MENU


async def handle_order_rejection_notice(update: Update, context: CallbackContext):
    message = update.channel_post
    if not message or message.chat_id != CHANNEL_ID:
        return

    text = message.text or ""
    if "تم رفض الطلب" not in text or "معرف الطلب" not in text:
        return

    logger.info(f"📩 تم استلام إشعار رفض طلب: {text}")

    # استخراج معرف الطلب
    match = re.search(r"معرف الطلب:\s*`?([\w\d]+)`?", text)
    if not match:
        logger.warning("⚠️ لم يتم استخراج معرف الطلب.")
        return

    order_id = match.group(1)
    user_info = context.bot_data.get(order_id)

    if not user_info:
        logger.warning(f"⚠️ لم يتم العثور على بيانات المستخدم المرتبطة بالطلب: {order_id}")
        return

    user_id = user_info["user_id"]

    # إعداد رسالة الرفض للمستخدم
    reply_markup = ReplyKeyboardMarkup([
        ["اطلب عالسريع 🔥"],
        ["تعديل معلوماتي 🖊", "التواصل مع الدعم 🎧"],
        ["من نحن 🏢", "أسئلة متكررة ❓"]
    ], resize_keyboard=True)

    await context.bot.send_message(
        chat_id=user_id,
        text="🚫 تم رفض طلبك. يمكنك تعديل معلوماتك أو المحاولة من مطعم آخر.",
        reply_markup=reply_markup
    )
    logger.info(f"📨 تم إرسال رسالة رفض الطلب للمستخدم: {user_id}")

    # إزالة بيانات الطلب المؤقتة
    context.bot_data.pop(order_id, None)




async def handle_report_based_cancellation(update: Update, context: CallbackContext):
    """📩 يلتقط إشعار إلغاء الطلب بسبب شكوى ويرسل إشعار للمستخدم"""

    try:
        text = update.channel_post.text
        logger.info(f"📥 استلمنا رسالة من القناة لمعالجتها كشكوى:\n{text}")

        # ✅ استخراج معرف الطلب والسبب من الرسالة (بدون backticks)
        match = re.search(r"📌 معرف الطلب: (\w+)\s+📍 السبب: (.+)", text)
        if not match:
            logger.warning(f"⚠️ لم يتم العثور على معرف الطلب أو السبب في الرسالة:\n{text}")
            return

        order_id = match.group(1)
        reason = match.group(2)

        logger.info(f"🔍 تم استخراج معرف الطلب: {order_id} والسبب: {reason}")

        # ✅ استخدام القاموس بدل قاعدة البيانات
        user_id = user_orders.get(order_id)
        if not user_id:
            logger.warning(f"⚠️ لم يتم العثور على مستخدم لهذا الطلب في الذاكرة: {order_id}")
            return

        # ✅ إعداد الرسالة للمستخدم
        message = (
            f"🚫 *تم إلغاء طلبك بسبب شكوى من الكاشير.*\n\n"
            f"📌 *سبب الإلغاء:* {reason}\n\n"
            f"نعتذر منك عن هذا الإزعاج.\n"
            f"يرجى التعاون عند التواصل معك لتحديد المشكلة.\n"
            f"يمكنك تعديل بياناتك أو اختيار مطعم آخر إن أردت.\n"
            f"وإذا واجهت مشكلة، لا تتردد بالتواصل معنا عبر الدعم. 🙏"
        )

        # ✅ إرسال الرسالة للمستخدم
        await context.bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )

        logger.info(f"✅ تم إعلام المستخدم {user_id} بإلغاء الطلب {order_id} بسبب شكوى.")

    except Exception as e:
        logger.error(f"❌ حدث خطأ أثناء معالجة الشكوى أو إرسالها للمستخدم: {e}")



async def reset_user_and_restart(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    cursor = db_conn.cursor()
    cursor.execute("DELETE FROM user_data WHERE user_id = ?", (user_id,))
    db_conn.commit()
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ انتهت خدمتنا في منطقتك مؤقتًا.\nسنعود بأقرب وقت ممكن بإذن الله 🙏\nسنبدأ من جديد الآن."
        )
        await start(update=None, context=context, user_id=user_id)  # تخصيص start لتقبل user_id
    except:
        pass







async def safe_reply(update, text, **kwargs):
    for _ in range(3):  # عدد المحاولات
        try:
            return await update.message.reply_text(text, **kwargs)
        except NetworkError:
            await asyncio.sleep(2)  # انتظر قبل إعادة المحاولة
    raise NetworkError("حدث خطأ في الشبكة بعد عدة محاولات.")

async def safe_request(bot_func, *args, **kwargs):
    for _ in range(3):  # عدد المحاولات
        try:
            return await bot_func(*args, **kwargs)
        except telegram.error.TimedOut:
            await asyncio.sleep(5)  # الانتظار قبل المحاولة مرة أخرى
    raise telegram.error.TimedOut("فشل الاتصال بعد عدة محاولات.")



async def handle_vip_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if not args or not args[0].startswith("vip_"):
        await update.message.reply_text("❌ رابط الإعلان غير صالح.")
        return ConversationHandler.END

    try:
        _, city_id_str, restaurant_id_str = args[0].split("_")
        city_id = int(city_id_str)
        restaurant_id = int(restaurant_id_str)
    except Exception:
        await update.message.reply_text("❌ رابط الإعلان غير صالح.")
        return ConversationHandler.END

    # ✅ التحقق من التسجيل
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT city_id FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("👋 لازم تسجل معلوماتك أولاً من خيار 'املأ بياناتي'.")
        return ConversationHandler.END

    if row[0] != city_id:
        await update.message.reply_text("❌ هذا الإعلان موجه لمدينة أخرى.")
        return ConversationHandler.END

    # ✅ التحقق من الطلبات الجارية
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM orders WHERE user_id = ? AND status = 'قيد التنفيذ'", (user_id,))
    active_order = cursor.fetchone()
    conn.close()

    if active_order:
        await update.message.reply_text("🚫 لا يمكنك فتح عرض جديد أثناء وجود طلب قيد التنفيذ.")
        return ConversationHandler.END

    # ✅ تفريغ السلة والانتقال للفئات
    context.user_data["orders"] = []
    context.user_data["selected_restaurant_id"] = restaurant_id

    return await show_restaurant_categories(update, context, from_ad=True)

BOT_USERNAME = "Fasterone1200_bot"  # اسم بوت الزبون بدون @

async def handle_vip_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "channel":
        return

    if not update.message.reply_markup or not update.message.reply_markup.inline_keyboard:
        return

    try:
        button = update.message.reply_markup.inline_keyboard[0][0]
        url = button.url
        if not url or "start=vip_" not in url:
            return

        # استخراج city_id و restaurant_id من الرابط
        parts = url.split("start=vip_")[1].split("_")
        city_id = int(parts[0])
        restaurant_id = int(parts[1]) if len(parts) > 1 else None
    except Exception as e:
        print("❌ فشل استخراج معلومات الإعلان:", e)
        return

    # جلب المستخدمين المسجلين في المدينة
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE city_id = ?", (city_id,))
    users = [row[0] for row in cursor.fetchall()]
    conn.close()

    # تجهيز الزر إن وُجد مطعم
    button_markup = None
    if restaurant_id:
        vip_link = f"https://t.me/{BOT_USERNAME}?start=vip_{city_id}_{restaurant_id}"
        button_markup = InlineKeyboardMarkup([[InlineKeyboardButton("اكبسني 😉", url=vip_link)]])

    for user_id in users:
        try:
            if update.message.photo:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=update.message.photo[-1].file_id,
                    caption=update.message.caption,
                    parse_mode="Markdown",
                    reply_markup=button_markup
                )
            elif update.message.video:
                await context.bot.send_video(
                    chat_id=user_id,
                    video=update.message.video.file_id,
                    caption=update.message.caption,
                    parse_mode="Markdown",
                    reply_markup=button_markup
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=update.message.text or "📢 إعلان جديد",
                    parse_mode="Markdown",
                    reply_markup=button_markup
                )
        except Exception as e:
            print(f"❌ فشل إرسال الإعلان للمستخدم {user_id}:", e)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    # 🧠 إرسال الخطأ للمشرف في قناة الأخطاء
    try:
        await context.bot.send_message(
            chat_id=ERRORS_CHANNEL,
            text=(
                "🚨 *حدث خطأ في البوت!*\n"
                f"🔧 `{context.error}`"
            ),
            parse_mode="Markdown"
        )
    except TelegramError:
        pass  # إذا فشل إرسال الخطأ، تجاهله بصمت

    # 🧾 إبلاغ المستخدم برسالة لطيفة
    if update and getattr(update, "message", None):
        try:
            await update.message.reply_text("❌ حدث خطأ أثناء تنفيذ الطلب. حاول مرة أخرى لاحقاً.")
        except:
            pass

def reset_order_counters():
    cursor = db_conn.cursor()
    cursor.execute("UPDATE restaurant_order_counter SET last_order_number = 0")
    db_conn.commit()
    print("✅ تم تصفير عدادات الطلبات لجميع المطاعم.")




conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        ASK_INFO: [
            MessageHandler(filters.Regex("^تفاصيل عن الأسئلة وما الغاية منها$"), ask_info_details),
            MessageHandler(filters.Regex("^من نحن 🏢$"), about_us),
            MessageHandler(filters.Regex("^أسئلة متكررة ❓$"), faq),
            MessageHandler(filters.Regex("^املأ بياناتي$"), ask_name)
        ],
        ASK_NAME: [
            MessageHandler(filters.Regex("^عودة ⬅️$"), handle_back_to_info),
            MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)
        ],
        ASK_PHONE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, send_verification_code)
        ],
        ASK_PHONE_VERIFICATION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, verify_code)
        ],
        ASK_PROVINCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_province)],
        ASK_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_city)],
        ASK_CUSTOM_CITY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_city)
        ],
        ASK_LOCATION_IMAGE: [
            MessageHandler(filters.LOCATION, handle_location),
            MessageHandler(filters.Regex("عودة ➡️"), ask_order_location)
        ],
        ASK_LOCATION_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_info),
            MessageHandler(filters.Regex("عودة ➡️"), ask_order_location)
        ],
        CONFIRM_INFO: [
            MessageHandler(filters.Regex("نعم متأكد ✅"), handle_confirmation),
            MessageHandler(filters.Regex("تعديل معلوماتي 🖊"), start)
        ],
        ASK_RATING: [
            MessageHandler(filters.Regex(r"⭐.*"), handle_rating),
            MessageHandler(filters.Regex("تخطي ⏭️"), handle_rating)
        ],
        MAIN_MENU: [
            MessageHandler(filters.Regex("اطلب عالسريع 🔥"), main_menu),
            MessageHandler(filters.Regex("تعديل معلوماتي 🖊"), main_menu),
            MessageHandler(filters.Regex("من نحن 🏢"), about_us),
            MessageHandler(filters.Regex("أسئلة متكررة ❓"), faq),
            MessageHandler(filters.Regex("التواصل مع الدعم 🎧"), main_menu),
            MessageHandler(filters.Regex("وصل طلبي شكرا لكم 🙏"), ask_rating),
            MessageHandler(filters.Regex("إلغاء الطلب بسبب مشكلة 🫢"), handle_order_issue),
            MessageHandler(filters.Regex("لم تصل رسالة أنو بلشو بطلبي! 🤔"), handle_no_confirmation),
            MessageHandler(filters.Regex("إلغاء الطلب لقد تأخروا بالرد ❌"), handle_order_cancellation_open),
            MessageHandler(filters.Regex("تذكير المطعم 🫡"), handle_reminder),
            MessageHandler(filters.Regex("تذكير المطعم بطلبي 👋"), handle_reminder_order_request),
            MessageHandler(filters.Regex("كم يتبقى لطلبي"), ask_remaining_time),
            MessageHandler(filters.Regex("إلغاء ❌ أريد تعديل الطلب"), handle_order_cancellation)
        ],
        SELECT_RESTAURANT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_restaurant_selection)
        ],
        ASK_NEW_RESTAURANT_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_missing_restaurant)
        ],
        ORDER_CATEGORY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_order_category)
        ],
        ORDER_MEAL: [
            CallbackQueryHandler(handle_add_meal_with_size, pattern="^add_meal_with_size:"),
            CallbackQueryHandler(handle_remove_last_meal, pattern="^remove_last_meal$"),
            CallbackQueryHandler(handle_done_adding_meals, pattern="^done_adding_meals$"),
            MessageHandler(filters.Regex("^تم ✅$"), handle_done_adding_meals),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_order_category),
            MessageHandler(filters.Regex("^القائمة الرئيسية 🪧$"), return_to_main_menu)
        ],
        CONFIRM_ORDER: [
            MessageHandler(filters.Regex("إلغاء ❌"), handle_final_cancellation),
            MessageHandler(filters.Regex("^القائمة الرئيسية 🪧$"), return_to_main_menu)
        ],
        ASK_ORDER_LOCATION: [
            MessageHandler(filters.Regex("نعم انا في موقع آخر 🙄"), ask_new_location),
            MessageHandler(filters.Regex("لا لم يتغير أنا في موقعي الأساسي 😄"), ask_order_location)
        ],
        ASK_NEW_LOCATION_IMAGE: [
            MessageHandler(filters.LOCATION, handle_new_location),
            MessageHandler(filters.Regex("عودة ⬅️"), ask_new_location)
        ],
        ASK_ORDER_NOTES: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_order_notes)
        ],
        CANCEL_ORDER_OPTIONS: [
            MessageHandler(filters.Regex("تذكير المطعم 🫡"), handle_reminder),
            MessageHandler(filters.Regex("تذكير المطعم بطلبي 👋"), handle_reminder_order_request),
            MessageHandler(filters.Regex("إلغاء الطلب لقد تأخروا بالرد ❌"), handle_order_cancellation_open),
            MessageHandler(filters.Regex("كم يتبقى لطلبي"), handle_remaining_time_for_order),
            MessageHandler(filters.Regex("إلغاء وإرسال تقرير ❌"), handle_report_issue),
            MessageHandler(filters.Regex("إلغاء وإنشاء تقرير ❌"), ask_report_reason),
            MessageHandler(filters.Regex("منرجع ومننطر 🙃"), handle_return_and_wait),
            MessageHandler(filters.Regex("العودة والانتظار 🙃"), handle_back_and_wait),
            MessageHandler(filters.Regex("إلغاء متأكد ❌"), handle_confirm_cancellation),
            MessageHandler(filters.Regex("تأكيد الإلغاء ❌"), handle_confirm_cancellation),
            MessageHandler(filters.Regex("مننطر اسا شوي 🤷"), handle_order_cancellation_open),
            MessageHandler(filters.Regex("إلغاء ❌ أريد تعديل الطلب"), handle_order_cancellation),
            MessageHandler(filters.Regex("لم تصل رسالة أنو بلشو بطلبي! 🤔"), handle_no_confirmation),
            MessageHandler(filters.Regex("العودة والانتظار رسالة بدأ التحضير 😃"), handle_confirm_cancellation),
            MessageHandler(filters.Regex("وصل طلبي شكرا لكم 🙏"), ask_rating),
            MessageHandler(filters.Regex("إلغاء الطلب بسبب مشكلة 🫢"), handle_order_issue),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cancellation_reason)
        ],
        ASK_NEW_LOCATION_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_location_description)
        ],
        CONFIRM_FINAL_ORDER: [
            MessageHandler(filters.Regex("يالله عالسريع 🔥|لا ماني متأكد 😐"), handle_confirm_final_order)
        ],
        ASK_REPORT_REASON: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_report_cancellation)
        ],
        ASK_RATING_COMMENT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rating_comment)
        ]
    },
    fallbacks=[CommandHandler("cancel", start)]
)
def run_user_bot():
    application = Application.builder().token("7675280742:AAF0aN8HjibzwtUKXaUoY1tg1FLS9cCIjEw").build()

    # إضافة معالج المحادثة
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("testimage", test_copy_image))

    # التفاعل مع رسائل القناة (للتحديثات من المطعم)
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.Regex(r"بسبب شكوى"),
        handle_report_based_cancellation
    ))

    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.Regex(r"تم رفض الطلب.*معرف الطلب"),
        handle_order_rejection_notice
    ))

    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.TEXT,
        handle_cashier_interaction
    ))

    application.add_handler(CommandHandler("start", handle_vip_start))

    application.add_handler(MessageHandler(
        filters.Chat(username="vip_ads_channel") & filters.Regex(r"/start vip_\d+_\d+"),
        handle_vip_broadcast_message
    ))

    application.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_vip_broadcast_message))

    scheduler = BackgroundScheduler()
    scheduler.add_job(reset_order_counters, CronTrigger(hour=0, minute=0))
    scheduler.start()

    # إضافة معالج الأخطاء
    application.add_error_handler(error_handler)

    application.run_polling()



if __name__ == "__main__":
     run_user_bot()
