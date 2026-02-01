import os
import asyncio
import requests
from bs4 import BeautifulSoup
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from flask import Flask
from threading import Thread

# --- RENDER WEB SERVER (To keep Render alive) ---
app = Flask(__name__)
@app.route('/')
def health_check():
    return "Bot is active!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

# --- DATABASE SETUP ---
db_client = AsyncIOMotorClient(MONGO_URI)
db = db_client["ContentPilotDB"]
channels_col = db["channels"]
history_col = db["history"]

bot = Client("ContentPilot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- SCRAPER LOGIC ---
async def fetch_movie_links(query):
    """Searches for movie links based on category"""
    search_url = f"https://www.google.com/search?q={query}+direct+download+link"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(search_url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        links = []
        for a in soup.find_all('a', href=True):
            link = a['href']
            if "url?q=" in link and "webcache" not in link:
                clean_link = link.split("url?q=")[1].split("&sa=")[0]
                if clean_link.startswith("http"):
                    links.append(clean_link)
        return links[:5]
    except Exception as e:
        print(f"Scraping error: {e}")
        return []

# --- AUTO POSTING ENGINE ---
async def auto_post_engine():
    while True:
        cursor = channels_col.find({"active": True})
        async for channel in cursor:
            chat_id = channel["chat_id"]
            category = channel["category"]
            
            links = await fetch_movie_links(category)
            
            for link in links:
                if await history_col.find_one({"link": link, "chat_id": chat_id}):
                    continue
                
                # Smart Captioning
                caption = (
                    f"🎬 **New Content Uploaded!**\n\n"
                    f"📂 **Category:** {category}\n"
                    f"🔗 **Download Link:** {link}\n\n"
                    f"📢 **Join Our Channel for More!**\n"
                    f"✨ *Powered by Content Pilot AI*"
                )
                
                try:
                    await bot.send_message(chat_id, caption)
                    await history_col.insert_one({"link": link, "chat_id": chat_id})
                    break 
                except Exception as e:
                    print(f"Post error in {chat_id}: {e}")
            
        await asyncio.sleep(3600) # Check every 1 hour

# --- COMMANDS ---
@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text(
        "🚀 **Content Pilot AI v1.5 (Global)**\n\n"
        "I can automate your channel content from my DM.\n\n"
        "**How to setup:**\n"
        "1. Add me to your channel as **Admin**.\n"
        "2. Get your Channel ID (use @userinfobot).\n"
        "3. Use `/setup <Channel_ID> <Category>` here in DM.\n\n"
        "Example: `/setup -1001234567890 Movies Hindi`"
    )

@bot.on_message(filters.command("setup") & filters.private)
async def setup_remote(client, message):
    if len(message.command) < 3:
        return await message.reply_text("❌ Usage: `/setup -1001234567890 CategoryName`")
    
    try:
        target_chat_id = int(message.command[1])
        category = " ".join(message.command[2:])
        
        await channels_col.update_one(
            {"chat_id": target_chat_id},
            {"$set": {"category": category, "active": True, "admin_id": message.from_user.id}},
            upsert=True
        )
        await message.reply_text(f"✅ **Linked!** Bot will post **{category}** in channel `{target_chat_id}`.")
    except ValueError:
        await message.reply_text("❌ Invalid ID. It must be a number starting with -100.")

# --- STARTUP ---
if __name__ == "__main__":
    Thread(target=run_flask).start()
    
    loop = asyncio.get_event_loop()
    loop.create_task(auto_post_engine())
    
    print("Bot is starting...")
    bot.run()
                    
