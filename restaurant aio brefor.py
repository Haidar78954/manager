import logging
import re
import os
import json
import datetime
import aiosqlite
import asyncio
import nest_asyncio
from telegram.error import TelegramError
from telegram import ReplyKeyboardMarkup, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext
import traceback

# ✅ إعداد سجل الأخطاء
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ✅ مسار قاعدة البيانات
DB_PATH = "restaurant_orders.db"

# ✅ دالة اتصال آمن بـ aiosqlite
async def get_db_connection():
    try:
        return await aiosqlite.connect(DB_PATH)
    except Exception as e:
        logger.error(f"❌ فشل الاتصال بقاعدة البيانات: {e}")
        return None

# ✅ إنشاء الجداول الأساسية
async def initialize_database():
    try:
        db = await get_db_connection()
        if db is None:
            logger.error("❌ الاتصال بقاعدة البيانات فشل. لم يتم إنشاء الجداول.")
            return

        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                order_number INTEGER,
                restaurant TEXT,
                total_price INTEGER,
                timestamp TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS delivery_persons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant TEXT NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL
            )
        """)

        await db.commit()
        await db.close()
        logger.info("✅ تم التأكد من وجود جدول الطلبات وجدول الدليفري.")
    except Exception as e:
        logger.error(f"❌ خطأ أثناء إنشاء الجداول: {e}")

# ✅ تحميل الإعدادات من ملفات JSON داخل مجلد config
def load_config():
    current_dir = os.path.dirname(__file__)
    config_dir = os.path.join(current_dir, "config")

    json_files = [f for f in os.listdir(config_dir) if f.endswith(".json")]
    if not json_files:
        raise FileNotFoundError("❌ لا يوجد أي ملف إعداد في مجلد config.")

    config_path = os.path.join(config_dir, json_files[0])
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    return config

# ✅ متغيرات عامة سيتم تحميلها لاحقًا من config
TOKEN = None
CASHIER_CHAT_ID = None
CHANNEL_ID = None
RESTAURANT_COMPLAINTS_CHAT_ID = None

# ✅ متغيرات مؤقتة لإدارة الطلبات
pending_orders = {}
pending_locations = {}

# ✅ دالة تحليل النجوم من التقييمات
def extract_stars(text: str) -> str:
    match = re.search(r"تقييمه بـ (\⭐+)", text)
    return match.group(1) if match else "⭐️"




# ✅ دالة start — لا تعديل كبير هنا
async def start(update: Update, context: CallbackContext):
    try:
        await update.message.reply_text(
            "✅ بوت المطعم جاهز لاستقبال الطلبات من القناة!",
            reply_markup=get_admin_main_menu()
        )
    except Exception as e:
        logger.error(f"❌ خطأ في دالة start: {e}")


# ✅ استقبال طلب من القناة
async def handle_channel_order(update: Update, context: CallbackContext):
    message = update.channel_post

    if not message or message.chat_id != CHANNEL_ID:
        return

    text = message.text or ""

    if "استلم طلبه رقم" in text and "قام بتقييمه بـ" in text:
        logger.info("ℹ️ تم تجاهل رسالة التقييم، ليست طلبًا جديدًا.")
        return

    if text.startswith("🚫 تم إلغاء الطلب رقم"):
        logger.info("⛔️ تم تجاهل رسالة إلغاء الطلب (ليست طلبًا جديدًا).")
        return

    logger.info(f"📥 استلم البوت طلبًا جديدًا من القناة: {text}")

    match = re.search(r"معرف الطلب:\s*([\w\d]+)", text)
    if not match:
        logger.warning("⚠️ لم يتم العثور على معرف الطلب في الرسالة!")
        return

    order_id = match.group(1)
    logger.info(f"🔍 تم استخراج معرف الطلب: {order_id}")

    location = pending_locations.pop("last_location", None)
    message_text = text + ("\n\n📍 *تم إرفاق الموقع الجغرافي*" if location else "")

    keyboard = [
        [InlineKeyboardButton("✅ قبول الطلب", callback_data=f"accept_{order_id}")],
        [InlineKeyboardButton("❌ رفض الطلب", callback_data=f"reject_{order_id}")],
        [InlineKeyboardButton("🚨 شكوى عن الزبون أو الطلب", callback_data=f"complain_{order_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        sent_message = await context.bot.send_message(
            chat_id=CASHIER_CHAT_ID,
            text=f"🆕 *طلب جديد من القناة:*\n\n{message_text}\n\n📌 معرف الطلب: `{order_id}`",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        logger.info(f"✅ تم إرسال الطلب إلى الكاشير (order_id={order_id})")

        pending_orders[order_id] = {
            "order_details": message_text,
            "channel_message_id": message.message_id,
            "message_id": sent_message.message_id
        }

        if location:
            try:
                latitude, longitude = location
                await context.bot.send_location(chat_id=CASHIER_CHAT_ID, latitude=latitude, longitude=longitude)
                logger.info(f"✅ تم إرسال الموقع للكاشير (order_id={order_id})")
            except Exception as e:
                logger.error(f"❌ فشل إرسال الموقع: {e}")

    except Exception as e:
        logger.error(f"❌ خطأ أثناء إرسال الطلب إلى الكاشير: {e}")


# ✅ استقبال الموقع الجغرافي بعد الطلب
async def handle_channel_location(update: Update, context: CallbackContext):
    message = update.channel_post
    if not message or message.chat_id != CHANNEL_ID:
        return

    if not message.location:
        return

    latitude = message.location.latitude
    longitude = message.location.longitude
    logger.info(f"📍 تم استلام موقع: {latitude}, {longitude}")
    pending_locations["last_location"] = (latitude, longitude)

    last_order_id = max(pending_orders.keys(), default=None)
    if not last_order_id:
        logger.warning("⚠️ لا يوجد طلبات حالية لربط الموقع بها.")
        return

    pending_orders[last_order_id]["location"] = (latitude, longitude)
    updated_order_text = f"{pending_orders[last_order_id]['order_details']}\n\n📍 *تم إرفاق الموقع الجغرافي*"

    keyboard = [
        [InlineKeyboardButton("✅ قبول الطلب", callback_data=f"accept_{last_order_id}")],
        [InlineKeyboardButton("❌ رفض الطلب", callback_data=f"reject_{last_order_id}")],
        [InlineKeyboardButton("🚨 شكوى عن الزبون أو الطلب", callback_data=f"complain_{last_order_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.send_location(chat_id=CASHIER_CHAT_ID, latitude=latitude, longitude=longitude)
        logger.info(f"✅ أُرسل الموقع مجددًا للكاشير (order_id={last_order_id})")
    except Exception as e:
        logger.error(f"❌ خطأ أثناء إعادة إرسال الموقع: {e}")

    try:
        await context.bot.send_message(
            chat_id=CASHIER_CHAT_ID,
            text=f"🆕 *طلب جديد محدث من القناة:*\n\n{updated_order_text}\n\n📌 معرف الطلب: `{last_order_id}`",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        logger.info(f"✅ تم إرسال الطلب المحدث مع الموقع (order_id={last_order_id})")
    except Exception as e:
        logger.error(f"❌ خطأ أثناء إرسال الطلب المحدث: {e}")






async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    data = query.data.split("_")
    if len(data) < 2:
        return

    action = data[0]

    if action == "report":
        report_type = f"{data[0]}_{data[1]}"
        order_id = "_".join(data[2:])
    else:
        report_type = None
        order_id = "_".join(data[1:])

    if order_id not in pending_orders:
        await query.answer("⚠️ هذا الطلب لم يعد متاحًا.", show_alert=True)
        return

    order_info = pending_orders[order_id]
    message_id = order_info.get("message_id")
    order_details = order_info.get("order_details", "")

    # ✅ قبول الطلب: عرض أزرار الوقت
    if action == "accept":
        keyboard = [
            [InlineKeyboardButton(f"{t} دقيقة", callback_data=f"time_{t}_{order_id}")]
            for t in [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 75, 90]
        ]
        keyboard.append([InlineKeyboardButton("📌 أكثر من 90 دقيقة", callback_data=f"time_90+_{order_id}")])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"back_{order_id}")])

        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        except TelegramError as e:
            logger.error(f"❌ فشل في تعديل الأزرار (accept): {e}")
        return

    # ✅ رفض الطلب: عرض تأكيد
    elif action == "reject":
        try:
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ تأكيد رفض الطلب", callback_data=f"confirmreject_{order_id}")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data=f"back_{order_id}")]
                ])
            )
        except TelegramError as e:
            logger.error(f"❌ فشل في عرض أزرار الرفض: {e}")

    # ✅ تأكيد الرفض النهائي
    elif action == "confirmreject":
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=CASHIER_CHAT_ID,
                message_id=message_id,
                reply_markup=None
            )

            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=(
                    f"🚫 تم رفض الطلب.\n"
                    f"📌 معرف الطلب: `{order_id}`\n"
                    "📍 السبب: قد تكون معلومات المستخدم غير مكتملة أو غير واضحة.\n"
                    "يمكنك اختيار *تعديل معلوماتي* لتصحيحها.\n"
                    "أو ربما منطقتك لا تغطيها خدمة التوصيل.\n"
                    "جرب اختيار مطعم أقرب أو المحاولة لاحقًا إن كانت هناك مشكلة لدى المطعم."
                ),
                parse_mode="Markdown"
            )

            logger.info(f"✅ تم رفض الطلب وإبلاغ المستخدم. (order_id={order_id})")

        except TelegramError as e:
            logger.error(f"❌ فشل في إرسال إشعار رفض الطلب: {e}")
        finally:
            pending_orders.pop(order_id, None)  # 🧹 تنظيف الطلب

    # ✅ زر الرجوع
    elif action == "back":
        try:
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ قبول الطلب", callback_data=f"accept_{order_id}")],
                    [InlineKeyboardButton("❌ رفض الطلب", callback_data=f"reject_{order_id}")],
                    [InlineKeyboardButton("🚨 شكوى عن الزبون أو الطلب", callback_data=f"complain_{order_id}")]
                ])
            )
        except TelegramError as e:
            logger.error(f"❌ فشل في عرض أزرار الرجوع: {e}")

    # ✅ عرض قائمة الشكاوى
    elif action == "complain":
        try:
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚪 وصل الديليفري ولم يجد الزبون", callback_data=f"report_delivery_{order_id}")],
                    [InlineKeyboardButton("📞 رقم الهاتف غير صحيح", callback_data=f"report_phone_{order_id}")],
                    [InlineKeyboardButton("📍 معلومات الموقع غير دقيقة", callback_data=f"report_location_{order_id}")],
                    [InlineKeyboardButton("❓ مشكلة أخرى", callback_data=f"report_other_{order_id}")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data=f"back_{order_id}")]
                ])
            )
        except TelegramError as e:
            logger.error(f"❌ فشل في عرض أزرار الشكاوى: {e}")

    # ✅ تنفيذ الشكوى الفعلية
    elif report_type:
        reason_map = {
            "report_delivery": "🚪 وصل الديليفري ولم يجد الزبون",
            "report_phone": "📞 رقم الهاتف غير صحيح",
            "report_location": "📍 معلومات الموقع غير دقيقة",
            "report_other": "❓ شكوى أخرى من الكاشير"
        }

        reason_text = reason_map.get(report_type, "شكوى غير معروفة")

        try:
            await context.bot.send_message(
                chat_id=RESTAURANT_COMPLAINTS_CHAT_ID,
                text=(
                    f"📣 *شكوى من الكاشير على الطلب:*\n"
                    f"📌 معرف الطلب: `{order_id}`\n"
                    f"📍 السبب: {reason_text}\n\n"
                    f"📝 *تفاصيل الطلب:*\n\n{order_details}"
                ),
                parse_mode="Markdown"
            )

            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=(
                    f"🚫 تم إلغاء الطلب بسبب شكوى الكاشير.\n"
                    f"📌 معرف الطلب: `{order_id}`\n"
                    f"📍 السبب: {reason_text}"
                ),
                parse_mode="Markdown"
            )

            await context.bot.edit_message_reply_markup(
                chat_id=CASHIER_CHAT_ID,
                message_id=message_id,
                reply_markup=None
            )

            await context.bot.send_message(
                chat_id=CASHIER_CHAT_ID,
                text="📨 تم إرسال الشكوى وإلغاء الطلب. سيتواصل معكم فريق الدعم إذا لزم الأمر."
            )

            logger.info(f"✅ تم إرسال شكوى بنجاح وتم تنظيف الطلب: {order_id}")

        except TelegramError as e:
            logger.error(f"❌ خطأ أثناء إرسال الشكوى: {e}")
        finally:
            pending_orders.pop(order_id, None)  # 🧹 تنظيف الطلب






async def handle_time_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    # استخراج الوقت ومعرف الطلب
    _, time_selected, order_id = query.data.split("_")

    # تحديث الأزرار مع إضافة زر "🚗 جاهز ليطلع"
    keyboard = [
        [InlineKeyboardButton(f"✅ {t} دقيقة" if str(t) == time_selected else f"{t} دقيقة", callback_data=f"time_{t}_{order_id}")]
        for t in [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 75, 90]
    ]
    keyboard.append([InlineKeyboardButton("🚗 جاهز ليطلع", callback_data=f"ready_{order_id}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"back_{order_id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"⚠️ لم يتم تحديث الأزرار: {e}")

    # التحقق من الطلب داخل الذاكرة
    order_data = pending_orders.get(order_id)
    if not order_data:
        logger.warning(f"⚠️ الطلب غير موجود في pending_orders: {order_id}")
        return

    order_text = order_data["order_details"]

    # استخراج البيانات
    order_number_match = re.search(r"رقم الطلب[:\s]*([0-9]+)", order_text)
    order_number = int(order_number_match.group(1)) if order_number_match else 0

    total_price_match = re.search(r"المجموع الكلي[:\s]*([0-9,]+)", order_text)
    total_price = int(total_price_match.group(1).replace(",", "")) if total_price_match else 0

    restaurant_match = re.search(r"المطعم[:\s]*(.+)", order_text)
    restaurant = restaurant_match.group(1).strip() if restaurant_match else "غير معروف"

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ✅ تسجيل الطلب في قاعدة البيانات
    try:
        async with await aiosqlite.connect("restaurant_orders.db") as db:
            await db.execute("""
                INSERT INTO orders (order_id, order_number, restaurant, total_price, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (order_id, order_number, restaurant, total_price, timestamp))
            await db.commit()
            logger.info(f"✅ تم تسجيل الطلب في قاعدة البيانات: {order_id}")
    except Exception as e:
        logger.error(f"❌ فشل تسجيل الطلب في قاعدة البيانات: {e}")

    # ✅ إرسال إشعار للمستخدم في القناة
    try:
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=(
                f"🔥 *الطلب عالنار بالمطبخ!* 🍽️\n\n"
                f"📌 *معرف الطلب:* `{order_id}`\n"
                f"⏳ *مدة التحضير:* {time_selected} دقيقة"
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"❌ فشل في إرسال إشعار القبول إلى القناة: {e}")

    # ❌ لا نحذف الطلب من pending_orders الآن
    # نحتاجه لاحقًا عند إسناده لدليفري باستخدام زر "🚗 جاهز ليطلع"



