# Imports
import quart
from quart import Quart
from discord.ext import commands

app = Quart(__name__)

@app.route("/")
def starting_url():
    status_code = quart.Response(status=200)
    return status_code

class QuartServer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        await app.run_task(host='0.0.0.0', port=10000)

async def setup(bot):
    await bot.add_cog(QuartServer(bot))
