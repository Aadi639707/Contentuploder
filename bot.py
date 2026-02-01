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

# --- RENDER WEB SERVER ---
app = Flask(__name__)
@app.route('/')
def health_check():
    return "Targeted Scraper Bot is Running!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "")

# TARGET WEBSITE (Yahan apni website ka base URL daalein)
# Example: https://thepiratebay.org ya koi bhi movie site
TARGET_SITE = "https://www.google.com/search?q=site:example.com+" 

bot = Client("ContentPilot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- DATABASE SETUP ---
db_client = AsyncIOMotorClient(MONGO_URI)
db = db_client["ContentPilotDB"]
channels_col = db["channels"]
history_col = db["history"]

# --- TARGETED SCRAPER LOGIC ---
async def fetch_specific_links(query):
    """Searches only within the targeted website"""
    search_query = query.replace(" ", "+")
    # Hum specific site par search karne ke liye Google Dork use kar rahe hain
    # Aap directly website ka search URL bhi yahan daal sakte hain
    url = f"{TARGET_SITE}{search_query}"
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        links = []
        
        for a in soup.find_all('a', href=True):
            link = a['href']
            # Link filtering logic
            if "url?q=" in link:
                clean_link = link.split("url?q=")[1].split("&sa=")[0]
                if clean_link.startswith("http") and "google.com" not in clean_link:
                    links.append(clean_link)
        return list(set(links))[:5]
    except Exception as e:
        print(f"Target Scraper Error: {e}")
        return []

# --- AUTOMATION ENGINE ---
async def channel_task(chat_id, category, interval):
    print(f"Started Targeted Bot for {chat_id} | Category: {category}")
    while True:
        links = await fetch_specific_links(category)
        
        for link in links:
            if await history_col.find_one({"link": link, "chat_id": chat_id}):
                continue
            
            caption = (
                f"🎬 **New Upload from Targeted Source!**\n\n"
                f"📂 **Category:** {category}\n"
                f"🔗 **Download:** {link}\n\n"
                f"✨ *Verified by Content Pilot v2.5*"
            )
            
            try:
                await bot.send_message(chat_id, caption)
                await history_col.insert_one({"link": link, "chat_id": chat_id})
                break 
            except Exception as e:
                print(f"Error posting: {e}")
        
        await asyncio.sleep(interval)

async def start_all_engines():
    cursor = channels_col.find({"active": True})
    async for channel in cursor:
        asyncio.create_task(channel_task(
            channel["chat_id"], 
            channel["category"], 
            channel.get("interval", 3600)
        ))

# --- COMMANDS ---
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    await message.reply_text("🎯 **Targeted Scraper Ready!**\nAdd to channel and use `/setup <ID> <Category>`")

@bot.on_message(filters.command("setup") & filters.private)
async def setup_cmd(client, message):
    if len(message.command) < 3:
        return await message.reply_text("❌ Usage: `/setup -100xxxx Movies`")
    
    chat_id = int(message.command[1])
    category = " ".join(message.command[2:])
    interval = 3600 
    
    await channels_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"category": category, "active": True, "interval": interval}},
        upsert=True
    )
    asyncio.create_task(channel_task(chat_id, category, interval))
    await message.reply_text(f"✅ **Linked!** Scraping from targeted site.")

@bot.on_message(filters.command("time") & filters.private)
async def time_cmd(client, message):
    if len(message.command) < 3:
        return await message.reply_text("❌ Usage: `/time <ID> <Value><Unit>`")
    
    chat_id = int(message.command[1])
    time_val = message.command[2].lower()
    seconds = 0
    if time_val.endswith("s"): seconds = int(re.findall(r'\d+', time_val)[0])
    elif time_val.endswith("m"): seconds = int(re.findall(r'\d+', time_val)[0]) * 60
    elif time_val.endswith("h"): seconds = int(re.findall(r'\d+', time_val)[0]) * 3600
    
    await channels_col.update_one({"chat_id": chat_id}, {"$set": {"interval": seconds}})
    await message.reply_text(f"✅ **Timer set to {time_val}!**")

# --- MAIN ---
if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot.start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_all_engines())
    asyncio.get_event_loop().run_forever()
    