# 🔔 إعادة إرسال التذكير كما هو
async def handle_channel_reminder(update: Update, context: CallbackContext):
    message = update.channel_post
    if not message or message.chat_id != CHANNEL_ID:
        return

    if "تذكير من الزبون" in message.text:
        logger.info(f"📥 استلم البوت تذكيرًا جديدًا: {message.text}")
        try:
            await context.bot.send_message(
                chat_id=CASHIER_CHAT_ID,
                text=f"🔔 *تذكير من الزبون!*\n\n{message.text}",
                parse_mode="Markdown"
            )
            logger.info("📩 تم إرسال التذكير إلى الكاشير بنجاح!")
        except Exception as e:
            logger.error(f"⚠️ خطأ أثناء إرسال التذكير إلى الكاشير: {e}")


# 🔔 إعادة إرسال التذكير بصيغة أخرى
async def handle_reminder_message(update: Update, context: CallbackContext):
    message = update.channel_post
    if not message or message.chat_id != CHANNEL_ID:
        return

    if "تذكير من الزبون" in message.text:
        logger.info("📌 تم استلام تذكير من الزبون، إعادة توجيهه للكاشير...")
        try:
            await context.bot.send_message(
                chat_id=CASHIER_CHAT_ID,
                text=message.text
            )
            logger.info("✅ تم إرسال التذكير إلى الكاشير بنجاح.")
        except Exception as e:
            logger.error(f"❌ خطأ أثناء إرسال التذكير للكاشير: {e}")


