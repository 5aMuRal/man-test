import logging
import os
import asyncio
from io import BytesIO
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from transformers import AutoTokenizer, AutoModel
from flask import Flask, request, jsonify, abort
import openai
import torch
from sklearn.metrics.pairwise import cosine_similarity
from docx import Document  # Для роботи з DOCX
import nest_asyncio
from threading import Thread

# Запускаємо keep_alive для підтримки активності серверу
# keep_alive.keep_alive()

# Ініціалізація Nest Asyncio
nest_asyncio.apply()

# Ініціалізація Flask
flask_app = Flask(__name__)

# Ініціалізація OpenAI API
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY не встановлено!")

# Ініціалізація Telegram Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не встановлено!")

# URL для вебхуків
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Наприклад, https://ваш-домен.com/telegram-webhook
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL не встановлено!")

# Маршрут для отримання запитів вебхука
@flask_app.route('/telegram-webhook', methods=['POST'])
def webhook():
    return "OK", 200

# Ініціалізація моделі для порівняння текстів
tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/paraphrase-MiniLM-L6-v2")
model = AutoModel.from_pretrained("sentence-transformers/paraphrase-MiniLM-L6-v2")

# Обмеження розміру файлу для Flask
@flask_app.before_request
def limit_file_size():
    if request.content_length and request.content_length > 16 * 1024 * 1024:  # 16 MB
        abort(413, description="Файл занадто великий.")

# Функція для читання PDF
def read_pdf(file) -> str:
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file)
        text = "".join(page.extract_text() or "" for page in reader.pages)
        return text
    except Exception as e:
        return f"Помилка обробки PDF: {str(e)}"

# Функція для читання DOCX
def read_docx(file) -> str:
    try:
        document = Document(file)
        text = "".join(paragraph.text + "\n" for paragraph in document.paragraphs)
        return text
    except Exception as e:
        return f"Помилка обробки DOCX: {str(e)}"

# Функція для читання TXT
def read_txt(file) -> str:
    try:
        return file.read().decode("utf-8")
    except Exception as e:
        return f"Помилка обробки TXT: {str(e)}"

# Flask маршрут для завантаження файлів
@flask_app.route('/upload/', methods=['POST'])
def upload_file():
    try:
        file = request.files['file']
        file_ext = os.path.splitext(file.filename)[-1].lower()
        buffer = BytesIO(file.read())  # Зберігаємо файл в пам'яті

        if file_ext == ".pdf":
            text = read_pdf(buffer)
        elif file_ext == ".txt":
            text = buffer.getvalue().decode("utf-8")
        elif file_ext == ".docx":
            text = read_docx(buffer)
        else:
            return jsonify({"detail": "Формат файлу не підтримується"}), 400

        return jsonify({"filename": file.filename, "content": text[:1000]})
    except Exception as e:
        return jsonify({"detail": f"Помилка: {str(e)}"}), 500

# Telegram бот
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Текстове повідомлення", "Текстовий документ"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Привіт! Виберіть тип задачі:", reply_markup=reply_markup)

# Функція для обробки текстів
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ви написали: {update.message.text}")

# Основний цикл для Telegram бота
async def telegram_main():
    # Ініціалізація Telegram бота
    global application
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Відключаємо старий вебхук перед налаштуванням нового
    await application.bot.delete_webhook()

    # Налаштовуємо новий вебхук
    await application.bot.set_webhook(WEBHOOK_URL + "/telegram-webhook")  # Для використання вебхука замість polling

    # Додаємо хендлери для команд та повідомлень
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Запускаємо Telegram бота
    await application.run_polling()

# Функція для запуску Flask
def flask_main():
    port = int(os.getenv("PORT", 5000))  # Порт задається Render через змінну PORT
    flask_app.run(host="0.0.0.0", port=port, threaded=True)

# Основна функція
def main():
    # Запускаємо Flask сервер в окремому потоці
    flask_thread = Thread(target=flask_main)
    flask_thread.daemon = True  # Встановлюємо потік як демон для коректного завершення
    flask_thread.start()

    # Запускаємо Telegram бота
    asyncio.run(telegram_main())

if __name__ == "__main__":
    main()
