import os
import socket
import discord
from discord import app_commands

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

USER = config["MONGODB_USER"]
PW = config["MONGODB_PASSWORD"]
BOT_OWNER = int(config["BOT_OWNER"])

cluster = MongoClient(f"mongodb+srv://{USER}:{PW}@packwatchercluter-iune6.mongodb.net/test?retryWrites=true&w=majority&authSource=admin")
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

class ServerStatus(app_commands.Group):
    @app_commands.command()
    @app_commands.describe(search="IP of server to search, if not default")
    async def status(self, interaction: discord.Interaction, search: str = "default"):
        """Displays status information about an inputted or default server."""

        requester = f"Requested by {interaction.user.name}."

        if search == "default":
            if isinstance(interaction.channel, discord.channel.DMChannel):
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

                await interaction.send_message(embed=discord.Embed.from_dict(error_embed_dict))
                return

            defaults_index = getindex(default_servers, "guildid", interaction.guild_id)

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

                await interaction.send_message(embed=discord.Embed.from_dict(error_embed_dict))
                return

            server_ip = default_servers[defaults_index]["serverip"]
        else:
            server_ip = search

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

            await interaction.send_message(embed=discord.Embed.from_dict(offline_embed_dict))
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
                    "value": server_ip
                },
                {
                    "name": "Status",
                    "value": 'Server is currently online!'
                },
                {
                    "name": "Player Count",
                    "value": player_count
                }, 
                {
                    "name": "Version",
                    "value": version
                }
            ]
        }

        if info.players.sample:
            online_embed_dict["fields"].append({
                "name": "Player List",
                "value": discord.utils.escape_markdown(", ".join([player.name for player in info.players.sample]))
            })

        await interaction.send_message(embed=discord.Embed.from_dict(online_embed_dict))

    @app_commands.command()
    @app_commands.describe(ip="IP of server to set as default")
    async def setdefault(self, interaction: discord.Interaction, server_ip: str):
        """Sets the inputted ip as the default for the Discord server."""

        requester = f"Requested by {interaction.user.name}."

        if isinstance(interaction.channel, discord.channel.DMChannel):
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

            await interaction.send_message(embed=discord.Embed.from_dict(error_embed_dict))
            return
        
        if not interaction.user.guild_permissions.manage_guild and interaction.user.id != BOT_OWNER:
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

            await interaction.send_message(embed=discord.Embed.from_dict(error_embed_dict))
            return
        
        guild_id = interaction.guild_id
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

        await interaction.send_message(embed=discord.Embed.from_dict(success_embed_dict))
