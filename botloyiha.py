import telebot
from flask import Flask
import threading
import asyncio
import os
import logging
import yt_dlp
import instaloader
import shutil
import uuid
import aiosqlite
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, FSInputFile

from openai import AsyncOpenAI
from gtts import gTTS
from duckduckgo_search import DDGS

# ---------------- SOZLAMALAR ----------------
load_dotenv()

# TOKENLARNI SHU YERGA YOZING
BOT_TOKEN = "8424580798:AAHPGab8dkb8ly5nFFJDnMiyorbC2KJCs6c"
OPENROUTER_KEY = "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"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_KEY
)

L = instaloader.Instaloader()
DB = "ultimate.db"

# ---------------- DATABASE (MA'LUMOTLAR BAZASI) ----------------
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY)")
        await db.execute("""CREATE TABLE IF NOT EXISTS history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT
        )""")
        await db.commit()

async def add_user(uid):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
        await db.commit()

async def add_history(uid, role, content):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO history(user_id, role, content) VALUES(?,?,?)", (uid, role, content))
        await db.commit()

async def get_history(uid):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT role, content FROM history WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))
        rows = await cur.fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

# ---------------- KLAVIATURA (O'ZBEKCHA) ----------------
menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📺 YouTube Yuklovchi"), KeyboardButton(text="📸 Instagram Yuklovchi")],
        [KeyboardButton(text="🤖 AI Chat (O'zbekcha)")]
    ],
    resize_keyboard=True
)

# ---------------- HANDLERS ----------------
@router.message(Command("start"))
async def start(m):
    await add_user(m.from_user.id)
    await m.answer(f"Assalomu alaykum, {m.from_user.full_name}!\n\nMenyu orqali kerakli bo'limni tanlang:", reply_markup=menu)

@router.message(F.text == "📺 YouTube Yuklovchi")
async def yt_prompt(m):
    await m.answer("🔗 YouTube video linkini yuboring:")

@router.message(F.text.contains("youtube.com") | F.text.contains("youtu.be"))
async def yt_download(m):
    msg = await m.answer("⏳ Video yuklanmoqda...")
    try:
        os.makedirs("downloads", exist_ok=True)
        filename = f"downloads/{uuid.uuid4()}.mp4"

        def download():
            ydl_opts = {'format': 'best', 'outtmpl': filename, 'quiet': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([m.text])
            return filename

        path = await asyncio.to_thread(download)
        await m.answer_video(FSInputFile(path), caption="✅ YouTube video tayyor!")
        if os.path.exists(path): os.remove(path)
    except Exception as e:
        await m.answer(f"❌ Xatolik: {str(e)}")
    finally:
        await msg.delete()

@router.message(F.text == "📸 Instagram Yuklovchi")
async def insta_prompt(m):
    await m.answer("🔗 Instagram Reel yoki Post linkini yuboring:")

@router.message(F.text.contains("instagram.com"))
async def insta_download(m):
    msg = await m.answer("⏳ Instagramdan yuklanmoqda...")
    try:
        shortcode = m.text.strip("/").split("/")[-1]
        folder = f"insta_{uuid.uuid4()}"
        def download():
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            L.download_post(post, target=folder)
            return folder
        await asyncio.to_thread(download)
        for file in os.listdir(folder):
            path = os.path.join(folder, file)
            if file.endswith(".mp4"): await m.answer_video(FSInputFile(path))
            elif file.endswith((".jpg", ".png")): await m.answer_photo(FSInputFile(path))
        shutil.rmtree(folder)
    except Exception as e:
        await m.answer(f"❌ Xato: {str(e)}")
    finally:
        await msg.delete()

@router.message(F.text == "🤖 AI Chat (O'zbekcha)")
async def ai_start(m):
    await m.answer("🤖 Savolingizni yozing, men faqat o'zbek tilida javob beraman:")

# ---------------- ASOSIY AI QISMI (O'ZBEKCHA) ----------------
@router.message(F.text & ~F.text.startswith("/"))
async def ai_handler(m):
    await add_user(m.from_user.id)
    
    if m.text.lower().startswith("search:"):
        q = m.text.replace("search:", "").strip()
        with DDGS() as d:
            results = [r['body'] for r in d.text(q, max_results=3)]
            return await m.answer("\n\n".join(results) if results else "Topilmadi.")

    await add_history(m.from_user.id, "user", m.text)
    history = await get_history(m.from_user.id)

    try:
        # AI-ga qat'iy ko'rsatma: faqat o'zbekcha javob berish
        system_msg = {
            "role": "system", 
            "content": "Sen foydali yordamchi botsan. Foydalanuvchi senga qaysi tilda murojaat qilsa ham, sen FAQAT o'zbek tilida javob berishing shart. Javobing qisqa va aniq bo'lsin."
        }
        
        response = await client.chat.completions.create(
            model="mistralai/mixtral-8x7b-instruct",
            messages=[system_msg] + history
        )
        
        ans = response.choices[0].message.content
        await add_history(m.from_user.id, "assistant", ans)
        await m.answer(ans)

        # Ovozli javob (O'zbekchaga yaqin 'tr' turkcha talaffuzi bilan)
        if len(ans) < 300:
            v_file = f"{uuid.uuid4()}.mp3"
            tts = gTTS(ans, lang='tr')
            await asyncio.to_thread(tts.save, v_file)
            await m.answer_voice(FSInputFile(v_file))
            if os.path.exists(v_file): os.remove(v_file)

    except Exception as e:
        await m.answer(f"⚠️ AI xatosi: {e}")

# ---------------- ISHGA TUSHIRISH ----------------
async def main():
    await init_db()
    dp.include_router(router)
    print("✅ Bot o'zbek tilida ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
