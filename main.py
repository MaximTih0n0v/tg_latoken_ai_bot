from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from config import settings
import openai
import asyncio
from openai import AsyncOpenAI, OpenAI
import aiohttp
import requests
from bs4 import BeautifulSoup
import re


TG_API = settings.TG_API
WEBHOOK_HOST = settings.WEBHOOK_HOST
WEBHOOK_PATH = settings.WEBHOOK_PATH
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEBAPP_HOST = settings.WEBAPP_HOST
WEBAPP_PORT = settings.WEBAPP_PORT

OPENAI_API_KEY = settings.OPENAI_API_KEY

URL2 = "https://deliver.latoken.com/hackathon"
URL3 = "https://coda.io/@latoken/latoken-talent/culture-139"

MAX_CONTENT_LENGTH = 255000


# Инициализация бота и диспетчера
bot = Bot(token=TG_API)
dp = Dispatcher()

# Настройка OpenAI API
openai.api_key = OPENAI_API_KEY
user_question_answer_map = {}

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)
    print(f"Webhook set to {WEBHOOK_URL}")
    print("Bot started")


async def on_shutdown(app):
    await bot.delete_webhook()


def get_text_from_url(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')


    page_text = soup.get_text(separator=' ', strip=True)


    return page_text[:MAX_CONTENT_LENGTH]

async def fetch_content(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            content = await response.text()
            return content[:MAX_CONTENT_LENGTH]  # Ограничиваем длину текста


async def get_openai_response_and_generate_question(prompt, chat_id):
    global question_text
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    try:
        content1 = get_text_from_url("https://coda.io/@latoken/latoken-talent/latoken-161")
        content2 = await fetch_content(URL2)
        content3 = get_text_from_url(URL3)


        assistant_for_answer = await client.beta.assistants.create(
            name="Personal assistant",
            instructions="You are a personal assistant who helps with any issue.",
            tools=[{"type": "code_interpreter"}],
            model="gpt-4o"
        )

        assistant_for_question = await client.beta.assistants.create(
            name="Question Generator",
            instructions="You are a knowledgeable assistant tasked with creating quiz questions based on provided content.",
            model="gpt-4o"
        )

        thread_for_answer = await client.beta.threads.create()

        await client.beta.threads.messages.create(
            thread_id=thread_for_answer.id,
            role="user",
            content=f"Content from URL 1:\n{content1}"
        )


        await client.beta.threads.messages.create(
            thread_id=thread_for_answer.id,
            role="user",
            content=f"Content from URL 2:\n{content2}"
        )


        await client.beta.threads.messages.create(
            thread_id=thread_for_answer.id,
            role="user",
            content=f"Content from URL 3:\n{content3}"
        )


        await client.beta.threads.messages.create(
            thread_id=thread_for_answer.id,
            role="user",
            content=f"User question: {prompt}"
        )

        run = await client.beta.threads.runs.create(
            thread_id=thread_for_answer.id,
            assistant_id=assistant_for_answer.id
        )

        while True:
            messages = await client.beta.threads.messages.list(thread_id=thread_for_answer.id)
            assistant_message = None

            async for msg in messages:
                if msg.role == 'assistant':
                    assistant_message = msg

            if assistant_message:
                if assistant_message.content:
                    text_content = assistant_message.content[0]
                    if hasattr(text_content, 'text'):
                        response_text = text_content.text.value
                        print(f"Response: {response_text}")
                        break

            await asyncio.sleep(1)


        thread_for_question = await client.beta.threads.create()

        await client.beta.threads.messages.create(
            thread_id=thread_for_question.id,
            role="user",
            content=f"На основе следующей информации:\n1. {content1}\n2. {content2}\n3. {content3}\n"
                    "Пожалуйста, создай короткий проверочный вопрос в виде теста с вариантами ответа, для кандидата, который поможет оценить понимание "
                    "этого материала. Без подсказок. Также создай правильный ответ на него."
        )


        run = await client.beta.threads.runs.create(
            thread_id=thread_for_question.id,
            assistant_id=assistant_for_question.id
        )

        while True:
            messages = await client.beta.threads.messages.list(thread_id=thread_for_question.id)
            assistant_question_message = None
            assistant_answer_message = None

            async for msg in messages:
                if msg.role == 'assistant':
                    assistant_question_message = msg
                    assistant_answer_message = msg

            if assistant_question_message:
                if assistant_question_message.content:
                    question_content = assistant_question_message.content[0]
                    if hasattr(question_content, 'text'):
                        question_text_with_answer = question_content.text.value
                        question_text = re.sub(r'\**Правильный ответ:\**.*', '', question_text_with_answer, flags=re.DOTALL)
                        print(f"Generated Question: {question_text_with_answer}")

            if assistant_answer_message:
                if assistant_answer_message.content:
                    answer_content = assistant_answer_message.content[0]
                    if hasattr(answer_content, 'text'):
                        correct_answer1 = re.search(r"Правильный ответ:\s*(.*)", answer_content.text.value, re.DOTALL)
                        correct_answer2 = correct_answer1.group(1).strip()
                        answer_letter = re.search(r'^[#\*\s]*([^\s)#\.])(?=\)|\.)', correct_answer2)

                        if answer_letter:
                            correct_answer = answer_letter.group(1).strip()

                            user_question_answer_map[chat_id] = {
                                "question": question_text,
                                "answer": correct_answer
                            }
                            return response_text, question_text

            await asyncio.sleep(1)

    except Exception as e:
        print(f"Failed to get OpenAI response: {e}")
        return "Не удалось получить ответ от OpenAI.", None


# Обработчик текстовых сообщений
async def handle_text_message(message: Message):
    chat_id = message.chat.id
    user_message = message.text

    if chat_id in user_question_answer_map:
        correct_answer = user_question_answer_map[chat_id]["answer"]
        user_answer = user_message

        if user_answer.strip().lower() == correct_answer.strip().lower():
            await bot.send_message(chat_id, "Правильно!")
        else:
            await bot.send_message(chat_id, f"Неправильно. Правильный ответ: {correct_answer}")

        del user_question_answer_map[chat_id]
    else:
        # Получаем ответ от OpenAI
        response, question = await get_openai_response_and_generate_question(user_message, chat_id)

        # Отправляем ответ пользователю
        await bot.send_message(chat_id, response)

        if question:
            await bot.send_message(chat_id, f"Теперь вопрос для Вас: {question}")



dp.message.register(handle_text_message, F.text)

if __name__ == "__main__":
    app = web.Application()
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)
