import os
import socket
from urllib.parse import quote_plus

import discord
from discord.ext import commands
from pymongo import MongoClient
from mcstatus import JavaServer
from dotenv import dotenv_values

# Bot Setup
BASEDIR = os.path.abspath(os.path.dirname(__file__))
ENV_POS = os.path.join(BASEDIR, '../.env')

config = {
    **dotenv_values(ENV_POS),
    **os.environ,
}

MONGO_USER = quote_plus(config["MONGODB_USER"])
MONGO_PW = quote_plus(config["MONGODB_PASSWORD"])
MONGO_URL = config["MONGODB_URL"]
BOT_OWNER = int(config["BOT_OWNER"])

cluster = MongoClient(f"mongodb+srv://{MONGO_USER}:{MONGO_PW}@{MONGO_URL}")
db = cluster["discordbot"]
defaults = db["defaults"]

default_servers = [*defaults.find()]

ERROR_HEX = 0xeb1515
SUCCESS_HEX = 0x6edd67

def getindex(lst, key, value):
    for i, dic in enumerate(lst):
        if dic[key] == value:
            return i
    return None

class ServerStatus(commands.Cog):
    @commands.hybrid_command(name="status")
    async def status(self, ctx: commands.Context, server_ip: str = None) -> None:
        """Displays status information about an inputted or default server. (.status <Optional: server_ip> or /status <Optional: server_ip>"""

        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        requester = f"Requested by {ctx.author.name}."

        if server_ip is None:
            if isinstance(ctx.channel, discord.channel.DMChannel):
                error_embed_dict = {
                    "title": "Error - Default Server Status",
                    "footer": {
                        "text": requester
                    },
                    "color": ERROR_HEX,
                    "fields": [
                        {
                            "name": "Cannot Use in DM Channels",
                            "value": "You cannot use the .status command in DMs. Please run this command in a server or supply an IP request instead."
                        }
                    ]
                }

                await ctx.send(embed=discord.Embed.from_dict(error_embed_dict))
                return

            defaults_index = getindex(default_servers, "guildid", ctx.guild.id)

            if defaults_index is None:
                error_embed_dict = {
                    "title": "Error - Default Server Status",
                    "footer": {
                        "text": requester
                    },
                    "color": ERROR_HEX,
                    "fields": [
                        {
                            "name": "Default Server Not Found",
                            "value": "A default server does not exist. Please set a default server with .setdefault (IP) and try again."
                        }
                    ]
                }

                await ctx.send(embed=discord.Embed.from_dict(error_embed_dict))
                return

            server_ip = default_servers[defaults_index]["serverip"]

        server = JavaServer.lookup(server_ip)
        try:
            info = server.status()
        except socket.gaierror:
            offline_embed_dict = {
                "title": "Server Status",
                "footer": {
                    "text": requester
                },
                "color": SUCCESS_HEX,
                "fields": [
                    {
                        "name": "Server IP",
                        "value": server_ip
                    },
                    {
                        "name": "Status",
                        "value": 'Server is currently offline!'
                    }
                ]
            }

            await ctx.send(embed=discord.Embed.from_dict(offline_embed_dict))
            return

        online = info.players.online
        player_max = info.players.max

        if online == 1:
            player_count = f"There is currently: 1/{player_max} players online."
        else:
            player_count = f"There are currently: {online}/{player_max} players online."

        version_raw = info.version.name
        version = " ".join([string for string in version_raw.split(" ") if not string.isalpha()])

        online_embed_dict = {
            "title": "Server Status",
            "footer": {
                "text": requester
            },
            "color": SUCCESS_HEX,
            "fields": [
                {
                    "name": "Server IP",
                    "value": server_ip,
                    "inline": True
                },
                {
                    "name": "Status",
                    "value": 'Server is currently online!',
                    "inline": True
                },
                {
                    "name": "Player Count",
                    "value": player_count,
                    "inline": True
                },
                {
                    "name": "Version",
                    "value": version,
                    "inline": True
                }
            ]
        }

        if info.players.sample:
            online_embed_dict["fields"].append({
                "name": "Player List",
                "value": discord.utils.escape_markdown(", ".join([player.name for player in info.players.sample]))
            })

        await ctx.send(embed=discord.Embed.from_dict(online_embed_dict))

    @commands.hybrid_command(name="setdefault")
    async def setdefault(self, ctx: commands.Context, server_ip: str) -> None:
        """Sets the inputted ip as the default for the Discord server. (.setdefault <server_ip> or /setdefault <server_ip>)"""

        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        requester = f"Requested by {ctx.author.name}."

        if isinstance(ctx.channel, discord.channel.DMChannel):
            error_embed_dict = {
                "title": "Error - Default Server Status",
                "footer": {
                    "text": requester
                },
                "color": ERROR_HEX,
                "fields": [
                    {
                        "name": "Cannot Use in DM Channels",
                        "value": "You cannot use the .setdefault command in DMs. Please run this command in a server or supply an IP request instead."
                    }
                ]
            }

            await ctx.send(embed=discord.Embed.from_dict(error_embed_dict))
            return
        
        if not ctx.author.guild_permissions.manage_guild and ctx.author.id != BOT_OWNER:
            error_embed_dict = {
                "title": "Error - Insufficient Permissions",
                "footer": {
                    "text": requester
                },
                "color": ERROR_HEX,
                "fields": [
                    {
                        "name": "Missing Guild Manage Permissions",
                        "value": "You do not have sufficient permissions to use this command."
                    }
                ]
            }

            await ctx.send(embed=discord.Embed.from_dict(error_embed_dict))
            return
        
        guild_id = ctx.guild.id
        defaults_index = getindex(default_servers, "guildid", guild_id)

        if defaults_index is None:
            defaults.update_one({"guildid":guild_id}, {"$set":{"serverip":server_ip}})
            del default_servers[defaults_index]
            default_servers.append({"guildid":guild_id, "serverip":server_ip})
        else:
            defaults.insert_one({"guildid":guild_id, "serverip":server_ip})
            default_servers.append({"guildid":guild_id, "serverip":server_ip})

        success_embed_dict = {
            "title": "Default Server IP Updated",
            "footer": {
                "text": requester
            },
            "color": SUCCESS_HEX,
            "fields": [
                {
                    "name": "New Server IP",
                    "value": server_ip
                }
            ]
        }

        await ctx.send(embed=discord.Embed.from_dict(success_embed_dict))

async def setup(bot):
    await bot.add_cog(ServerStatus(bot))
