import os
import asyncio
import requests
from bs4 import BeautifulSoup
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from flask import Flask
from threading import Thread

# --- RENDER WEB SERVER ---
app = Flask(__name__)
@app.route('/')
def health_check():
    return "Bot is alive and running!"

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

# --- SCRAPER LOGIC (Example: Search Engine Scraping) ---
async def fetch_movie_links(query):
    """Simple scraper that searches for links based on category"""
    search_url = f"https://www.google.com/search?q={query}+direct+download+link+movies"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(search_url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        links = []
        for a in soup.find_all('a', href=True):
            link = a['href']
            if "url?q=" in link and "webcache" not in link:
                clean_link = link.split("url?q=")[1].split("&sa=")[0]
                links.append(clean_link)
        return links[:5] # Return top 5 links
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
            
            # Find Content
            links = await fetch_movie_links(category)
            
            for link in links:
                # Check if already posted
                if await history_col.find_one({"link": link, "chat_id": chat_id}):
                    continue
                
                # Format Caption (AI Style)
                caption = (
                    f"🎬 **New Content Uploaded!**\n\n"
                    f"📂 **Category:** {category}\n"
                    f"🔗 **Link:** {link}\n\n"
                    f"✨ *Automated by Content Pilot AI*"
                )
                
                try:
                    await bot.send_message(chat_id, caption)
                    await history_col.insert_one({"link": link, "chat_id": chat_id})
                    break # Post one at a time
                except Exception as e:
                    print(f"Post error in {chat_id}: {e}")
            
        await asyncio.sleep(3600) # Wait 1 Hour

# --- COMMANDS ---
@bot.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "🚀 **Content Pilot AI v1.0**\n\n"
        "I am a fully automated content scraper and poster.\n"
        "1. Add me to your channel as Admin.\n"
        "2. Use /setup <category> to start auto-posting.\n"
        "3. Language: Fully English supported."
    )

@bot.on_message(filters.command("setup") & filters.group)
async def setup_channel(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /setup Movies Hindi")
    
    category = " ".join(message.command[1:])
    chat_id = message.chat.id
    
    await channels_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"category": category, "active": True}},
        upsert=True
    )
    await message.reply_text(f"✅ Success! I will post **{category}** content every hour.")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # Start Flask thread for Render
    Thread(target=run_flask).start()
    
    # Run Bot
    bot.run()
    
    # Start loop
    loop = asyncio.get_event_loop()
    loop.create_task(auto_post_engine())
              
