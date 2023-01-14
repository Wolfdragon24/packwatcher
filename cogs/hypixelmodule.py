#import
import os
import math
import datetime
from datetime import datetime

import discord
import requests
from discord.ext import commands
from pytz import timezone
from dotenv import dotenv_values

# Bot Setup
BASEDIR = os.path.abspath(os.path.dirname(__file__))
ENV_POS = os.path.join(BASEDIR, '../.env')

config = {
    **dotenv_values(ENV_POS),
    **os.environ,
}

TIMEZONE = timezone(config["BOT_TIMEZONE"])
API_KEY = config["HYPIXEL_API_KEY"]

#levelcalc vars
easylevels = 4
easylevelxp = 7000
xpperprestige = 96 * 5000 + easylevelxp
levelsperprestige = 100
highestprestige = 10

#level calc functions
def getlevelrespectingprestige(level):
    if level > highestprestige * levelsperprestige:
        return level - highestprestige * levelsperprestige

    return level % levelsperprestige

def getexpfromlevel(level):
    exp = 0
    if level:
        respectedlevel = getlevelrespectingprestige(level)
        if respectedlevel > easylevels:
            exp = 5000
        if respectedlevel == 1:
            exp = 500
        elif respectedlevel == 2:
            exp = 1000
        elif respectedlevel == 3:
            exp = 2000
        elif respectedlevel == 4:
            exp = 3500
        else:
            exp = 5000

    return exp

def getlevelfromexp(exp):
    prestiges = math.floor(exp/xpperprestige)
    level = prestiges * levelsperprestige
    expwithoutprestige = exp - prestiges * xpperprestige

    count = 1
    while count <= easylevels:
        expforeasylevel = getexpfromlevel(count)
        if expwithoutprestige < expforeasylevel:
            break
        count += 1
        expwithoutprestige -= expforeasylevel

    return level + math.floor(expwithoutprestige / 5000)

