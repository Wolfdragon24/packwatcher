# Imports
import asyncio
import os
from typing import Literal, Optional
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import quart
import discord
from discord.ext import commands
from discord.ext.commands import Greedy, Context
from dotenv import dotenv_values
from quart import Quart

# Bot Setup
BASEDIR = os.path.abspath(os.path.dirname(__file__))
ENV_POS = os.path.join(BASEDIR, '.env')

config = {
    **dotenv_values(ENV_POS),
    **os.environ,
}

intents = discord.Intents.all()

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
        "footer": f"Requested by {ctx.message.author.name}.",
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
        "footer": f"Requested by {ctx.message.author.name}.",
        "fields": [],
    }

@bot.command()
@commands.guild_only()
@commands.is_owner()
async def sync(
  ctx: Context, guilds: Greedy[discord.Object], spec: Optional[Literal["~", "*", "^"]] = None) -> None:
    if not guilds:
        if spec == "~":
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "*":
            ctx.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "^":
            ctx.bot.tree.clear_commands(guild=ctx.guild)
            await ctx.bot.tree.sync(guild=ctx.guild)
            synced = []
        else:
            synced = await ctx.bot.tree.sync()

        await ctx.send(
            f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}"
        )
        return

    ret = 0
    for guild in guilds:
        try:
            await ctx.bot.tree.sync(guild=guild)
        except discord.HTTPException:
            pass
        else:
            ret += 1

    await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

EXTENSION_LIST = [
    "cogs.wynn_guildlist", "cogs.wynn_playtime", "cogs.serverstatus", "cogs.usersearch",
]

app = Quart(__name__)

@app.route("/")
def starting_url():
    status_code = quart.Response(status=200)
    return status_code

async def main():
    await app.run_task(host='0.0.0.0', port=10000)

    async with bot:
        for extension in EXTENSION_LIST:
            await bot.load_extension(extension)
        await bot.start(config["DISCORD_BOT_TOKEN"])

asyncio.run(main())
