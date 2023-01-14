# Imports
import asyncio
import os
from typing import Literal, Optional
import logging
import re
import traceback

import discord
from discord.ext import commands
from discord.ext.commands import Greedy, Context, CommandNotFound
from dotenv import dotenv_values
import quart
from quart import Quart

import global_vars

# Bot Setup
BASEDIR = os.path.abspath(os.path.dirname(__file__))
ENV_POS = os.path.join(BASEDIR, '.env')

config = {
    **dotenv_values(ENV_POS),
    **os.environ,
}

intents = discord.Intents.all()
handler = logging.FileHandler(filename='bot.log', encoding='utf-8')

bot = commands.Bot(command_prefix=".", intents=intents)
bot.remove_command("help")

# Bot Base Events
@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')

# Bot Base Commands
@bot.command()
async def invite(ctx: Context):
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        pass

    embed_object = {
        "title": "Invite",
        "color": 0xa9e88b,
        "footer": {
            "text": f"Requested by {ctx.message.author.name}."
        },
        "fields": [{
            "name": "Bot Invite",
            "value": "You can invite me to any server by clicking [here](https://discord.com/api/oauth2/authorize?client_id=606829493193277441&permissions=8&scope=bot)",
        }],
    }

    embed = discord.Embed.from_dict(embed_object)

    await ctx.send(embed=embed)

@bot.command()
async def help(ctx: Context):
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        pass

    embed_object = {
        "title": "Help Menu",
        "color": 0xa9e88b,
        "footer": {
            "text": f"Requested by {ctx.message.author.name}."
        },
        "fields": [],
    }

@bot.command()
@commands.guild_only()
@commands.is_owner()
async def sync(
  ctx: Context, guilds: Greedy[discord.Object], spec: Optional[Literal["~", "*", "^"]] = None) -> None:
    if not guilds:
        if spec == "~":
            synced = await bot.tree.sync(guild=ctx.guild)
        elif spec == "*":
            bot.tree.copy_global_to(guild=ctx.guild)
            synced = await bot.tree.sync(guild=ctx.guild)
        elif spec == "^":
            bot.tree.clear_commands(guild=ctx.guild)
            await bot.tree.sync(guild=ctx.guild)
            synced = []
        else:
            synced = await bot.tree.sync()

        await ctx.send(
            f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}"
        )
        return

    ret = 0
    for guild in guilds:
        try:
            await bot.tree.sync(guild=guild)
        except discord.HTTPException:
            pass
        else:
            ret += 1

    await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

@bot.event
async def on_command_error(ctx, error):
    if global_vars.dev_mode:
        print(error)
    ignores = {
            121,    # the semaphore timeout period has expired
        }
    if (isinstance(error, CommandNotFound)) or (isinstance(error, OSError) and error in ignores):
        return

    errorchannel = bot.get_channel(837917735089340446)
    embed = discord.Embed(title="PackWatcher Error", color=0xeb1515)

    embed.add_field(name="Error",value="An error occurred in typical operation.")

    req = "Automated Error Logging."
    embed.set_footer(text=req)

    error = re.sub(r'"(.*)"', "", traceback.format_exc(), 1)
    ertext = f"```{error}```"

    await errorchannel.send(embed=embed)
    await errorchannel.send(ertext)

EXTENSION_LIST = [
    "cogs.wynn_guildlist", "cogs.wynn_playtime", "cogs.serverstatus", "cogs.usersearch",
    "cogs.hypixelmodule", "cogs.owner"
]

app = Quart(__name__)

@app.route("/")
def starting_url():
    status_code = quart.Response(status=200)
    return status_code

async def main():
    async with bot:
        for extension in EXTENSION_LIST:
            await bot.load_extension(extension)
        if not global_vars.dev_mode:
            bot.loop.create_task(app.run_task(host='0.0.0.0', port=10000))
        await bot.start(config["DISCORD_BOT_TOKEN"])

asyncio.run(main())