#hypixel module commands
class HypixelModule(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['hypixelstatus'])
    async def hypixelcheck(self, ctx, username = None):
        req = "Requested by " + ctx.message.author.name + "."
        await ctx.message.delete()

        if not username:
            warn = discord.Embed(title="No Username Entered", color=0x6edd67)
            warn.add_field(name="Error",value="Please enter the intended username, the command is .hypixelcheck <Username> or .hypixelstatus <Username>",inline=False)
            warn.set_footer(text=req)

            await ctx.send(embed=warn)
            return

        try:
            uuidget = requests.get(f"https://api.minetools.eu/uuid/{username}").json()
            uuid = uuidget["id"]
            statusdata = requests.get(f"https://api.hypixel.net/status?key={API_KEY}&uuid={uuid}").json()
            if not statusdata["success"] and statusdata["cause"] == "Invalid API key":
                return

            embed = discord.Embed(title=f"Hypixel Player Status - {uuidget['name']}",color=0x6edd67)

            session = statusdata["session"]

            if session["online"]:
                status = "Online"
                embed.add_field(name="Status",value=status,inline=False)
                if "gameType" in session:
                    gametype = session["gameType"]
                    embed.add_field(name="Gamemode",value=gametype,inline=True)
                if "mode" in session:
                    gamemode = session["mode"]
                    embed.add_field(name="Game Type",value=gamemode,inline=True)
                if "map" in session:
                    game_map = session["map"]
                    embed.add_field(name="Map",value=game_map,inline=True)
            else:
                status = "Offline"
                embed.add_field(name="Status",value=status,inline=True)

                try:
                    playerdata = requests.get(f"https://api.hypixel.net/player?key={API_KEY}&uuid={uuid}").json()
                    lastonline = playerdata["player"]["lastLogin"]
                    lastjoin = datetime.fromtimestamp(lastonline / 1e3)
                    locallastjoin = lastjoin.astimezone(TIMEZONE).strftime("%d %B %Y - %I:%M:%S %p")
                    embed.add_field(name="Last Seen",value=locallastjoin,inline=True)

                    pastdata = requests.get(f"https://api.hypixel.net/recentGames?key={API_KEY}&uuid={uuid}").json()
                    lastdata = pastdata["games"][0]
                    if "gameType" in lastdata:
                        lgametype = lastdata["gameType"]
                        embed.add_field(name="Last Gamemode",value=lgametype,inline=True)
                    if "mode" in lastdata:
                        lgamemode = lastdata["mode"]
                        embed.add_field(name="Last Game Type",value=lgamemode,inline=True)
                    if "map" in lastdata:
                        lmap = lastdata["map"]
                        embed.add_field(name="Last Map",value=lmap,inline=True)
                except:
                    embed.add_field(name="No data",value="No past data was found",inline=True)

            embed.set_footer(text=req)
            await ctx.send(embed=embed)
        except:
            warn = discord.Embed(title="No Player Found", color=0x6edd67)
            warn.add_field(name="Error",value=f"No players were found with the username: {username}",inline=False)
            warn.set_footer(text=req)

            await ctx.send(embed=warn)

    @commands.command(aliases=["bedwarsstats"])
    async def bedwarsinfo(self, ctx, username = None):
        req = "Requested by " + ctx.message.author.name + "."
        await ctx.message.delete()

        if not username:
            warn = discord.Embed(title="No Username Entered", color=0x6edd67)
            warn.add_field(name="Error",value=f"Please enter the intended username, the command is .bedwarsinfo <Username> or .bedwarsstats <Username>",inline=False)
            warn.set_footer(text=req)

            await ctx.send(embed=warn)
            return

        uuidget = requests.get(f"https://api.minetools.eu/uuid/{username}").json()

        try:
            uuid = uuidget["id"]
            playerdata = requests.get(f"https://api.hypixel.net/player?key={API_KEY}&uuid={uuid}").json()
            bedwarsinfo = playerdata["player"]["stats"]["Bedwars"]

            embed = discord.Embed(title=f"Hypixel Bedwars Statistics - {uuidget['name']}",color=0x6edd67)

            experience = bedwarsinfo.get("Experience", "0")
            coins = bedwarsinfo.get("coins", "0")
            plyrlevel = playerdata["player"]["achievements"]["bedwars_level"]
            beds_broken = playerdata["player"]["achievements"]["bedwars_beds"]
            loot_box = playerdata["player"]["achievements"]["bedwars_loot_box"]
            totalgames = bedwarsinfo.get("games_played_bedwars", "0")
            ffgames = bedwarsinfo.get("four_four_games_played_bedwars", "0")
            thfgames = bedwarsinfo.get("four_three_games_played_bedwars", "0")
            twegames = bedwarsinfo.get("eight_two_games_played_bedwars", "0")
            oegames = bedwarsinfo.get("eight_one_games_played_bedwars", "0")
            totalwins = bedwarsinfo.get("wins_bedwars", "0")
            ffwins = bedwarsinfo.get("four_four_wins_bedwars", "0")
            thfwins = bedwarsinfo.get("four_three_wins_bedwars", "0")
            twewins = bedwarsinfo.get("eight_two_wins_bedwars", "0")
            oewins = bedwarsinfo.get("eight_one_wins_bedwars", "0")
            totalkills = bedwarsinfo.get("kills_bedwars")
            ffkills = bedwarsinfo.get("four_four_kills_bedwars", "0")
            thfkills = bedwarsinfo.get("four_three_kills_bedwars", "0")
            twekills = bedwarsinfo.get("eight_two_kills_bedwars", "0")
            oekills = bedwarsinfo.get("eight_one_kills_bedwars", "0")
            totaldeaths = bedwarsinfo.get("deaths_bedwars", "0")
            ffdeaths = bedwarsinfo.get("four_four_deaths_bedwars", "0")
            thfdeaths = bedwarsinfo.get("four_three_deaths_bedwars", "0")
            twedeaths = bedwarsinfo.get("eight_two_deaths_bedwars", "0")
            oedeaths = bedwarsinfo.get("eight_one_deaths_bedwars", "0")
            totalwinstreak = bedwarsinfo.get("winstreak", "0")
            ffwinstreak = bedwarsinfo.get("four_four_winstreak", "0")
            thfwinstreak = bedwarsinfo.get("four_three_winstreak", "0")
            twewinstreak = bedwarsinfo.get("eight_two_winstreak", "0")
            oewinstreak = bedwarsinfo.get("eight_one_winstreak", "0")

            games = f"{totalgames} | {ffgames} {thfgames} {twegames} {oegames}"
            wins = f"{totalwins} | {ffwins} {thfwins} {twewins} {oewins}"
            kills = f"{totalkills} | {ffkills} {thfkills} {twekills} {oekills}"
            deaths = f"{totaldeaths} | {ffdeaths} {thfdeaths} {twedeaths} {oedeaths}"
            winstreak = f"{totalwinstreak} | {ffwinstreak} {thfwinstreak} {twewinstreak} {oewinstreak}"

            data = f"Format: Total | 4x4 4x3 8x2 8x1\n\nGames: {games}\nWins: {wins}\nKills: {kills}\nDeaths: {deaths}\nWinstreak: {winstreak}"

            embed.add_field(name="Experience",value=f"{experience:,}",inline=True)
            embed.add_field(name="Level",value=f"{plyrlevel:,}",inline=True)
            embed.add_field(name="Coins",value=f"{coins:,}",inline=True)
            embed.add_field(name="Beds Broken", value=f"{beds_broken:,}", inline=True)
            embed.add_field(name="Loot Chests Opened", value=f"{loot_box:,}", inline=True)
            embed.add_field(name="Data",value=data,inline=False)
        except:
            embed = discord.Embed(title=f"Hypixel Bedwars Statistics - {username}", color=0x6edd67)
            embed.add_field(name="Error",value="Data is missing or unavailable.", inline=False)

        embed.set_footer(text=req)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(HypixelModule(bot))
