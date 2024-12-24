import logging
import os
import asyncio
from io import BytesIO
from flask import Flask, request, jsonify, abort
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import openai
import nest_asyncio

# Ініціалізація Nest Asyncio
nest_asyncio.apply()

# Ініціалізація Flask
flask_app = Flask(__name__)

# API ключ OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY не встановлено!")

# Telegram Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не встановлено!")

# URL для вебхуків
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL не встановлено!")

# Маршрут для отримання запитів вебхука
@flask_app.route("/telegram-webhook", methods=["POST"])
def webhook():
    if request.method == "POST":
        json_update = request.get_json()
        application.update_queue.put(json_update)
        return "OK", 200

# Функція для оцінки унікальності тексту через OpenAI
def check_text_uniqueness_openai(text: str) -> str:
    try:
        response = openai.Completion.create(
            model="text-davinci-003",
            prompt=f"Оцініть унікальність наступного тексту: {text}\n"
                   f"Відповідь повинна бути у відсотках унікальності. Якщо текст є звичайним плагіатом, вкажіть це.",
            max_tokens=100,
            temperature=0.7
        )
        result = response.choices[0].text.strip()
        return f"Результат оцінки унікальності: {result}"
    except Exception as e:
        return f"Помилка при перевірці тексту: {str(e)}"

# Telegram бот
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Перевірити текст", "Перевірити файл"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Привіт! Оберіть дію:", reply_markup=reply_markup)

# Обробка текстових повідомлень
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_text("Текст отримано. Перевіряю унікальність...")
    result = check_text_uniqueness_openai(user_text)
    await update.message.reply_text(result)

# Flask маршрут для завантаження файлів
@flask_app.route('/upload/', methods=['POST'])
def upload_file():
    try:
        file = request.files['file']
        file_ext = os.path.splitext(file.filename)[-1].lower()
        buffer = BytesIO(file.read())  # Зберігаємо файл в пам'яті

        if file_ext == ".txt":
            text = buffer.getvalue().decode("utf-8")
        else:
            return jsonify({"detail": "Формат файлу не підтримується"}), 400

        result = check_text_uniqueness_openai(text)
        return jsonify({"filename": file.filename, "result": result})
    except Exception as e:
        return jsonify({"detail": f"Помилка: {str(e)}"}), 500

# Основний цикл
async def main():
    # Ініціалізація Telegram бота
    global application
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Відключаємо старий вебхук перед налаштуванням нового
    await application.bot.delete_webhook()

    # Налаштовуємо новий вебхук
    await application.bot.set_webhook(WEBHOOK_URL + "/telegram-webhook")

    # Додаємо хендлери для команд та повідомлень
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Запускаємо Flask сервер на порті 80 для вебхуків
    flask_app.run(host="0.0.0.0", port=80, threaded=True)

if __name__ == "__main__":
    asyncio.run(main())
