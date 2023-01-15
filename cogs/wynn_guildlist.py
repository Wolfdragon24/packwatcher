# Imports
import asyncio
import os
import time
import json
import ast
from concurrent.futures import ThreadPoolExecutor

import requests
import discord
from discord.ext import commands, tasks
from dotenv import dotenv_values

import global_vars

# Bot Setup
BASEDIR = os.path.abspath(os.path.dirname(__file__))
ENV_POS = os.path.join(BASEDIR, '../.env')

config = {
    **dotenv_values(ENV_POS),
    **os.environ,
}

USER_KEY = config["PASTEE_USER_KEY"]
WYNN_TOKEN = config["WYNNCRAFT_API_TOKEN"]

PASTEE_BASE_URL = "https://api.paste.ee/v1/pastes"
WYNN_BASE_URL = "https://api.wynncraft.com/public_api.php"
WYNN_GUILD_LIST_URL = f"{WYNN_BASE_URL}?action=guildList"
WYNN_GUILD_STATS_URL = f"{WYNN_BASE_URL}?action=guildStats"

PASTE_NAME = "Guild List"

paste_headers = {'X-Auth-Token': USER_KEY}
wynn_headers = {"apikey": WYNN_TOKEN}

def get_key(title):
    request = requests.get(PASTEE_BASE_URL, headers=paste_headers, timeout=10)
    if request.status_code != 200:
        pass
    paste_lst = request.json()
    for paste in paste_lst["data"]:
        if paste["description"] == title:
            return paste["id"]

    payload = {"description": title, "expiration": "31536000", "sections": [{"contents": str({})}]}
    send = requests.post(PASTEE_BASE_URL, json=payload, headers=paste_headers, timeout=10).json()
    return send["id"]

def paste_fetch(title):
    key = get_key(title)

    request = requests.get(f"{PASTEE_BASE_URL}/{key}", headers=paste_headers, timeout=10)
    if request.status_code != 200:
        pass
    paste_data = request.text
    loaded = json.loads(paste_data.replace("\'","\""))
    data = loaded["paste"]["sections"][0]["contents"]
    try:
        data = json.loads(data)
    except json.decoder.JSONDecodeError:
        data = ast.literal_eval(data)
    return data

def guild_list_update():
    guild_list = global_vars.guild_list

    key = get_key(PASTE_NAME)

    guilds_fetched_list = requests.get(WYNN_GUILD_LIST_URL, params=wynn_headers, timeout=10).json()

    checklist = []

    for guildname in guilds_fetched_list['guilds']:
        if guildname not in guild_list.values() and not any(guildname in guildnames for guildnames in guild_list.values()):
            checklist.append(guildname)

    for guildname in checklist:
        request = requests.get(f"{WYNN_GUILD_STATS_URL}&command={guildname}", params=wynn_headers, timeout=10)
        if request.status_code != 200:
            continue
        guild_stats = request.json()
        prefix = (guild_stats["prefix"]).lower()

        if prefix in guild_list:
            guild_list[prefix] += f'|{guildname}'
        else:
            guild_list[prefix] = guildname
        time.sleep(0.6)

    requests.delete(f"https://api.paste.ee/v1/pastes/{key}", headers=paste_headers, timeout=10).json()

    payload = {"description":PASTE_NAME, "expiration":"31536000", "sections":[{"contents":str(guild_list).replace("\'","\"")}]}
    requests.post("https://api.paste.ee/v1/pastes", json=payload, headers=paste_headers, timeout=10)

class GuildListUpdater(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        if not global_vars.guild_list:
            try:
                global_vars.guild_list = paste_fetch(PASTE_NAME)
            except:
                pass

        if not global_vars.dev_mode:
            self.run_playtime_update.start()

    async def cog_unload(self):
        self.run_playtime_update.cancel()

    @tasks.loop(hours=12)
    async def run_playtime_update(self):
        await asyncio.get_event_loop().run_in_executor(ThreadPoolExecutor(), guild_list_update)

async def setup(bot):
    await bot.add_cog(GuildListUpdater(bot))