# ⏳ استفسار "كم يتبقى؟"
async def handle_time_left_question(update: Update, context: CallbackContext):
    message = update.channel_post
    if not message or message.chat_id != CHANNEL_ID:
        return

    if "كم يتبقى" in message.text and "الطلب رقم" in message.text:
        logger.info("📥 تم استلام استفسار عن المدة المتبقية للطلب...")
        try:
            await context.bot.send_message(
                chat_id=CASHIER_CHAT_ID,
                text=f"⏳ *استفسار من الزبون:*\n\n{message.text}",
                parse_mode="Markdown"
            )
            logger.info("✅ تم إرسال الاستفسار إلى الكاشير بنجاح.")
        except Exception as e:
            logger.error(f"❌ خطأ أثناء إرسال الاستفسار للكاشير: {e}")



# ⭐ استلام التقييم من الزبون
async def handle_rating_feedback(update: Update, context: CallbackContext):
    message = update.channel_post
    if not message or message.chat_id != CHANNEL_ID:
        return

    text = message.text or ""
    logger.info(f"📩 استلمنا إشعار تقييم من الزبون: {text}")

    match = re.search(r"رقم (\d+)", text)
    if not match:
        logger.warning("⚠️ لم يتم العثور على رقم الطلب في إشعار التقييم!")
        return

    order_number = match.group(1)

    for order_id, data in pending_orders.items():
        if f"رقم الطلب:* `{order_number}`" in data["order_details"]:
            message_id = data.get("message_id")
            if not message_id:
                logger.warning(f"⚠️ لا يوجد message_id محفوظ للطلب: {order_id}")
                return
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=CASHIER_CHAT_ID,
                    message_id=message_id,
                    reply_markup=None
                )
                logger.info(f"✅ تم إزالة الأزرار من رسالة الطلب رقم: {order_number}")
            except Exception as e:
                logger.error(f"❌ فشل في إزالة الأزرار: {e}")
            finally:
                pending_orders.pop(order_id, None)  # 🧹 تنظيف الطلب بعد التقييم
            break




