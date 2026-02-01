import os
import asyncio
import re
import requests
from bs4 import BeautifulSoup
from pyrogram import Client, filters
from motor.motor_asyncio import AsyncIOMotorClient
from flask import Flask
from threading import Thread

# --- RENDER PORT FIX ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is Online"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- CONFIG ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "")

bot = Client("ContentPilot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db = AsyncIOMotorClient(MONGO_URI)["ContentPilotDB"]

# --- DIRECT SITE SCRAPER (No Google) ---
async def get_movie_links(query):
    # Seedha website ke search page ko target kar rahe hain
    search_url = f"https://vegamovies.to/?s={query.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(search_url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        results = []
        # Website ke title aur link nikalna
        for h3 in soup.find_all('h3', class_='entry-title'):
            a = h3.find('a')
            if a:
                results.append({"title": a.text, "url": a['href']})
        return results[:3]
    except Exception as e:
        print(f"Scraper Error: {e}")
        return []

# --- BACKGROUND ENGINE ---
async def channel_task(chat_id, category, interval):
    print(f"Automation active for: {chat_id}")
    while True:
        movies = await get_movie_links(category)
        if not movies:
            print(f"No results found for {category}")
        
        for m in movies:
            # Check if already posted
            if await db.history.find_one({"url": m['url'], "chat_id": chat_id}):
                continue
            
            caption = f"🎬 **{m['title']}**\n\n📂 Category: {category}\n🔗 Link: {m['url']}\n\n✨ Powered by Content Pilot"
            try:
                await bot.send_message(chat_id, caption)
                await db.history.insert_one({"url": m['url'], "chat_id": chat_id})
                print(f"Posted: {m['title']}")
                break 
            except Exception as e:
                print(f"Post error: {e}")
        
        await asyncio.sleep(interval)

async def start_engines():
    async for ch in db.channels.find({"active": True}):
        asyncio.create_task(channel_task(ch["chat_id"], ch["category"], ch.get("interval", 3600)))

# --- COMMANDS ---
@bot.on_message(filters.command("setup") & filters.private)
async def setup(c, m):
    try:
        cid = int(m.command[1])
        cat = " ".join(m.command[2:])
        await db.channels.update_one({"chat_id": cid}, {"$set": {"category": cat, "active": True}}, upsert=True)
        asyncio.create_task(channel_task(cid, cat, 3600))
        await m.reply(f"✅ Setup Done for `{cid}`\nCategory: {cat}")
    except: await m.reply("Usage: `/setup ID Category`")

# --- MAIN ---
if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot.start()
    asyncio.get_event_loop().create_task(start_engines())
    print("Bot is running...")
    asyncio.get_event_loop().run_forever()
                
