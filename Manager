from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.ext import MessageHandler, filters
import logging
import sqlite3
import json
from urllib.parse import quote
from telegram import InputMediaPhoto
from telegram.constants import ParseMode
import time
import re
import os
import secrets
import string
import sys
import pandas as pd
from datetime import datetime
from telegram import InputFile

# 🧱 أنشئ جداول المواقع
def setup_location_tables():
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  cursor.execute("""
      CREATE TABLE IF NOT EXISTS provinces (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT UNIQUE NOT NULL
      )
  """)
  cursor.execute("""
      CREATE TABLE IF NOT EXISTS cities (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          province_id INTEGER NOT NULL,
          ads_channel TEXT,
          FOREIGN KEY (province_id) REFERENCES provinces (id)
      )
  """)

  conn.commit()
  conn.close()

# 🧱 أنشئ جداول القائمة والمطاعم والوجبات
def setup_menu_tables():
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  # جدول المطاعم
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

  # الأرقام المحظورة
  cursor.execute("""
      CREATE TABLE IF NOT EXISTS blacklisted_numbers (
          phone TEXT PRIMARY KEY
      )
  """)

  # الفئات
  cursor.execute("""
      CREATE TABLE IF NOT EXISTS categories (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          restaurant_id INTEGER NOT NULL,
          UNIQUE(name, restaurant_id),
          FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
      )
  """)

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

  # ✅ تحقق من وجود الأعمدة الإضافية القديمة (احتياطي)
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

# ✅ تأكد من وجود عمود city_id إذا لم يكن مضافًا (يعمل احتياطيًا فقط إن أردت تشغيله يدويًا)
def add_city_id_to_restaurants():
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  cursor.execute("PRAGMA table_info(restaurants)")
  columns = [col[1] for col in cursor.fetchall()]

  if "city_id" not in columns:
      cursor.execute("ALTER TABLE restaurants ADD COLUMN city_id INTEGER")
      print("✅ تم إضافة city_id إلى جدول المطاعم.")
  else:
      print("✅ العمود city_id موجود مسبقًا.")

  conn.commit()
  conn.close()

# 🧱 إنشاء جدول الإعلانات
def create_ads_table():
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  cursor.execute("""
      CREATE TABLE IF NOT EXISTS ads (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          city TEXT NOT NULL,
          restaurant TEXT NOT NULL,
          ad_text TEXT NOT NULL,
          media_file_id TEXT NOT NULL,
          media_type TEXT NOT NULL,
          expire_timestamp INTEGER NOT NULL
      )
  """)

  conn.commit()
  conn.close()

# ✅ إضافة عمود unique_id إلى الوجبات
def add_unique_id_column():
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  cursor.execute("PRAGMA table_info(meals)")
  meal_columns = [col[1] for col in cursor.fetchall()]
  if "unique_id" not in meal_columns:
      cursor.execute("ALTER TABLE meals ADD COLUMN unique_id TEXT")
      print("✅ تم إضافة العمود unique_id إلى جدول meals.")
  else:
      print("✅ العمود unique_id موجود بالفعل.")

  conn.commit()
  conn.close()



def generate_unique_id(length=50):
  alphabet = string.ascii_letters + string.digits
  return ''.join(secrets.choice(alphabet) for _ in range(length))

def ensure_is_frozen_column():
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("PRAGMA table_info(restaurants)")
  columns = [col[1] for col in cursor.fetchall()]
  if "is_frozen" not in columns:
      cursor.execute("ALTER TABLE restaurants ADD COLUMN is_frozen INTEGER DEFAULT 0")
      print("✅ تم إضافة عمود is_frozen إلى جدول المطاعم.")
  else:
      print("✅ العمود is_frozen موجود مسبقًا.")
  conn.commit()
  conn.close()


