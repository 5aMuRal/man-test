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

# Нест
nest_asyncio.apply()

# Фласк
flask_app = Flask(__name__)

# Апішка чат гпт
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY не встановлено!")

# Токен тєлєга (змінна)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не встановлено!")

# Вебхуки
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Наприклад, https://ваш-домен.com/telegram-webhook
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL не встановлено!")

# Запити вебхуків
@flask_app.route("/telegram-webhook", methods=["POST"])
def webhook():
    if request.method == "POST":
        json_update = request.get_json()
        application.update_queue.put(json_update)
        return "OK", 200

# Підключення трансформера
tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/paraphrase-MiniLM-L6-v2")
model = AutoModel.from_pretrained("sentence-transformers/paraphrase-MiniLM-L6-v2")

# Ліміт фласк
@flask_app.before_request
def limit_file_size():
    if request.content_length and request.content_length > 16 * 1024 * 1024:  # 16 MB
        abort(413, description="Файл занадто великий.")

# ПДФ
def read_pdf(file) -> str:
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file)
        text = "".join(page.extract_text() or "" for page in reader.pages)
        return text
    except Exception as e:
        return f"Помилка обробки PDF: {str(e)}"

# Ворд
def read_docx(file) -> str:
    try:
        document = Document(file)
        text = "".join(paragraph.text + "\n" for paragraph in document.paragraphs)
        return text
    except Exception as e:
        return f"Помилка обробки DOCX: {str(e)}"

# ТХТ
def read_txt(file) -> str:
    try:
        return file.read().decode("utf-8")
    except Exception as e:
        return f"Помилка обробки TXT: {str(e)}"

# Шлях збереження файлів фласк
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

# Команда старт, кнопки
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Текстове повідомлення", "Текстовий документ"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Привіт! Виберіть тип задачі:", reply_markup=reply_markup)

# Обробка текстів 
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ви написали: {update.message.text}")

# Основний цикл
async def main():
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    config = Config()
    config.bind = ["0.0.0.0:5000"]  

    # Запуск бота
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Видалення старих вебхуків
    application.bot.delete_webhook()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Фласк сєрвак
    flask_task = serve(flask_app, config)
    
    # Запуск бота через поллінг
    telegram_task = application.run_polling(close_loop=False)

    await asyncio.gather(flask_task, telegram_task)

if __name__ == "__main__":
    application.bot.set_webhook(WEBHOOK_URL + "/telegram-webhook") # Для використання вебхука замість polling
    asyncio.run(main())
