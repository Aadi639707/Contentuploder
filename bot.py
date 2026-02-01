import os
import asyncio
import re
import requests
from bs4 import BeautifulSoup
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from flask import Flask
from threading import Thread

# --- RENDER WEB SERVER (To bypass Port Timeout error) ---
app = Flask(__name__)
@app.route('/')
def health_check():
    return "Bot is alive and running 24/7!"

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
            custom_interval = channel.get("interval", 3600) # Default 1 hour
            
            # Find and Post
            links = await fetch_movie_links(category)
            for link in links:
                if await history_col.find_one({"link": link, "chat_id": chat_id}):
                    continue
                
                caption = (
                    f"🎬 **New Content Uploaded!**\n\n"
                    f"📂 **Category:** {category}\n"
                    f"🔗 **Download Link:** {link}\n\n"
                    f"✨ *Powered by Content Pilot AI*"
                )
                
                try:
                    await bot.send_message(chat_id, caption)
                    await history_col.insert_one({"link": link, "chat_id": chat_id})
                    break 
                except Exception as e:
                    print(f"Post error: {e}")
            
            await asyncio.sleep(5) # Gap between multiple channels
            
        await asyncio.sleep(10) # Global check interval

# --- COMMANDS ---
@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text(
        "🚀 **Content Pilot AI v2.0**\n\n"
        "I can automate your channels directly from this DM.\n\n"
        "**Commands:**\n"
        "1️⃣ `/setup <ChannelID> <Category>` - Connect channel\n"
        "2️⃣ `/time <ChannelID> <Value><Unit>` - Set interval\n\n"
        "Example:\n`/setup -100123456789 Movies` \n`/time -100123456789 30m`"
    )

@bot.on_message(filters.command("setup") & filters.private)
async def setup_remote(client, message):
    if len(message.command) < 3:
        return await message.reply_text("❌ Use: `/setup <ID> <Category>`")
    try:
        target_chat_id = int(message.command[1])
        category = " ".join(message.command[2:])
        await channels_col.update_one(
            {"chat_id": target_chat_id},
            {"$set": {"category": category, "active": True, "admin_id": message.from_user.id}},
            upsert=True
        )
        await message.reply_text(f"✅ **Linked!** Category: **{category}**")
    except:
        await message.reply_text("❌ Error in ID or Category.")

@bot.on_message(filters.command("time") & filters.private)
async def set_flexible_time(client, message):
    if len(message.command) < 3:
        return await message.reply_text("❌ Use: `/time <ID> <30s/10m/2h>`")
    
    try:
        target_chat_id = int(message.command[1])
        time_val = message.command[2].lower()
        seconds = 0
        
        if time_val.endswith("s"): seconds = int(re.findall(r'\d+', time_val)[0])
        elif time_val.endswith("m"): seconds = int(re.findall(r'\d+', time_val)[0]) * 60
        elif time_val.endswith("h"): seconds = int(re.findall(r'\d+', time_val)[0]) * 3600
        else: return await message.reply_text("❌ Use `s`, `m`, or `h` unit.")

        await channels_col.update_one({"chat_id": target_chat_id}, {"$set": {"interval": seconds}})
        await message.reply_text(f"✅ **Interval set to {time_val}!**")
    except:
        await message.reply_text("❌ Error setting time.")

# --- STARTUP ---
if __name__ == "__main__":
    Thread(target=run_flask).start()
    loop = asyncio.get_event_loop()
    loop.create_task(auto_post_engine())
    bot.run()
    