# ✅ استلام التقييم من الزبون
async def handle_order_delivered_rating(update: Update, context: CallbackContext):
    message = update.channel_post
    if not message or message.chat_id != CHANNEL_ID:
        return

    text = message.text or ""
    logger.info(f"📩 محتوى رسالة القناة (لتقييم الطلب): {text}")

    if "استلم طلبه رقم" not in text or "معرف الطلب" not in text:
        logger.info("ℹ️ تم تجاهل رسالة التقييم، ليست كاملة.")
        return

    order_number_match = re.search(r"طلبه رقم\s*(\d+)", text)
    order_number = order_number_match.group(1) if order_number_match else None

    order_id_match = re.search(r"معرف الطلب:\s*(\w+)", text)
    order_id = order_id_match.group(1) if order_id_match else None

    if not order_number or not order_id:
        logger.warning("⚠️ لم يتم استخراج رقم الطلب أو معرف الطلب من رسالة التقييم.")
        return

    logger.info(f"🔍 تم استلام تقييم لطلب رقم: {order_number} - معرف الطلب: {order_id}")

    order_data = pending_orders.get(order_id)
    if not order_data:
        logger.warning(f"⚠️ لم يتم العثور على الطلب بمعرف: {order_id}")
        return

    message_id = order_data.get("message_id")
    if not message_id:
        logger.warning(f"⚠️ لا يوجد message_id محفوظ للطلب: {order_id}")
        return

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=CASHIER_CHAT_ID,
            message_id=message_id,
            reply_markup=None
        )
        logger.info(f"✅ تم إزالة أزرار الطلب رقم {order_number} (معرف: {order_id})")

        stars = extract_stars(text)

        await context.bot.send_message(
            chat_id=CASHIER_CHAT_ID,
            text=f"✅ الزبون استلم طلبه رقم {order_number} وقام بتقييمه بـ {stars}"
        )

    except Exception as e:
        logger.error(f"❌ خطأ أثناء إزالة الأزرار أو إرسال إشعار: {e}")
    finally:
        pending_orders.pop(order_id, None)


