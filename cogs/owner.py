#import
import ast
import asyncio
import base64
import concurrent
import copy
import datetime
import dateutil
import discord
import github
import io
import json
import linecache
import math
import mcstatus
import os
import pymongo
import pytz
import re
import requests
import string
import traceback
import tracemalloc
import time
import urllib
import random
import psutil

from dotenv import dotenv_values
from discord.ext import commands, tasks
from datetime import datetime
from pytz import timezone

tzone = timezone("Australia/Sydney")

# Bot Setup
BASEDIR = os.path.abspath(os.path.dirname(__file__))
ENV_POS = os.path.join(BASEDIR, '../.env')
MAIN_LOG_POS = os.path.join(BASEDIR, '../bot.log')

config = {
    **dotenv_values(ENV_POS),
    **os.environ,
}

# Constants
BOT_OWNER = int(config["BOT_OWNER"])

tracemalloc.start()

class OwnerCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.memory_check.start()
        self.process_mem_check.start()
        self.bot_logging.start()

    @commands.command()
    async def logmemd(self, ctx):
        if ctx.message.author.id == BOT_OWNER:
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')
            process_mem = psutil.Process().memory_info().rss

            out = "[ Top 10 ]"
            for stat in top_stats[:10]:
                out += f"\n{stat}"
            out += f"\nTotal process memory: {round(process_mem / 1024)} KiB ({round(process_mem / (1024 * 1024))} MiB)"

            await ctx.send(out)

    @commands.command()
    async def logmemc(self, ctx):
        if ctx.message.author.id == BOT_OWNER:
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')
            process_mem = psutil.Process().memory_info().rss

            print("[ Top 10 ]")
            for stat in top_stats[:10]:
                print(stat)
            print(f"Total process memory: {round(process_mem / 1024)} KiB ({round(process_mem / (1024 * 1024))} MiB)")

    @tasks.loop(minutes=30)
    async def memory_check(self):
        logchannel = self.bot.get_channel(1031895323783729232)

        out = "```"

        snapshot = tracemalloc.take_snapshot()
        snapshot = snapshot.filter_traces((
        tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
        tracemalloc.Filter(False, "<unknown>"),
        ))
        top_stats = snapshot.statistics("lineno")
        process_mem = psutil.Process().memory_info().rss

        out += f"\n[Top 10] - [{datetime.now(tzone).strftime('%d/%m/%Y-%H:%M:%S')}]"
        for index, stat in enumerate(top_stats[:10], 1):
            frame = stat.traceback[0]
            out += f"\n#{index}: {frame.filename}:{frame.lineno}: {round(stat.size / 1024)} KiB ({round(stat.size / (1024 * 1024))} MiB)"
            line = linecache.getline(frame.filename, frame.lineno).strip()
            if line:
                out += f'\n    {line}'

        other = top_stats[10:]
        if other:
            size = sum(stat.size for stat in other)
            out += f"\n{len(other)} other: {round(size / 1024)} KiB ({round(size / (1024 * 1024))} MiB)"
        total = sum(stat.size for stat in top_stats)
        out += f"\nTotal allocated size: {round(total / 1024)} KiB ({round(total / (1024 * 1024))} MiB)"
        out += f"\nTotal process memory: {round(process_mem / 1024)} KiB ({round(process_mem / (1024 * 1024))} MiB)"

        out += "\n```"

        await logchannel.send(out)

    @memory_check.before_loop
    async def before_memory_check(self):
        print("Memory Check: Waiting...")
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=1)
    async def process_mem_check(self):
        logchannel = self.bot.get_channel(1045451921630183464)
        out = "```"
        process_mem = psutil.Process().memory_info().rss
        out += f"\nTotal process memory: {round(process_mem / 1024)} KiB ({round(process_mem / (1024 * 1024))} MiB)"

        out += "\n```"
        await logchannel.send(out)
    
    @process_mem_check.before_loop
    async def before_process_mem_check(self):
        print("Process Memory Check: Waiting...")
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def bot_logging(self):
        log_channel = self.bot.get_channel(1056035790762815539)

        if os.path.getsize(MAIN_LOG_POS) > 0:
            await log_channel.send(file=discord.File(MAIN_LOG_POS))
            os.remove(MAIN_LOG_POS)

    @bot_logging.before_loop
    async def before_bot_logging(self):
        await self.bot.wait_until_ready()

    #evaluate statements
    @commands.command()
    async def eval(self, ctx, *statement):
        if ctx.message.author.id == BOT_OWNER:
            try:
                await ctx.message.delete()
            except:
                pass

            inputv = " ".join(statement)

            try:
                if statement[0].lower() not in ("true","on","hide"):

                    result = eval(inputv)
                    output = str(result)

                    if len(output) < 900:
                        warn = discord.Embed(title="Evaluate", color=0x1c9442)

                        warn.add_field(name="Input", value=inputv, inline=False)
                        warn.add_field(name="Evaluated Output", value=output, inline=False)

                        await ctx.send(embed=warn)
                    elif len(output) < 4800:
                        outs = [output[i:i+1000] for i in range(0,len(output), 1000)]

                        warn = discord.Embed(title="Evaluate", color=0x1c9442)

                        warn.add_field(name="Input", value=inputv)

                        for index in range(len(outs)):
                            chunk = outs[index]
                            if index == 0:
                                warn.add_field(name="Evaluated Output", value=chunk,inline=False)
                            else:
                                warn.add_field(name="Evaluated Output (cont.)", value=chunk,inline=False)

                        await ctx.send(embed=warn)
                    else:
                        warn = discord.Embed(title="Evaluate", color=0x1c9442)

                        warn.add_field(name="Input", value=inputv, inline=False)
                        warn.add_field(name="Evaluated Output", value="The output is longer than 5000 characters and will be sent as a file", inline=False)

                        file = discord.File(io.StringIO(output),"evaluated_output.txt")

                        await ctx.send(embed=warn)
                        await ctx.send(file=file)
                else:
                    for i in ("true","on","hide"):
                        inputv = inputv.replace(f'{i} ', '', 1)
                    eval(inputv)

            except:
                if statement[0].lower() not in ("true","on","hide"):
                    error = re.sub(r'"(.*)"', "", traceback.format_exc(),1)

                    warn = discord.Embed(title="Evaluate", color=0x941c1c)

                    warn.add_field(name="Input", value=inputv, inline=False)

                    warn.add_field(name="Error", value=error, inline=False)

                    await ctx.send(embed=warn)

    #evaluate statements
    @commands.command()
    async def asynceval(self, ctx, *statement):
        if ctx.message.author.id == BOT_OWNER:
            try:
                await ctx.message.delete()
            except:
                pass

            inputv = " ".join(statement)

            try:
                if statement[0].lower() not in ("true","on","hide"):

                    result = await eval(inputv)
                    output = str(result)

                    if len(output) < 900:
                        warn = discord.Embed(title="Async Evaluate", color=0x1c9442)

                        warn.add_field(name="Input", value=inputv, inline=False)
                        warn.add_field(name="Evaluated Output", value=output, inline=False)

                        await ctx.send(embed=warn)
                    elif len(output) < 4800:
                        outs = [output[i:i+1000] for i in range(0,len(output), 1000)]

                        warn = discord.Embed(title="Async Evaluate", color=0x1c9442)

                        warn.add_field(name="Input", value=inputv)

                        for index in range(len(outs)):
                            chunk = outs[index]
                            if index == 0:
                                warn.add_field(name="Evaluated Output", value=chunk,inline=False)
                            else:
                                warn.add_field(name="Evaluated Output (cont.)", value=chunk,inline=False)

                        await ctx.send(embed=warn)
                    else:
                        warn = discord.Embed(title="Async Evaluate", color=0x1c9442)

                        warn.add_field(name="Input", value=inputv, inline=False)
                        warn.add_field(name="Evaluated Output", value="The output is longer than 5000 characters and will be sent as a file", inline=False)

                        file = discord.File(io.StringIO(output),"evaluated_output.txt")

                        await ctx.send(embed=warn)
                        await ctx.send(file=file)
                else:
                    for i in ("true","on","hide"):
                        inputv = inputv.replace(f'{i} ', '', 1)
                    await eval(inputv)

            except:
                if statement[0].lower() not in ("true","on","hide"):
                    error = re.sub(r'"(.*)"', "", traceback.format_exc(),1)

                    warn = discord.Embed(title="Evaluate", color=0x941c1c)

                    warn.add_field(name="Input", value=inputv, inline=False)

                    warn.add_field(name="Error", value=error, inline=False)

                    await ctx.send(embed=warn)

    #evaluate statements
    @commands.command()
    async def exec(self, ctx, *statement):
        if ctx.message.author.id == BOT_OWNER:
            try:
                await ctx.message.delete()
            except:
                pass

            inputv = " ".join(statement)

            try:
                if statement[0].lower() not in ("true","on","hide"):
                    exec(inputv)

                    warn = discord.Embed(title="Evaluate", color=0x1c9442)

                    warn.add_field(name="Input", value=inputv, inline=False)

                    await ctx.send(embed=warn)

                else:
                    for i in ("true","on","hide"):
                        inputv = inputv.replace(f'{i} ', '', 1)
                    exec(inputv)

            except:
                if statement[0].lower() not in ("true","on","hide"):
                    error = re.sub(r'"(.*)"', "", traceback.format_exc(),1)

                    warn = discord.Embed(title="Evaluate", color=0x941c1c)

                    warn.add_field(name="Input", value=inputv, inline=False)

                    warn.add_field(name="Error", value=error, inline=False)

                    await ctx.send(embed=warn)

    #normal copy
    @commands.command()
    async def copy(self, ctx, *statement):
        if ctx.message.author.id == BOT_OWNER:
            try:
                await ctx.message.delete()
            except:
                pass

            inputv = " ".join(statement)

            await ctx.send(inputv)

    #embedcopy
    @commands.command()
    async def embedcopy(self, ctx, *statement):
        if ctx.message.author.id == BOT_OWNER:
            try:
                await ctx.message.delete()
            except:
                pass

            inputv = " ".join(statement)

            section = inputv.split("^")
            setup = section[0].split("~")

            colour = int(f"0x{setup[1]}", 0)
            if len(setup) >= 3:
                desc = setup[2]
                embed = discord.Embed(title=setup[0], color=colour, description=desc)
            else:
                embed = discord.Embed(title=setup[0], color=colour)

            if len(section) >= 3:
                inline = section[2]
                if inline not in ["True","t","true","T"]:
                    inline=False
                else:
                    inline=True
            else:
                inline=False

            try:
                segments = section[1].split("%")
                for seg in segments:
                    data = seg.split("$")
                    embed.add_field(name=data[0], value=data[1], inline=inline)
            except:
                pass

            if len(section) >= 4:
                embed.set_footer(text=section[3])

            if len(section) >= 5:
                words = section[4]
                await ctx.send(content=words,embed=embed)
            else:
                await ctx.send(embed=embed)

    #read channel messages
    @commands.command()
    async def fetchmsg(self, ctx, guild, channel, number):

        if ctx.message.author.id == BOT_OWNER:

            try:
                await ctx.message.delete()
            except:
                pass

            server = self.bot.get_guild(int(guild))

            try:
                srvchnl = discord.utils.get(server.text_channels, name=channel)

                if not srvchnl:
                    srvchnl = self.bot.get_channel(int(channel))

                if srvchnl:
                    divider = "```" + "="*10 + "```"
                    await ctx.send(divider)

                    messages = await srvchnl.history(limit=int(number)).flatten()

                    for msg in reversed(messages):
                        utct = msg.created_at
                        timestamp = str(utct.astimezone(tzone))
                        text = f'```[{timestamp}]: {msg.author.name}#{msg.author.discriminator}: "{msg.content}"```'
                        embeds = msg.embeds
                        attachments = msg.attachments
                        filelst = []
                        for i in attachments:
                            try:
                                file = await i.to_file(use_cached=True,spoiler=False)
                                filelst.append(file)
                            except:
                                pass

                        if embeds:
                            if filelst:
                                await ctx.send(content=text,embeds=embeds,files=filelst)
                            else:
                                await ctx.send(content=text,embeds=embeds)
                        elif filelst:
                            await ctx.send(content=text,files=filelst)
                        else:
                            await ctx.send(content=text)

                    await ctx.send(divider)
                else:
                    warn = await ctx.send("Channel not found")
                    await asyncio.sleep(2)
                    await warn.delete()

            except:
                warn = await ctx.send("Channel not found")
                await asyncio.sleep(2)
                await warn.delete()

    @commands.command()
    async def listsrvs(self, ctx):

        if ctx.message.author.id == BOT_OWNER:

            try:
                await ctx.message.delete()
            except:
                pass

            outsrvs = "```Connected Servers: "
            servers = self.bot.guilds
            for i in servers:
                if len(outsrvs) < 1900:
                    outsrvs += f"\n{i.name}:{i.id}"
                else:
                    outsrvs += "```"
                    await ctx.send(outsrvs)

                    outsrvs = "```"
            outsrvs += "```"
            await ctx.send(outsrvs)

    @commands.command()
    async def listchnls(self, ctx, guild):

        if ctx.message.author.id == BOT_OWNER:

            try:
                await ctx.message.delete()
            except:
                pass

            server = self.bot.get_guild(int(guild))
            outchnls = f"```Channels - [{server.name}|{server.id}]: \n"
            channels = server.text_channels
            for i in channels:
                if len(outchnls) < 1900:
                    outchnls += f"\n{i.name}:{i.id}"
                else:
                    outchnls += "```"
                    await ctx.send(outchnls)

                    outchnls = "```"
            outchnls += "```"
            await ctx.send(outchnls)

async def setup(bot):
    await bot.add_cog(OwnerCommands(bot))
