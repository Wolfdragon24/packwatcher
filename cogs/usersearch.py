import discord
from discord import app_commands
import requests

ERROR_HEX = 0xeb1515
SUCCESS_HEX = 0x6edd67

PLAYERDB_MINECRAFT_API = "https://playerdb.co/api/player/minecraft/"

class UserSearch(app_commands.Group):
    @app_commands.command()
    @app_commands.describe(search="Username or UUID to search")
    async def user(self, interaction: discord.Interaction, search: str):
        """Outputs information regarding a certain Minecraft account"""

        requester = f"Requested by {interaction.user.name}."

        request = requests.get(f"{PLAYERDB_MINECRAFT_API}{search}", timeout=5)
        request_data = request.json()

        if (request.status_code != requests.codes['ok']):
            error_embed_dict = {
                "title": "Error - User Search",
                "footer": {
                    "text": requester
                },
                "color": ERROR_HEX,
                "fields": [
                    {
                        "name": f"{request_data.message}",
                        "value": f"No user was found with the username or UUID '{discord.utils.escape_markdown(search)}'"
                    }
                ]
            }

            await interaction.send_message(embed=discord.Embed.from_dict(error_embed_dict))
            return
        
        cleaned_username = discord.utils.escape_markdown(request_data.data.player.username)
        uuid = request_data.data.player.raw_id
        formatted_uuid = request_data.data.player.id
        avatar = request_data.data.avatar

        success_embed_dict = {
            "title": f"User Search - '{cleaned_username}'",
            "url": f"https://namemc.com/search?q={search}",
            "image": {
                "url": avatar
            },
            "footer": {
                "text": requester
            },
            "color": SUCCESS_HEX,
            "fields": [
                {
                    "name": "Username",
                    "value": cleaned_username,
                    "inline": False
                },
                {
                    "name": "Formatted UUID",
                    "value": formatted_uuid
                },
                {
                    "name": "UUID",
                    "value": uuid
                }
            ]
        }

        await interaction.send_message(embed=discord.Embed.from_dict(success_embed_dict))