# ✅ استلام إلغاء الطلب من الزبون
async def handle_report_cancellation_notice(update: Update, context: CallbackContext):
    message = update.channel_post
    if not message or message.chat_id != CHANNEL_ID:
        return

    text = message.text or ""
    logger.info(f"📩 تم استلام إشعار إلغاء مع تقرير: {text}")

    order_number_match = re.search(r"إلغاء الطلب رقم[:\s]*(\d+)", text)
    order_number = order_number_match.group(1) if order_number_match else None

    order_id_match = re.search(r"معرف الطلب[:\s]*`?([\w\d]+)`?", text)
    order_id = order_id_match.group(1) if order_id_match else None

    if not order_number or not order_id:
        logger.warning("⚠️ لم يتم العثور على رقم الطلب أو معرف الطلب في رسالة الإلغاء.")
        return

    order_data = pending_orders.get(order_id)
    if not order_data:
        logger.warning(f"⚠️ الطلب غير موجود في pending_orders: {order_id}")
        return

    message_id = order_data.get("message_id")
    if not message_id:
        logger.warning(f"⚠️ لا يوجد message_id محفوظ للطلب: {order_id}")
        return

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=CASHIER_CHAT_ID,
            message_id=message_id,
            reply_markup=None
        )
        logger.info(f"✅ تم إزالة أزرار الطلب رقم {order_number} (معرف: {order_id})")

        await context.bot.send_message(
            chat_id=CASHIER_CHAT_ID,
            text=(
                f"🚫 تم إلغاء الطلب رقم {order_number} من قبل الزبون.\n"
                f"📌 معرف الطلب: `{order_id}`\n"
                f"📍 السبب: تأخر المطعم وتم إنشاء تقرير بالمشكلة وسنتواصل مع الزبون ومعكم لنفهم سبب الإلغاء.\n\n"
                f"📞 يمكنكم التواصل مع الزبون عبر رقم الهاتف المرفق في الطلب."
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"❌ خطأ أثناء معالجة إلغاء مع تقرير: {e}")
    finally:
        pending_orders.pop(order_id, None)


# ✅ استلام إلغاء الطلب من الزبون
async def handle_standard_cancellation_notice(update: Update, context: CallbackContext):
    message = update.channel_post
    if not message or message.chat_id != CHANNEL_ID:
        return

    text = message.text or ""
    logger.info(f"📩 تم استلام إشعار إلغاء عادي: {text}")

    order_number_match = re.search(r"إلغاء الطلب رقم[:\s]*(\d+)", text)
    order_number = order_number_match.group(1) if order_number_match else None

    order_id_match = re.search(r"معرف الطلب[:\s]*`?([\w\d]+)`?", text)
    order_id = order_id_match.group(1) if order_id_match else None

    if not order_number or not order_id:
        logger.warning("⚠️ لم يتم العثور على رقم الطلب أو معرف الطلب في رسالة الإلغاء.")
        return

    order_data = pending_orders.get(order_id)
    if not order_data:
        logger.warning(f"⚠️ الطلب غير موجود في pending_orders: {order_id}")
        return

    message_id = order_data.get("message_id")
    if not message_id:
        logger.warning(f"⚠️ لا يوجد message_id محفوظ للطلب: {order_id}")
        return

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=CASHIER_CHAT_ID,
            message_id=message_id,
            reply_markup=None
        )
        logger.info(f"✅ تم إزالة أزرار الطلب رقم {order_number} (معرف: {order_id})")

        await context.bot.send_message(
            chat_id=CASHIER_CHAT_ID,
            text=(
                f"🚫 تم إلغاء الطلب رقم {order_number} من قبل الزبون.\n"
                f"📌 معرف الطلب: `{order_id}`\n"
                f"📍 السبب: تردد الزبون وقرر الإلغاء."
            ),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"❌ خطأ أثناء معالجة الإلغاء العادي: {e}")
    finally:
        pending_orders.pop(order_id, None)