def drop_old_city_column():
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  # ✅ تأكد من أن العمود city موجود أصلًا
  cursor.execute("PRAGMA table_info(restaurants)")
  columns = [col[1] for col in cursor.fetchall()]
  if "city" not in columns:
      print("✅ العمود city محذوف مسبقًا.")
      conn.close()
      return

  # 🗃️ جلب البيانات القديمة
  cursor.execute("SELECT id, name, city, channel, open_hour, close_hour FROM restaurants")
  old_restaurants = cursor.fetchall()

  # ✅ جلب خريطة الأسماء إلى city_id
  cursor.execute("SELECT id, name FROM cities")
  city_map = {name: id_ for id_, name in cursor.fetchall()}

  # 🏗️ إنشاء جدول جديد بدون عمود city
  cursor.execute("""
      CREATE TABLE IF NOT EXISTS restaurants_new (
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

  skipped = 0
  for r in old_restaurants:
      old_id, name, old_city_name, channel, open_hour, close_hour = r
      city_id = city_map.get(old_city_name)

      if not city_id:
          print(f"⚠️ لم يتم العثور على city_id للمدينة '{old_city_name}' - تجاهل المطعم '{name}'")
          skipped += 1
          continue

      cursor.execute("""
          INSERT OR IGNORE INTO restaurants_new (id, name, city_id, channel, open_hour, close_hour)
          VALUES (?, ?, ?, ?, ?, ?)
      """, (old_id, name, city_id, channel, open_hour, close_hour))

  # 📦 حذف الجدول القديم وإعادة تسميه الجديد
  cursor.execute("DROP TABLE restaurants")
  cursor.execute("ALTER TABLE restaurants_new RENAME TO restaurants")

  conn.commit()
  conn.close()

  print(f"✅ تم حذف العمود city نهائيًا من جدول restaurants.")
  if skipped:
      print(f"⚠️ عدد المطاعم التي تم تجاهلها بسبب غياب المدينة: {skipped}")



def verify_city_column_removed():
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("PRAGMA table_info(restaurants)")
  columns = [col[1] for col in cursor.fetchall()]
  conn.close()

  if "city" in columns:
      print("❌ العمود city لا يزال موجودًا في جدول restaurants.")
  else:
      print("✅ تأكيد: العمود city غير موجود في جدول restaurants.")

verify_city_column_removed()

import sqlite3

def sync_city_ids_in_restaurants():
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  # 1. التحقق من وجود العمود city في جدول restaurants
  cursor.execute("PRAGMA table_info(restaurants)")
  columns = [row[1] for row in cursor.fetchall()]

  if "city_id" not in columns:
      print("❌ العمود city_id غير موجود في جدول restaurants.")
      conn.close()
      return

  if "city" not in columns:
      print("⚠️ العمود city غير موجود. لا حاجة للمزامنة.")
      conn.close()
      return

  # 2. بناء خريطة من أسماء المدن إلى معرفاتها
  cursor.execute("SELECT id, name FROM cities")
  city_map = {name: id_ for id_, name in cursor.fetchall()}

  # 3. جلب جميع المطاعم التي تحتوي على عمود city
  cursor.execute("SELECT id, city FROM restaurants")
  updated = 0
  for r_id, city_name in cursor.fetchall():
      city_id = city_map.get(city_name)
      if city_id:
          cursor.execute("UPDATE restaurants SET city_id = ? WHERE id = ?", (city_id, r_id))
          updated += 1
      else:
          print(f"⚠️ لم يتم العثور على معرف لمدينة: {city_name}")

  conn.commit()
  conn.close()

  print(f"✅ تم تحديث {updated} مطعم/مطاعم بقيم city_id الصحيحة.")




# 🧪 سكربت لفحص بنية جدول الوجبات
def debug_check_meals_table_structure():
  print("🧪 فحص بنية جدول الوجبات:")
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("PRAGMA table_info(meals)")
  columns = cursor.fetchall()
  if not columns:
      print("❌ جدول meals غير موجود.")
  else:
      for col in columns:
          print(f"- الاسم: {col[1]:<15} | النوع: {col[2]:<10} | NOT NULL: {col[3]}")
  conn.close()



def debug_check_categories_and_restaurants():
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  print("📊 جميع الفئات المرتبطة بكل مطعم:")
  cursor.execute("""
      SELECT c.id, c.name, r.name, r.id
      FROM categories c
      JOIN restaurants r ON c.restaurant_id = r.id
  """)
  rows = cursor.fetchall()
  for row in rows:
      print(f"🧾 الفئة: {row[1]} - المطعم: {row[2]} (category_id: {row[0]}, restaurant_id: {row[3]})")

  conn.close()

def print_all_meal_names():
  import sqlite3

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  cursor.execute("SELECT name FROM meals")
  rows = cursor.fetchall()

  if not rows:
      print("📭 لا توجد وجبات محفوظة في قاعدة البيانات.")
  else:
      print("📋 أسماء جميع الوجبات المحفوظة:")
      for name, in rows:
          print(f"🍽️ {name}")

  conn.close()

def check_sizes_format():
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  cursor.execute("SELECT id, name, size_options FROM meals WHERE size_options IS NOT NULL")
  meals = cursor.fetchall()

  total_meals = 0
  correct_meals = 0
  wrong_meals = 0

  for meal_id, meal_name, size_options_json in meals:
      try:
          sizes = json.loads(size_options_json)
          if not isinstance(sizes, list):
              print(f"❌ {meal_name} (ID {meal_id}) - القياسات ليست قائمة List!")
              wrong_meals += 1
              continue

          if all(isinstance(s, dict) and "name" in s and "price" in s for s in sizes):
              correct_meals += 1
          else:
              print(f"❌ {meal_name} (ID {meal_id}) - يوجد قياسات غير صحيحة.")
              wrong_meals += 1

      except Exception as e:
          print(f"❌ خطأ عند قراءة {meal_name} (ID {meal_id}): {e}")
          wrong_meals += 1

      total_meals += 1

  conn.close()

  print("\n📋 تقرير فحص القياسات:")
  print(f"✅ عدد الوجبات المفحوصة: {total_meals}")
  print(f"✅ عدد الوجبات الصحيحة: {correct_meals}")
  print(f"⚠️ عدد الوجبات الخاطئة: {wrong_meals}")
  print("✅ تم تنفيذ فحص قياسات جميع الوجبات.\n")


def normalize_size_options():
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  cursor.execute("SELECT id, size_options FROM meals WHERE size_options IS NOT NULL")
  meals = cursor.fetchall()

  updated_count = 0

  for meal_id, size_options_json in meals:
      try:
          sizes = json.loads(size_options_json)
          if all(isinstance(s, dict) for s in sizes):
              continue  # الصيغة أصلاً حديثة

          normalized = []
          for item in sizes:
              if isinstance(item, str) and "/" in item:
                  name, price = item.split("/")
                  normalized.append({"name": name.strip(), "price": int(price.strip())})
              elif isinstance(item, dict):
                  normalized.append(item)

          cursor.execute("UPDATE meals SET size_options = ? WHERE id = ?", (
              json.dumps(normalized, ensure_ascii=False), meal_id
          ))
          updated_count += 1

      except Exception as e:
          print(f"❌ خطأ في معالجة الوجبة ID={meal_id}: {e}")

  conn.commit()
  conn.close()
  print(f"✅ تم تحديث {updated_count} وجبة إلى الصيغة الجديدة.")

def add_ads_channel_column_to_cities():
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  # فحص هل العمود موجود
  cursor.execute("PRAGMA table_info(cities)")
  columns = [col[1] for col in cursor.fetchall()]

  if "ads_channel" not in columns:
      cursor.execute("ALTER TABLE cities ADD COLUMN ads_channel TEXT")
      print("✅ تم إضافة عمود ads_channel إلى جدول المدن.")
  else:
      print("✅ العمود ads_channel موجود بالفعل.")

  conn.commit()
  conn.close()

def update_restaurants_city_id():
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  cursor.execute("SELECT id, name FROM cities")
  cities = cursor.fetchall()
  city_map = {name: cid for cid, name in cities}

  updated = 0
  for city_name, city_id in city_map.items():
      cursor.execute("""
          UPDATE restaurants SET city_id = ?
          WHERE city = ?
      """, (city_id, city_name))
      updated += cursor.rowcount

  conn.commit()
  conn.close()

  print(f"✅ تم تحديث {updated} مطعمًا بـ city_id.")



# 🔐 توكن بوت الإدارة (غيّره بتوكنك الفعلي)
ADMIN_BOT_TOKEN = "8035243318:AAGiaP7K8ErWJar1xuxrnqPA8KD9QQwKT0c"

VIP_MEDIA_CHANNEL_ID = -1001234567890  # ← استبدله بمعرف القناة الحقيقي

# 🔧 إعدادات السجل (اختياري لتتبع الأخطاء)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  # ✅ منع تنفيذ /start إذا كان هناك تعديل حساس جارٍ (مثل تعديل السعر أو القياسات)
  if context.user_data.get("edit_price_step") or context.user_data.get("meal_action"):
      await update.effective_message.reply_text(
          "⚠️ لا يمكنك استخدام /start أثناء تعديل وجبة.\n"
          "يرجى إنهاء العملية الحالية أو إرسال أي نص للخروج منها."
      )
      return

  keyboard = [
      [InlineKeyboardButton("🏙️ إدارة المحافظات", callback_data="go_manage_provinces")],
      [InlineKeyboardButton("🌆 إدارة المدن", callback_data="go_manage_cities")],
      [InlineKeyboardButton("🍽️ إدارة المطاعم", callback_data="go_manage_restaurants")],
      [InlineKeyboardButton("📂 إدارة الفئات", callback_data="go_manage_categories")],
      [InlineKeyboardButton("🍔 إدارة الوجبات", callback_data="go_manage_meals")],
      [InlineKeyboardButton("📵 الأرقام المحظورة", callback_data="go_blacklist_menu")],
      [InlineKeyboardButton("📊 عرض الإحصائيات", callback_data="show_statistics")],
      [InlineKeyboardButton("🔍 بحث عن مستخدم", callback_data="search_user")],
      [InlineKeyboardButton("🧾 تصدير البيانات", callback_data="export_data")]
  ]

  # ✅ دعم كلا الحالتين: رسالة أو زر
  if update.message:
      await update.message.reply_text(
          "👋 أهلاً بك في *بوت الإدارة*\nاختر من القائمة التالية:",
          reply_markup=InlineKeyboardMarkup(keyboard),
          parse_mode="Markdown"
      )
  elif update.callback_query:
      await update.callback_query.message.reply_text(
          "👋 أهلاً بك في *بوت الإدارة*\nاختر من القائمة التالية:",
          reply_markup=InlineKeyboardMarkup(keyboard),
          parse_mode="Markdown"
      )


async def handle_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  await start(update, context)


# دالة عرض أزرار إدارة المحافظات
async def manage_provinces(update: Update, context: ContextTypes.DEFAULT_TYPE):
  keyboard = [
      [InlineKeyboardButton("➕ إضافة محافظة", callback_data="add_province")],
      [InlineKeyboardButton("➖ حذف محافظة", callback_data="delete_province")],
      [InlineKeyboardButton("✏️ تعديل اسم محافظة", callback_data="edit_province_name")],
      [InlineKeyboardButton("↩️ العودة للقائمة الرئيسية", callback_data="go_main_menu")]
  ]

  if update.message:
      await update.message.reply_text(
          "🗂️ إدارة المحافظات:\nاختر أحد الخيارات التالية:",
          reply_markup=InlineKeyboardMarkup(keyboard)
      )
  else:
      await update.callback_query.message.reply_text(
          "🗂️ إدارة المحافظات:\nاختر أحد الخيارات التالية:",
          reply_markup=InlineKeyboardMarkup(keyboard)
      )







async def handle_province_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  action = query.data

  if action == "add_province":
      await query.edit_message_text("✏️ يرجى إرسال اسم المحافظة التي تريد إضافتها.")
      context.user_data["province_action"] = "add"

  elif action == "delete_province":
      await query.edit_message_text("🗑️ يرجى إرسال اسم المحافظة التي تريد حذفها.")
      context.user_data["province_action"] = "delete"

  elif action == "edit_province_name":
      # عرض المحافظات كخيارات لاختيار القديمة منها
      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("SELECT name FROM provinces ORDER BY name")
      provinces = [row[0] for row in cursor.fetchall()]
      conn.close()

      if not provinces:
          await query.edit_message_text("❌ لا توجد محافظات مسجلة.")
          return

      keyboard = [
          [InlineKeyboardButton(province, callback_data=f"rename_province_old_{province}")]
          for province in provinces
      ]
      keyboard.append([InlineKeyboardButton("↩️ العودة", callback_data="go_manage_provinces")])

      await query.edit_message_text("✏️ اختر المحافظة التي تريد تعديل اسمها:", reply_markup=InlineKeyboardMarkup(keyboard))







async def handle_province_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
  province_name = update.message.text.strip()
  action = context.user_data.get("province_action")

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  if action == "add":
      try:
          cursor.execute("INSERT INTO provinces (name) VALUES (?)", (province_name,))
          conn.commit()
          await update.message.reply_text(f"✅ تم إضافة المحافظة: {province_name}")
      except sqlite3.IntegrityError:
          await update.message.reply_text("⚠️ هذه المحافظة موجودة بالفعل.")

  elif action == "delete":
      # جلب معرف المحافظة
      cursor.execute("SELECT id FROM provinces WHERE name = ?", (province_name,))
      result = cursor.fetchone()

      if not result:
          await update.message.reply_text("⚠️ لم يتم العثور على المحافظة.")
          conn.close()
          return

      province_id = result[0]

      # جلب معرفات المدن المرتبطة بالمحافظة
      cursor.execute("SELECT id FROM cities WHERE province_id = ?", (province_id,))
      city_ids = [row[0] for row in cursor.fetchall()]

      for city_id in city_ids:
          # جلب معرفات المطاعم المرتبطة بكل مدينة
          cursor.execute("SELECT id FROM restaurants WHERE city_id = ?", (city_id,))
          restaurant_ids = [row[0] for row in cursor.fetchall()]

          for rest_id in restaurant_ids:
              # حذف الوجبات والفئات والمطعم
              cursor.execute("DELETE FROM meals WHERE category_id IN (SELECT id FROM categories WHERE restaurant_id = ?)", (rest_id,))
              cursor.execute("DELETE FROM categories WHERE restaurant_id = ?", (rest_id,))
              cursor.execute("DELETE FROM restaurants WHERE id = ?", (rest_id,))

      # حذف المدن والمحافظة
      cursor.execute("DELETE FROM cities WHERE province_id = ?", (province_id,))
      cursor.execute("DELETE FROM provinces WHERE id = ?", (province_id,))

      # حذف المستخدمين في هذه المحافظة
      cursor.execute("SELECT user_id FROM user_data WHERE province = ?", (province_name,))
      users = [row[0] for row in cursor.fetchall()]

      for user_id in users:
          cursor.execute("DELETE FROM user_data WHERE user_id = ?", (user_id,))
          try:
              await context.bot.send_message(
                  chat_id=user_id,
                  text="❌ انتهت خدمتنا في محافظتك مؤقتًا.\nسنحاول العودة قريبًا بإذن الله.\nسنبدأ من جديد الآن..."
              )
              await start(update=update, context=context)
          except:
              pass

      conn.commit()
      await update.message.reply_text(f"🗑️ تم حذف المحافظة '{province_name}' وكل ما يتعلق بها.")

  elif action == "rename_old":
      context.user_data["old_province_name"] = province_name
      context.user_data["province_action"] = "rename_new"
      await update.message.reply_text("✏️ أرسل الاسم الجديد للمحافظة:")

  elif action == "rename_new":
      old_name = context.user_data.get("old_province_name")
      new_name = province_name
      try:
          cursor.execute("UPDATE provinces SET name = ? WHERE name = ?", (new_name, old_name))
          cursor.execute("UPDATE user_data SET province = ? WHERE province = ?", (new_name, old_name))
          conn.commit()
          await update.message.reply_text(f"✅ تم تعديل اسم المحافظة من '{old_name}' إلى '{new_name}'.")
      except sqlite3.IntegrityError:
          await update.message.reply_text("⚠️ توجد محافظة بهذا الاسم مسبقًا.")
      context.user_data.pop("old_province_name", None)

  conn.close()
  context.user_data.pop("province_action", None)
  await start(update, context)



async def handle_rename_province_old(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  old_name = query.data.replace("rename_province_old_", "")
  context.user_data["old_province_name"] = old_name
  context.user_data["province_action"] = "rename_new"

  await query.edit_message_text(f"✏️ أرسل الاسم الجديد للمحافظة '{old_name}':")




async def manage_cities(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT name FROM provinces ORDER BY name")
  provinces = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not provinces:
      await query.edit_message_text("❌ لا توجد محافظات مسجلة.")
      return

  # إنشاء أزرار المحافظات + زر العودة
  keyboard = [
      [InlineKeyboardButton(province, callback_data=f"select_province_for_city_{province}")]
      for province in provinces
  ]
  keyboard.append([InlineKeyboardButton("↩️ العودة للقائمة الرئيسية", callback_data="go_main_menu")])

  await query.edit_message_text(
      "🌍 اختر المحافظة التي تريد إدارة المدن فيها:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )




async def handle_province_for_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  # حفظ اسم المحافظة
  province = query.data.replace("select_province_for_city_", "")
  context.user_data["selected_province"] = province

  keyboard = [
      [InlineKeyboardButton("➕ إضافة مدينة", callback_data="add_city")],
      [InlineKeyboardButton("➖ حذف مدينة", callback_data="delete_city")],
      [InlineKeyboardButton("✏️ تعديل اسم مدينة", callback_data="edit_city_name")],
      [InlineKeyboardButton("✏️ تعديل قناة الإعلانات", callback_data="edit_ads_channel")],
      [InlineKeyboardButton("📢 إرسال إعلان لقناة مدينة", callback_data="send_city_ad")],
      [InlineKeyboardButton("↩️ العودة للقائمة الرئيسية", callback_data="go_main_menu")]
  ]

  await query.edit_message_text(
      f"📍 إدارة المدن ضمن المحافظة: {province}",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )



async def handle_city_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  action = query.data
  print("🟡 city_action =", action)

  if action == "add_city":
      context.user_data["city_action"] = "add_city"
      await query.edit_message_text("✏️ أرسل اسم المدينة التي تريد إضافتها:")

  elif action == "delete_city":
      context.user_data["city_action"] = "delete_city"
      await query.edit_message_text("🗑️ أرسل اسم المدينة التي تريد حذفها:")

  elif action == "edit_city_name":
      # تعديل اسم مدينة
      province = context.user_data.get("selected_province")
      if not province:
          await query.edit_message_text("⚠️ لم يتم تحديد المحافظة.")
          return

      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("""
          SELECT c.name FROM cities c
          JOIN provinces p ON c.province_id = p.id
          WHERE p.name = ?
      """, (province,))
      cities = [row[0] for row in cursor.fetchall()]
      conn.close()

      if not cities:
          await query.edit_message_text("❌ لا توجد مدن مسجلة في هذه المحافظة.")
          return

      keyboard = [
          [InlineKeyboardButton(city, callback_data=f"rename_city_old_{city}")]
          for city in cities
      ]
      keyboard.append([InlineKeyboardButton("↩️ العودة", callback_data="go_main_menu")])

      await query.edit_message_text(
          "✏️ اختر المدينة التي تريد تعديل اسمها:",
          reply_markup=InlineKeyboardMarkup(keyboard)
      )

  elif action == "edit_ads_channel":
      # تعديل معرف قناة الإعلانات
      province = context.user_data.get("selected_province")
      if not province:
          await query.edit_message_text("⚠️ لم يتم تحديد المحافظة.")
          return

      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("""
          SELECT c.name FROM cities c
          JOIN provinces p ON c.province_id = p.id
          WHERE p.name = ?
      """, (province,))
      cities = [row[0] for row in cursor.fetchall()]
      conn.close()

      if not cities:
          await query.edit_message_text("❌ لا توجد مدن مسجلة في هذه المحافظة.")
          return

      keyboard = [
          [InlineKeyboardButton(city, callback_data=f"edit_ads_channel_for_city_{city}")]
          for city in cities
      ]
      keyboard.append([InlineKeyboardButton("↩️ العودة", callback_data="go_main_menu")])

      await query.edit_message_text(
          "📢 اختر المدينة لتعديل قناة الإعلانات الخاصة بها:",
          reply_markup=InlineKeyboardMarkup(keyboard)
      )



async def handle_rename_city_old(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  old_city = query.data.replace("rename_city_old_", "")
  context.user_data["old_city_name"] = old_city
  context.user_data["city_action"] = "rename_city_new"

  await query.edit_message_text(f"✏️ أرسل الاسم الجديد للمدينة '{old_city}':")





async def handle_city_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
  province = context.user_data.get("selected_province")
  action = context.user_data.get("city_action")
  text = update.message.text.strip()

  if not province:
      await update.message.reply_text("⚠️ لم يتم تحديد المحافظة. يرجى العودة واختيار المحافظة أولًا.")
      return

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  cursor.execute("SELECT id FROM provinces WHERE name = ?", (province,))
  result = cursor.fetchone()
  if not result:
      await update.message.reply_text("⚠️ لم يتم العثور على المحافظة.")
      conn.close()
      return

  province_id = result[0]

  # 🟡 إضافة مدينة جديدة (اسم المدينة)
  if action == "add_city" and "new_city_name" not in context.user_data:
      context.user_data["new_city_name"] = text
      await update.message.reply_text("✏️ أرسل معرف قناة الإعلانات الخاصة بالمدينة (ابدأ بـ @) أو اكتب 'لا يوجد'.")
      return

  # 🟡 إضافة مدينة جديدة (استقبال المعرف)
  elif action == "add_city" and "new_city_name" in context.user_data:
      city_name = context.user_data["new_city_name"]
      ads_channel = text.strip()

      if ads_channel.lower() == "لا يوجد":
          ads_channel = None
      elif not ads_channel.startswith("@"):
          await update.message.reply_text("⚠️ يجب أن يبدأ معرف القناة بـ @ أو اكتب 'لا يوجد'.")
          return

      try:
          cursor.execute(
              "INSERT INTO cities (name, province_id, ads_channel) VALUES (?, ?, ?)",
              (city_name, province_id, ads_channel)
          )
          conn.commit()
          await update.message.reply_text(f"✅ تم إضافة المدينة '{city_name}' بنجاح.")
      except sqlite3.IntegrityError:
          await update.message.reply_text("⚠️ هذه المدينة موجودة بالفعل.")

      context.user_data.pop("new_city_name", None)
      context.user_data.pop("city_action", None)
      conn.close()
      return await start(update, context)

  # 🟡 حذف مدينة
  elif action == "delete_city":
      try:
          cursor.execute("DELETE FROM cities WHERE name = ? AND province_id = ?", (text, province_id))
          conn.commit()
          await update.message.reply_text(f"🗑️ تم حذف المدينة '{text}' بنجاح.")
      except Exception as e:
          await update.message.reply_text("❌ حدث خطأ أثناء حذف المدينة.")
          print(e)

  # 🟡 بدء تعديل اسم مدينة (استقبال الاسم القديم)
  elif action == "rename_city_old":
      context.user_data["old_city_name"] = text
      context.user_data["city_action"] = "rename_city_new"
      await update.message.reply_text("✏️ أرسل الاسم الجديد للمدينة:")
      return

  # 🟡 إنهاء تعديل اسم مدينة (استقبال الاسم الجديد)
  elif action == "rename_city_new":
      old_name = context.user_data.get("old_city_name")
      new_name = text

      try:
          cursor.execute("UPDATE cities SET name = ? WHERE name = ? AND province_id = ?", (new_name, old_name, province_id))
          cursor.execute("UPDATE user_data SET city = ? WHERE city = ?", (new_name, old_name))
          cursor.execute("UPDATE restaurants SET city = ? WHERE city = ?", (new_name, old_name))
          conn.commit()
          await update.message.reply_text(f"✅ تم تعديل اسم المدينة من '{old_name}' إلى '{new_name}'.")
      except sqlite3.IntegrityError:
          await update.message.reply_text("⚠️ هناك مدينة بهذا الاسم موجودة مسبقًا.")

      context.user_data.pop("old_city_name", None)

  conn.close()
  context.user_data.pop("city_action", None)
  context.user_data.pop("selected_province", None)
  await start(update, context)



async def handle_select_city_for_ads_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  city_name = query.data.replace("edit_ads_channel_city_", "")
  context.user_data["city_action"] = "edit_ads_channel"
  context.user_data["city_to_edit_ads_channel"] = city_name  # ✅ تعديل هنا

  await query.edit_message_text(
      f"✏️ أرسل معرف القناة الخاص بمدينة: {city_name}\n\n"
      f"➖ ملاحظة: اكتب 'لا يوجد' لحذف المعرف الحالي."
  )


async def handle_edit_ads_channel_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
  new_channel = update.message.text.strip()
  city = context.user_data.get("city_to_edit_ads_channel")

  if not city:
      await update.message.reply_text("❌ لم يتم تحديد المدينة.")
      return

  if new_channel.lower() == "لا يوجد":
      new_channel = None
  elif not new_channel.startswith("@"):
      await update.message.reply_text("⚠️ يجب أن يبدأ معرف القناة بـ @ أو اكتب 'لا يوجد'.")
      return

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("UPDATE cities SET ads_channel = ? WHERE name = ?", (new_channel, city))
  conn.commit()
  conn.close()

  await update.message.reply_text(f"✅ تم تعديل قناة الإعلانات لمدينة '{city}' بنجاح.")
  context.user_data.pop("city_action", None)
  context.user_data.pop("city_to_edit_ads_channel", None)
  return await start(update, context)


async def handle_send_city_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, name FROM cities ORDER BY name")
  cities = cursor.fetchall()
  conn.close()

  if not cities:
      await query.edit_message_text("❌ لا توجد مدن مسجلة.")
      return

  # نضيف خيار إلى كل المدن أعلى القائمة
  keyboard = [[InlineKeyboardButton("📢 إلى كل المدن", callback_data="ad_city_all")]]

  keyboard += [
      [InlineKeyboardButton(city_name, callback_data=f"ad_city_{city_id}")]
      for city_id, city_name in cities
  ]
  keyboard.append([InlineKeyboardButton("↩️ العودة", callback_data="go_main_menu")])

  await query.edit_message_text(
      "🌆 اختر المدينة التي تريد إرسال الإعلان إليها:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )


async def handle_ad_all_cities_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  # حفظ إشارة أن الإعلان موجه لكل المدن
  context.user_data["ad_city"] = "كل المدن"
  context.user_data["ad_all_cities"] = True  # <-- علامة تمييز
  context.user_data["ad_step"] = "awaiting_ad_restaurant_for_all"

  # اختيار المطعم الذي سيكون باسم الإعلان
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, name FROM restaurants ORDER BY name")
  restaurants = cursor.fetchall()
  conn.close()

  if not restaurants:
      await query.edit_message_text("❌ لا توجد مطاعم مسجلة.")
      return

  keyboard = [
      [InlineKeyboardButton(name, callback_data=f"ad_restaurant_{rid}")]
      for rid, name in restaurants
  ]
  await query.edit_message_text(
      "🏪 اختر المطعم الذي تريد نشر الإعلان باسمه في جميع المدن:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )


async def handle_ad_city_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  city_id_raw = query.data.replace("ad_city_", "")

  if city_id_raw == "all":
      context.user_data["ad_city"] = "all"
      context.user_data["ad_city_id"] = "all"
      restaurants = []
      city_name = "كل المدن"
  else:
      city_id = int(city_id_raw)
      context.user_data["ad_city_id"] = city_id

      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("SELECT name FROM cities WHERE id = ?", (city_id,))
      row = cursor.fetchone()
      if not row:
          await query.edit_message_text("❌ لم يتم العثور على المدينة.")
          conn.close()
          return

      city_name = row[0]
      context.user_data["ad_city"] = city_name

      cursor.execute("SELECT id, name FROM restaurants WHERE city_id = ?", (city_id,))
      restaurants = cursor.fetchall()
      conn.close()

      if not restaurants:
          await query.edit_message_text("❌ لا توجد مطاعم في هذه المدينة.")
          return

  keyboard = [[InlineKeyboardButton("⏭️ تخطي اختيار المطعم (نص حر)", callback_data="skip_ad_restaurant")]]

  for rid, name in restaurants:
      keyboard.append([InlineKeyboardButton(name, callback_data=f"ad_restaurant_{rid}")])

  text = f"🏪 اختر المطعم الذي تريد الإعلان باسمه في مدينة {city_name}:"
  if city_id_raw == "all":
      text = "🏪 اختر المطعم الذي تريد الإعلان باسمه في جميع المدن:\n(أو اختر تخطي لإرسال إعلان حر بدون اسم مطعم)"

  await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_skip_ad_restaurant(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  context.user_data["ad_restaurant"] = None
  context.user_data["ad_skip_restaurant"] = True
  context.user_data["ad_step"] = "awaiting_ad_text"

  await query.edit_message_text("📝 أرسل الآن نص الإعلان (سيُنشر كنص حر بدون اسم مطعم):")


async def handle_ad_restaurant_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  restaurant_id = int(query.data.replace("ad_restaurant_", ""))
  context.user_data["ad_restaurant_id"] = restaurant_id

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT name FROM restaurants WHERE id = ?", (restaurant_id,))
  row = cursor.fetchone()
  conn.close()

  if not row:
      await query.edit_message_text("❌ لم يتم العثور على المطعم.")
      return

  context.user_data["ad_restaurant"] = row[0]
  context.user_data.pop("ad_skip_restaurant", None)  # ✅ إزالة التخطي إذا اختار مطعمًا
  context.user_data["ad_step"] = "awaiting_ad_text"

  await query.edit_message_text("📝 أرسل نص الإعلان الذي تريد نشره:")

async def handle_ad_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
  ad_text = update.message.text.strip()
  context.user_data["ad_text"] = ad_text
  context.user_data["ad_step"] = "awaiting_ad_duration"

  await update.message.reply_text(
      "⏱️ كم المدة التي يستمر فيها هذا الإعلان؟\n"
      "📝 يمكنك كتابة أي مدة مثل: 'يومان' أو 'حتى نهاية الأسبوع' أو 'شهر كامل'.\n"
      "أو يمكنك الضغط على 'تخطي ⏭️' إذا لم تكن هناك مدة محددة.",
      reply_markup=ReplyKeyboardMarkup([["تخطي ⏭️"]], resize_keyboard=True)
  )

async def handle_ad_duration_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
  duration = update.message.text.strip()

  # إذا ضغط "تخطي"، لا نسجل مدة
  if duration != "تخطي ⏭️":
      context.user_data["ad_duration"] = duration
  else:
      context.user_data["ad_duration"] = None

  context.user_data["ad_step"] = "awaiting_ad_media"
  await update.message.reply_text("📸 أرسل الآن صورة أو فيديو للإعلان.")




async def manage_restaurants(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT name FROM provinces ORDER BY name")
  provinces = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not provinces:
      await query.edit_message_text("❌ لا توجد محافظات مسجلة.")
      return

  # إنشاء أزرار المحافظات لاختيار المحافظة لإدارة مطاعمها
  keyboard = [
      [InlineKeyboardButton(province, callback_data=f"select_province_for_restaurant_{province}")]
      for province in provinces
  ]
  await query.edit_message_text(
      "🏙️ اختر المحافظة لإدارة المطاعم فيها:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )


async def handle_province_for_restaurant(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  province = query.data.split("select_province_for_restaurant_")[1]
  context.user_data["selected_province_restaurant"] = province

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT cities.name FROM cities
      JOIN provinces ON cities.province_id = provinces.id
      WHERE provinces.name = ?
      GROUP BY cities.name
      ORDER BY cities.name
  """, (province,))
  cities = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not cities:
      await query.edit_message_text("❌ لا توجد مدن مسجلة ضمن هذه المحافظة.")
      return

  keyboard = [
      [InlineKeyboardButton(city, callback_data=f"select_city_for_restaurant_{city}")]
      for city in cities
  ]
  await query.edit_message_text(
      f"🌆 اختر المدينة ضمن المحافظة ({province}) لإدارة مطاعمها:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )



async def handle_city_for_restaurant(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  city = query.data.replace("select_city_for_restaurant_", "")
  context.user_data["selected_city_restaurant"] = city

  keyboard = [
      [InlineKeyboardButton("➕ إضافة مطعم", callback_data="add_restaurant")],
      [InlineKeyboardButton("❌ حذف مطعم", callback_data="delete_restaurant")],
      [InlineKeyboardButton("✏️ تعديل اسم مطعم", callback_data="rename_restaurant")],
      [InlineKeyboardButton("📣 تعديل معرف قناة", callback_data="edit_restaurant_channel")],
      [InlineKeyboardButton("⏰ تعديل وقت الفتح/الإغلاق", callback_data="edit_restaurant_hours")],
      [InlineKeyboardButton("❄️ تجميد مطعم", callback_data="freeze_restaurant")],
      [InlineKeyboardButton("✅ إلغاء تجميد مطعم", callback_data="unfreeze_restaurant")],
      [InlineKeyboardButton("↩️ العودة للقائمة الرئيسية", callback_data="go_main_menu")]
  ]

  await query.edit_message_text(
      f"🏪 إدارة المطاعم في المدينة: {city}",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )

async def start_rename_restaurant(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  city_name = context.user_data.get("selected_city_restaurant")
  if not city_name:
      await query.edit_message_text("⚠️ لم يتم تحديد المدينة.")
      return

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id FROM cities WHERE name = ?", (city_name,))
  result = cursor.fetchone()
  if not result:
      await query.edit_message_text("❌ لم يتم العثور على المدينة.")
      conn.close()
      return

  city_id = result[0]
  cursor.execute("SELECT name FROM restaurants WHERE city_id = ?", (city_id,))
  restaurants = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not restaurants:
      await query.edit_message_text("❌ لا توجد مطاعم في هذه المدينة.")
      return

  keyboard = [
      [InlineKeyboardButton(name, callback_data=f"select_restaurant_to_rename_{name}")]
      for name in restaurants
  ]
  keyboard.append([InlineKeyboardButton("↩️ العودة", callback_data="go_manage_restaurants")])

  await query.edit_message_text(
      "✏️ اختر المطعم الذي تريد تعديل اسمه:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )


async def start_delete_restaurant(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  city = context.user_data.get("selected_city_restaurant")
  if not city:
      await query.edit_message_text("⚠️ لم يتم تحديد المدينة.")
      return

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT r.name FROM restaurants r
      JOIN cities c ON r.city_id = c.id
      WHERE c.name = ?
  """, (city,))
  restaurants = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not restaurants:
      await query.edit_message_text("❌ لا توجد مطاعم في هذه المدينة.")
      return

  keyboard = [
      [InlineKeyboardButton(name, callback_data=f"confirm_delete_restaurant_{name}")]
      for name in restaurants
  ]
  keyboard.append([InlineKeyboardButton("↩️ العودة", callback_data="go_manage_restaurants")])

  await query.edit_message_text(
      f"❌ اختر المطعم الذي تريد حذفه من ({city}):",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )


async def ask_new_restaurant_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  old_name = query.data.split("select_restaurant_to_rename_")[1]
  context.user_data["restaurant_action"] = "rename"
  context.user_data["old_restaurant_name"] = old_name

  await query.edit_message_text(f"✏️ أرسل الاسم الجديد للمطعم: {old_name}")






async def confirm_delete_restaurant(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  restaurant_name = query.data.split("confirm_delete_restaurant_")[1]

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  # حذف الوجبات المرتبطة
  cursor.execute("""
      DELETE FROM meals WHERE category_id IN (
          SELECT id FROM categories WHERE restaurant_id = (
              SELECT id FROM restaurants WHERE name = ?
          )
      )
  """, (restaurant_name,))

  # حذف الفئات
  cursor.execute("""
      DELETE FROM categories WHERE restaurant_id = (
          SELECT id FROM restaurants WHERE name = ?
      )
  """, (restaurant_name,))

  # حذف التقييمات
  cursor.execute("DELETE FROM restaurant_ratings WHERE restaurant = ?", (restaurant_name,))

  # حذف المطعم
  cursor.execute("DELETE FROM restaurants WHERE name = ?", (restaurant_name,))

  conn.commit()
  conn.close()

  await query.edit_message_text(f"🗑️ تم حذف المطعم '{restaurant_name}' وكل محتوياته.")
  return await start(update, context)



async def handle_add_delete_restaurant(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  action = query.data  # add_restaurant أو delete_restaurant
  context.user_data["restaurant_action"] = action

  await query.edit_message_text("🏪 أرسل اسم المطعم الذي تريد إضافته أو حذفه:")

async def handle_restaurant_edit_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  action = query.data
  context.user_data["restaurant_edit_action"] = action

  city_name = context.user_data.get("selected_city_restaurant")
  if not city_name:
      await query.edit_message_text("⚠️ لم يتم تحديد المدينة.")
      return

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id FROM cities WHERE name = ?", (city_name,))
  result = cursor.fetchone()
  if not result:
      await query.edit_message_text("❌ لم يتم العثور على المدينة.")
      conn.close()
      return

  city_id = result[0]
  cursor.execute("SELECT name FROM restaurants WHERE city_id = ?", (city_id,))
  restaurants = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not restaurants:
      await query.edit_message_text("❌ لا توجد مطاعم مسجلة في هذه المدينة.")
      return

  keyboard = [
      [InlineKeyboardButton(name, callback_data=f"select_restaurant_edit_target_{name}")]
      for name in restaurants
  ]
  await query.edit_message_text(
      "🏪 اختر المطعم المستهدف:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )

async def handle_selected_restaurant_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  restaurant = query.data.split("select_restaurant_edit_target_")[1]
  context.user_data["selected_restaurant_to_edit"] = restaurant

  action = context.user_data.get("restaurant_edit_action")
  if action == "rename_restaurant":
      await query.edit_message_text(f"✏️ أرسل الاسم الجديد للمطعم '{restaurant}':")
      context.user_data["restaurant_edit_step"] = "rename"
  elif action == "edit_restaurant_channel":
      await query.edit_message_text(f"📣 أرسل المعرف الجديد لقناة المطعم '{restaurant}' (مثال: @channel):")
      context.user_data["restaurant_edit_step"] = "edit_channel"
  elif action == "edit_restaurant_hours":
      await query.edit_message_text(f"⏰ أرسل وقت الفتح الجديد (من 0 إلى 24):")
      context.user_data["restaurant_edit_step"] = "edit_open_hour"



async def handle_restaurant_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
  name = update.message.text.strip()
  action = context.user_data.get("restaurant_action")

  if not action:
      await update.message.reply_text("⚠️ لم يتم تحديد العملية. أعد تشغيل /start.")
      return

  context.user_data["restaurant_name"] = name

  if action == "add_restaurant":
      await update.message.reply_text("📣 أرسل *معرف قناة المطعم* (مثال: @mychannel):", parse_mode="Markdown")
      return "ASK_CHANNEL"

  elif action == "delete_restaurant":
      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("DELETE FROM restaurants WHERE name = ?", (name,))
      cursor.execute("DELETE FROM restaurant_ratings WHERE restaurant = ?", (name,))
      conn.commit()
      conn.close()

      await update.message.reply_text(f"🗑️ تم حذف المطعم '{name}' وكل ما يتعلق به.")
      context.user_data.clear()
      return ConversationHandler.END


async def handle_open_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
  try:
      open_hour = float(update.message.text.strip())
      if not 0 <= open_hour < 24:
          raise ValueError
  except ValueError:
      await update.message.reply_text("⚠️ يرجى إرسال رقم بين 0 و 24 (مثال: 9 أو 13.5).")
      return "ASK_OPEN_HOUR"  # ضروري إعادة الحالة

  context.user_data["open_hour"] = open_hour
  await update.message.reply_text("⏰ أرسل وقت *الإغلاق* (مثال: 23 أو 22.5):", parse_mode="Markdown")
  return "ASK_CLOSE_HOUR"



async def handle_text_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
  text = update.message.text.strip()

  # ✅ تعديل قناة الإعلانات أولًا إذا تم اختياره
  if context.user_data.get("city_action") == "edit_ads_channel":
      new_channel = text
      city = context.user_data.get("city_to_edit_ads_channel")

      if not city:
          await update.message.reply_text("❌ لم يتم تحديد المدينة.")
          return

      if new_channel.lower() == "لا يوجد":
          new_channel = None
      elif not new_channel.startswith("@"):
          await update.message.reply_text("⚠️ يجب أن يبدأ معرف القناة بـ @ أو اكتب 'لا يوجد'.")
          return

      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("UPDATE cities SET ads_channel = ? WHERE name = ?", (new_channel, city))
      conn.commit()
      conn.close()

      await update.message.reply_text(f"✅ تم تعديل قناة الإعلانات لمدينة '{city}' بنجاح.")
      context.user_data.pop("city_action", None)
      context.user_data.pop("city_to_edit_ads_channel", None)
      return await start(update, context)

  # ✅ بعده بقية إدارة المحافظات والمدن والمطاعم
  elif context.user_data.get("province_action"):
      return await handle_province_name(update, context)

  elif context.user_data.get("city_action"):
      return await handle_city_name(update, context)

  elif context.user_data.get("restaurant_action") == "add_restaurant" and "restaurant_name" not in context.user_data:
      return await handle_restaurant_name(update, context)

  elif context.user_data.get("restaurant_action") == "add_restaurant" and "restaurant_channel" not in context.user_data:
      return await handle_restaurant_channel(update, context)

  elif context.user_data.get("restaurant_action") == "add_restaurant" and "open_hour" not in context.user_data:
      return await handle_open_hour(update, context)

  elif context.user_data.get("restaurant_action") == "add_restaurant" and (
      "restaurant_name" in context.user_data and
      "restaurant_channel" in context.user_data and
      "open_hour" in context.user_data
  ):
      return await handle_close_hour(update, context)


  # ✅ استقبال اسم الوجبة
  elif context.user_data.get("meal_action") == "add" and "new_meal_name" not in context.user_data:
      context.user_data["new_meal_name"] = text

      # ✅ تأمين selected_category مبكرًا
      if "selected_category" not in context.user_data:
          for key in ["selected_category_meal", "selected_category_category", "selected_category_restaurant"]:
              if key in context.user_data:
                  context.user_data["selected_category"] = context.user_data[key]
                  break

      await update.message.reply_text(
          "📏 هل لهذه الوجبة قياسات؟",
          reply_markup=ReplyKeyboardMarkup(
              [["نعم، لها قياسات", "لا، لا يوجد قياسات"]],
              one_time_keyboard=True,
              resize_keyboard=True
          )
      )
      return

  # ✅ سؤال: هل لهذه الوجبة قياسات؟
  elif context.user_data.get("meal_action") == "add" and text in ["نعم، لها قياسات", "لا، لا يوجد قياسات"]:
      context.user_data["has_sizes"] = text

      # ✅ تأمين selected_category مجددًا لو لم يكن موجود
      if "selected_category" not in context.user_data:
          for key in ["selected_category_meal", "selected_category_category", "selected_category_restaurant"]:
              if key in context.user_data:
                  context.user_data["selected_category"] = context.user_data[key]
                  break

      if text == "نعم، لها قياسات":
          context.user_data["add_meal_step"] = "awaiting_size_values"
          await update.message.reply_text("📝 الرجاء إدخال القياسات مفصولة بفواصل (مثال: صغير/2000، وسط/3000، كبير/4000):")
      else:
          context.user_data["add_meal_step"] = "awaiting_single_price"
          await update.message.reply_text("💰 أرسل سعر الوجبة (رقم فقط):")
      return

  elif context.user_data.get("meal_action") == "add" and context.user_data.get("add_meal_step") == "awaiting_size_values":
      sizes_raw = text.replace("،", ",")
      sizes = [s.strip() for s in sizes_raw.split(",")]
      size_data = []

      for s in sizes:
          if "/" not in s:
              await update.message.reply_text("⚠️ الصيغة غير صحيحة. استخدم الشكل: صغير/5000")
              return
          size_name, price_str = s.split("/", 1)
          try:
              price = int(price_str)
          except ValueError:
              await update.message.reply_text("⚠️ السعر غير صالح. تأكد من استخدام أرقام فقط.")
              return
          size_data.append((size_name.strip(), price))

      context.user_data["sizes_data"] = size_data
      context.user_data["add_meal_step"] = "awaiting_caption"
      await update.message.reply_text("📝 أرسل وصفًا (مكونات الوجبة):")
      return


  # تعديل اسم وجبة
  elif context.user_data.get("meal_action") == "edit_name" and "old_meal_name" in context.user_data:
      new_name = text
      old_name = context.user_data["old_meal_name"]
      category_name = context.user_data.get("selected_category_meal")
      restaurant_name = context.user_data.get("selected_restaurant_meal")

      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      try:
          cursor.execute("""
              UPDATE meals SET name = ?
              WHERE name = ? AND category_id = (
                  SELECT c.id FROM categories c
                  JOIN restaurants r ON c.restaurant_id = r.id
                  WHERE c.name = ? AND r.name = ?
              )
          """, (new_name, old_name, category_name, restaurant_name))
          conn.commit()
          await update.message.reply_text(f"✅ تم تعديل اسم الوجبة إلى: {new_name}")
      except sqlite3.IntegrityError:
          await update.message.reply_text("⚠️ هناك وجبة بهذا الاسم موجودة مسبقًا.")
      finally:
          conn.close()

      context.user_data.pop("meal_action", None)
      context.user_data.pop("old_meal_name", None)
      return await show_meal_options(update, context)


  # تعديل سعر وجبة (بقياسات أو بدون)
  elif context.user_data.get("meal_action") == "edit_price":
      step = context.user_data.get("edit_price_step")
      meal_name = context.user_data.get("meal_to_edit_price")
      category = context.user_data.get("selected_category_meal")
      restaurant = context.user_data.get("selected_restaurant_meal")

      if not meal_name or not category or not restaurant:
          await update.message.reply_text("❌ لا يمكن تحديد نوع التعديل. يرجى البدء من جديد.")
          context.user_data.clear()
          return await start(update, context)

      if not text.isdigit():
          await update.message.reply_text("❌ السعر يجب أن يكون رقمًا.")
          return

      if not step:
          # تعديل مباشر بدون قياسات
          new_price = int(text)

          cursor = db_conn.cursor()
          cursor.execute("""
              UPDATE meals SET price = ?, size_options = NULL
              WHERE name = ? AND category_id = (
                  SELECT c.id FROM categories c
                  JOIN restaurants r ON c.restaurant_id = r.id
                  WHERE c.name = ? AND r.name = ?
              )
          """, (new_price, meal_name, category, restaurant))
          db_conn.commit()

          await update.message.reply_text(f"✅ تم تعديل سعر '{meal_name}' إلى {new_price} ل.س.")
          for key in ["meal_action", "meal_to_edit_price"]:
              context.user_data.pop(key, None)
          return await show_meal_options(update, context)

      elif step == "single_price":
          new_price = int(text)

          cursor = db_conn.cursor()
          cursor.execute("""
              UPDATE meals SET price = ?, size_options = NULL
              WHERE name = ? AND category_id = (
                  SELECT c.id FROM categories c
                  JOIN restaurants r ON c.restaurant_id = r.id
                  WHERE c.name = ? AND r.name = ?
              )
          """, (new_price, meal_name, category, restaurant))
          db_conn.commit()

          await update.message.reply_text(f"✅ تم تعديل سعر '{meal_name}' بنجاح.")
          for key in ["meal_action", "edit_price_step", "meal_to_edit_price"]:
              context.user_data.pop(key, None)
          return await show_meal_options(update, context)

      elif step == "multi_price":
          current_index = context.user_data.get("current_size_index", 0)
          sizes = context.user_data.get("edit_price_sizes", [])
          if current_index >= len(sizes):
              await update.message.reply_text("❌ حدث خطأ في عدد القياسات. يرجى البدء من جديد.")
              context.user_data.clear()
              return await start(update, context)

          current_size_obj = sizes[current_index]
          size_name = current_size_obj["name"]

          if "edit_price_data" not in context.user_data:
              context.user_data["edit_price_data"] = {}

          context.user_data["edit_price_data"][size_name] = int(text)

          if current_index + 1 < len(sizes):
              context.user_data["current_size_index"] = current_index + 1
              next_size = sizes[current_index + 1]
              await update.message.reply_text(
                  f"💬 أرسل السعر الجديد للقياس: {next_size['name']} (السعر الحالي: {next_size['price']} ل.س)"
              )
              return

          # بعد إدخال جميع الأسعار
          price_dict = context.user_data["edit_price_data"]
          base_price = max(price_dict.values())

          cursor = db_conn.cursor()
          cursor.execute("""
              UPDATE meals SET price = ?, size_options = ?
              WHERE name = ? AND category_id = (
                  SELECT c.id FROM categories c
                  JOIN restaurants r ON c.restaurant_id = r.id
                  WHERE c.name = ? AND r.name = ?
              )
          """, (
              base_price,
              json.dumps([
                  {"name": name, "price": price}
                  for name, price in price_dict.items()
              ], ensure_ascii=False),
              meal_name,
              category,
              restaurant
          ))
          db_conn.commit()

          await update.message.reply_text(f"✅ تم تعديل سعر '{meal_name}' بنجاح.")
          for key in ["meal_action", "edit_price_step", "meal_to_edit_price", "edit_price_data", "edit_price_sizes", "current_size_index"]:
              context.user_data.pop(key, None)

          return await show_meal_options(update, context)


  # استقبال وصف جديد للوجبة
  # ✅ استقبال وصف جديد للوجبة (تعديل الكابشن)
  elif context.user_data.get("meal_action") == "edit_caption" and "meal_to_edit_caption_id" in context.user_data:
      new_caption = text
      meal_id = context.user_data["meal_to_edit_caption_id"]

      try:
          conn = sqlite3.connect("database.db")
          cursor = conn.cursor()
          cursor.execute("UPDATE meals SET caption = ? WHERE id = ?", (new_caption, meal_id))
          conn.commit()
          await update.message.reply_text("✅ تم تعديل وصف الوجبة بنجاح.")
      except Exception as e:
          await update.message.reply_text("❌ حدث خطأ أثناء تعديل الكابشن.")
          print("❌ خطأ أثناء تعديل الكابشن:", e)
      finally:
          conn.close()

      context.user_data.pop("meal_action", None)
      context.user_data.pop("meal_to_edit_caption_id", None)
      return await show_meal_management_menu(update, context)


  # تعديل القياسات - استقبال خيار الإضافة أو الحذف
  elif context.user_data.get("meal_action") == "edit_sizes_choice":
      if text == "➕ إضافة قياس":
          context.user_data["edit_step"] = "add_single_size"
          context.user_data["meal_action"] = "edit_sizes"
          await update.message.reply_text("✏️ أرسل القياس والسعر بصيغة مثل: وسط/6000")
      elif text == "❌ حذف قياس":
          meal_name = context.user_data.get("meal_to_edit_sizes")
          category_name = context.user_data.get("selected_category_meal")
          restaurant_name = context.user_data.get("selected_restaurant_meal")

          conn = sqlite3.connect("database.db")
          cursor = conn.cursor()
          cursor.execute("""
              SELECT sizes FROM meals
              WHERE name = ? AND category_id = (
                  SELECT c.id FROM categories c
                  JOIN restaurants r ON c.restaurant_id = r.id
                  WHERE c.name = ? AND r.name = ?
              )
          """, (meal_name, category_name, restaurant_name))
          result = cursor.fetchone()
          conn.close()

          if not result or not result[0]:
              await update.message.reply_text("❌ لا توجد قياسات محفوظة لهذه الوجبة.")
              context.user_data.clear()
              return await show_meal_options(update, context)

          sizes_data = json.loads(result[0])
          context.user_data["sizes_to_remove"] = sizes_data

          keyboard = [
              [InlineKeyboardButton(s["name"], callback_data=f"remove_size_{s['name']}")]
              for s in sizes_data
          ]
          await update.message.reply_text(
              "🗑️ اختر القياس الذي تريد حذفه:",
              reply_markup=InlineKeyboardMarkup(keyboard)
          )
          context.user_data["meal_action"] = "remove_size"
      return

  # حذف قياس معين
  # حذف قياس معين
  elif context.user_data.get("meal_action") == "remove_size":
      size_to_remove = text
      sizes = context.user_data.get("sizes_to_remove", [])
      updated_sizes = [s for s in sizes if s["name"] != size_to_remove]

      if len(updated_sizes) == len(sizes):
          await update.message.reply_text("⚠️ القياس غير موجود.")
          return

      meal_name = context.user_data.get("meal_to_edit_sizes")
      category_name = context.user_data.get("selected_category_meal")
      restaurant_name = context.user_data.get("selected_restaurant_meal")

      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("""
          UPDATE meals SET size_options = ?, price = ?
          WHERE name = ? AND category_id = (
              SELECT c.id FROM categories c
              JOIN restaurants r ON c.restaurant_id = r.id
              WHERE c.name = ? AND r.name = ?
          )
      """, (
          json.dumps(updated_sizes, ensure_ascii=False),
          max([s["price"] for s in updated_sizes]) if updated_sizes else 0,
          meal_name, category_name, restaurant_name
      ))
      conn.commit()
      conn.close()

      await update.message.reply_text("✅ تم حذف القياس بنجاح.")
      for key in ["meal_action", "meal_to_edit_sizes", "edit_step", "sizes_to_remove"]:
          context.user_data.pop(key, None)

      return await show_meal_management_menu(update, context)

  # ➕ استقبال قياس جديد أثناء تعديل القياسات
  elif context.user_data.get("edit_step") == "add_single_size":
      if "/" not in text:
          await update.message.reply_text("⚠️ الصيغة غير صحيحة. أرسلها مثل: وسط/6000")
          return

      size_name, price_str = text.split("/", 1)
      try:
          price = int(price_str)
      except ValueError:
          await update.message.reply_text("⚠️ السعر غير صالح. أرسل رقمًا فقط.")
          return

      new_size = {"name": size_name.strip(), "price": price}
      meal_name = context.user_data.get("meal_to_edit_sizes")
      category_name = context.user_data.get("selected_category_meal")
      restaurant_name = context.user_data.get("selected_restaurant_meal")

      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("""
          SELECT size_options FROM meals
          WHERE name = ? AND category_id = (
              SELECT c.id FROM categories c
              JOIN restaurants r ON c.restaurant_id = r.id
              WHERE c.name = ? AND r.name = ?
          )
      """, (meal_name, category_name, restaurant_name))
      result = cursor.fetchone()

      sizes = json.loads(result[0]) if result and result[0] else []
      sizes.append(new_size)

      cursor.execute("""
          UPDATE meals SET size_options = ?, price = ?
          WHERE name = ? AND category_id = (
              SELECT c.id FROM categories c
              JOIN restaurants r ON c.restaurant_id = r.id
              WHERE c.name = ? AND r.name = ?
          )
      """, (
          json.dumps(sizes, ensure_ascii=False),
          max([s["price"] for s in sizes]),
          meal_name, category_name, restaurant_name
      ))
      conn.commit()
      conn.close()

      await update.message.reply_text("✅ تم إضافة القياس الجديد بنجاح.")
      context.user_data.clear()
      return await show_meal_management_menu(update, context)

  # ✅ تعديل قياسات وجبة لا تحتوي على قياسات سابقًا
  elif context.user_data.get("meal_action") == "edit_sizes" and context.user_data.get("edit_step") == "add_sizes_to_empty":
      text = update.message.text.strip()
      try:
          sizes = [s.strip() for s in text.split(",")]
          formatted_sizes = []

          for s in sizes:
              if "/" not in s:
                  raise ValueError("صيغة غير صحيحة.")
              name, price = s.split("/")
              formatted_sizes.append({"name": name.strip(), "price": int(price.strip())})

      except Exception as e:
          await update.message.reply_text("❌ تأكد من كتابة القياسات بشكل صحيح مثل: كبير/5000, صغير/3000")
          return

      meal_name = context.user_data.get("meal_to_edit_sizes")
      category = context.user_data.get("selected_category_meal")
      restaurant = context.user_data.get("selected_restaurant_meal")

      cursor = sqlite3.connect("database.db").cursor()
      cursor.execute("""
          UPDATE meals SET size_options = ?, price = ?
          WHERE name = ? AND category_id = (
              SELECT c.id FROM categories c
              JOIN restaurants r ON c.restaurant_id = r.id
              WHERE c.name = ? AND r.name = ?
          )
      """, (
          json.dumps(formatted_sizes, ensure_ascii=False),
          max(s["price"] for s in formatted_sizes),
          meal_name, category, restaurant
      ))
      db_conn.commit()

      await update.message.reply_text("✅ تم حفظ القياسات بنجاح.")
      for key in ["meal_action", "edit_step", "meal_to_edit_sizes"]:
          context.user_data.pop(key, None)
      return await show_meal_management_menu(update, context)



  # إضافة فئة جديدة
  elif context.user_data.get("category_action") == "add":
      category_name = text
      restaurant_name = context.user_data.get("selected_restaurant_category")

      if not restaurant_name:
          await update.message.reply_text("⚠️ لم يتم تحديد المطعم. يرجى العودة واختياره من جديد.")
          return

      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("SELECT id FROM restaurants WHERE name = ?", (restaurant_name,))
      result = cursor.fetchone()

      if not result:
          await update.message.reply_text("❌ لم يتم العثور على المطعم في قاعدة البيانات.")
          conn.close()
          return

      restaurant_id = result[0]
      try:
          cursor.execute(
              "INSERT INTO categories (name, restaurant_id) VALUES (?, ?)",
              (category_name, restaurant_id)
          )
          conn.commit()
          await update.message.reply_text(f"✅ تم إضافة الفئة: {category_name}")
      except sqlite3.IntegrityError:
          await update.message.reply_text("⚠️ هذه الفئة موجودة بالفعل لهذا المطعم.")
      finally:
          conn.close()

      context.user_data.pop("category_action", None)
      return await show_category_options(update, context)

  # حذف فئة
  elif context.user_data.get("category_action") == "delete":
      category_name = text
      restaurant_name = context.user_data.get("selected_restaurant_category")

      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("""
          DELETE FROM categories
          WHERE name = ? AND restaurant_id = (
              SELECT id FROM restaurants WHERE name = ?
          )
      """, (category_name, restaurant_name))
      conn.commit()
      conn.close()

      await update.message.reply_text(f"🗑️ تم حذف الفئة: {category_name}")
      context.user_data.pop("category_action", None)
      return await show_category_options(update, context)

  # تعديل اسم الفئة - استلام الاسم القديم
  elif context.user_data.get("category_action") == "edit_old_name":
      context.user_data["old_category_name"] = text
      context.user_data["category_action"] = "edit_new_name"
      await update.message.reply_text("📝 أرسل الاسم الجديد للفئة:")
      return

  # تعديل اسم الفئة - استلام الاسم الجديد
  elif context.user_data.get("category_action") == "edit_new_name":
      new_name = text
      old_name = context.user_data.get("old_category_name")
      restaurant_name = context.user_data.get("selected_restaurant_category")

      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("""
          UPDATE categories SET name = ?
          WHERE name = ? AND restaurant_id = (
              SELECT id FROM restaurants WHERE name = ?
          )
      """, (new_name, old_name, restaurant_name))
      conn.commit()
      conn.close()

      await update.message.reply_text(f"✏️ تم تعديل اسم الفئة إلى: {new_name}")
      context.user_data.pop("category_action", None)
      context.user_data.pop("old_category_name", None)
      return await show_category_options(update, context)
  # تعديل اسم مطعم (من اختيار المطعم أولًا)
  elif context.user_data.get("restaurant_action") == "rename" and "old_restaurant_name" in context.user_data:
      new_name = text
      old_name = context.user_data["old_restaurant_name"]

      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      try:
          cursor.execute("UPDATE restaurants SET name = ? WHERE name = ?", (new_name, old_name))
          cursor.execute("UPDATE restaurant_ratings SET restaurant = ? WHERE restaurant = ?", (new_name, old_name))
          cursor.execute("UPDATE user_orders SET restaurant = ? WHERE restaurant = ?", (new_name, old_name))
          conn.commit()
          await update.message.reply_text(f"✅ تم تعديل اسم المطعم إلى: {new_name}")
      except sqlite3.IntegrityError:
          await update.message.reply_text("⚠️ يوجد مطعم بهذا الاسم مسبقًا.")
      finally:
          conn.close()

      context.user_data.pop("restaurant_action", None)
      context.user_data.pop("old_restaurant_name", None)
      return await start(update, context)

  # تعديل اسم مطعم (عبر خطوة edit)
  elif context.user_data.get("restaurant_edit_step") == "rename":
      new_name = text
      old_name = context.user_data.get("selected_restaurant_to_edit")

      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("UPDATE restaurants SET name = ? WHERE name = ?", (new_name, old_name))
      conn.commit()
      conn.close()

      await update.message.reply_text(f"✅ تم تعديل اسم المطعم إلى: {new_name}")
      context.user_data.clear()
      return await start(update, context)

  # تعديل معرف القناة
  elif context.user_data.get("restaurant_edit_step") == "edit_channel":
      new_channel = text
      if not new_channel.startswith("@"):
          await update.message.reply_text("❌ يرجى إرسال معرف يبدأ بـ @")
          return

      restaurant = context.user_data.get("selected_restaurant_to_edit")
      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("UPDATE restaurants SET channel = ? WHERE name = ?", (new_channel, restaurant))
      conn.commit()
      conn.close()

      await update.message.reply_text(f"✅ تم تعديل معرف القناة إلى: {new_channel}")
      context.user_data.clear()
      return await start(update, context)

  # تعديل ساعة الفتح
  elif context.user_data.get("restaurant_edit_step") == "edit_open_hour":
      try:
          open_hour = float(text)
          if not 0 <= open_hour < 24:
              raise ValueError
      except ValueError:
          await update.message.reply_text("⚠️ أرسل رقم بين 0 و 24.")
          return

      context.user_data["new_open_hour"] = open_hour
      await update.message.reply_text("⏰ أرسل وقت الإغلاق الجديد:")
      context.user_data["restaurant_edit_step"] = "edit_close_hour"
      return

  # تعديل ساعة الإغلاق
  elif context.user_data.get("restaurant_edit_step") == "edit_close_hour":
      try:
          close_hour = float(text)
          if not 0 <= close_hour <= 24:
              raise ValueError
      except ValueError:
          await update.message.reply_text("⚠️ أرسل رقم بين 0 و 24.")
          return

      open_hour = context.user_data.get("new_open_hour")
      restaurant = context.user_data.get("selected_restaurant_to_edit")

      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("""
          UPDATE restaurants SET open_hour = ?, close_hour = ?
          WHERE name = ?
      """, (open_hour, close_hour, restaurant))
      conn.commit()
      conn.close()

      await update.message.reply_text(f"✅ تم تعديل أوقات المطعم إلى {open_hour} - {close_hour}")
      context.user_data.clear()
      return await start(update, context)
  # 🧩 استقبال القياسات بعد اختيار "نعم، لها قياسات"
  elif context.user_data.get("meal_action") == "add" and context.user_data.get("add_meal_step") == "awaiting_size_values":
      sizes_raw = text.replace("،", ",")  # دعم الفاصلة العربية
      sizes = [s.strip() for s in sizes_raw.split(",")]
      size_data = []

      for s in sizes:
          if "/" not in s:
              await update.message.reply_text("⚠️ الصيغة غير صحيحة. استخدم الشكل: صغير/5000, وسط/6000")
              return
          size_name, price_str = s.split("/", 1)
          try:
              price = int(price_str)
          except ValueError:
              await update.message.reply_text("⚠️ السعر غير صالح. تأكد من استخدام أرقام فقط.")
              return
          size_data.append((size_name.strip(), price))

      # حفظ القياسات في المتغير مؤقتًا (لاحقًا سيتم إدخالها في قاعدة البيانات بعد استقبال الصورة)
      context.user_data["sizes_data"] = size_data
      context.user_data["add_meal_step"] = "awaiting_caption"

      await update.message.reply_text("✅ تم حفظ القياسات بنجاح.")
      await update.message.reply_text("📝 أرسل وصفًا (مكونات الوجبة):")
      return

  # 🧩 استقبال السعر في حالة "لا، لا يوجد قياسات"
  elif context.user_data.get("add_meal_step") == "awaiting_single_price":
      try:
          price = int(text)
      except ValueError:
          await update.message.reply_text("❌ السعر غير صالح. أرسل رقمًا فقط.")
          return

      context.user_data["new_meal_price"] = price
      context.user_data["add_meal_step"] = "awaiting_caption"
      await update.message.reply_text("📝 أرسل وصفًا (مكونات الوجبة):")
      return

  # 🧾 استقبال وصف الوجبة بعد القياسات أو السعر
  elif context.user_data.get("add_meal_step") == "awaiting_caption":
      context.user_data["meal_caption"] = text
      context.user_data["add_meal_step"] = "awaiting_photo"
      await update.message.reply_text("📸 أرسل صورة الوجبة الآن:")
      return

  elif context.user_data.get("ad_step") == "awaiting_ad_text":
      context.user_data["ad_text"] = text
      context.user_data["ad_step"] = "awaiting_ad_duration"
      await update.message.reply_text(
          "⏱️ كم المدة التي يستمر فيها هذا الإعلان؟\n"
          "📝 يمكنك كتابة أي مدة مثل: 'يومان' أو 'حتى نهاية الأسبوع' أو 'شهر كامل'.\n"
          "أو يمكنك الضغط على 'تخطي ⏭️' إذا لم تكن هناك مدة محددة.",
          reply_markup=ReplyKeyboardMarkup([["تخطي ⏭️"]], resize_keyboard=True)
      )
      return

  # ✅ تخطي الوسائط (إعلان نصي فقط)
  elif context.user_data.get("ad_step") == "awaiting_ad_duration":
      if text != "تخطي ⏭️":
          context.user_data["ad_duration"] = text
      else:
          context.user_data["ad_duration"] = None

      context.user_data["ad_step"] = "awaiting_ad_media"
      await update.message.reply_text(
          "📸 أرسل الآن صورة أو فيديو للإعلان، أو اضغط 'تخطي ⏭️' لنشر الإعلان كنص فقط.",
          reply_markup=ReplyKeyboardMarkup([["تخطي ⏭️"]], resize_keyboard=True)
      )
      return

  # ✅ عند اختيار "تخطي" للوسائط (نشر نص فقط)
  elif context.user_data.get("ad_step") == "awaiting_ad_media" and text == "تخطي ⏭️":
      ad_text = context.user_data.get("ad_text")
      ad_city = context.user_data.get("ad_city")
      ad_restaurant = context.user_data.get("ad_restaurant")
      ad_duration = context.user_data.get("ad_duration")
      skip_restaurant = context.user_data.get("ad_skip_restaurant", False)

      if not ad_text or not ad_city:
          await update.message.reply_text("⚠️ البيانات غير مكتملة. يرجى البدء من جديد.")
          context.user_data.clear()
          return await start(update, context)

      # توليد النص
      if skip_restaurant:
          full_text = ad_text
          if ad_duration:
              full_text += f"\n\n⏳ ديير بالك بس لـ {ad_duration} 🕒"
          button = InlineKeyboardMarkup([[InlineKeyboardButton("🍽️ اطلب عالسريع 🍽️", url="https://t.me/Fasterone1200_bot")]])
      else:
          full_text = "🔥 يالله عالسرييع 🔥\n\n" + ad_text
          if ad_duration:
              full_text += f"\n\n⏳ ديير بالك بس لـ {ad_duration} 🕒"
          full_text += f"\n\n⬇️ اختر الزر أدناه:\nالقائمة الرئيسية 🧭 ← اطلب عالسريع 🔥 ← مطعم {ad_restaurant}، وتفرّج يا معلمم 😎"
          restaurant_encoded = quote(ad_restaurant)
          url = f"https://t.me/Fasterone1200_bot?start=go_{restaurant_encoded}"
          button = InlineKeyboardMarkup([[InlineKeyboardButton("🍽️ اطلب عالسريع 🍽️", url=url)]])

      # إرسال
      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      if ad_city == "all":
          cursor.execute("SELECT ads_channel FROM cities WHERE ads_channel IS NOT NULL")
          channels = [row[0] for row in cursor.fetchall()]
      else:
          cursor.execute("SELECT ads_channel FROM cities WHERE name = ?", (ad_city,))
          result = cursor.fetchone()
          if not result or not result[0]:
              await update.message.reply_text("❌ لم يتم العثور على قناة المدينة.")
              context.user_data.clear()
              conn.close()
              return await start(update, context)
          channels = [result[0]]
      conn.close()

      for channel in channels:
          await context.bot.send_message(chat_id=channel, text=full_text, parse_mode="Markdown", reply_markup=button)

      await update.message.reply_text("✅ تم نشر الإعلان كنص فقط بدون وسائط.")
      context.user_data.clear()
      return await start(update, context)

  elif context.user_data.get("ad_step") == "awaiting_vip_button_text":
      if text != "تخطي ⏭️":
          context.user_data["vip_button_text"] = text
      else:
          context.user_data["vip_button_text"] = None

      context.user_data["ad_step"] = "awaiting_ad_text"
      await update.message.reply_text("📝 أرسل الآن نص الإعلان الذي تريد نشره:")
      return


  # 🛑 نص غير متوقع أو سياق غير معروف
  else:
      print("⚠️ لم يتم تحديد نوع التعديل الصحيح.")
      await update.message.reply_text("❌ لا يمكن تحديد نوع التعديل. يرجى البدء من جديد.")





async def handle_close_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
  try:
      close_hour = float(update.message.text.strip())
      if not 0 <= close_hour <= 24:
          raise ValueError
  except ValueError:
      await update.message.reply_text("⚠️ يرجى إرسال رقم بين 0 و 24.")
      return "ASK_CLOSE_HOUR"

  context.user_data["close_hour"] = close_hour

  # جلب القيم المطلوبة
  name = context.user_data.get("restaurant_name")
  channel = context.user_data.get("restaurant_channel")
  open_hour = context.user_data.get("open_hour")
  city_name = context.user_data.get("selected_city_restaurant")

  # 🐞 DEBUG
  print(f"DEBUG: name = {name}")
  print(f"DEBUG: channel = {channel}")
  print(f"DEBUG: open_hour = {open_hour}")
  print(f"DEBUG: close_hour = {close_hour}")
  print(f"DEBUG: city_name = {city_name}")

  # ✅ إصلاح هنا: لا تستخدم all(...) مع open_hour = 0.0
  if name is None or channel is None or open_hour is None or city_name is None:
      await update.message.reply_text("❌ حدث خطأ. بعض البيانات مفقودة.")
      return ConversationHandler.END

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id FROM cities WHERE name = ?", (city_name,))
  result = cursor.fetchone()

  if not result:
      await update.message.reply_text("❌ لم يتم العثور على المدينة.")
      conn.close()
      return ConversationHandler.END

  city_id = result[0]

  cursor.execute("""
      INSERT INTO restaurants (name, city_id, channel, open_hour, close_hour)
      VALUES (?, ?, ?, ?, ?)
  """, (name, city_id, channel, open_hour, close_hour))

  conn.commit()
  conn.close()

  await update.message.reply_text(f"✅ تم إضافة المطعم '{name}' بنجاح.")
  context.user_data.clear()
  await start(update, context)  # هذا السطر يعيد المستخدم للقائمة الرئيسية
  return ConversationHandler.END




async def handle_restaurant_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
  channel = update.message.text.strip()
  if not channel.startswith("@"):
      await update.message.reply_text("❌ يرجى إدخال المعرف بشكل صحيح ويبدأ بـ @")
      return "ASK_CHANNEL"

  context.user_data["restaurant_channel"] = channel
  await update.message.reply_text(
      "⏰ أرسل *ساعة الفتح* (مثال: 9 أو 13.5 للواحدة والنصف ظهرًا):",
      parse_mode="Markdown"
  )
  return "ASK_OPEN_HOUR"  # ✅ هذا السطر المهم


async def manage_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT name FROM provinces ORDER BY name")
  provinces = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not provinces:
      await query.edit_message_text("❌ لا توجد محافظات مسجلة.")
      return

  keyboard = [
      [InlineKeyboardButton(province, callback_data=f"select_province_for_category_{province}")]
      for province in provinces
  ]
  await query.edit_message_text(
      "📍 اختر المحافظة لإدارة الفئات:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )


async def handle_province_for_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  province = query.data.split("select_province_for_category_")[1]
  context.user_data["selected_province_category"] = province

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT cities.name FROM cities
      JOIN provinces ON cities.province_id = provinces.id
      WHERE provinces.name = ?
      ORDER BY cities.name
  """, (province,))
  cities = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not cities:
      await query.edit_message_text("❌ لا توجد مدن مسجلة ضمن هذه المحافظة.")
      return

  keyboard = [
      [InlineKeyboardButton(city, callback_data=f"select_city_for_category_{city}")]
      for city in cities
  ]
  await query.edit_message_text(
      f"🌆 اختر المدينة ضمن المحافظة ({province}) لإدارة فئات مطاعمها:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )


async def handle_city_for_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  city = query.data.split("select_city_for_category_")[1]
  context.user_data["selected_city_category"] = city

  # ✅ استعلام جديد بناءً على city_id وليس city النصي
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT r.name FROM restaurants r
      JOIN cities c ON r.city_id = c.id
      WHERE c.name = ?
  """, (city,))
  restaurants = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not restaurants:
      await query.edit_message_text("❌ لا توجد مطاعم مسجلة ضمن هذه المدينة.")
      return

  keyboard = [
      [InlineKeyboardButton(name, callback_data=f"select_restaurant_for_category_{name}")]
      for name in restaurants
  ]
  await query.edit_message_text(
      f"🏪 اختر المطعم الذي تريد إدارة فئاته في المدينة ({city}):",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )


async def show_category_options(update: Update, context: ContextTypes.DEFAULT_TYPE, force_message=False):
  # نحصل على اسم المطعم من الزر فقط إن وجد
  if update.callback_query:
      query = update.callback_query
      await query.answer()
      restaurant = query.data.split("select_restaurant_for_category_")[1]
      context.user_data["selected_restaurant_category"] = restaurant
  else:
      restaurant = context.user_data.get("selected_restaurant_category")

  keyboard = [
      [InlineKeyboardButton("➕ إضافة فئة", callback_data="add_category")],
      [InlineKeyboardButton("➖ حذف فئة", callback_data="delete_category")],
      [InlineKeyboardButton("✏️ تعديل اسم فئة", callback_data="edit_category_name")],
      [InlineKeyboardButton("↩️ العودة للقائمة الرئيسية", callback_data="go_main_menu")]
  ]

  text = f"📂 إدارة الفئات في المطعم: {restaurant}"

  if update.callback_query:
      await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
  else:
      await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))





async def handle_category_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  action = query.data  # add_category أو delete_category أو edit_category_name أو go_main_menu

  # ✅ إضافة فئة
  if action == "add_category":
      await query.edit_message_text("📝 أرسل اسم الفئة التي تريد إضافتها:")
      context.user_data["category_action"] = "add"

  # 🗑️ حذف فئة (عرض الفئات كأزرار للاختيار)
  elif action == "delete_category":
      restaurant = context.user_data.get("selected_restaurant_category")

      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("""
          SELECT id, name FROM categories
          WHERE restaurant_id = (SELECT id FROM restaurants WHERE name = ?)
          ORDER BY name
      """, (restaurant,))
      categories = cursor.fetchall()
      conn.close()

      print("📋 الفئات المعروضة للحذف:", categories)  # ✅ طباعة للتأكد

      if not categories:
          await query.edit_message_text("❌ لا توجد فئات لحذفها.")
          return

      keyboard = [
          [InlineKeyboardButton(name, callback_data=f"delete_category_id:{cat_id}")]
          for cat_id, name in categories
      ]
      print("✅ أزرار الحذف:", [btn[0].callback_data for btn in keyboard])  # ✅ طباعة للتأكد

      await query.edit_message_text("🗑️ اختر الفئة التي تريد حذفها:", reply_markup=InlineKeyboardMarkup(keyboard))

  # ✏️ تعديل اسم فئة (عرض الفئات كأزرار للاختيار)
  elif action == "edit_category_name":
      restaurant = context.user_data.get("selected_restaurant_category")

      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()
      cursor.execute("""
          SELECT id, name FROM categories
          WHERE restaurant_id = (SELECT id FROM restaurants WHERE name = ?)
          ORDER BY name
      """, (restaurant,))
      categories = cursor.fetchall()
      conn.close()

      if not categories:
          await query.edit_message_text("❌ لا توجد فئات مسجلة لهذا المطعم.")
          return

      keyboard = [
          [InlineKeyboardButton(name, callback_data=f"rename_category_id:{cat_id}")]
          for cat_id, name in categories
      ]
      await query.edit_message_text("✏️ اختر الفئة التي تريد تعديل اسمها:", reply_markup=InlineKeyboardMarkup(keyboard))

  # 🔙 العودة للقائمة الرئيسية
  elif action == "go_main_menu":
      await start(update, context)





async def ask_new_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  old_name = query.data.split("select_category_to_rename_")[1]
  context.user_data["category_action"] = "edit_new_name"
  context.user_data["old_category_name"] = old_name

  await query.edit_message_text(f"📝 أرسل الاسم الجديد للفئة: {old_name}")


async def delete_selected_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  # استخراج المعرف من callback_data
  try:
      category_id = int(query.data.split("delete_category_id:")[1])
  except (IndexError, ValueError):
      await query.edit_message_text("❌ حدث خطأ في قراءة الفئة المختارة.")
      return

  # حذف الفئة
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT name FROM categories WHERE id = ?", (category_id,))
  result = cursor.fetchone()

  if not result:
      await query.edit_message_text("❌ لم يتم العثور على الفئة.")
      conn.close()
      return

  category_name = result[0]

  cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
  conn.commit()
  conn.close()

  await query.edit_message_text(f"🗑️ تم حذف الفئة: {category_name}")
  return await show_category_options(update, context)



async def manage_meals(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  # جلب المحافظات
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT name FROM provinces ORDER BY name")
  provinces = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not provinces:
      await query.edit_message_text("❌ لا توجد محافظات مسجلة.")
      return

  # عرض المحافظات كأزرار
  keyboard = [
      [InlineKeyboardButton(province, callback_data=f"select_province_for_meals_{province}")]
      for province in provinces
  ]
  keyboard.append([InlineKeyboardButton("↩️ العودة للقائمة الرئيسية", callback_data="go_main_menu")])

  await query.edit_message_text(
      "🍔 اختر المحافظة لإدارة *الوجبات* فيها:",
      reply_markup=InlineKeyboardMarkup(keyboard),
      parse_mode="Markdown"
  )

async def handle_province_for_meals(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  province = query.data.split("select_province_for_meals_")[1]
  context.user_data["selected_province_meal"] = province

  # جلب المدن المرتبطة بالمحافظة
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT cities.name FROM cities
      JOIN provinces ON cities.province_id = provinces.id
      WHERE provinces.name = ?
      ORDER BY cities.name
  """, (province,))
  cities = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not cities:
      await query.edit_message_text("❌ لا توجد مدن مسجلة ضمن هذه المحافظة.")
      return

  keyboard = [
      [InlineKeyboardButton(city, callback_data=f"select_city_for_meals_{city}")]
      for city in cities
  ]
  keyboard.append([InlineKeyboardButton("↩️ العودة للقائمة الرئيسية", callback_data="go_main_menu")])

  await query.edit_message_text(
      f"🌆 اختر المدينة ضمن المحافظة ({province}) لإدارة الوجبات:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )


async def handle_city_for_meals(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  city = query.data.split("select_city_for_meals_")[1]
  context.user_data["selected_city_meal"] = city

  # استخدام city_id بدلًا من city name
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  # جلب معرف المدينة
  cursor.execute("SELECT id FROM cities WHERE name = ?", (city,))
  city_row = cursor.fetchone()
  if not city_row:
      await query.edit_message_text("❌ لم يتم العثور على المدينة في قاعدة البيانات.")
      conn.close()
      return

  city_id = city_row[0]

  # جلب أسماء المطاعم التي تنتمي لهذه المدينة
  cursor.execute("SELECT name FROM restaurants WHERE city_id = ?", (city_id,))
  restaurants = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not restaurants:
      await query.edit_message_text("❌ لا توجد مطاعم مسجلة ضمن هذه المدينة.")
      return

  keyboard = [
      [InlineKeyboardButton(name, callback_data=f"select_restaurant_for_meals_{name}")]
      for name in restaurants
  ]
  keyboard.append([InlineKeyboardButton("↩️ العودة للقائمة الرئيسية", callback_data="go_main_menu")])

  await query.edit_message_text(
      f"🏪 اختر المطعم ضمن المدينة ({city}) لإدارة وجباته:",
      reply_markup=InlineKeyboardMarkup(keyboard)  # ✅ الصحيح
  )


async def handle_restaurant_for_meals(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  restaurant_name = query.data.split("select_restaurant_for_meals_")[1]
  context.user_data["selected_restaurant_meal"] = restaurant_name

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id FROM restaurants WHERE name = ?", (restaurant_name,))
  result = cursor.fetchone()

  if not result:
      await query.edit_message_text("❌ لم يتم العثور على المطعم في قاعدة البيانات.")
      conn.close()
      return

  restaurant_id = result[0]
  context.user_data["selected_restaurant_id"] = restaurant_id  # ✅ إضافة هذا السطر

  cursor.execute("SELECT name FROM categories WHERE restaurant_id = ?", (restaurant_id,))
  categories = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not categories:
      await query.edit_message_text("❌ لا توجد فئات مضافة لهذا المطعم حتى الآن.")
      return

  keyboard = [
      [InlineKeyboardButton(category, callback_data=f"select_category_for_meals_{category}")]
      for category in categories
  ]
  keyboard.append([InlineKeyboardButton("↩️ العودة للقائمة الرئيسية", callback_data="go_main_menu")])

  await query.edit_message_text(
      f"📂 اختر الفئة التي تريد إدارة الوجبات ضمنها في مطعم {restaurant_name}:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )



async def show_meal_options(update: Update, context: ContextTypes.DEFAULT_TYPE, force_message=False):
  if update.callback_query:
      query = update.callback_query
      await query.answer()

      # التحقق من البيانات القادمة
      if not query.data.startswith("select_category_for_meals_"):
          category_name = context.user_data.get("selected_category_meal")
          if not category_name:
              await query.edit_message_text("⚠️ تعذر تحديد الفئة. يرجى الرجوع خطوة للخلف والمحاولة مجددًا.")
              return
      else:
          # استخراج اسم الفئة وتخزينه
          category_name = query.data.split("select_category_for_meals_")[1]
          context.user_data["selected_category_meal"] = category_name

  else:
      category_name = context.user_data.get("selected_category_meal")
      if not category_name:
          await update.message.reply_text("⚠️ تعذر تحديد الفئة. يرجى الرجوع خطوة للخلف والمحاولة مجددًا.")
          return

  # جلب معرف المطعم للعودة إليه
  restaurant_id = context.user_data.get("selected_restaurant_id")

  keyboard = [
      [InlineKeyboardButton("➕ إضافة وجبة", callback_data="add_meal")],
      [InlineKeyboardButton("❌ حذف وجبة", callback_data="delete_meal")],
      [InlineKeyboardButton("✏️ تعديل اسم وجبة", callback_data="edit_meal_name")],
      [InlineKeyboardButton("💰 تعديل سعر وجبة", callback_data="edit_meal_price")],
      [InlineKeyboardButton("✏️ تعديل الكابشن", callback_data="edit_meal_caption")],
      [InlineKeyboardButton("📸 تعديل الصورة", callback_data="edit_meal_photo")],
      [InlineKeyboardButton("📏 تعديل القياسات", callback_data="edit_meal_sizes")],
  ]

  # زر العودة إذا كان معرف المطعم موجود
  if restaurant_id:
      keyboard.append([InlineKeyboardButton("↩️ العودة لاختيار الفئة", callback_data=f"select_restaurant_for_category_{restaurant_id}")])
  else:
      keyboard.append([InlineKeyboardButton("↩️ العودة", callback_data="go_manage_meals")])

  text = f"🍽️ إدارة الوجبات ضمن الفئة: {category_name}"

  if update.callback_query:
      await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
  else:
      await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))







async def start_add_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  # استخراج البيانات من callback_data
  # تأكد أن هذه البيانات موجودة مسبقًا في user_data عند اختيار الفئة
  selected_category = context.user_data.get("selected_category_meal")
  selected_restaurant = context.user_data.get("selected_restaurant_meal")
  selected_restaurant_id = context.user_data.get("selected_restaurant_id")

  if not selected_category or not selected_restaurant or not selected_restaurant_id:
      await query.edit_message_text("⚠️ تعذر تحديد المطعم أو الفئة. يرجى الرجوع والمحاولة من جديد.")
      return

  # حفظ حالة الإضافة
  context.user_data["meal_action"] = "add"
  context.user_data["add_meal_step"] = "awaiting_meal_name"  # يمكنك استخدامها لاحقًا لو أحببت

  await query.edit_message_text("🍽️ أرسل اسم الوجبة التي تريد إضافتها:")


async def start_delete_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  category_name = context.user_data.get("selected_category_meal")
  restaurant_name = context.user_data.get("selected_restaurant_meal")

  if not category_name or not restaurant_name:
      await query.edit_message_text("⚠️ لم يتم تحديد الفئة أو المطعم.")
      return

  # جلب الوجبات ضمن الفئة
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT m.name FROM meals m
      JOIN categories c ON m.category_id = c.id
      JOIN restaurants r ON c.restaurant_id = r.id
      WHERE c.name = ? AND r.name = ?
  """, (category_name, restaurant_name))
  meals = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not meals:
      await query.edit_message_text("❌ لا توجد وجبات مسجلة ضمن هذه الفئة.")
      return

  # عرض الوجبات كأزرار
  keyboard = [
      [InlineKeyboardButton(meal, callback_data=f"confirm_delete_meal_{meal}")]
      for meal in meals
  ]
  keyboard.append([InlineKeyboardButton("↩️ العودة", callback_data="show_meal_options_again")])

  await query.edit_message_text(
      "❌ اختر الوجبة التي تريد حذفها:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )


async def handle_add_meal_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if context.user_data.get("add_meal_step") != "awaiting_photo":
      return

  if not update.message.photo:
      await update.message.reply_text("❌ يرجى إرسال صورة صالحة.")
      return

  photo_file_id = update.message.photo[-1].file_id
  meal_name = context.user_data.get("new_meal_name")
  caption = context.user_data.get("meal_caption")
  has_sizes = context.user_data.get("has_sizes")
  category_name = context.user_data.get("selected_category_meal")
  restaurant_id = context.user_data.get("selected_restaurant_id")

  unique_id = generate_unique_id()
  context.user_data["meal_unique_id"] = unique_id

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id FROM categories WHERE name = ? AND restaurant_id = ?", (category_name, restaurant_id))
  result = cursor.fetchone()

  if not result:
      await update.message.reply_text("⚠️ تعذر تحديد الفئة. حاول مجددًا.")
      conn.close()
      return

  category_id = result[0]

  if has_sizes == "لا، لا يوجد قياسات":
      price = context.user_data.get("new_meal_price")
      sizes_json = None
  else:
      size_data = context.user_data.get("sizes_data", [])
      sizes_json = json.dumps([{"name": s[0], "price": s[1]} for s in size_data], ensure_ascii=False)
      price = None

  # 🟣 أرسل الصورة إلى القناة بدون كابشن، وخزّن message_id
  try:
      admin_channel_id = ADMIN_MEDIA_CHANNEL  # ← رقم معرف القناة
      sent_message = await context.bot.send_photo(
          chat_id=admin_channel_id,
          photo=photo_file_id
      )
      image_message_id = sent_message.message_id
  except Exception as e:
      await update.message.reply_text(f"❌ فشل إرسال الصورة للقناة: {e}")
      conn.close()
      return

  # ✅ حفظ الوجبة في قاعدة البيانات
  try:
      cursor.execute("""
          INSERT INTO meals (name, price, category_id, caption, image_file_id, size_options, unique_id, image_message_id)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      """, (meal_name, price, category_id, caption, photo_file_id, sizes_json, unique_id, image_message_id))
      conn.commit()
      await update.message.reply_text(f"✅ تم حفظ الوجبة '{meal_name}' بنجاح مع الصورة.")
  except Exception as e:
      await update.message.reply_text(f"❌ حدث خطأ أثناء حفظ الوجبة: {str(e)}")
  finally:
      conn.close()

  # 🧹 تنظيف السياق
  keys_to_keep = ["selected_category_meal", "selected_restaurant_meal", "selected_restaurant_id", "selected_province_meal", "selected_city_meal"]
  preserved = {k: v for k, v in context.user_data.items() if k in keys_to_keep}
  context.user_data.clear()
  context.user_data.update(preserved)

  await show_meal_options(update, context)





async def handle_new_meal_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if context.user_data.get("meal_action") != "edit_photo":
      return

  if not update.message.photo:
      await update.message.reply_text("❌ الرجاء إرسال صورة حقيقية.")
      return

  meal_id = context.user_data.get("meal_to_edit_photo")

  # جلب unique_id و image_message_id من قاعدة البيانات
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT unique_id, image_message_id FROM meals WHERE id = ?", (meal_id,))
  result = cursor.fetchone()

  if not result:
      await update.message.reply_text("❌ لم يتم العثور على الوجبة.")
      conn.close()
      return

  unique_id, old_message_id = result
  conn.close()

  # إرسال الصورة الجديدة إلى القناة بنفس الـ unique_id
  new_photo = update.message.photo[-1].file_id
  sent = await context.bot.send_photo(
      chat_id=ADMIN_MEDIA_CHANNEL,
      photo=new_photo,
      caption=f"[{unique_id}]"
  )
  new_message_id = sent.message_id

  # تحديث قاعدة البيانات
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("UPDATE meals SET image_file_id = ?, image_message_id = ? WHERE id = ?", (
      new_photo, new_message_id, meal_id
  ))
  conn.commit()
  conn.close()

  await update.message.reply_text("✅ تم تحديث صورة الوجبة بنجاح.")

  # تنظيف الحالة
  for key in ["meal_action", "meal_to_edit_photo"]:
      context.user_data.pop(key, None)

  return await show_meal_management_menu(update, context)


from urllib.parse import quote
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo

def generate_ad_text(ad_text, ad_restaurant=None, ad_duration=None, skip_restaurant=False):
  full_text = ""
  if not skip_restaurant:
      full_text += "🔥 يالله عالسرييع 🔥\n\n"
  full_text += ad_text.strip()
  if ad_duration:
      full_text += f"\n\n⏳ ديير بالك بس لـ {ad_duration} 🕒"
  if ad_restaurant and not skip_restaurant:
      full_text += f"\n\n⬇️ اختر الزر 👇\nالقائمة الرئيسية 🪧 ← اطلب عالسريع 🔥 ← مطعم {ad_restaurant}، وتفرّج يا معلمم 😎"
  return full_text

def generate_ad_button(ad_restaurant):
  restaurant_encoded = quote(ad_restaurant)
  url = f"https://t.me/Fasterone1200_bot?start=go_{restaurant_encoded}"
  return InlineKeyboardMarkup([[InlineKeyboardButton("🍽️ اطلب عالسريع 🍽️", url=url)]])



async def handle_all_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if update.message.media_group_id:
      return await handle_ad_media_group(update, context)

  print("📸 تم استلام صورة/فيديو مفرد")
  print("📦 user_data =", context.user_data)

  if context.user_data.get("ad_step") == "awaiting_ad_media":
      ad_text = context.user_data.get("ad_text")
      ad_city = context.user_data.get("ad_city")
      ad_restaurant = context.user_data.get("ad_restaurant")
      ad_duration = context.user_data.get("ad_duration")
      skip_restaurant = context.user_data.get("ad_skip_restaurant", False)

      if not ad_text or not ad_city:
          await update.message.reply_text("⚠️ البيانات غير مكتملة. يرجى البدء من جديد.")
          context.user_data.clear()
          return await start(update, context)

      # توليد النص والزر
      full_text = generate_ad_text(ad_text, ad_restaurant, ad_duration, skip_restaurant)
      button = generate_ad_button(ad_restaurant) if not skip_restaurant else None

      # إرسال الإعلان إلى قناة واحدة أو جميع القنوات
      conn = sqlite3.connect("database.db")
      cursor = conn.cursor()

      if ad_city == "all":
          cursor.execute("SELECT ads_channel FROM cities WHERE ads_channel IS NOT NULL")
          channels = [row[0] for row in cursor.fetchall()]
      else:
          cursor.execute("SELECT ads_channel FROM cities WHERE name = ?", (ad_city,))
          result = cursor.fetchone()
          if not result or not result[0]:
              await update.message.reply_text("❌ لم يتم العثور على قناة المدينة.")
              context.user_data.clear()
              conn.close()
              return await start(update, context)
          channels = [result[0]]

      conn.close()

      # إرسال الوسائط
      file_id = update.message.photo[-1].file_id if update.message.photo else (
          update.message.video.file_id if update.message.video else None
      )
      if not file_id:
          await update.message.reply_text("❌ يجب إرسال صورة أو فيديو.")
          return

      for channel in channels:
          if update.message.photo:
              await context.bot.send_photo(chat_id=channel, photo=file_id, caption=full_text, parse_mode="Markdown", reply_markup=button)
          elif update.message.video:
              await context.bot.send_video(chat_id=channel, video=file_id, caption=full_text, parse_mode="Markdown", reply_markup=button)

      await update.message.reply_text("✅ تم إرسال الإعلان بنجاح.")
      context.user_data.clear()
      return await start(update, context)

  # تعديل صور أو إضافة وجبات
  step = context.user_data.get("add_meal_step")
  action = context.user_data.get("meal_action")
  if action == "edit_photo":
      return await handle_new_meal_photo(update, context)
  elif step == "awaiting_photo":
      return await handle_add_meal_image(update, context)

  await update.message.reply_text("❌ لم يتم التعرف على سياق الصورة الحالية.")

async def handle_ad_media_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if context.user_data.get("ad_step") != "awaiting_ad_media":
      return

  ad_text = context.user_data.get("ad_text")
  ad_city = context.user_data.get("ad_city")
  ad_restaurant = context.user_data.get("ad_restaurant")
  ad_duration = context.user_data.get("ad_duration")
  skip_restaurant = context.user_data.get("ad_skip_restaurant", False)

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT ads_channel FROM cities WHERE name = ?", (ad_city,))
  result = cursor.fetchone()
  conn.close()

  if not result or not result[0]:
      await update.message.reply_text("❌ لم يتم العثور على قناة المدينة.")
      context.user_data.clear()
      return await start(update, context)

  channel = result[0]
  full_text = generate_ad_text(ad_text, ad_restaurant, ad_duration, skip_restaurant)
  button = generate_ad_button(ad_restaurant) if not skip_restaurant else None

  media = []
  for msg in context.user_data.get("ad_media_group_msgs", []):
      if msg.photo:
          media.append(InputMediaPhoto(media=msg.photo[-1].file_id))
      elif msg.video:
          media.append(InputMediaVideo(media=msg.video.file_id))

  if media:
      media[0].caption = full_text
      media[0].parse_mode = "Markdown"
      media[0].reply_markup = button
      await context.bot.send_media_group(chat_id=channel, media=media)

  context.user_data.clear()
  await update.message.reply_text("✅ تم إرسال الإعلان كمجموعة وسائط.")
  return await start(update, context)


async def confirm_delete_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  meal_name = query.data.split("confirm_delete_meal_")[1]
  category_name = context.user_data.get("selected_category_meal")
  restaurant_name = context.user_data.get("selected_restaurant_meal")

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      DELETE FROM meals
      WHERE name = ? AND category_id = (
          SELECT c.id FROM categories c
          JOIN restaurants r ON c.restaurant_id = r.id
          WHERE c.name = ? AND r.name = ?
      )
  """, (meal_name, category_name, restaurant_name))
  conn.commit()
  conn.close()

  await query.edit_message_text(f"🗑️ تم حذف الوجبة: {meal_name}")
  # الرجوع إلى شاشة إدارة الوجبات بنفس الفئة
  return await show_meal_options(update, context)


async def start_edit_meal_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  category_name = context.user_data.get("selected_category_meal")
  restaurant_name = context.user_data.get("selected_restaurant_meal")

  if not category_name or not restaurant_name:
      await query.edit_message_text("⚠️ لم يتم تحديد الفئة أو المطعم.")
      return

  # جلب أسماء الوجبات
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT m.name FROM meals m
      JOIN categories c ON m.category_id = c.id
      JOIN restaurants r ON c.restaurant_id = r.id
      WHERE c.name = ? AND r.name = ?
  """, (category_name, restaurant_name))
  meals = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not meals:
      await query.edit_message_text("❌ لا توجد وجبات ضمن هذه الفئة.")
      return

  keyboard = [
      [InlineKeyboardButton(meal, callback_data=f"select_meal_to_rename_{meal}")]
      for meal in meals
  ]
  keyboard.append([InlineKeyboardButton("↩️ العودة", callback_data="show_meal_options_again")])

  await query.edit_message_text(
      "✏️ اختر الوجبة التي تريد تعديل اسمها:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )



async def ask_new_meal_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  old_meal_name = query.data.split("select_meal_to_rename_")[1]
  context.user_data["meal_action"] = "edit_name"
  context.user_data["old_meal_name"] = old_meal_name

  await query.edit_message_text(f"📝 أرسل الاسم الجديد للوجبة: {old_meal_name}")




async def start_edit_meal_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  category = context.user_data.get("selected_category_meal")
  restaurant = context.user_data.get("selected_restaurant_meal")

  if not category or not restaurant:
      await query.edit_message_text("⚠️ لم يتم تحديد الفئة أو المطعم.")
      return

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT m.name FROM meals m
      JOIN categories c ON m.category_id = c.id
      JOIN restaurants r ON c.restaurant_id = r.id
      WHERE c.name = ? AND r.name = ?
  """, (category, restaurant))
  meals = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not meals:
      await query.edit_message_text("❌ لا توجد وجبات في هذه الفئة.")
      return

  keyboard = [[InlineKeyboardButton(meal, callback_data=f"select_meal_to_edit_price_{meal}")] for meal in meals]
  keyboard.append([InlineKeyboardButton("↩️ العودة", callback_data="show_meal_options_again")])

  await query.edit_message_text(
      "💰 اختر الوجبة التي تريد تعديل سعرها:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )



async def ask_new_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  meal_name = query.data.replace("edit_price_", "")
  context.user_data["meal_to_edit_price"] = meal_name

  category = context.user_data.get("selected_category_meal")
  restaurant = context.user_data.get("selected_restaurant_meal")

  cursor = db_conn.cursor()
  cursor.execute("""
      SELECT size_options, price FROM meals
      WHERE name = ? AND category_id = (
          SELECT c.id FROM categories c
          JOIN restaurants r ON c.restaurant_id = r.id
          WHERE c.name = ? AND r.name = ?
      )
  """, (meal_name, category, restaurant))
  result = cursor.fetchone()

  if not result:
      await query.edit_message_text("❌ لم يتم العثور على الوجبة.")
      return

  size_options, base_price = result
  sizes = json.loads(size_options) if size_options else []

  if not sizes:
      context.user_data["edit_step"] = "single_price"
      await query.edit_message_text(f"💰 السعر الحالي: {base_price} ل.س\n\nأرسل السعر الجديد:")
  else:
      context.user_data["edit_step"] = "multi_price"
      context.user_data["sizes_list"] = sizes
      context.user_data["price_sizes"] = {}
      size, current_price = sizes[0].split("/")
      await query.edit_message_text(
          f"💰 القياسات الحالية:\n{', '.join(sizes)}\n\n"
          f"أرسل السعر الجديد للقياس: {size} (الحالي {current_price} ل.س)"
      )




async def ask_price_for_each_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  meal_name = query.data.split("edit_price_")[1]
  context.user_data["meal_action"] = "edit_price"
  context.user_data["meal_to_edit_price"] = meal_name

  category = context.user_data.get("selected_category_meal")
  restaurant = context.user_data.get("selected_restaurant_meal")

  # جلب القياسات من قاعدة البيانات مباشرة
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT size_options FROM meals
      WHERE name = ? AND category_id = (
          SELECT c.id FROM categories c
          JOIN restaurants r ON c.restaurant_id = r.id
          WHERE c.name = ? AND r.name = ?
      )
  """, (meal_name, category, restaurant))
  result = cursor.fetchone()
  conn.close()

  sizes = json.loads(result[0]) if result and result[0] else []

  if sizes:  # ✅ الوجبة تحتوي على قياسات
      context.user_data["edit_price_sizes"] = sizes
      context.user_data["edit_price_data"] = {}
      context.user_data["edit_price_step"] = "multi_price"
      context.user_data["current_size_index"] = 0

      current_size = sizes[0]
      size_name = current_size["name"]
      current_price = current_size["price"]

      sizes_text = ", ".join([f"{s['name']}/{s['price']}" for s in sizes])
      await query.edit_message_text(
          f"💰 القياسات الحالية: {sizes_text}\n\n"
          f"أرسل السعر الجديد للقياس: {size_name} (السعر الحالي: {current_price} ل.س)"
      )

  else:  # ✅ لا تحتوي على قياسات
      context.user_data["edit_price_sizes"] = []
      context.user_data["edit_price_step"] = "single_price"
      await query.edit_message_text(
          f"💰 هذه الوجبة ليس لها قياسات.\nأرسل السعر الجديد للوجبة: {meal_name}"
      )




async def handle_edit_price_step_by_step(update: Update, context: CallbackContext):
  step = context.user_data.get("edit_step")
  text = update.message.text.strip()

  if not text.isdigit():
      await update.message.reply_text("❌ السعر يجب أن يكون رقمًا.")
      return

  meal = context.user_data.get("meal_to_edit_price")
  category = context.user_data.get("selected_category_meal")
  restaurant = context.user_data.get("selected_restaurant_meal")

  if step == "single_price":
      price = int(text)
      cursor = db_conn.cursor()
      cursor.execute("""
          UPDATE meals SET price = ?, size_options = NULL
          WHERE name = ? AND category_id = (
              SELECT c.id FROM categories c
              JOIN restaurants r ON c.restaurant_id = r.id
              WHERE c.name = ? AND r.name = ?
          )
      """, (price, meal, category, restaurant))
      db_conn.commit()

      await update.message.reply_text("✅ تم تعديل السعر بنجاح.")
  elif step == "multi_price":
      sizes = context.user_data["sizes_list"]
      index = len(context.user_data["price_sizes"])

      size, _ = sizes[index].split("/")
      context.user_data["price_sizes"][size] = int(text)

      if index + 1 < len(sizes):
          next_size, next_price = sizes[index + 1].split("/")
          await update.message.reply_text(f"💬 أرسل السعر الجديد للقياس: {next_size} (الحالي {next_price} ل.س)")
      else:
          # حفظ كل الأسعار بعد الانتهاء
          updated_sizes = [f"{s}/{p}" for s, p in context.user_data["price_sizes"].items()]
          base_price = max(context.user_data["price_sizes"].values())

          cursor = db_conn.cursor()
          cursor.execute("""
              UPDATE meals SET price = ?, size_options = ?
              WHERE name = ? AND category_id = (
                  SELECT c.id FROM categories c
                  JOIN restaurants r ON c.restaurant_id = r.id
                  WHERE c.name = ? AND r.name = ?
              )
          """, (base_price, json.dumps(updated_sizes, ensure_ascii=False), meal, category, restaurant))
          db_conn.commit()

          await update.message.reply_text("✅ تم تعديل الأسعار لجميع القياسات بنجاح.")

  # تنظيف المتغيرات
  for key in ["edit_step", "meal_to_edit_price", "sizes_list", "price_sizes"]:
      context.user_data.pop(key, None)

  await show_meal_management_menu(update, context)




async def handle_edit_meal_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
  step = context.user_data.get("edit_step")
  meal_name = context.user_data.get("edit_meal_name")
  category_name = context.user_data.get("selected_category_meal")
  restaurant_name = context.user_data.get("selected_restaurant_meal")

  if not all([step, meal_name, category_name, restaurant_name]):
      await update.message.reply_text("❌ البيانات غير مكتملة.")
      return

  value = update.message.text.strip()
  cursor = db_conn.cursor()

  try:
      if step == "caption":
          cursor.execute("""
              UPDATE meals
              SET caption = ?
              WHERE name = ? AND category_id = (
                  SELECT c.id FROM categories c
                  JOIN restaurants r ON c.restaurant_id = r.id
                  WHERE c.name = ? AND r.name = ?
              )
          """, (value, meal_name, category_name, restaurant_name))
          await update.message.reply_text("✅ تم تعديل الكابشن بنجاح.")

      elif step == "sizes":
          sizes = [s.strip() for s in value.split(",") if s.strip()]
          cursor.execute("""
              UPDATE meals
              SET size_options = ?
              WHERE name = ? AND category_id = (
                  SELECT c.id FROM categories c
                  JOIN restaurants r ON c.restaurant_id = r.id
                  WHERE c.name = ? AND r.name = ?
              )
          """, (json.dumps(sizes, ensure_ascii=False), meal_name, category_name, restaurant_name))
          await update.message.reply_text("✅ تم تعديل القياسات بنجاح.")

      elif step == "edit_price_single":
          if not value.isdigit():
              await update.message.reply_text("❌ الرجاء إدخال رقم فقط.")
              return
          new_price = int(value)
          cursor.execute("""
              UPDATE meals
              SET price = ?
              WHERE name = ? AND category_id = (
                  SELECT c.id FROM categories c
                  JOIN restaurants r ON c.restaurant_id = r.id
                  WHERE c.name = ? AND r.name = ?
              )
          """, (new_price, meal_name, category_name, restaurant_name))
          await update.message.reply_text("✅ تم تعديل السعر بنجاح.")

      elif step == "edit_price_multiple":
          try:
              size_price_pairs = [part.strip() for part in value.split(",")]
              sizes = context.user_data.get("current_sizes", [])
              prices_dict = {}

              for pair in size_price_pairs:
                  if "/" not in pair:
                      raise ValueError("صيغة غير صحيحة: استخدم قياس/سعر")
                  size, price_str = pair.split("/")
                  size = size.strip()
                  price = int(price_str.strip())
                  if size not in sizes:
                      raise ValueError(f"القياس '{size}' غير موجود")
                  prices_dict[size] = price

              max_price = max(prices_dict.values())
              cursor.execute("""
                  UPDATE meals
                  SET price = ?, size_options = ?
                  WHERE name = ? AND category_id = (
                      SELECT c.id FROM categories c
                      JOIN restaurants r ON c.restaurant_id = r.id
                      WHERE c.name = ? AND r.name = ?
                  )
              """, (
                  max_price,
                  json.dumps([f"{s}/{p}" for s, p in prices_dict.items()], ensure_ascii=False),
                  meal_name,
                  category_name,
                  restaurant_name
              ))
              await update.message.reply_text("✅ تم تعديل أسعار القياسات بنجاح.")

          except Exception as e:
              logger.error(f"خطأ في تعديل سعر وجبة متعددة القياسات: {e}")
              await update.message.reply_text("❌ حدث خطأ أثناء حفظ الأسعار. تأكد من التنسيق (مثال: صغير/2000, وسط/3000).")
              return

  except Exception as e:
      logger.error(f"❌ خطأ أثناء تعديل بيانات الوجبة: {e}")
      await update.message.reply_text("❌ حدث خطأ أثناء حفظ التعديلات.")

  finally:
      db_conn.commit()

  # تنظيف
  for key in ["edit_meal_name", "edit_step", "current_sizes", "current_price"]:
      context.user_data.pop(key, None)

  await show_meal_management_menu(update, context)



async def handle_add_meal_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
  meal_name = update.message.text.strip()
  if not meal_name:
      await update.message.reply_text("❌ الرجاء إدخال اسم صالح للوجبة.")
      return

  context.user_data["new_meal_name"] = meal_name
  await update.message.reply_text("💰 الرجاء إدخال سعر الوجبة (رقم فقط):")
  context.user_data["add_meal_step"] = "awaiting_price"


async def handle_add_meal_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if context.user_data.get("add_meal_step") != "awaiting_price":
      return

  price_text = update.message.text.strip()
  if not price_text.isdigit():
      await update.message.reply_text("❌ السعر يجب أن يكون رقمًا.")
      return

  context.user_data["new_meal_price"] = int(price_text)
  await update.message.reply_text("✏️ أدخل مكونات أو وصف الوجبة (الكابشن):")
  context.user_data["add_meal_step"] = "awaiting_caption"


async def handle_add_meal_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if context.user_data.get("add_meal_step") != "awaiting_caption":
      return

  context.user_data["new_meal_caption"] = update.message.text.strip()
  await update.message.reply_text("📷 الرجاء إرسال صورة الوجبة الآن:")
  context.user_data["add_meal_step"] = "awaiting_photo"


async def handle_add_meal_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if context.user_data.get("add_meal_step") != "awaiting_photo":
      return

  if not update.message.photo:
      await update.message.reply_text("❌ الرجاء إرسال صورة حقيقية.")
      return

  file_id = update.message.photo[-1].file_id
  context.user_data["new_meal_image_id"] = file_id

  # الآن نطلب القياسات أو الحجم
  reply_markup = ReplyKeyboardMarkup([["نعم، لها قياسات", "لا، لا يوجد قياسات"]], resize_keyboard=True)
  await update.message.reply_text("📏 هل لهذه الوجبة قياسات مختلفة (صغير، وسط، كبير...)?", reply_markup=reply_markup)
  context.user_data["add_meal_step"] = "awaiting_size_option"


async def handle_add_meal_size_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
  decision = update.message.text.strip()

  if decision == "نعم، لها قياسات":
      context.user_data["has_sizes"] = "نعم، لها قياسات"
      context.user_data["add_meal_step"] = "awaiting_size_values"
      await update.message.reply_text("📝 الرجاء إدخال القياسات مفصولة بفواصل (مثال: صغير/2000، وسط/3000، كبير/4000):")

  elif decision == "لا، لا يوجد قياسات":
      context.user_data["has_sizes"] = "لا، لا يوجد قياسات"
      context.user_data["add_meal_step"] = "awaiting_single_price"
      await update.message.reply_text("💰 أرسل سعر الوجبة (رقم فقط):")

  else:
      await update.message.reply_text("❌ يرجى اختيار خيار من الأزرار.")




async def handle_add_meal_sizes(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if context.user_data.get("add_meal_step") != "awaiting_size_values":
      return

  sizes = [s.strip() for s in update.message.text.split(",") if s.strip()]
  if not sizes:
      await update.message.reply_text("❌ لم يتم إدخال أي قياسات. أعد المحاولة.")
      return

  context.user_data["new_meal_sizes"] = sizes
  await save_meal_to_database(update, context)


async def save_meal_to_database(update, context):
  name = context.user_data.get("new_meal_name")
  price = context.user_data.get("new_meal_price")
  caption = context.user_data.get("new_meal_caption")
  image_id = context.user_data.get("new_meal_image_id")

  # تحويل القياسات لصيغة موحّدة
  raw_sizes = context.user_data.get("new_meal_sizes", [])
  size_options = []
  for item in raw_sizes:
      if isinstance(item, str) and "/" in item:
          name_part, price_part = item.split("/", 1)
          try:
              size_options.append({"name": name_part.strip(), "price": int(price_part.strip())})
          except ValueError:
              continue  # تجاهل أي خطأ بالصياغة
      elif isinstance(item, dict):
          size_options.append(item)  # إذا كان dict منطق قديم أو تعديل

  # إذا لا يوجد قياسات (وجبة عادية)
  size_options_json = json.dumps(size_options, ensure_ascii=False) if size_options else None

  selected_category = context.user_data.get("selected_category")
  if not selected_category:
      await update.message.reply_text("❌ لم يتم تحديد الفئة. أعد المحاولة من البداية.")
      return

  # جلب category_id
  cursor = db_conn.cursor()
  cursor.execute("SELECT id FROM categories WHERE name = ?", (selected_category,))
  category_row = cursor.fetchone()
  if not category_row:
      await update.message.reply_text("❌ لم يتم العثور على الفئة في قاعدة البيانات.")
      return

  category_id = category_row[0]

  # إذا كانت لا تحتوي قياسات، نحفظ السعر كـ price عادي، أما إذا فيها قياسات، نخليه None (ونعتمد الأسعار من القياسات)
  save_price = price if not size_options else None

  try:
      cursor.execute("""
          INSERT INTO meals (name, price, category_id, caption, image_file_id, size_options)
          VALUES (?, ?, ?, ?, ?, ?)
      """, (
          name, save_price, category_id, caption, image_id, size_options_json
      ))
      db_conn.commit()
      await update.message.reply_text("✅ تم حفظ الوجبة بنجاح.")
  except Exception as e:
      logger.error(f"❌ خطأ أثناء الحفظ: {e}")
      await update.message.reply_text("❌ حدث خطأ أثناء حفظ الوجبة. تأكد من أن الاسم غير مكرر.")

  # تنظيف البيانات المؤقتة
  for key in list(context.user_data.keys()):
      if key.startswith("new_meal") or key == "add_meal_step":
          del context.user_data[key]

  # العودة للقائمة السابقة أو عرض ملخص حسب نظامك
  # await show_meal_management_menu(update, context)



async def handle_add_meal_name_price_caption_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
  step = context.user_data.get("add_meal_step")

  if step == "awaiting_meal_name":
      context.user_data["new_meal_name"] = update.message.text.strip()
      context.user_data["add_meal_step"] = "awaiting_meal_price"
      await update.message.reply_text("💰 أرسل السعر (أرقام فقط):")

  elif step == "awaiting_meal_price":
      if not update.message.text.strip().isdigit():
          await update.message.reply_text("❌ السعر غير صحيح. الرجاء إدخال رقم.")
          return
      context.user_data["new_meal_price"] = int(update.message.text.strip())
      context.user_data["add_meal_step"] = "awaiting_meal_caption"
      await update.message.reply_text("📝 أرسل وصف المكونات (مثل: جبنة، خضار، زيتون):")

  elif step == "awaiting_meal_caption":
      context.user_data["new_meal_caption"] = update.message.text.strip()
      context.user_data["add_meal_step"] = "awaiting_meal_image"
      await update.message.reply_text("📷 أرسل صورة للوجبة:")

  else:
      return  # تجاهل أي نصوص خارج السياق الحالي


async def start_edit_meal_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  category_name = context.user_data.get("selected_category_meal")
  restaurant_name = context.user_data.get("selected_restaurant_meal")

  if not category_name or not restaurant_name:
      await query.edit_message_text("⚠️ لم يتم تحديد الفئة أو المطعم.")
      return

  # جلب الوجبات بالـ id والاسم
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT m.id, m.name FROM meals m
      JOIN categories c ON m.category_id = c.id
      JOIN restaurants r ON c.restaurant_id = r.id
      WHERE c.name = ? AND r.name = ?
  """, (category_name, restaurant_name))
  meals = cursor.fetchall()
  conn.close()

  if not meals:
      await query.edit_message_text("❌ لا توجد وجبات في هذه الفئة.")
      return

  keyboard = [
      [InlineKeyboardButton(meal_name, callback_data=f"edit_caption_{meal_id}")]
      for meal_id, meal_name in meals
  ]
  keyboard.append([InlineKeyboardButton("↩️ العودة", callback_data="show_meal_options_again")])

  await query.edit_message_text(
      "✏️ اختر الوجبة التي تريد تعديل مكوناتها (الكابشن):",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )



async def ask_new_meal_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  meal_id = int(query.data.split("edit_caption_")[1])  # ✅ مطابق تمامًا لما أُرسل من الزر
  context.user_data["meal_action"] = "edit_caption"
  context.user_data["meal_to_edit_caption_id"] = meal_id

  # جلب اسم الوجبة فقط للعرض
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT name FROM meals WHERE id = ?", (meal_id,))
  result = cursor.fetchone()
  conn.close()

  meal_name = result[0] if result else "غير معروف"
  await query.edit_message_text(f"📝 أرسل المكونات أو الكابشن الجديد للوجبة: {meal_name}")




async def start_edit_meal_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
  print("📸 دخلنا إلى start_edit_meal_photo")
  query = update.callback_query
  await query.answer()

  category_name = context.user_data.get("selected_category_meal")
  restaurant_name = context.user_data.get("selected_restaurant_meal")

  if not category_name or not restaurant_name:
      await query.edit_message_text("⚠️ لم يتم تحديد الفئة أو المطعم.")
      return

  # جلب الوجبات بالـ id والاسم
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT m.id, m.name FROM meals m
      JOIN categories c ON m.category_id = c.id
      JOIN restaurants r ON c.restaurant_id = r.id
      WHERE c.name = ? AND r.name = ?
  """, (category_name, restaurant_name))
  meals = cursor.fetchall()
  conn.close()

  if not meals:
      await query.edit_message_text("❌ لا توجد وجبات في هذه الفئة.")
      return

  keyboard = [
      [InlineKeyboardButton(meal_name, callback_data=f"select_meal_to_edit_photo_{meal_id}")]
      for meal_id, meal_name in meals
  ]
  keyboard.append([InlineKeyboardButton("↩️ العودة", callback_data="show_meal_options_again")])

  await query.edit_message_text(
      "📸 اختر الوجبة التي تريد تعديل صورتها:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )


async def start_edit_meal_sizes(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  category = context.user_data.get("selected_category_meal")
  restaurant = context.user_data.get("selected_restaurant_meal")

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT m.name, m.size_options FROM meals m
      JOIN categories c ON m.category_id = c.id
      JOIN restaurants r ON c.restaurant_id = r.id
      WHERE c.name = ? AND r.name = ?
  """, (category, restaurant))
  meals = cursor.fetchall()
  conn.close()

  if not meals:
      await query.edit_message_text("❌ لا توجد وجبات.")
      return

  keyboard = []
  for name, size_json in meals:
      sizes = json.loads(size_json) if size_json else []
      label = f"{name} ({'بدون قياسات' if not sizes else 'بقياسات'})"
      keyboard.append([InlineKeyboardButton(label, callback_data=f"edit_sizes_for_meal_{name}")])

  keyboard.append([InlineKeyboardButton("↩️ العودة", callback_data="show_meal_options_again")])

  await query.edit_message_text("📏 اختر وجبة لتعديل قياساتها:", reply_markup=InlineKeyboardMarkup(keyboard))

async def ask_new_meal_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  meal_id = int(query.data.split("select_meal_to_edit_photo_")[1])
  context.user_data["meal_action"] = "edit_photo"
  context.user_data["meal_to_edit_photo"] = meal_id

  # جلب اسم الوجبة للعرض فقط
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT name FROM meals WHERE id = ?", (meal_id,))
  result = cursor.fetchone()
  conn.close()

  meal_name = result[0] if result else "غير معروف"
  await query.edit_message_text(f"📸 الرجاء إرسال الصورة الجديدة للوجبة: {meal_name}")


async def ask_edit_size_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  meal_name = query.data.split("edit_sizes_for_meal_")[1]
  context.user_data["meal_action"] = "edit_sizes"
  context.user_data["meal_to_edit_sizes"] = meal_name

  # التحقق هل لها قياسات
  category = context.user_data.get("selected_category_meal")
  restaurant = context.user_data.get("selected_restaurant_meal")

  cursor = db_conn.cursor()
  cursor.execute("""
      SELECT size_options FROM meals
      WHERE name = ? AND category_id = (
          SELECT c.id FROM categories c
          JOIN restaurants r ON c.restaurant_id = r.id
          WHERE c.name = ? AND r.name = ?
      )
  """, (meal_name, category, restaurant))
  result = cursor.fetchone()

  if not result:
      await query.edit_message_text("❌ لم يتم العثور على الوجبة.")
      return

  current_sizes = json.loads(result[0]) if result[0] else []

  if not current_sizes:
      context.user_data["edit_step"] = "add_sizes_to_empty"
      await query.edit_message_text(
          "🔍 هذه الوجبة لا تحتوي على قياسات.\n"
          "أرسل القياسات الجديدة بصيغة مثل:\n\n"
          "`عائلي/5000, وسط/4000, صغير/3000`",
          parse_mode="Markdown"
      )
  else:
      # حفظ القياسات الحالية مؤقتًا
      context.user_data["existing_sizes"] = current_sizes
      keyboard = [
          [InlineKeyboardButton("➕ إضافة قياس", callback_data="add_size_to_meal")],
          [InlineKeyboardButton("❌ حذف قياس", callback_data="delete_size_choice")],
          [InlineKeyboardButton("↩️ العودة", callback_data="show_meal_options_again")]
      ]
      await query.edit_message_text("📏 اختر إجراء لتعديل القياسات:", reply_markup=InlineKeyboardMarkup(keyboard))



async def ask_add_single_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  context.user_data["edit_step"] = "add_single_size"
  context.user_data["meal_action"] = "edit_sizes"
  await query.edit_message_text("✏️ أرسل القياس الجديد بصيغة: وسط/6000")


async def ask_add_new_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  context.user_data["edit_step"] = "add_single_size"  # تثبيت القيمة الموحدة
  await query.edit_message_text(
      "➕ أرسل القياس الجديد مع سعره بصيغة:\n\nاسم الحجم/السعر\n\nمثال: دبل/7000"
  )


async def handle_add_new_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if context.user_data.get("edit_step") != "add_single_size":
      return

  text = update.message.text.strip()
  if "/" not in text:
      await update.message.reply_text("❌ استخدم الصيغة: اسم القياس/السعر (مثال: كبير/6000)")
      return

  try:
      name, price = text.split("/")
      name = name.strip()
      price = int(price.strip())
  except:
      await update.message.reply_text("❌ تأكد من كتابة القياس والسعر بشكل صحيح.")
      return

  meal_name = context.user_data.get("meal_to_edit_sizes")
  category = context.user_data.get("selected_category_meal")
  restaurant = context.user_data.get("selected_restaurant_meal")

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT size_options FROM meals
      WHERE name = ? AND category_id = (
          SELECT c.id FROM categories c
          JOIN restaurants r ON c.restaurant_id = r.id
          WHERE c.name = ? AND r.name = ?
      )
  """, (meal_name, category, restaurant))
  result = cursor.fetchone()

  sizes = json.loads(result[0]) if result and result[0] else []

  # تحقق من التكرار
  if any(s.split("/")[0] == name for s in sizes):
      await update.message.reply_text("⚠️ هذا القياس موجود مسبقًا.")
      conn.close()
      return

  sizes.append(f"{name}/{price}")

  cursor.execute("""
      UPDATE meals SET size_options = ?
      WHERE name = ? AND category_id = (
          SELECT c.id FROM categories c
          JOIN restaurants r ON c.restaurant_id = r.id
          WHERE c.name = ? AND r.name = ?
      )
  """, (json.dumps(sizes, ensure_ascii=False), meal_name, category, restaurant))
  conn.commit()
  conn.close()

  await update.message.reply_text("✅ تم إضافة القياس بنجاح.")
  context.user_data.pop("edit_step", None)
  context.user_data.pop("meal_to_edit_sizes", None)
  await show_meal_management_menu(update, context)






async def ask_new_meal_sizes(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  meal_name = query.data.split("select_meal_to_edit_sizes_")[1]
  context.user_data["meal_to_edit_sizes"] = meal_name

  category = context.user_data.get("selected_category_meal")
  restaurant = context.user_data.get("selected_restaurant_meal")

  cursor = db_conn.cursor()
  cursor.execute("""
      SELECT size_options FROM meals
      WHERE name = ? AND category_id = (
          SELECT c.id FROM categories c
          JOIN restaurants r ON c.restaurant_id = r.id
          WHERE c.name = ? AND r.name = ?
      )
  """, (meal_name, category, restaurant))
  result = cursor.fetchone()
  cursor.close()

  if not result or not result[0]:
      await query.edit_message_text(
          "❌ لا توجد قياسات حالية.\n"
          "📥 أرسل القياسات الجديدة مع أسعارها بصيغة: وسط/5000, كبير/7000",
      )
      context.user_data["edit_step"] = "add_sizes_to_empty"
  else:
      sizes = json.loads(result[0])
      keyboard = [
          [InlineKeyboardButton("➕ إضافة قياس", callback_data="add_new_size")],
          [InlineKeyboardButton("❌ حذف قياس", callback_data="remove_existing_size")]
      ]
      await query.edit_message_text(
          f"📏 القياسات الحالية:\n" + "\n".join(sizes) + "\n\n"
          "ماذا تريد أن تفعل؟",
          reply_markup=InlineKeyboardMarkup(keyboard)
      )

async def handle_add_sizes_to_empty_meal(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if context.user_data.get("edit_step") != "add_sizes_to_empty":
      return

  text = update.message.text.strip()
  if not text:
      await update.message.reply_text("❌ يرجى إدخال القياسات مع الأسعار.")
      return

  try:
      sizes = [s.strip() for s in text.split(",")]
      formatted_sizes = []

      for s in sizes:
          name, price = s.split("/")
          formatted_sizes.append(f"{name.strip()}/{int(price.strip())}")
  except Exception:
      await update.message.reply_text("❌ تأكد من كتابة القياسات بشكل صحيح مثل: صغير/3000, كبير/5000")
      return

  meal_name = context.user_data.get("meal_to_edit_sizes")
  category = context.user_data.get("selected_category_meal")
  restaurant = context.user_data.get("selected_restaurant_meal")

  cursor = db_conn.cursor()
  cursor.execute("""
      UPDATE meals SET size_options = ?, price = ?
      WHERE name = ? AND category_id = (
          SELECT c.id FROM categories c
          JOIN restaurants r ON c.restaurant_id = r.id
          WHERE c.name = ? AND r.name = ?
      )
  """, (json.dumps(formatted_sizes), max(int(s.split("/")[1]) for s in formatted_sizes), meal_name, category, restaurant))
  db_conn.commit()

  await update.message.reply_text("✅ تم حفظ القياسات بنجاح.")
  context.user_data.pop("edit_step", None)
  context.user_data.pop("meal_to_edit_sizes", None)
  await show_meal_management_menu(update, context)



async def ask_which_size_to_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  meal_name = context.user_data.get("meal_to_edit_sizes")
  category = context.user_data.get("selected_category_meal")
  restaurant = context.user_data.get("selected_restaurant_meal")

  cursor = db_conn.cursor()
  cursor.execute("""
      SELECT size_options FROM meals
      WHERE name = ? AND category_id = (
          SELECT c.id FROM categories c
          JOIN restaurants r ON c.restaurant_id = r.id
          WHERE c.name = ? AND r.name = ?
      )
  """, (meal_name, category, restaurant))
  result = cursor.fetchone()
  cursor.close()

  if not result or not result[0]:
      await query.edit_message_text("❌ لا توجد قياسات لحذفها.")
      return

  sizes = json.loads(result[0])
  if not sizes:
      await query.edit_message_text("❌ لا توجد قياسات لحذفها.")
      return

  keyboard = []
  for s in sizes:
      name = str(s.get("name", "")).strip()
      price = str(s.get("price", "")).strip()

      if not name:
          continue  # تجاهل أي قياس غير صالح

      button_text = f"{name} ({price} ل.س)"
      callback_data = f"remove_size_{name}"

      keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

  keyboard.append([InlineKeyboardButton("↩️ العودة", callback_data="show_meal_options_again")])

  await query.edit_message_text(
      "🗑️ اختر القياس الذي تريد حذفه:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )








async def handle_remove_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  size_to_remove = query.data.split("remove_size_")[1]
  meal_name = context.user_data.get("meal_to_edit_sizes")
  category = context.user_data.get("selected_category_meal")
  restaurant = context.user_data.get("selected_restaurant_meal")

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT size_options FROM meals
      WHERE name = ? AND category_id = (
          SELECT c.id FROM categories c
          JOIN restaurants r ON c.restaurant_id = r.id
          WHERE c.name = ? AND r.name = ?
      )
  """, (meal_name, category, restaurant))
  result = cursor.fetchone()

  if not result or not result[0]:
      await query.edit_message_text("❌ لا توجد قياسات لحذفها.")
      conn.close()
      return

  sizes = json.loads(result[0])
  print("📋 size_to_remove:", repr(size_to_remove))
  print("📋 available sizes:", [repr(s["name"]) for s in sizes])
  updated_sizes = [s for s in sizes if s["name"].strip() != size_to_remove.strip()]

  if len(updated_sizes) == len(sizes):
      await query.edit_message_text("⚠️ لم يتم العثور على القياس المحدد.")
      conn.close()
      return

  if len(updated_sizes) == 1:
      # إذا تبقى قياس واحد فقط ➔ نحول الوجبة إلى وجبة بلا قياسات
      remaining_size = updated_sizes[0]
      new_price = remaining_size["price"]

      cursor.execute("""
          UPDATE meals SET size_options = NULL, price = ?
          WHERE name = ? AND category_id = (
              SELECT c.id FROM categories c
              JOIN restaurants r ON c.restaurant_id = r.id
              WHERE c.name = ? AND r.name = ?
          )
      """, (
          new_price,
          meal_name, category, restaurant
      ))
      conn.commit()
      conn.close()

      await query.edit_message_text(f"✅ تم حذف القياس {size_to_remove} بنجاح.\n⚡ الوجبة الآن أصبحت بدون قياسات.")
  else:
      # إذا تبقى أكثر من قياس
      new_base_price = max([s["price"] for s in updated_sizes]) if updated_sizes else 0
      cursor.execute("""
          UPDATE meals SET size_options = ?, price = ?
          WHERE name = ? AND category_id = (
              SELECT c.id FROM categories c
              JOIN restaurants r ON c.restaurant_id = r.id
              WHERE c.name = ? AND r.name = ?
          )
      """, (
          json.dumps(updated_sizes, ensure_ascii=False),
          new_base_price,
          meal_name, category, restaurant
      ))
      conn.commit()
      conn.close()

      await query.edit_message_text(f"✅ تم حذف القياس {size_to_remove} بنجاح.")

  # تنظيف البيانات
  for key in ["edit_step", "meal_to_edit_sizes", "existing_sizes", "meal_action"]:
      context.user_data.pop(key, None)

  await show_meal_management_menu(update, context)



async def handle_new_meal_sizes(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if context.user_data.get("edit_step") != "add_sizes_to_empty":
      return

  text = update.message.text.strip()
  if not text:
      await update.message.reply_text("❌ يرجى إدخال القياسات مع الأسعار.")
      return

  try:
      sizes = [s.strip() for s in text.split(",")]
      formatted_sizes = []

      for s in sizes:
          if "/" not in s:
              raise ValueError("صيغة غير صحيحة.")
          name, price = s.split("/")
          name = name.strip()
          price = int(price.strip())
          formatted_sizes.append(f"{name}/{price}")
  except Exception:
      await update.message.reply_text("❌ تأكد من كتابة القياسات بشكل صحيح مثل: صغير/3000, كبير/5000")
      return

  meal_name = context.user_data.get("meal_to_edit_sizes")
  category = context.user_data.get("selected_category_meal")
  restaurant = context.user_data.get("selected_restaurant_meal")

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      UPDATE meals SET size_options = ?, price = ?
      WHERE name = ? AND category_id = (
          SELECT c.id FROM categories c
          JOIN restaurants r ON c.restaurant_id = r.id
          WHERE c.name = ? AND r.name = ?
      )
  """, (
      json.dumps(formatted_sizes, ensure_ascii=False),
      max(int(s.split("/")[1]) for s in formatted_sizes),
      meal_name, category, restaurant
  ))
  conn.commit()
  conn.close()

  await update.message.reply_text("✅ تم حفظ القياسات بنجاح.")
  context.user_data.pop("edit_step", None)
  context.user_data.pop("meal_to_edit_sizes", None)
  await show_meal_management_menu(update, context)

async def show_meal_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
  keyboard = [
      [InlineKeyboardButton("➕ إضافة وجبة", callback_data="add_meal")],
      [InlineKeyboardButton("❌ حذف وجبة", callback_data="delete_meal")],
      [InlineKeyboardButton("✏️ تعديل اسم وجبة", callback_data="edit_meal_name")],
      [InlineKeyboardButton("💰 تعديل سعر وجبة", callback_data="edit_meal_price")],
      [InlineKeyboardButton("✏️ تعديل الكابشن", callback_data="edit_meal_caption")],
      [InlineKeyboardButton("📸 تعديل الصورة", callback_data="edit_meal_photo")],
      [InlineKeyboardButton("📏 تعديل القياسات", callback_data="edit_meal_sizes")],
  ]

  query = update.callback_query if update.callback_query else None
  if query:
      await query.edit_message_text("📋 قائمة إدارة الوجبات:", reply_markup=InlineKeyboardMarkup(keyboard))
  else:
      await update.message.reply_text("📋 قائمة إدارة الوجبات:", reply_markup=InlineKeyboardMarkup(keyboard))




async def _choose_meal_for_edit(update, context, action_key, message):
  query = update.callback_query
  await query.answer()
  category = context.user_data.get("selected_category_meal")
  restaurant = context.user_data.get("selected_restaurant_meal")

  cursor = db_conn.cursor()
  cursor.execute("""
      SELECT m.name FROM meals m
      JOIN categories c ON m.category_id = c.id
      JOIN restaurants r ON c.restaurant_id = r.id
      WHERE c.name = ? AND r.name = ?
  """, (category, restaurant))
  meals = [row[0] for row in cursor.fetchall()]

  if not meals:
      await query.edit_message_text("❌ لا توجد وجبات في هذه الفئة.")
      return

  keyboard = [
      [InlineKeyboardButton(meal, callback_data=f"{action_key}_meal_{meal}")]
      for meal in meals
  ]
  keyboard.append([InlineKeyboardButton("↩️ العودة", callback_data="show_meal_options_again")])

  await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))




async def handle_blacklist_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if update.callback_query:
      query = update.callback_query
      await query.answer()
      send = query.edit_message_text
  else:
      send = update.message.reply_text

  keyboard = [
      [InlineKeyboardButton("➕ إضافة رقم محظور", callback_data="add_blacklisted_number")],
      [InlineKeyboardButton("➖ فك حظر رقم", callback_data="remove_blacklisted_number")],
      [InlineKeyboardButton("⬅️ العودة إلى القائمة الرئيسية", callback_data="go_back_main")],
  ]
  await send(
      text="📵 *إدارة الأرقام المحظورة:*",
      reply_markup=InlineKeyboardMarkup(keyboard),
      parse_mode="Markdown"
  )


async def handle_add_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
  context.user_data["blacklist_action"] = "add"
  await update.message.reply_text("📱 أرسل الرقم الذي تريد حظره (مثال: 09xxxxxxxx):")


async def handle_remove_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
  context.user_data["blacklist_action"] = "remove"
  await update.message.reply_text("📱 أرسل الرقم الذي تريد فك الحظر عنه:")


async def handle_blacklist_phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
  action = context.user_data.get("blacklist_action")
  phone = update.message.text.strip()

  if not re.fullmatch(r"09\d{8}", phone):
      await update.message.reply_text("❌ صيغة الرقم غير صحيحة. يرجى إرسال رقم مثل: 09xxxxxxxx")
      return

  cursor = db_conn.cursor()

  if action == "add":
      cursor.execute("INSERT OR IGNORE INTO blacklisted_numbers (phone) VALUES (?)", (phone,))
      db_conn.commit()
      await update.message.reply_text(f"✅ تم حظر الرقم {phone} بنجاح.")
  elif action == "remove":
      cursor.execute("DELETE FROM blacklisted_numbers WHERE phone = ?", (phone,))
      db_conn.commit()
      await update.message.reply_text(f"✅ تم فك الحظر عن الرقم {phone} بنجاح.")
  else:
      await update.message.reply_text("⚠️ لم يتم تحديد العملية بشكل صحيح.")

  context.user_data.pop("blacklist_action", None)

  # ✅ العودة لقائمة الحظر بعد تنفيذ العملية
  await handle_blacklist_menu(update, context)



async def handle_blacklist_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  action = query.data

  if action == "add_blacklisted_number":
      context.user_data["blacklist_action"] = "add"
      await query.message.reply_text("📞 أرسل الرقم الذي تريد حظره:")
  elif action == "remove_blacklisted_number":
      context.user_data["blacklist_action"] = "remove"
      await query.message.reply_text("📞 أرسل الرقم الذي تريد فك الحظر عنه:")


async def handle_freeze_unfreeze_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  action = query.data
  context.user_data["freeze_action"] = action

  selected_city = context.user_data.get("selected_city_restaurant")
  if not selected_city:
      await query.message.reply_text("❌ لم يتم تحديد المدينة.")
      return

  cursor = db_conn.cursor()
  if action == "freeze_restaurant":
      cursor.execute("SELECT name FROM restaurants WHERE city = ? AND is_frozen = 0", (selected_city,))
  else:
      cursor.execute("SELECT name FROM restaurants WHERE city = ? AND is_frozen = 1", (selected_city,))

  restaurants = [r[0] for r in cursor.fetchall()]
  if not restaurants:
      await query.message.reply_text("⚠️ لا توجد مطاعم مطابقة.")
      return

  keyboard = [[InlineKeyboardButton(r, callback_data=f"select_freeze_restaurant_{r}")] for r in restaurants]
  await query.message.reply_text("اختر المطعم:", reply_markup=InlineKeyboardMarkup(keyboard))



async def handle_freeze_restaurant_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  restaurant_name = query.data.replace("select_freeze_restaurant_", "")
  action = context.user_data.get("freeze_action")

  is_frozen = 1 if action == "freeze_restaurant" else 0
  cursor = db_conn.cursor()
  cursor.execute("UPDATE restaurants SET is_frozen = ? WHERE name = ?", (is_frozen, restaurant_name))
  db_conn.commit()

  status_text = "❄️ تم تجميد" if is_frozen else "✅ تم إلغاء تجميد"
  await query.message.reply_text(f"{status_text} المطعم: {restaurant_name}")

  context.user_data.pop("freeze_action", None)

  # ✅ العودة إلى القائمة الرئيسية بعد العملية
  keyboard = [
      [InlineKeyboardButton("🏙️ إدارة المحافظات", callback_data="go_manage_provinces")],
      [InlineKeyboardButton("🌆 إدارة المدن", callback_data="go_manage_cities")],
      [InlineKeyboardButton("🍽️ إدارة المطاعم", callback_data="go_manage_restaurants")],
      [InlineKeyboardButton("📂 إدارة الفئات", callback_data="go_manage_categories")],
      [InlineKeyboardButton("🍔 إدارة الوجبات", callback_data="go_manage_meals")],
      [InlineKeyboardButton("📵 الأرقام المحظورة", callback_data="go_blacklist_menu")],
  ]

  await query.message.reply_text(
      "⬅️ عدت إلى القائمة الرئيسية.",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )



async def start_city_ad_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  # جلب المحافظات
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT name FROM provinces ORDER BY name")
  provinces = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not provinces:
      await query.edit_message_text("❌ لا توجد محافظات.")
      return

  keyboard = [
      [InlineKeyboardButton(p, callback_data=f"select_ad_province_{p}")]
      for p in provinces
  ]
  await query.edit_message_text("🌍 اختر المحافظة للإعلان:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_ad_province_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  province = query.data.replace("select_ad_province_", "")
  context.user_data["ad_province"] = province

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT c.name FROM cities c
      JOIN provinces p ON c.province_id = p.id
      WHERE p.name = ?
  """, (province,))
  cities = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not cities:
      await query.edit_message_text("❌ لا توجد مدن في هذه المحافظة.")
      return

  keyboard = [
      [InlineKeyboardButton(c, callback_data=f"select_ad_city_{c}")]
      for c in cities
  ]
  await query.edit_message_text("🏙️ اختر المدينة:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_ad_city_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  city = query.data.replace("select_ad_city_", "")
  context.user_data["ad_city"] = city

  # جلب المطاعم باستخدام city_id بدلاً من النص
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT r.name FROM restaurants r
      JOIN cities c ON r.city_id = c.id
      WHERE c.name = ?
  """, (city,))
  restaurants = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not restaurants:
      await query.edit_message_text("❌ لا توجد مطاعم في هذه المدينة.")
      return

  keyboard = [
      [InlineKeyboardButton(r, callback_data=f"select_ad_restaurant_{r}")]
      for r in restaurants
  ]
  await query.edit_message_text("🍽️ اختر المطعم المرسل للإعلان:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_ad_restaurant_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  restaurant = query.data.replace("select_ad_restaurant_", "")
  context.user_data["ad_restaurant"] = restaurant
  context.user_data["ad_step"] = "awaiting_ad_text"

  await query.edit_message_text("📝 أرسل الآن نص الإعلان:")


async def start_send_ad_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
  context.user_data.clear()

  # جلب المحافظات لاختيار المدينة
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT DISTINCT p.name FROM provinces p JOIN cities c ON p.id = c.province_id")
  provinces = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not provinces:
      await update.message.reply_text("❌ لا توجد محافظات تحتوي على مدن.")
      return

  keyboard = [
      [InlineKeyboardButton(province, callback_data=f"ad_select_province_{province}")]
      for province in provinces
  ]
  await update.message.reply_text(
      "🌍 اختر المحافظة لاختيار المدينة التي تريد نشر الإعلان فيها:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )


async def handle_ad_province(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  province = query.data.replace("ad_select_province_", "")
  context.user_data["ad_province"] = province

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT c.name FROM cities c
      JOIN provinces p ON c.province_id = p.id
      WHERE p.name = ?
  """, (province,))
  cities = [row[0] for row in cursor.fetchall()]
  conn.close()

  if not cities:
      await query.edit_message_text("❌ لا توجد مدن في هذه المحافظة.")
      return

  keyboard = [
      [InlineKeyboardButton(city, callback_data=f"ad_select_city_{city}")]
      for city in cities
  ]
  await query.edit_message_text(
      "🏙️ اختر المدينة التي تريد النشر فيها:",
      reply_markup=InlineKeyboardMarkup(keyboard)
  )


async def start_send_vip_ad_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
  context.user_data.clear()
  context.user_data["vip_ad"] = True
  context.user_data["ad_step"] = "awaiting_ad_province"

  # عرض المحافظات
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, name FROM provinces")
  provinces = cursor.fetchall()
  conn.close()

  keyboard = [[InlineKeyboardButton(province[1], callback_data=f"vip_ad_select_province_{province[0]}")] for province in provinces]
  await update.message.reply_text("🌍 اختر المحافظة التي تريد توجيه الإعلان الذهبي إليها:", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_vip_ad_restaurant_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  restaurant_id = int(query.data.replace("vip_ad_restaurant_", ""))
  context.user_data["ad_restaurant_id"] = restaurant_id

  # جلب اسم المطعم
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT name FROM restaurants WHERE id = ?", (restaurant_id,))
  row = cursor.fetchone()
  conn.close()

  if not row:
      await query.edit_message_text("❌ لم يتم العثور على المطعم.")
      return

  context.user_data["ad_restaurant"] = row[0]

  # 👇 نضيف هنا سؤال الزر
  context.user_data["ad_step"] = "awaiting_vip_button_text"
  await query.edit_message_text(
      "📝 ماذا تريد أن يُكتب على زر التوجيه؟ (مثال: اكبسني 😉)\n"
      "أو اضغط 'تخطي ⏭️' إذا لم يكن هناك زر توجيه.",
      reply_markup=ReplyKeyboardMarkup([["تخطي ⏭️"]], resize_keyboard=True)
  )

async def handle_skip_vip_ad_restaurant(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  context.user_data["ad_restaurant"] = None
  context.user_data["ad_skip_restaurant"] = True

  # 👇 نضيف نفس السؤال
  context.user_data["ad_step"] = "awaiting_vip_button_text"
  await query.edit_message_text(
      "📝 ماذا تريد أن يُكتب على زر التوجيه؟ (مثال: اكبسني 😉)\n"
      "أو اضغط 'تخطي ⏭️' إذا لم يكن هناك زر توجيه.",
      reply_markup=ReplyKeyboardMarkup([["تخطي ⏭️"]], resize_keyboard=True)
  )


async def send_vip_ad_to_channel(context: ContextTypes.DEFAULT_TYPE, ad_text: str, ad_duration: str | None, ad_restaurant: str | None, vip_button_text: str | None, media_type: str, file_id: str):
  """
  نشر إعلان VIP إلى القناة الوسيطة مع الزر المخصص إن وُجد.
  media_type: "photo" أو "video"
  """

  # 🔥 تجهيز نص الإعلان
  if ad_restaurant:
      full_text = f"🔥 يالله عالسرييع 🔥\n\n{ad_text}"
      if ad_duration:
          full_text += f"\n\n⏳ ديير بالك بس لـ {ad_duration} 🕒"
      full_text += f"\n\nمطعم {ad_restaurant} 😋"
  else:
      full_text = ad_text
      if ad_duration:
          full_text += f"\n\n⏳ ديير بالك بس لـ {ad_duration} 🕒"

  # 🎯 الزر إذا لم يتم تخطي المطعم
  if ad_restaurant and vip_button_text:
      restaurant_encoded = quote(ad_restaurant)
      url = f"https://t.me/Fasterone1200_bot?start=go_{restaurant_encoded}"
      button = InlineKeyboardMarkup([[InlineKeyboardButton(vip_button_text, url=url)]])
  else:
      button = None

  # 📨 إرسال الوسيط
  if media_type == "photo":
      await context.bot.send_photo(
          chat_id=VIP_MEDIA_CHANNEL_ID,
          photo=file_id,
          caption=full_text,
          parse_mode=ParseMode.MARKDOWN,
          reply_markup=button
      )
  elif media_type == "video":
      await context.bot.send_video(
          chat_id=VIP_MEDIA_CHANNEL_ID,
          video=file_id,
          caption=full_text,
          parse_mode=ParseMode.MARKDOWN,
          reply_markup=button
      )

async def handle_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()

  # عدد المستخدمين
  cursor.execute("SELECT COUNT(*) FROM users")
  total_users = cursor.fetchone()[0]

  # المستخدمين حسب المدن
  cursor.execute("""
      SELECT c.name, COUNT(*) FROM users u
      JOIN cities c ON u.city_id = c.id
      GROUP BY c.name
  """)
  city_user_counts = cursor.fetchall()
  city_user_lines = "\n".join([f"- {name}: {count}" for name, count in city_user_counts]) or "لا يوجد"

  # الطلبات حسب المحافظات
  cursor.execute("""
      SELECT p.name, 
             SUM(CASE WHEN o.status = 'مؤكد' THEN 1 ELSE 0 END) as confirmed,
             SUM(CASE WHEN o.status = 'ملغى' THEN 1 ELSE 0 END) as canceled,
             COUNT(*) as total
      FROM orders o
      JOIN restaurants r ON o.restaurant_id = r.id
      JOIN cities c ON r.city_id = c.id
      JOIN provinces p ON c.province_id = p.id
      GROUP BY p.name
  """)
  province_stats = cursor.fetchall()
  province_lines = "\n".join([
      f"- {p}: ✅ {conf} | ❌ {canc} | 📦 {total}"
      for p, conf, canc, total in province_stats
  ]) or "لا يوجد"

  # الطلبات حسب المدن
  cursor.execute("""
      SELECT c.name, 
             SUM(CASE WHEN o.status = 'مؤكد' THEN 1 ELSE 0 END) as confirmed,
             SUM(CASE WHEN o.status = 'ملغى' THEN 1 ELSE 0 END) as canceled,
             COUNT(*) as total
      FROM orders o
      JOIN restaurants r ON o.restaurant_id = r.id
      JOIN cities c ON r.city_id = c.id
      GROUP BY c.name
  """)
  city_stats = cursor.fetchall()
  city_order_lines = "\n".join([
      f"- {c}: ✅ {conf} | ❌ {canc} | 📦 {total}"
      for c, conf, canc, total in city_stats
  ]) or "لا يوجد"

  # إجمالي الطلبات
  cursor.execute("SELECT COUNT(*) FROM orders")
  total_orders = cursor.fetchone()[0]
  cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'مؤكد'")
  confirmed_orders = cursor.fetchone()[0]
  cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'ملغى'")
  canceled_orders = cursor.fetchone()[0]

  # عدد الإعلانات
  cursor.execute("SELECT COUNT(*) FROM ads")
  total_ads = cursor.fetchone()[0]

  conn.close()

  text = (
      "📊 إحصائيات النشاط:\n\n"
      f"👥 عدد المستخدمين الكلي: {total_users}\n\n"
      f"🗺️ التوزع حسب المدن:\n{city_user_lines}\n\n"
      f"🍽️ الطلبات حسب المحافظات:\n{province_lines}\n\n"
      f"🍽️ الطلبات حسب المدن:\n{city_order_lines}\n\n"
      f"📢 عدد الإعلانات المرسلة: {total_ads}"
  )

  await update.message.reply_text(text)

async def ask_user_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
  await update.message.reply_text("🔍 أرسل رقم المستخدم (يبدأ بـ 09) أو معرفه (يبدأ بـ @):")
  context.user_data["awaiting_user_search"] = True

async def handle_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
  if not context.user_data.get("awaiting_user_search"):
      return

  query = update.message.text.strip()
  context.user_data["awaiting_user_search"] = False

  info = get_user_full_info(query)
  await update.message.reply_text(info, parse_mode="Markdown")


# ⬅️ هذه لعرض الخيارات فقط (نوع التصدير)
async def handle_export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  keyboard = [
      [InlineKeyboardButton("👤 تصدير بيانات المستخدمين", callback_data="export_users")],
      [InlineKeyboardButton("📦 تصدير بيانات الطلبات", callback_data="export_orders")],
      [InlineKeyboardButton("🔙 العودة", callback_data="go_main_menu")]
  ]
  await query.edit_message_text("📤 اختر نوع البيانات التي تريد تصديرها:", reply_markup=InlineKeyboardMarkup(keyboard))

# ⬅️ هذه لتصدير المستخدمين
async def handle_export_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT name, phone, province, city, location_text, latitude, longitude, is_blocked
      FROM users
  """)
  rows = cursor.fetchall()
  conn.close()

  if not rows:
      await query.edit_message_text("لا يوجد مستخدمون لتصدير بياناتهم.")
      return

  df = pd.DataFrame(rows, columns=[
      "الاسم", "رقم الهاتف", "المحافظة", "المدينة",
      "وصف الموقع", "Latitude", "Longitude", "محظور؟"
  ])

  filename = f"users_export_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
  filepath = f"/tmp/{filename}"
  df.to_excel(filepath, index=False)

  await query.message.reply_document(document=InputFile(filepath), filename=filename)

# ⬅️ هذه لتصدير الطلبات
async def handle_export_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  conn = sqlite3.connect("database.db")
  cursor = conn.cursor()
  cursor.execute("""
      SELECT o.id, u.name, u.phone, u.city, o.restaurant_name, o.status, o.timestamp
      FROM orders o
      JOIN users u ON o.user_id = u.user_id
      ORDER BY o.timestamp DESC
  """)
  rows = cursor.fetchall()
  conn.close()

  if not rows:
      await query.edit_message_text("❌ لا يوجد طلبات لتصديرها.")
      return

  df = pd.DataFrame(rows, columns=[
      "معرف الطلب", "اسم الزبون", "رقم الهاتف", "المدينة",
      "اسم المطعم", "حالة الطلب", "تاريخ الطلب"
  ])

  filename = f"orders_export_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
  filepath = f"/tmp/{filename}"
  df.to_excel(filepath, index=False)

  await query.message.reply_document(document=InputFile(filepath), filename=filename)





def run_admin_bot():
  app = Application.builder().token("8035243318:AAGiaP7K8ErWJar1xuxrnqPA8KD9QQwKT0c").build()

  # أوامر البداية
  app.add_handler(CommandHandler("start", start))
  app.add_handler(CommandHandler("manage_provinces", manage_provinces))
  app.add_handler(CommandHandler("manage_cities", manage_cities))

  # إدارة المحافظات
  app.add_handler(CallbackQueryHandler(handle_province_action, pattern="^(add_province|delete_province|edit_province_name)$"))
  app.add_handler(CallbackQueryHandler(handle_rename_province_old, pattern=r"^rename_province_old_"))

  # إدارة المدن
  app.add_handler(CallbackQueryHandler(handle_province_for_city, pattern=r"^select_province_for_city_"))
  app.add_handler(CallbackQueryHandler(handle_city_action, pattern="^(add_city|delete_city|edit_city_name|edit_ads_channel)$"))
  app.add_handler(CallbackQueryHandler(handle_rename_city_old, pattern=r"^rename_city_old_"))
  app.add_handler(CallbackQueryHandler(handle_select_city_for_ads_channel, pattern="^edit_ads_channel_city_"))
  app.add_handler(CallbackQueryHandler(
      lambda u, c: (
          c.user_data.update({
              "city_to_edit_ads_channel": u.callback_query.data.replace("edit_ads_channel_for_city_", ""),
              "city_action": "edit_ads_channel"
          }),
          u.callback_query.edit_message_text("✏️ أرسل المعرف الجديد لقناة الإعلانات (أو اكتب 'لا يوجد'):")
      )[1],
      pattern="^edit_ads_channel_for_city_"
  ))

  # إدارة المطاعم
  app.add_handler(CallbackQueryHandler(manage_restaurants, pattern="^go_manage_restaurants$"))
  app.add_handler(CallbackQueryHandler(handle_province_for_restaurant, pattern=r"^select_province_for_restaurant_"))
  app.add_handler(CallbackQueryHandler(handle_city_for_restaurant, pattern=r"^select_city_for_restaurant_"))
  app.add_handler(CallbackQueryHandler(handle_add_delete_restaurant, pattern="^(add_restaurant|delete_restaurant)$"))

  # التنقل بين الأقسام
  app.add_handler(CallbackQueryHandler(lambda u, c: manage_provinces(u, c), pattern="^go_manage_provinces$"))
  app.add_handler(CallbackQueryHandler(lambda u, c: manage_cities(u, c), pattern="^go_manage_cities$"))

  # إدارة الفئات
  app.add_handler(CallbackQueryHandler(manage_categories, pattern="^go_manage_categories$"))
  app.add_handler(CallbackQueryHandler(handle_province_for_category, pattern=r"^select_province_for_category_"))
  app.add_handler(CallbackQueryHandler(handle_city_for_category, pattern=r"^select_city_for_category_"))
  app.add_handler(CallbackQueryHandler(show_category_options, pattern=r"^select_restaurant_for_category_"))

  # ✅ أولاً: الحذف (الأكثر دقة)
  app.add_handler(CallbackQueryHandler(delete_selected_category, pattern=r"^delete_category_id:\d+$"))

  # ✅ ثم تعديل الاسم
  app.add_handler(CallbackQueryHandler(ask_new_category_name, pattern=r"^select_category_to_rename_"))

  # ✅ أخيرًا: الإجراء العام
  app.add_handler(CallbackQueryHandler(handle_category_action, pattern="^(add_category|delete_category|edit_category_name|go_main_menu)$"))


  # ✅ إدارة الوجبات
  app.add_handler(CallbackQueryHandler(manage_meals, pattern="^go_manage_meals$"))
  app.add_handler(CallbackQueryHandler(handle_province_for_meals, pattern=r"^select_province_for_meals_"))
  app.add_handler(CallbackQueryHandler(handle_city_for_meals, pattern=r"^select_city_for_meals_"))
  app.add_handler(CallbackQueryHandler(handle_restaurant_for_meals, pattern=r"^select_restaurant_for_meals_"))
  app.add_handler(CallbackQueryHandler(show_meal_options, pattern=r"^select_category_for_meals_"))
  app.add_handler(CallbackQueryHandler(ask_edit_size_mode, pattern=r"^edit_sizes_for_meal_"))
  app.add_handler(CallbackQueryHandler(ask_which_size_to_remove, pattern="^delete_size_choice$"))
  app.add_handler(CallbackQueryHandler(ask_add_single_size, pattern="^add_size_to_meal$"))



  # إضافة وحذف وجبة
  app.add_handler(CallbackQueryHandler(start_add_meal, pattern="^add_meal$"))
  app.add_handler(CallbackQueryHandler(start_delete_meal, pattern="^delete_meal$"))
  app.add_handler(CallbackQueryHandler(confirm_delete_meal, pattern=r"^confirm_delete_meal_"))

  # تعديل وجبة - السعر
  app.add_handler(CallbackQueryHandler(ask_price_for_each_size, pattern=r"^select_meal_to_edit_price_"))

  # تعديل وجبة - الكابشن
  app.add_handler(CallbackQueryHandler(ask_new_meal_caption, pattern=r"^edit_caption_\d+$"))

  # الرجوع إلى القائمة
  app.add_handler(CallbackQueryHandler(show_meal_options, pattern="^show_meal_options_again$"))



  app.add_handler(CallbackQueryHandler(start_edit_meal_name, pattern="^edit_meal_name$"))
  app.add_handler(CallbackQueryHandler(ask_new_meal_name, pattern=r"^select_meal_to_rename_"))
  app.add_handler(CallbackQueryHandler(start_edit_meal_price, pattern="^edit_meal_price$"))
  app.add_handler(CallbackQueryHandler(start_edit_meal_caption, pattern="^edit_meal_caption$"))
  app.add_handler(CallbackQueryHandler(start_edit_meal_photo, pattern="^edit_meal_photo$"))
  app.add_handler(CallbackQueryHandler(ask_new_meal_photo, pattern="^select_meal_to_edit_photo_"))
  app.add_handler(CallbackQueryHandler(start_edit_meal_sizes, pattern="^edit_meal_sizes$"))
  app.add_handler(CallbackQueryHandler(ask_new_meal_sizes, pattern="^select_meal_to_edit_sizes_"))
  app.add_handler(CallbackQueryHandler(ask_add_new_size, pattern="^add_new_size$"))
  app.add_handler(CallbackQueryHandler(ask_which_size_to_remove, pattern="^remove_existing_size$"))
  app.add_handler(CallbackQueryHandler(handle_remove_size, pattern="^remove_size_"))


  # الصور
  # ✅ معالج الصور الموحد
  app.add_handler(MessageHandler(filters.PHOTO, handle_all_images))

  # خيارات نعم/لا للقياسات
  app.add_handler(MessageHandler(
      filters.TEXT & filters.Regex("^(نعم، لها قياسات|لا، لا يوجد قياسات)$"),
      handle_add_meal_size_decision
  ))

  # إدارة المطاعم - اسم، قناة، دوام
  app.add_handler(CallbackQueryHandler(start_delete_restaurant, pattern="^delete_restaurant$"))
  app.add_handler(CallbackQueryHandler(confirm_delete_restaurant, pattern=r"^confirm_delete_restaurant_"))
  app.add_handler(CallbackQueryHandler(start_rename_restaurant, pattern="^rename_restaurant$"))
  app.add_handler(CallbackQueryHandler(ask_new_restaurant_name, pattern=r"^select_restaurant_to_rename_"))
  app.add_handler(CallbackQueryHandler(handle_restaurant_edit_action, pattern="^(rename_restaurant|edit_restaurant_channel|edit_restaurant_hours)$"))
  app.add_handler(CallbackQueryHandler(handle_selected_restaurant_edit, pattern="^select_restaurant_edit_target_"))

  # الحظر
  app.add_handler(CallbackQueryHandler(handle_blacklist_menu, pattern="^go_blacklist_menu$"))
  app.add_handler(CallbackQueryHandler(handle_blacklist_actions, pattern="^(add_blacklisted_number|remove_blacklisted_number)$"))
  app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📵 الأرقام المحظورة$"), handle_blacklist_menu))
  app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^➕ إضافة رقم محظور$"), handle_add_blacklist))
  app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^➖ فك حظر رقم$"), handle_remove_blacklist))
  app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^09\d{8}$"), handle_blacklist_phone_input))

  # التجميد
  app.add_handler(CallbackQueryHandler(handle_freeze_unfreeze_selection, pattern="^(freeze_restaurant|unfreeze_restaurant)$"))
  app.add_handler(CallbackQueryHandler(handle_freeze_restaurant_choice, pattern="^select_freeze_restaurant_"))

  # بدء إرسال الإعلان
  # ✅ بدء إرسال الإعلان
  app.add_handler(MessageHandler(filters.Regex("^📢 إرسال إعلان$"), start_send_ad_flow))
  app.add_handler(MessageHandler(filters.Regex("^📣 إرسال إعلان ذهبي$"), start_send_vip_ad_flow))
  app.add_handler(MessageHandler(filters.Regex("^🔍 بحث عن مستخدم$"), ask_user_query))
  app.add_handler(CallbackQueryHandler(handle_statistics, pattern="^show_statistics$"))
  app.add_handler(CallbackQueryHandler(handle_export_data, pattern="^export_data$"))  # إذا أردت لاحقًا
  app.add_handler(CallbackQueryHandler(handle_export_users, pattern="^export_users$"))
  app.add_handler(CallbackQueryHandler(handle_export_orders, pattern="^export_orders$"))



  # إعلان المدن والمطاعم
  app.add_handler(CallbackQueryHandler(handle_ad_province, pattern=r"^ad_select_province_"))
  app.add_handler(CallbackQueryHandler(handle_send_city_ad, pattern="^send_city_ad$"))
  app.add_handler(CallbackQueryHandler(handle_ad_city_selection, pattern=r"^ad_select_city_"))
  app.add_handler(CallbackQueryHandler(handle_ad_city_selected, pattern="^ad_city_"))
  app.add_handler(CallbackQueryHandler(handle_ad_restaurant_selected, pattern="^ad_restaurant_"))
  app.add_handler(CallbackQueryHandler(handle_ad_all_cities_selected, pattern="^ad_all_cities$"))
  app.add_handler(CallbackQueryHandler(handle_skip_ad_restaurant, pattern="^skip_ad_restaurant$"))

  # صور وفيديو
  app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_all_images))

  # الرجوع
  app.add_handler(CallbackQueryHandler(handle_main_menu_callback, pattern="^go_back_main$"))
  app.add_handler(CallbackQueryHandler(start, pattern="^go_main_menu$"))

  # معالج النصوص الموحد (يجب أن يكون في النهاية)
  app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_inputs))

  app.run_polling()




if __name__ == "__main__":
      # 🧱 إنشاء الجداول الأساسية
  setup_location_tables()
  setup_menu_tables()
  add_city_id_to_restaurants()
  sync_city_ids_in_restaurants()
  ensure_is_frozen_column()
  drop_old_city_column()
      # ✅ إنشاء الأعمدة الأخرى
  add_ads_channel_column_to_cities()
  add_unique_id_column()
  create_ads_table()



      # 🧪 فحوصات
  print("🚀 بدء تنفيذ الكود في main.py")
  print_all_meal_names()
  debug_check_categories_and_restaurants()
  debug_check_meals_table_structure()
  check_sizes_format()

run_admin_bot()
