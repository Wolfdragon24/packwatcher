import ast
import asyncio
import base64
import copy
import datetime
import os
import time
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote_plus

import discord
import github
import requests
from dotenv import dotenv_values
from pytz import timezone
from github import Github
from urllib3 import Retry
from discord.ext import tasks, commands
from pymongo import MongoClient

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
TIMEZONE = timezone(config["BOT_TIMEZONE"])
GITHUB_PAT = config["GITHUB_PACKWATCHERBOT_TOKEN"]
MONGO_USER = quote_plus(config["MONGODB_USER"])
MONGO_PW = quote_plus(config["MONGODB_PASSWORD"])
MONGO_URL = config["MONGODB_URL"]
BOT_OWNER = int(config["BOT_OWNER"])

PASTEE_BASE_URL = "https://api.paste.ee/v1/pastes"
WYNN_BASE_URL = "https://api.wynncraft.com/public_api.php"
WYNN_ONLINE_PLAYERS_URL = f"{WYNN_BASE_URL}?action=onlinePlayers"
WYNN_GUILD_STATS_URL = f"{WYNN_BASE_URL}?action=guildStats"
PLAYERDB_MINECRAFT_API = "https://playerdb.co/api/player/minecraft"
MINETOOLS_PROFILE_API = "https://api.minetools.eu/profile"
MINETOOLS_UUID_API = "https://api.minetools.eu/uuid"

PASTE_NAME = "Guild Playtime Change Data"
PLAYTIME_GIT = "playtime.txt"
MEMBERS_GIT = "members.txt"
ERROR_HEX = 0xeb1515
SUCCESS_HEX = 0x6edd67
EMBED_LIMIT = 5000

paste_headers = {'X-Auth-Token': USER_KEY}
wynn_headers = {"apikey": WYNN_TOKEN}

#github repo setup
retry_obj = Retry(total = 10, status_forcelist = (500, 502, 504), backoff_factor = 0.3)
git = Github(GITHUB_PAT, retry = retry_obj)
repo = git.get_user().get_repo("packwatcher-data")

cluster = MongoClient(f"mongodb+srv://{MONGO_USER}:{MONGO_PW}@{MONGO_URL}")
db = cluster["discordbot"]
settings = [*db["settings"].find()][0]

guilds_to_check = json.loads(config["GUILDS"])
try:
    exclusive_users = settings["exclusers"]
except KeyError:
    exclusive_users = []

def rank_select(value):
    rankselection = {"OWNER":1,"CHIEF":2,"STRATEGIST":3,"CAPTAIN":4,"RECRUITER":5,"RECRUIT":6,"NOT IN GUILD":7}
    revrankselection = {1:"OWNER",2:"CHIEF",3:"STRATEGIST",4:"CAPTAIN",5:"RECRUITER",6:"RECRUIT",7:"NOT IN GUILD"}

    if isinstance(value, int):
        return revrankselection[value]
    return rankselection[value]

def get_index(lst, key, value):
    for i, dic in enumerate(lst):
        if dic[key] == value:
            return i
    return None

def get_key(title):
    request = requests.get(PASTEE_BASE_URL, headers=paste_headers, timeout=5)
    if request.status_code != 200:
        pass
    paste_lst = request.json()
    for paste in paste_lst["data"]:
        if paste["description"] == title:
            return paste["id"]

    payload = {"description": title, "expiration": "31536000", "sections": [{"contents": str({})}]}
    send = requests.post(PASTEE_BASE_URL, json=payload, headers=paste_headers, timeout=5).json()
    return send["id"]

def paste_fetch(title):
    key = get_key(title)

    request = requests.get(f"{PASTEE_BASE_URL}/{key}", headers=paste_headers, timeout=5)
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

def get_repo_data(filename):
    try:
        data = repo.get_contents(filename).decoded_content.decode().replace("'","\"")
        return (repo.get_contents(filename), json.loads(data))
    except github.GithubException:
        ref = repo.get_git_ref("heads/main")
        tree = repo.get_git_tree(ref.object.sha, recursive='/' in filename).tree
        sha = [x.sha for x in tree if x.path == filename]
        if not sha:
            file = repo.create_file(filename, "Automated Data Generation","{}")["content"]
            return(file, {})
        data = base64.b64decode(repo.get_git_blob(sha[0]).content).decode().replace("'","\"")
        return (repo.get_git_blob(sha[0]), json.loads(data))

def str_to_int(string: str, positive: bool = False):
    try:
        num = int(string)
    except ValueError:
        return None
    if positive and num < 0:
        return None
    return num

