# Imports
import os
import discord

from discord.ext import commands
from dotenv import dotenv_values

# Bot Setup
BASEDIR = os.path.abspath(os.path.dirname(__file__))
ENV_POS = os.path.join(BASEDIR, '../.env')

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
    info_status = discord.Activity(type=discord.ActivityType.listening, name=".help")
    await bot.change_presence(activity=info_status)

# Bot Base Commands
@bot.command()
async def invite(ctx):
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
async def help(ctx):
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


bot.run(config["DISCORD_BOT_TOKEN"])