async def handle_delivery_menu(update: Update, context: CallbackContext):
    reply_keyboard = [["➕ إضافة دليفري", "❌ حذف دليفري"], ["🔙 رجوع"]]
    await update.message.reply_text(
        "📦 إدارة الدليفري:\nاختر الإجراء المطلوب:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    )
    context.user_data["delivery_action"] = "menu"

async def handle_add_delivery(update: Update, context: CallbackContext):
    text = update.message.text

    # 🔙 الرجوع من أي خطوة
    if text == "🔙 رجوع":
        context.user_data.pop("delivery_action", None)
        context.user_data.pop("new_delivery_name", None)
        reply_keyboard = [["➕ إضافة دليفري", "❌ حذف دليفري"], ["🔙 رجوع"]]
        await update.message.reply_text("⬅️ تم الرجوع إلى قائمة الدليفري.", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return

    action = context.user_data.get("delivery_action")

    # 🧑‍💼 المرحلة 1: استلام الاسم
    if action == "adding_name":
        context.user_data["new_delivery_name"] = text
        context.user_data["delivery_action"] = "adding_phone"
        await update.message.reply_text("📞 ما رقم الهاتف؟", reply_markup=ReplyKeyboardMarkup([["🔙 رجوع"]], resize_keyboard=True))

    # ☎️ المرحلة 2: استلام الرقم وحفظ البيانات
    elif action == "adding_phone":
        name = context.user_data.get("new_delivery_name")
        phone = text
        restaurant_name = context.user_data.get("restaurant")  # تأكد أنه مخزن مسبقًا

        try:
            async with await get_db_connection() as db:
                await db.execute(
                    "INSERT INTO delivery_persons (restaurant, name, phone) VALUES (?, ?, ?)",
                    (restaurant_name, name, phone)
                )
                await db.commit()

            # ✅ إنهاء العملية
            context.user_data.pop("delivery_action", None)
            context.user_data.pop("new_delivery_name", None)

            reply_keyboard = [["➕ إضافة دليفري", "❌ حذف دليفري"], ["🔙 رجوع"]]
            await update.message.reply_text(
                f"✅ تم إضافة الدليفري:\n🧑‍💼 {name}\n📞 {phone}",
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
            )

        except Exception as e:
            logger.error(f"❌ خطأ أثناء إضافة الدليفري: {e}")
            await update.message.reply_text("⚠️ حدث خطأ أثناء حفظ الدليفري. حاول مرة أخرى.")

async def ask_add_delivery_name(update: Update, context: CallbackContext):
    context.user_data["delivery_action"] = "adding_name"
    await update.message.reply_text("🧑‍💼 ما اسم الدليفري؟", reply_markup=ReplyKeyboardMarkup([["🔙 رجوع"]], resize_keyboard=True))

async def handle_delete_delivery_menu(update: Update, context: CallbackContext):
    restaurant_name = context.user_data.get("restaurant")

    try:
        async with await get_db_connection() as db:
            async with db.execute(
                "SELECT name FROM delivery_persons WHERE restaurant = ?", (restaurant_name,)
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            await update.message.reply_text("⚠️ لا يوجد أي دليفري مسجل حالياً.", reply_markup=ReplyKeyboardMarkup(
                [["➕ إضافة دليفري", "❌ حذف دليفري"], ["🔙 رجوع"]], resize_keyboard=True
            ))
            return

        names = [row[0] for row in rows]
        context.user_data["delivery_action"] = "deleting"
        await update.message.reply_text(
            "🗑 اختر اسم الدليفري الذي تريد حذفه:",
            reply_markup=ReplyKeyboardMarkup([[name] for name in names] + [["🔙 رجوع"]], resize_keyboard=True)
        )

    except Exception as e:
        logger.error(f"❌ خطأ أثناء جلب قائمة الدليفري للحذف: {e}")
        await update.message.reply_text("⚠️ حدث خطأ أثناء عرض القائمة.")


async def handle_delete_delivery_choice(update: Update, context: CallbackContext):
    text = update.message.text

    # الرجوع
    if text == "🔙 رجوع":
        context.user_data.pop("delivery_action", None)
        reply_keyboard = [["➕ إضافة دليفري", "❌ حذف دليفري"], ["🔙 رجوع"]]
        await update.message.reply_text("⬅️ تم الرجوع إلى قائمة الدليفري.", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
        return

    if context.user_data.get("delivery_action") != "deleting":
        return  # تجاهل

    restaurant_name = context.user_data.get("restaurant")

    try:
        async with await get_db_connection() as db:
            await db.execute(
                "DELETE FROM delivery_persons WHERE restaurant = ? AND name = ?",
                (restaurant_name, text)
            )
            await db.commit()

        context.user_data.pop("delivery_action", None)

        reply_keyboard = [["➕ إضافة دليفري", "❌ حذف دليفري"], ["🔙 رجوع"]]
        await update.message.reply_text(
            f"✅ تم حذف الدليفري: {text}",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
        )

    except Exception as e:
        logger.error(f"❌ خطأ أثناء حذف الدليفري: {e}")
        await update.message.reply_text("⚠️ حدث خطأ أثناء حذف الدليفري.")




async def handle_today_stats(update: Update, context: CallbackContext):
    today = datetime.datetime.now().strftime('%Y-%m-%d')

    try:
        async with aiosqlite.connect("restaurant_orders.db") as db:
            async with db.execute("""
                SELECT COUNT(*), SUM(total_price) 
                FROM orders 
                WHERE DATE(timestamp) = ?
            """, (today,)) as cursor:
                result = await cursor.fetchone()

        count = result[0] or 0
        total = result[1] or 0

        await update.message.reply_text(
            f"📊 *إحصائيات اليوم*\n\n"
            f"🔢 عدد الطلبات: *{count}*\n"
            f"💰 الدخل الكلي: *{total}* ل.س",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"❌ فشل استخراج إحصائيات اليوم: {e}")

async def handle_yesterday_stats(update: Update, context: CallbackContext):
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).date()

    try:
        async with aiosqlite.connect("restaurant_orders.db") as db:
            async with db.execute("""
                SELECT COUNT(*), SUM(total_price) 
                FROM orders 
                WHERE DATE(timestamp) = ?
            """, (yesterday.isoformat(),)) as cursor:
                result = await cursor.fetchone()

        count = result[0] or 0
        total = result[1] or 0

        await update.message.reply_text(
            f"📅 *إحصائيات يوم أمس:*\n\n"
            f"🔢 عدد الطلبات: {count}\n"
            f"💰 الدخل الكلي: {total} ل.س",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"❌ فشل استخراج إحصائيات أمس: {e}")


async def handle_current_month_stats(update: Update, context: CallbackContext):
    today = datetime.datetime.now()
    first_day = today.replace(day=1).date().isoformat()
    last_day = today.date().isoformat()

    try:
        async with aiosqlite.connect("restaurant_orders.db") as db:
            async with db.execute("""
                SELECT COUNT(*), SUM(total_price)
                FROM orders
                WHERE DATE(timestamp) BETWEEN ? AND ?
            """, (first_day, last_day)) as cursor:
                result = await cursor.fetchone()

        count = result[0] or 0
        total = result[1] or 0

        await update.message.reply_text(
            f"🗓️ *إحصائيات الشهر الحالي:*\n\n"
            f"🔢 عدد الطلبات: {count}\n"
            f"💰 الدخل الكلي: {total} ل.س",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"❌ خطأ أثناء استخراج إحصائيات الشهر الحالي: {e}")

async def handle_last_month_stats(update: Update, context: CallbackContext):
    today = datetime.datetime.now()
    first_day_this_month = today.replace(day=1)
    last_day_last_month = first_day_this_month - datetime.timedelta(days=1)
    first_day_last_month = last_day_last_month.replace(day=1)

    start_date = first_day_last_month.date().isoformat()
    end_date = last_day_last_month.date().isoformat()

    try:
        async with aiosqlite.connect("restaurant_orders.db") as db:
            async with db.execute("""
                SELECT COUNT(*), SUM(total_price)
                FROM orders
                WHERE DATE(timestamp) BETWEEN ? AND ?
            """, (start_date, end_date)) as cursor:
                result = await cursor.fetchone()

        count = result[0] or 0
        total = result[1] or 0

        await update.message.reply_text(
            f"📆 *إحصائيات الشهر الماضي:*\n\n"
            f"🔢 عدد الطلبات: {count}\n"
            f"💰 الدخل الكلي: {total} ل.س",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"❌ خطأ أثناء استخراج إحصائيات الشهر الماضي: {e}")

async def handle_current_year_stats(update: Update, context: CallbackContext):
    today = datetime.datetime.now()
    start_date = today.replace(month=1, day=1).date().isoformat()
    end_date = today.date().isoformat()

    try:
        async with aiosqlite.connect("restaurant_orders.db") as db:
            async with db.execute("""
                SELECT COUNT(*), SUM(total_price)
                FROM orders
                WHERE DATE(timestamp) BETWEEN ? AND ?
            """, (start_date, end_date)) as cursor:
                result = await cursor.fetchone()

        count = result[0] or 0
        total = result[1] or 0

        await update.message.reply_text(
            f"📈 *إحصائيات السنة الحالية:*\n\n"
            f"🔢 عدد الطلبات: {count}\n"
            f"💰 الدخل الكلي: {total} ل.س",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"❌ خطأ أثناء استخراج إحصائيات السنة الحالية: {e}")


async def handle_last_year_stats(update: Update, context: CallbackContext):
    today = datetime.datetime.now()
    last_year = today.year - 1
    start_date = f"{last_year}-01-01"
    end_date = f"{last_year}-12-31"

    try:
        async with aiosqlite.connect("restaurant_orders.db") as db:
            async with db.execute("""
                SELECT COUNT(*), SUM(total_price)
                FROM orders
                WHERE DATE(timestamp) BETWEEN ? AND ?
            """, (start_date, end_date)) as cursor:
                result = await cursor.fetchone()

        count = result[0] or 0
        total = result[1] or 0

        await update.message.reply_text(
            f"📉 *إحصائيات السنة الماضية ({last_year}):*\n\n"
            f"🔢 عدد الطلبات: {count}\n"
            f"💰 الدخل الكلي: {total} ل.س",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"❌ خطأ أثناء استخراج إحصائيات السنة الماضية: {e}")

async def handle_total_stats(update: Update, context: CallbackContext):
    try:
        async with aiosqlite.connect("restaurant_orders.db") as db:
            async with db.execute("SELECT COUNT(*), SUM(total_price) FROM orders") as cursor:
                result = await cursor.fetchone()

        count = result[0] or 0
        total = result[1] or 0

        await update.message.reply_text(
            f"📋 *إجمالي الإحصائيات:*\n\n"
            f"🔢 عدد كل الطلبات: {count}\n"
            f"💰 مجموع الدخل: {total} ل.س",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"❌ خطأ أثناء استخراج إجمالي الإحصائيات: {e}")


async def error_handler(update: object, context: CallbackContext) -> None:
    logger.error(msg="🚨 حدث استثناء أثناء معالجة التفاعل:", exc_info=context.error)

    traceback_str = ''.join(traceback.format_exception(None, context.error, context.error.__traceback__))
    print("⚠️ تفاصيل الخطأ:\n", traceback_str)

    try:
        if update and hasattr(update, 'callback_query') and update.callback_query.message:
            await update.callback_query.message.reply_text("❌ حدث خطأ غير متوقع أثناء تنفيذ العملية. سيتم التحقيق في الأمر.")
    except Exception as e:
        logger.error(f"❌ خطأ أثناء محاولة إرسال إشعار الخطأ: {e}")



# ✅ **إعداد البوت وتشغيله**
async def run_bot():
    # ✅ تحميل إعدادات المطعم من ملف JSON
    config = load_config()

    global TOKEN, CASHIER_CHAT_ID, CHANNEL_ID, RESTAURANT_COMPLAINTS_CHAT_ID
    TOKEN = config["token"]
    CASHIER_CHAT_ID = int(config["cashier_id"])
    CHANNEL_ID = int(config["channel_id"])
    RESTAURANT_COMPLAINTS_CHAT_ID = int(config.get("complaints_channel_id", CHANNEL_ID))  # fallback

    # ✅ بناء التطبيق بالتوكن المحمّل
    app = Application.builder().token(TOKEN).build()

    # ✅ إنشاء قاعدة البيانات
    await initialize_database()

    # ✅ أوامر البوت
    app.add_handler(CommandHandler("start", start))

    app.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.Regex(r"^✅ الزبون استلم طلبه رقم \d+ وقام بتقييمه بـ .+?\n📌 معرف الطلب: "), 
        handle_order_delivered_rating
    ))

    app.add_error_handler(error_handler)

    app.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Regex("تردد الزبون"), handle_standard_cancellation_notice))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Regex("تأخر المطعم.*تم إنشاء تقرير"), handle_report_cancellation_notice))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Regex(r"تذكير من الزبون"), handle_channel_reminder))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Regex(r"كم يتبقى.*الطلب رقم"), handle_time_left_question))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.LOCATION, handle_channel_location))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.TEXT, handle_channel_order))

    app.add_handler(CallbackQueryHandler(button, pattern=r"^(accept|reject|confirmreject|back|complain|report_(delivery|phone|location|other))_.+"))
    app.add_handler(CallbackQueryHandler(handle_time_selection, pattern=r"^time_\d+_.+"))

    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("🚚 الدليفري"), handle_delivery_menu))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("➕ إضافة دليفري"), ask_add_delivery_name))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_delivery))  
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("❌ حذف دليفري"), handle_delete_delivery_menu))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delete_delivery_choice))

    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("📊 عدد الطلبات اليوم والدخل"), handle_today_stats))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("📅 عدد الطلبات أمس والدخل"), handle_yesterday_stats))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("🗓️ طلبات الشهر الحالي"), handle_current_month_stats))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("📆 طلبات الشهر الماضي"), handle_last_month_stats))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("📈 طلبات السنة الحالية"), handle_current_year_stats))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("📉 طلبات السنة الماضية"), handle_last_year_stats))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("📋 إجمالي الطلبات والدخل"), handle_total_stats))

    # ✅ تشغيل البوت
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()

    import logging
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    logging.info("🚀 جارٍ بدء تشغيل بوت المطعم (النسخة المعدلة للبيئات ذات الـ loop النشط).")

    try:
        loop = asyncio.get_event_loop()
        logging.info("📌 جدولة دالة run_bot على الـ event loop الموجود.")
        task = loop.create_task(run_bot())

        def _log_task_exception_if_any(task_future):
            if task_future.done() and task_future.exception():
                logging.error("❌ مهمة run_bot انتهت بخطأ:", exc_info=task_future.exception())

        task.add_done_callback(_log_task_exception_if_any)

        loop.run_forever()  # ⬅️ هذه تبقي البوت نشطًا للأبد

    except KeyboardInterrupt:
        logging.info("🛑 تم إيقاف السكربت يدويًا (KeyboardInterrupt).")
    except Exception as e:
        logging.error(f"❌ حدث خطأ فادح في التنفيذ الرئيسي: {e}", exc_info=True)
