import asyncio
import os
import logging
import yt_dlp
import instaloader
import shutil
import uuid
import aiosqlite

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, FSInputFile

from openai import OpenAI
from gtts import gTTS
from duckduckgo_search import DDGS

# ---------------- CONFIG ----------------
BOT_TOKEN = "8424580798:AAHPGab8dkb8ly5nFFJDnMiyorbC2KJCs6c"
OPENROUTER_KEY = "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"
ADMIN_ID = 123456789

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_KEY
)

L = instaloader.Instaloader()
DB = "ultimate.db"

# ---------------- DATABASE ----------------
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            messages INTEGER DEFAULT 0
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT
        )
        """)
        await db.commit()

async def add_user(uid):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
        await db.commit()

async def add_history(uid, role, content):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO history(user_id, role, content) VALUES(?,?,?)",
            (uid, role, content)
        )
        await db.commit()

async def get_history(uid):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT role, content FROM history WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (uid,)
        )
        rows = await cur.fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

async def stats():
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users")
        users = (await cur.fetchone())[0]
        return users

# ---------------- UI ----------------
menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📺 YouTube"), KeyboardButton(text="📸 Instagram")],
        [KeyboardButton(text="🤖 AI Chat")]
    ],
    resize_keyboard=True
)

# ---------------- START ----------------
@dp.message(Command("start"))
async def start(m: types.Message):
    await add_user(m.from_user.id)
    await m.answer("🚀 ULTIMATE BOT ga xush kelibsiz!", reply_markup=menu)

# ---------------- YOUTUBE ----------------
@dp.message(F.text == "📺 YouTube")
async def yt(m):
    await m.answer("YouTube link yuboring...")

@dp.message(lambda m: m.text and "youtube" in m.text)
async def yt_dl(m):
    wait = await m.answer("⏳ Yuklanmoqda...")
    try:
        ydl_opts = {
            "format": "best",
            "outtmpl": "downloads/%(title)s.%(ext)s",
            "quiet": True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(m.text, download=True)
            path = ydl.prepare_filename(info)

        await m.answer_video(FSInputFile(path))
        os.remove(path)

    except Exception as e:
        await m.answer(str(e))

    await wait.delete()

# ---------------- INSTAGRAM ----------------
@dp.message(F.text == "📸 Instagram")
async def insta(m):
    await m.answer("Instagram link yuboring...")

@dp.message(lambda m: m.text and "instagram" in m.text)
async def insta_dl(m):
    wait = await m.answer("⏳ Yuklanmoqda...")
    try:
        shortcode = m.text.split("/")[-2]
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        folder = f"insta_{shortcode}"

        L.download_post(post, target=folder)

        for f in os.listdir(folder):
            if f.endswith(".mp4"):
                await m.answer_video(FSInputFile(os.path.join(folder, f)))

        shutil.rmtree(folder)

    except Exception as e:
        await m.answer(str(e))

    await wait.delete()

# ---------------- WEB SEARCH ----------------
def search(q):
    with DDGS() as d:
        return "\n".join([r["body"] for r in d.text(q, max_results=3)])

# ---------------- VOICE ----------------
async def voice(m, text):
    file = f"v_{uuid.uuid4()}.mp3"
    gTTS(text=text, lang="en").save(file)
    await m.answer_voice(FSInputFile(file))
    os.remove(file)

# ---------------- AI ----------------
@dp.message(F.text == "🤖 AI Chat")
async def ai_info(m):
    await m.answer("Savol yozing...")

@dp.message()
async def ai(m):
    try:
        uid = m.from_user.id
        await add_user(uid)

        # SEARCH MODE
        if m.text.lower().startswith("search:"):
            q = m.text.replace("search:", "")
            await m.answer(search(q))
            return

        # DB MEMORY
        history = await get_history(uid)

        await add_history(uid, "user", m.text)

        response = client.chat.completions.create(
            model="mistralai/mixtral-8x7b-instruct",
            messages=history + [{"role": "user", "content": m.text}]
        )

        answer = response.choices[0].message.content

        await add_history(uid, "assistant", answer)

        await m.answer(answer)
        await voice(m, answer)

    except Exception as e:
        await m.answer(str(e))

# ---------------- ADMIN ----------------
@dp.message(Command("stats"))
async def stats_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return await m.answer("❌ Ruxsat yo‘q")

    users = await stats()

    await m.answer(f"""
📊 ULTIMATE BOT

👥 Users: {users}
🤖 AI: Active
⚡ System: Stable
""")

# ---------------- MAIN ----------------
async def main():
    await init_db()

    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