def prefix_to_name(prefix: str):
    for guild in guilds_to_check:
        if prefix == guilds_to_check[guild][1]:
            return guild
    return None

class PlaytimeUpdater(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.stored_playtime = {}
        self.stored_changing = {}
        self.stored_members = {}
        self.changing_counter = 5

        self.playtime_file = None
        self.members_file = None

        #Fetches data if not present
        if not self.stored_playtime:
            self.playtime_file, self.stored_playtime = get_repo_data(PLAYTIME_GIT)     
        if not self.stored_changing:
            self.stored_changing = paste_fetch(PASTE_NAME)
        if not self.stored_members:
            self.members_file, self.stored_members = get_repo_data(MEMBERS_GIT)

        if not global_vars.dev_mode:
            self.run_playtime_update.start()

    async def cog_unload(self):
        self.run_playtime_update.cancel()

    def playtime_update(self):
        #Fetches data if not present
        if not self.stored_playtime:
            self.playtime_file, self.stored_playtime = get_repo_data(PLAYTIME_GIT)     
        if not self.stored_changing:
            self.stored_changing = paste_fetch(PASTE_NAME)
        if not self.stored_members:
            self.members_file, self.stored_members = get_repo_data(MEMBERS_GIT)

        old_stored = copy.deepcopy(self.stored_playtime)
        old_members = copy.deepcopy(self.stored_members)

        all_players = []

        #gets list of all players online
        request = requests.get(WYNN_ONLINE_PLAYERS_URL, params=wynn_headers, timeout=5)

        if request.status_code != 200:
            return
        online_players = request.json()
        for world in online_players:
            if world != "request":
                all_players.extend(online_players[world])

        #gets current time
        now_time = datetime.now(TIMEZONE)
        text_time = now_time.strftime("%H-%d/%m/%y")
        text_day = now_time.strftime("%d/%m/%y")

        guild_players, guild_players_id = self.get_guild_members(guilds_to_check)

        for player in all_players:
            if any(player in guild_players[prefix] for prefix in guild_players) and player not in self.stored_changing:
                self.stored_changing[player] = int(time.time())

        self.stored_members[text_day] = guild_players_id

        to_clear = self.update_stored_data(all_players, guild_players, text_time)

        for player in (to_clear):
            try:
                del self.stored_changing[player]
            except KeyError:
                pass

        self.changing_counter += 1

        if self.changing_counter >= 5:

            self.changing_counter = 0

            #update pastes
            ckey = get_key(PASTE_NAME)
            requests.delete(f"{PASTEE_BASE_URL}/{ckey}", headers=paste_headers, timeout=5)

            changing_payload = {
                "description": PASTE_NAME,
                "expiration": "31536000",
                "sections": [
                    {"contents": str(self.stored_changing).replace("\'","\"")}
                ]
            }
            requests.post(PASTEE_BASE_URL, json=changing_payload, headers=paste_headers, timeout=5)

            if not self.stored_playtime or self.stored_playtime != old_stored:
                if self.playtime_file:
                    try:
                        self.playtime_file = repo.update_file(PLAYTIME_GIT, "Automated Data Generation", str(self.stored_playtime), self.playtime_file.sha)["content"]
                    except github.GithubException:
                        pass
                else:
                    try:
                        self.playtime_file = repo.create_file(PLAYTIME_GIT, "Automated Data Generation", str(self.stored_playtime))["content"]
                    except github.GithubException:
                        pass
            if not self.stored_members or self.stored_members != old_members:
                if self.members_file:
                    try:
                        self.members_file = repo.update_file(MEMBERS_GIT, "Automated Data Generation", str(self.stored_members), self.members_file.sha)["content"]
                    except github.GithubException:
                        pass
                else:
                    try:
                        self.members_file = repo.create_file(MEMBERS_GIT, "Automated Data Generation", str(self.stored_members))["content"]
                    except github.GithubException:
                        pass

    def get_guild_members(self, guild_names):
        guild_players = {}
        guild_players_id = {}

        for guild in guild_names:
            request = requests.get(f"{WYNN_GUILD_STATS_URL}&command={guild}", params=wynn_headers, timeout=5)
            if request.status_code != 200:
                continue
            data = request.json()
            prefix = data["prefix"]

            guild_players[prefix] = [member["name"] for member in data["members"]]
            guild_players_id[prefix] = [member["uuid"] for member in data["members"]]

            for player in guild_players_id[prefix]:
                request = requests.get(f"{MINETOOLS_PROFILE_API}/{player}", timeout=5)
                if request.status_code != 200:
                    continue
                player_data = request.json()
                username = player_data["raw"]["name"]
                if username and username not in guild_players[prefix]:
                    guild_players[prefix].append(username)

        return guild_players, guild_players_id

    def update_stored_data(self, all_players, guild_players, text_time):
        to_clear = []

        for player in self.stored_changing:
            if player not in all_players:
                if text_time not in self.stored_playtime:
                    self.stored_playtime[text_time] = []

                request = requests.get(f"{MINETOOLS_UUID_API}/{player}", timeout=5)
                if request.status_code != 200:
                    continue
                data = request.json()
                if data["status"] != "ERR":
                    uuid = data["id"]

                    prefix = next((prefix for prefix in guild_players if player in guild_players[prefix]), None)
                    time_diff = int((int(time.time()) - self.stored_changing[player]) / 60)

                    if prefix:
                        inputted_data = {"uuid": uuid, "duration": time_diff, "guild": prefix}
                        self.stored_playtime[text_time].append(inputted_data)

                to_clear.append(player)

        return to_clear

    @tasks.loop(minutes=1)
    async def run_playtime_update(self):
        await asyncio.get_event_loop().run_in_executor(ThreadPoolExecutor(), self.playtime_update)

    @commands.hybrid_command(name="playtime")
    async def playtime(self, ctx: commands.Context, form: str = None, data: str = None, members: str = None,  guild: str = None):
        """Displays the playtime for the relevant guild. (.playtime help or /playtime help)"""

        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        requester = f"Requested by {ctx.author.name}."

        if form == "help":
            # Display a help embed then return
            help_embed_dict = {
                "title": "Playtime Command Help",
                "footer": {
                    "text": requester
                },
                "color": SUCCESS_HEX,
                "fields": [
                    {
                        "name": "Help Menu",
                        "value": "Displays the help menu, using the format (playtime help)."
                    },
                    {
                        "name": "Date Argument - from",
                        "value": "Can be used with dates in dd/mm/yy formats, and using input formats of (playtime from <date>-<date>). Either of the date arguments can be neglected to filter from a certain date forwards/backwards."
                    },
                    {
                        "name": "Time Argument - w/d/h",
                        "value": "Can be used with duration based inputs in the format (playtime <w(eeks)/d(ays)/h(ours)> <number>) to filter from a certain time."
                    },
                    {
                        "name": "Members Argument - all",
                        "value": "Can be used in the format (playtime <w/d/h/from> <data> all) to filter all members who have ever been in the guild at any point in time."
                    },
                    {
                        "name": "Argument-less",
                        "value": "Can be used in the format (playtime) to fetch playtime with no filters, including only current members."
                    },
                    {
                        "name": "Guild Argument - prefix/name [Exclusive]",
                        "value": "This command is limited to exclusive users. Can be used in the format (playtime <m/w/d/h/from> <data> <all/other> <guild>) to filter for certain guilds."
                    }
                ]
            }
            await ctx.send(embed=discord.Embed.from_dict(help_embed_dict))
            return

        if (ctx.author.id == BOT_OWNER or ctx.author.id in exclusive_users) and guild:
            # Allowed users can set the guild for searching
            if guild in guilds_to_check:
                guild_prefix = guilds_to_check[guild][1]
            elif guild in [guilds_to_check[to_check][1] for to_check in guilds_to_check]:
                guild_prefix = guild
            elif ctx.guild.id in [guilds_to_check[to_check][0] for to_check in guilds_to_check]:
                guild_prefix = next(guilds_to_check[to_check][1] for to_check in guilds_to_check if guilds_to_check[to_check][0] == ctx.guild.id)
            else:
                #Errors
                error_embed_dict = {
                    "title": "Error - Playtime",
                    "footer": {
                        "text": requester
                    },
                    "color": ERROR_HEX,
                    "fields": [
                        {
                            "name": "Invalid Guild Input",
                            "value": "The inputted guild was not found and the current server does not correspond to a linked guild, please try again."
                        }
                    ]
                }

                await ctx.send(embed=discord.Embed.from_dict(error_embed_dict))
                return
        elif ctx.guild and ctx.guild.id in [guilds_to_check[to_check][0] for to_check in guilds_to_check]:
            # Defaults to reflect current guild
            guild_prefix = next(guilds_to_check[to_check][1] for to_check in guilds_to_check if guilds_to_check[to_check][0] == ctx.guild.id)
        else:
            #Errors
            error_embed_dict = {
                "title": "Error - Playtime",
                "footer": {
                    "text": requester
                },
                "color": ERROR_HEX,
                "fields": [
                    {
                        "name": "Invalid Guild Input",
                        "value": "The current server does not correspond to a linked guild, please try again in another server."
                    }
                ]
            }

            await ctx.send(embed=discord.Embed.from_dict(error_embed_dict))
            return

        # Gathers required data using form argument
        if form == "from":
            # Fetch data between given dates
            if not data or "-" not in data:
                #Error
                error_embed_dict = {
                    "title": "Error - Playtime",
                    "footer": {
                        "text": requester
                    },
                    "color": ERROR_HEX,
                    "fields": [
                        {
                            "name": "Invalid Date Input",
                            "value": "An invalid input was given for the 'from' argument, please try again or reference the help menu."
                        }
                    ]
                }

                await ctx.send(embed=discord.Embed.from_dict(error_embed_dict))
                return
            
            if data.startswith("-"):
                date_str = data.replace("-", "")
                try:
                    start_time = datetime.min
                    end_time = datetime.strptime(date_str, "%d/%m/%y")
                    title = f"{guild_prefix} Playtime - From {date_str}"
                except ValueError:
                    error_embed_dict = {
                        "title": "Error - Playtime",
                        "footer": {
                            "text": requester
                        },
                        "color": ERROR_HEX,
                        "fields": [
                            {
                                "name": "Invalid Date Format",
                                "value": "An invalid format was provided for dates, please try again or reference the help menu."
                            }
                        ]
                    }

                    await ctx.send(embed=discord.Embed.from_dict(error_embed_dict))
                    return
                
            elif data.endswith("-"):
                date_str = data.replace("-", "")
                try:
                    end_time = datetime.max
                    start_time = datetime.strptime(date_str, "%d/%m/%y")
                    title = f"{guild_prefix} Playtime - Till {date_str}"
                except ValueError:
                    error_embed_dict = {
                        "title": "Error - Playtime",
                        "footer": {
                            "text": requester
                        },
                        "color": ERROR_HEX,
                        "fields": [
                            {
                                "name": "Invalid Date Format",
                                "value": "An invalid format was provided for dates, please try again or reference the help menu."
                            }
                        ]
                    }

                    await ctx.send(embed=discord.Embed.from_dict(error_embed_dict))
                    return
            else:
                date_strs = data.split("-")
                try:
                    start_time = datetime.strptime(date_strs[0], "%d/%m/%y")
                    end_time = datetime.strptime(date_strs[1], "%d/%m/%y")
                    title = f"{guild_prefix} Playtime - From {date_strs[0]} to {date_strs[1]}"
                except ValueError:
                    error_embed_dict = {
                        "title": "Error - Playtime",
                        "footer": {
                            "text": requester
                        },
                        "color": ERROR_HEX,
                        "fields": [
                            {
                                "name": "Invalid Date Format",
                                "value": "An invalid format was provided for dates, please try again or reference the help menu."
                            }
                        ]
                    }

                    await ctx.send(embed=discord.Embed.from_dict(error_embed_dict))
                    return
        elif form == "m":
            # Fetch data from some amount of months ago
            num = str_to_int(data, True)
            if not num:
                error_embed_dict = {
                    "title": "Error - Playtime",
                    "footer": {
                        "text": requester
                    },
                    "color": ERROR_HEX,
                    "fields": [
                        {
                            "name": "Invalid Months Input",
                            "value": "An invalid value was inputted for months, please try again or reference the help menu."
                        }
                    ]
                }

                await ctx.send(embed=discord.Embed.from_dict(error_embed_dict))
                return
            start_time = datetime.now() - timedelta(days=(30 * num))
            end_time = datetime.max
            title = f"{guild_prefix} Playtime - {num} Months"
        elif form == "w":
            # Fetch data from some amount of weeks ago
            num = str_to_int(data, True)
            if not num:
                error_embed_dict = {
                    "title": "Error - Playtime",
                    "footer": {
                        "text": requester
                    },
                    "color": ERROR_HEX,
                    "fields": [
                        {
                            "name": "Invalid Weeks Input",
                            "value": "An invalid value was inputted for weeks, please try again or reference the help menu."
                        }
                    ]
                }

                await ctx.send(embed=discord.Embed.from_dict(error_embed_dict))
                return
            start_time = datetime.now() - timedelta(weeks=num)
            end_time = datetime.max
            title = f"{guild_prefix} Playtime - From {num} Weeks"
        elif form == "d":
            # Fetch data from some amount of days ago
            num = str_to_int(data, True)
            if not num:
                error_embed_dict = {
                    "title": "Error - Playtime",
                    "footer": {
                        "text": requester
                    },
                    "color": ERROR_HEX,
                    "fields": [
                        {
                            "name": "Invalid Days Input",
                            "value": "An invalid value was inputted for days, please try again or reference the help menu."
                        }
                    ]
                }

                await ctx.send(embed=discord.Embed.from_dict(error_embed_dict))
                return
            start_time = datetime.now() - timedelta(days=num)
            end_time = datetime.max
            title = f"{guild_prefix} Playtime - From {num} Days"
        elif form == "h":
            # Fetch data from some amount of days ago
            num = str_to_int(data, True)
            if not num:
                error_embed_dict = {
                    "title": "Error - Playtime",
                    "footer": {
                        "text": requester
                    },
                    "color": ERROR_HEX,
                    "fields": [
                        {
                            "name": "Invalid Hours Input",
                            "value": "An invalid value was inputted for hours, please try again or reference the help menu."
                        }
                    ]
                }

                await ctx.send(embed=discord.Embed.from_dict(error_embed_dict))
                return
            start_time = datetime.now() - timedelta(hours=num)
            end_time = datetime.max
            title = f"{guild_prefix} Playtime - From {num} Hours"
        else:
            # Fetch data from all time with current members
            start_time = datetime.min
            end_time = datetime.max
            title = f"{guild_prefix} Playtime - All"

        # Gets all data sets between the given times
        data_sets = {}
        for time_value in self.stored_playtime:
            datetime_object = datetime.strptime(time_value, "%H-%d/%m/%y")
            if start_time < datetime_object < end_time:
                data_sets[time_value] = self.stored_playtime[time_value]

        request = requests.get(f"{WYNN_GUILD_STATS_URL}&command={prefix_to_name(guild_prefix)}", params=wynn_headers, timeout=5)
        guild_data = request.json()

        active_members = [str(member["uuid"]).replace("-","") for member in guild_data["members"]]

        playtime_stats = {}

        for time_set in enumerate(data_sets.items()):
            user_sets = time_set[1][1]
            for user_set in user_sets:
                uuid = user_set["uuid"]
                if (members == "all" and user_set["guild"] == guild_prefix) or (members != "all" and uuid in active_members):
                    playtime_stats[uuid] = user_set["duration"] if uuid not in playtime_stats else (playtime_stats[uuid] + user_set["duration"])

        for member_uuid in active_members:
            if member_uuid not in playtime_stats:
                playtime_stats[member_uuid] = 0

        publishable_stats = []
        total = len(playtime_stats)
        count = 0
        last = 0

        req = "Please wait, this process may take a few minutes..."
        pmsg = f"0/{total} checks completed: 0.0% done."
        prg_title = f"Playtime Check Progress - {guild_prefix}"
        progress = discord.Embed(title=prg_title, color=0xf5c242)

        progress.add_field(name="Checks Completed", value=pmsg, inline=True)
        progress.set_footer(text=req)

        pmessage = await ctx.channel.send(embed=progress)

        for i in enumerate(playtime_stats.items()):
            count += 1

            player = i[1][0]
            total_playtime = i[1][1]
            request = requests.get(f"{MINETOOLS_PROFILE_API}/{player}", timeout=5)
            if request.status_code != 200:
                continue
            player_data = request.json()
            if player_data["raw"]["status"] == "ERR":
                continue
            username = player_data["raw"]["name"]
            rank = rank_select(next(data_set for data_set in guild_data["members"] if str(data_set["uuid"]).replace("-", "") == player)["rank"])
            publishable_stats.append({"name": username, "total": total_playtime, "rank": rank})

            if (count == last + 20) or (count + 3 > total):
                #embed update
                req = "Please wait, this process may take a few minutes..."
                perc = (count/len(playtime_stats))*100
                pmsg = f"{count}/{total} checks completed: {perc:.1f}% done."
                newprogress = discord.Embed(title=prg_title, color=0xf5c242)

                newprogress.add_field(name="Checks Completed", value=pmsg, inline=True)
                newprogress.set_footer(text=req)

                await pmessage.edit(embed=newprogress)
                last = count

        await asyncio.sleep(1)
        await pmessage.delete()

        publishable_stats.sort(key = lambda x: x['name'])
        publishable_stats.sort(key = lambda x: x["total"], reverse=True)
        publishable_stats.sort(key = lambda x: x["rank"])

        if not publishable_stats:
            error_embed_dict = {
                "title": "Error - Playtime",
                "footer": {
                    "text": requester
                },
                "color": ERROR_HEX,
                "fields": [
                    {
                        "name": "No Data Found",
                        "value": "No playtime information was found during this period."
                    }
                ]
            }

            await ctx.send(embed=discord.Embed.from_dict(error_embed_dict))
            return

        #send message
        embed = discord.Embed(title=title, color=SUCCESS_HEX)

        allstring = "".join(str(val) for val in [[player[a] for a in player] for player in publishable_stats])
        subtotallen = 0
        totallen = len(allstring + " " * 6 * len(publishable_stats))
        if totallen > EMBED_LIMIT:
            secembed = discord.Embed(title=f"{title} (cont.)", color=SUCCESS_HEX)
            cleared = False

        output = {"rank":"","text":""}

        for player in publishable_stats:
            storedrank = player["rank"]
            rank = rank_select(storedrank)
            playtime = player["total"]
            if len(str(playtime)) > 3:
                playtime = '{:,}'.format(playtime).replace(","," ")
            statement = f"\n{player['name']} : {playtime} minutes"
            if subtotallen > EMBED_LIMIT:
                if not cleared:
                    if output["text"]:
                        output["text"] = discord.utils.escape_markdown(output["text"])
                        embed.add_field(name=output["rank"],value=output["text"],inline=False)
                    subtotallen += len(output["text"])
                    output = {"rank":rank,"text":""}
                    cleared = True

                if output["rank"] == rank: #same or lower rank
                    if len(output["text"]) < 950:
                        output["text"] += statement
                    else: #full
                        if output["text"]:
                            output["text"] = discord.utils.escape_markdown(output["text"])
                            secembed.add_field(name=output["rank"],value=output["text"],inline=False)
                        subtotallen += len(output["text"])
                        output = {"rank":rank,"text":""}
                        output["text"] += statement
                else: #was higher rank
                    if output["text"]:
                        output["text"] = discord.utils.escape_markdown(output["text"])
                        secembed.add_field(name=output["rank"],value=output["text"],inline=False)
                    subtotallen += len(output["text"])
                    output = {"rank":rank,"text":""}
                    output["text"] += statement
            else:
                if output["rank"] == rank: #same or lower rank
                    if len(output["text"]) < 950:
                        output["text"] += statement
                    else: #full
                        if output["text"]:
                            output["text"] = discord.utils.escape_markdown(output["text"])
                            embed.add_field(name=output["rank"],value=output["text"],inline=False)
                        subtotallen += len(output["text"])
                        output = {"rank":rank,"text":""}
                        output["text"] += statement
                else: #was higher rank
                    if output["text"]:
                        output["text"] = discord.utils.escape_markdown(output["text"])
                        embed.add_field(name=output["rank"],value=output["text"],inline=False)
                    subtotallen += len(output["text"])
                    output = {"rank":rank,"text":""}
                    output["text"] += statement

        output["text"] = discord.utils.escape_markdown(output["text"])

        if subtotallen > EMBED_LIMIT:
            secembed.add_field(name=output["rank"], value=output["text"], inline=False)
        else:
            embed.add_field(name=output["rank"], value=output["text"], inline=False)

        embed.set_footer(text=requester)

        if subtotallen <= EMBED_LIMIT:
            await ctx.send(embed=embed)
        else:
            secembed.set_footer(text=requester)
            await ctx.send(embeds=[embed, secembed])

    # @commands.hybrid_command(name="activity")
    # async def new_activity(self, ctx: commands.Context, *guild: str):
    #     """Displays the activity for the inputted guild. (.activity <guild> or /activity guild)"""

    #     if ctx.interaction:
    #         await ctx.interaction.response.defer(ephemeral=True)
    #     requester = f"Requested by {ctx.author.name}."
        
    #     guild_list = cogs.wynn_guildlist.guild_list
    #     guild_search = " ".join(guild)

    @commands.command()
    async def activity(self, ctx, *guildcheck):
        try:
            await ctx.message.delete()
        except:
            pass

        req = f"Requested by {ctx.author.name}."

        guildlst = global_vars.guild_list
        guildsearch = " ".join(guildcheck)
        srvtrack = global_vars.srvtrack

        try:
            guildstats = requests.get(f"https://api.wynncraft.com/public_api.php?action=guildStats&command={guildsearch}", params=wynn_headers).json()

            members = guildstats["members"]

            total = len(members)
            count = 0

            req = "Please wait, this process may take a few minutes..."
            pmsg = f"0/{total} checks completed: 0.0% done."
            title = f"Guild Activity Progress - {guildsearch}"
            progress = discord.Embed(title=title, color=0xf5c242)

            progress.add_field(name="Checks Completed", value=pmsg, inline=True)
            progress.set_footer(text=req)

            pmessage = await ctx.send(embed=progress)

            memberslst = []
            last = 0

            rankselection = {"OWNER":1,"CHIEF":2,"STRATEGIST":3,"CAPTAIN":4,"RECRUITER":5,"RECRUIT":6}
            revrankselection = {1:"OWNER",2:"CHIEF",3:"STRATEGIST",4:"CAPTAIN",5:"RECRUITER",6:"RECRUIT"}

            for member in members:
                #member add
                username = member["name"]
                rank = member["rank"]
                uuid = member["uuid"]

                memberinfo = requests.get(f"https://api.wynncraft.com/v2/player/{uuid}/stats", params=wynn_headers).json()
                joingrab = memberinfo["data"][0]["meta"]["lastJoin"]
                lastjoin = joingrab.split("T")
                lastjoinobj = datetime.strptime(lastjoin[0], "%Y-%m-%d")
                currenttime = datetime.utcnow()
                indays = (currenttime - lastjoinobj).days

                member_data = {"username":username,"rank":rankselection[rank],"daysdif":indays}
                memberslst.append(member_data)

                count += 1

                if (count == last + 20) or (count + 3 > total):
                    #embed update
                    req = "Please wait, this process may take a few minutes..."
                    perc = (count/total)*100
                    pmsg = f"{count}/{total} checks completed: {perc:.1f}% done."
                    title = f"Guild Activity Progress - {guildsearch}"
                    newprogress = discord.Embed(title=title, color=0xf5c242)

                    newprogress.add_field(name="Checks Completed", value=pmsg, inline=True)
                    newprogress.set_footer(text=req)

                    await pmessage.edit(embed=newprogress)
                    last = count

            await asyncio.sleep(1)
            await pmessage.delete()

            memberslst.sort(key = lambda x: x['username'])
            memberslst.sort(key = lambda x: x["daysdif"],reverse=True)
            memberslst.sort(key = lambda x: x["rank"])

            title = f"Guild Activity - {guildsearch}"
            #send message
            embed = discord.Embed(title=title, color=0x6edd67)

            output = {"rank":"","text":""}

            for player in memberslst:
                storedrank = player["rank"]
                rank = revrankselection[storedrank]
                if output["rank"] == rank: #same or lower rank
                    if len(output["text"]) < 950:
                        if player['daysdif'] == 1:
                            output["text"] += f"\n{player['username']} : Last joined 1 day ago."
                        else:
                            output["text"] += f"\n{player['username']} : Last joined {player['daysdif']} days ago."
                    else: #full
                        if output["text"]:
                            output["text"] = discord.utils.escape_markdown(output["text"])
                            embed.add_field(name=output["rank"],value=output["text"],inline=False)
                        output = {"rank":rank,"text":""}
                        if player['daysdif'] == 1:
                            output["text"] += f"{player['username']} : Last joined 1 day ago."
                        else:
                            output["text"] += f"{player['username']} : Last joined {player['daysdif']} days ago."
                else: #was higher rank
                    if output["text"]:
                        output["text"] = discord.utils.escape_markdown(output["text"])
                        embed.add_field(name=output["rank"],value=output["text"],inline=False)
                    output = {"rank":rank,"text":""}
                    if player['daysdif'] == 1:
                        output["text"] += f"{player['username']} : Last joined 1 day ago."
                    else:
                        output["text"] += f"{player['username']} : Last joined {player['daysdif']} days ago."
            if output["text"]:
                output["text"] = discord.utils.escape_markdown(output["text"])
                embed.add_field(name=output["rank"],value=output["text"],inline=False)

            embed.set_footer(text=req)

            await ctx.send(embed=embed)

        except:
            if guildsearch.lower() in guildlst:
                guildsearched = guildlst[guildsearch.lower()]
                if "|" in guildsearched:
                    guildspot = guildsearched.split("|")
                    gldpotlst = ""

                    count = 1
                    while count < len(guildspot):
                        if gldpotlst == "":
                            gldpotlst = f"{guildspot[count-1]} - {count}"
                        else:
                            gldpotlst += f"\n{guildspot[count-1]} - {count}"
                        count += 1
                    choosemessage = f'```There are multiple guilds with the prefix: "{guildsearch}". Please respond with the number corresponding to the intended guild, within the next 30 seconds. \n{gldpotlst}```'
                    cmsg = await ctx.send(choosemessage)

                    srvtrack[ctx.guild.id] = (guildspot, ctx.author.id, cmsg, "activity")

                    await asyncio.sleep(30)
                    try:
                        await cmsg.delete()
                        del srvtrack[ctx.guild.id]
                    except:
                        pass
                else:
                    try:
                        guildstats = requests.get(f"https://api.wynncraft.com/public_api.php?action=guildStats&command={guildsearched}", params=wynn_headers).json()

                        members = guildstats["members"]

                        total = len(members)
                        count = 0

                        req = "Please wait, this process may take a few minutes..."
                        pmsg = f"0/{total} checks completed: 0.0% done."
                        title = f"Guild Activity Progress - {guildsearched}"
                        progress = discord.Embed(title=title, color=0xf5c242)

                        progress.add_field(name="Checks Completed", value=pmsg, inline=True)
                        progress.set_footer(text=req)

                        pmessage = await ctx.send(embed=progress)

                        memberslst = []
                        last = 0

                        rankselection = {"OWNER":1,"CHIEF":2,"STRATEGIST":3,"CAPTAIN":4,"RECRUITER":5,"RECRUIT":6}
                        revrankselection = {1:"OWNER",2:"CHIEF",3:"STRATEGIST",4:"CAPTAIN",5:"RECRUITER",6:"RECRUIT"}

                        for member in members:
                            #member add
                            username = member["name"]
                            rank = member["rank"]
                            uuid = member["uuid"]

                            memberinfo = requests.get(f"https://api.wynncraft.com/v2/player/{uuid}/stats", params=wynn_headers).json()
                            joingrab = memberinfo["data"][0]["meta"]["lastJoin"]
                            lastjoin = joingrab.split("T")
                            lastjoinobj = datetime.strptime(lastjoin[0], "%Y-%m-%d")
                            currenttime = datetime.utcnow()
                            indays = (currenttime - lastjoinobj).days

                            member_data = {"username":username,"rank":rankselection[rank],"daysdif":indays}
                            memberslst.append(member_data)

                            count += 1

                            if (count == last + 20) or (count + 3 > total):
                                #embed update
                                req = "Please wait, this process may take a few minutes..."
                                perc = (count/total)*100
                                pmsg = f"{count}/{total} checks completed: {perc:.1f}% done."
                                title = f"Guild Activity Progress - {guildsearched}"
                                newprogress = discord.Embed(title=title, color=0xf5c242)

                                newprogress.add_field(name="Checks Completed", value=pmsg, inline=True)
                                newprogress.set_footer(text=req)

                                await pmessage.edit(embed=newprogress)
                                last = count

                        await asyncio.sleep(1)
                        await pmessage.delete()

                        memberslst.sort(key = lambda x: x['username'])
                        memberslst.sort(key = lambda x: x["daysdif"],reverse=True)
                        memberslst.sort(key = lambda x: x["rank"])

                        req = "Requested by " + ctx.message.author.name + "."

                        title = f"Guild Activity - {guildsearched}"
                        #send message
                        embed = discord.Embed(title=title, color=0x6edd67)

                        output = {"rank":"","text":""}

                        for player in memberslst:
                            storedrank = player["rank"]
                            rank = revrankselection[storedrank]
                            if output["rank"] == rank: #same or lower rank
                                if len(output["text"]) < 950:
                                    if player['daysdif'] == 1:
                                        output["text"] += f"\n{player['username']} : Last joined 1 day ago."
                                    else:
                                        output["text"] += f"\n{player['username']} : Last joined {player['daysdif']} days ago."
                                else: #full
                                    if output["text"]:
                                        output["text"] = discord.utils.escape_markdown(output["text"])
                                        embed.add_field(name=output["rank"],value=output["text"],inline=False)
                                    output = {"rank":rank,"text":""}
                                    if player['daysdif'] == 1:
                                        output["text"] += f"{player['username']} : Last joined 1 day ago."
                                    else:
                                        output["text"] += f"{player['username']} : Last joined {player['daysdif']} days ago."
                            else: #was higher rank
                                if output["text"]:
                                    output["text"] = discord.utils.escape_markdown(output["text"])
                                    embed.add_field(name=output["rank"],value=output["text"],inline=False)
                                output = {"rank":rank,"text":""}
                                if player['daysdif'] == 1:
                                    output["text"] += f"{player['username']} : Last joined 1 day ago."
                                else:
                                    output["text"] += f"{player['username']} : Last joined {player['daysdif']} days ago."
                        if output["text"]:
                            output["text"] = discord.utils.escape_markdown(output["text"])
                            embed.add_field(name=output["rank"],value=output["text"],inline=False)

                        embed.set_footer(text=req)

                        await ctx.send(embed=embed)
                    except:
                        pass

            else:
                wmsg = f'No guilds were found with the name/prefix: "{guildsearch}".'
                warn = discord.Embed(title="Error - Guild Not Found", color=0xeb1515)

                warn.add_field(name="Error", value=wmsg, inline=True)

                req = "Requested by " + ctx.message.author.name + "."
                warn.set_footer(text=req)

                await ctx.send(embed=warn)
            
async def setup(bot):
    await bot.add_cog(PlaytimeUpdater(bot))
