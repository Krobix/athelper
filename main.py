#!/usr/bin/env python3
import discord
import asyncio
from discord.ext import commands, tasks
from discord import utils
import os
import pickle
import copy
import sys
import datetime
import secrets

bot = commands.Bot(command_prefix="at.")

bot.remove_command("help")

config_table = None #data/config.table

modmail_table = None #data/modmail.table

testing_mode = False

#Discord objects loaded from config table
once_monthly_channel = None

once_hourly_channel = None

mm_channel_category = None

mod_role = None

at_guild = None
#########################################

m_channel_names = []

h_channel_names = []

mm_category_list = []

now = datetime.datetime.now()

man_entries = {}

day_loop_obj = None

day_loop_num = 0

m_index = 0

m_changed = False

chr_unapproved_list = []

class ATHelperTableEntry:
    def __init__(self, id, field_values, table):
        self.id = id
        self.field_values = list(field_values)
        self.table = table
        self.field_map = {}
        for i in self.table.fields:
            pos = self.table.fields.index(i)
            self.field_map[i] = self.field_values[pos]

class ATHelperTable:
    def __init__(self, path, fields):
        self.fields = fields
        self.entries = []
        self.len_entries = 0
        self.path = path
    
    def add_entry(self, *values):
        tmp = ATHelperTableEntry(self.len_entries, values, self)
        self.entries.append(tmp)
        self.len_entries += 1

    def get_entry(self, field, search_value):
        search_value = search_value.lower()
        for i in self.entries:
            if testing_mode:
                print(f"comparing {search_value} and {i.field_map[field].lower()}")
            if search_value == i.field_map[field].lower():
                cmap = copy.copy(i.field_map)
                cmap["id"] = i.id
                return cmap
        else:
            raise KeyError(f"value {search_value} for {field} not found in table")

    def get_raw_entry_from_id(self, id):
        for i in self.entries:
            if i.id == id:
                return i

    def edit_entry(self, id, field, new_value):
        entry = self.get_raw_entry_from_id(id)
        pos = self.fields.index(field)
        entry.field_values[pos] = new_value
        entry.__init__(id, entry.field_values, self)

    def remove_entry(self, id):
        entry = self.get_raw_entry_from_id(id)
        self.entries.remove(entry)
        del entry

    def commit(self):
        with open(self.path, "wb") as f:
            pickle.dump(self, f)

class ATCharacter:
    def __init__(self, name, sheet):
        self.name = name
        self.sheet = sheet
        self.id = secrets.token_hex(10)
        self.path = f"data/chr/obj/{self.id}"
        self.currency_amount = 0
        self.products_owned = []
        self.approved_bio = False
        self.approved_stats = False

    async def commit(self):
        with open(self.path, "wb") as f:
            pickle.dump(self, f)

    async def submit(self):
        chr_unapproved_list.append(self.id) 
        await self.commit()
        with open("data/chr/tables/unapproved.list", "wb") as f:
            pickle.dump(chr_unapproved_list, f)
    
    async def approve(self, which):
        if which == "bio":
            self.approved_bio = True
        elif which == "stats":
            self.approved_stats = True
        if (self.approved_bio) and (self.approved_stats):
            chr_unnaproved_list.remove(self.id)

def load_obj(path):
    with open(path, "rb") as f:
        return pickle.load(f)

def try_mkdir(dir):
    if not os.path.isdir(dir):
        os.mkdir(dir)

def add_days(amount):
    global day_loop_num, m_changed
    tmpnum = day_loop_num + amount
    if tmpnum > 35:
        day_loop_num = tmpnum - 35
        m_changed = True
    else:
        day_loop_num = tmpnum

def inc_m_index():
    global m_index
    m_index += 1
    if m_index > 10:
        m_index = 0

def setup_directories():
    try_mkdir("data")
    try_mkdir("data/chr")
    try_mkdir("data/chr/tables")
    try_mkdir("data/chr/tables/usr")
    try_mkdir("data/chr/obj")

def setup_tables():
    global config_table, modmail_table
    #Config table
    config_table = ATHelperTable("data/config.table", ["key", "value"])
    config_table.add_entry("once_monthly_channel", "None")
    config_table.add_entry("once_hourly_channel", "None")
    config_table.add_entry("devuser", "None")
    config_table.add_entry("modmail_category_id", "None")
    config_table.add_entry("mod_role", "None")
    config_table.add_entry("at_guild_id", "None")
    config_table.commit()
    #Modmail table
    modmail_table = ATHelperTable("data/modmail.table", ["opener_id", "subject", "category", "channel_id"])
    modmail_table.commit()

def get_config(key):
    return config_table.get_entry("key", key)["value"]

def set_config(key, val):
    id = config_table.get_entry("key", key)["id"]
    if testing_mode:
        print(f"set_config: id is {id}")
    config_table.edit_entry(id, "value", val)
    config_table.commit()

def dump_days():
    with open("data/dln.bin", "wb") as f:
        pickle.dump(day_loop_obj, f)
    with open("data/dlnn.bin", "wb") as f:
        pickle.dump(day_loop_num, f)
    with open("data/mind.bin", "wb") as f:
        pickle.dump(m_index, f)

def setup_days():
    global day_loop_obj
    day_loop_obj = datetime.datetime.now()
    dump_days()

def full_setup():
    setup_directories()
    setup_tables()
    setup_days()

def init_already_installed():
    global config_table, modmail_table, day_loop_obj, day_loop_num, m_index, chr_unapproved_list
    config_table = load_obj("data/config.table")
    modmail_table = load_obj("data/modmail.table")
    with open("data/dlnn.bin", "rb") as f:
        add_days(pickle.load(f))
    with open("data/mind.bin", "rb") as f:
        m_index = pickle.load(f)
    with open("data/dln.bin", "rb") as f:
        day_loop_obj = pickle.load(f)
        ndln = datetime.datetime.now()
        diff = ndln - day_loop_obj
        add_days(diff.days)
    if os.path.exists("data/chr/tables/unapproved.list"):
        chr_unapproved_list = load_obj("data/chr/tables/unapproved.list")

async def create_character_table_skeleton(user_id):
    return ATHelperTable(f"data/chr/tables/usr/{user_id}.table", ["name", "chr_id", "approved"])

async def get_users_character_table(user_id):
    path = f"data/chr/tables/usr/{user_id}.table"
    if not (os.path.exists(path)):
        table = await create_character_table_skeleton(user_id)
        table.commit()
        return table
    else:
        return load_obj(path)

async def get_character(user_id=None, name=None, chr_id=None):
    if user_id != None:
        table = await get_users_character_table(user_id)
        if name != None:
            char = table.get_entry("name", name)
            return load_obj(f"data/chr/obj/{char['chr_id']}")
    elif chr_id != None:
        return load_obj(f"data/chr/obj/{chr_id}")

@bot.command()
async def set_once_monthly(ctx, ch_id):
    if str(ctx.author.id) == get_config("devuser"):
        ch_id = str(ch_id)
        set_config("once_monthly_channel", ch_id)
        await ctx.send("OK")
    else:
        await ctx.send("error: you are not the devuser")

@bot.command()
async def set_once_hourly(ctx, ch_id):
    if str(ctx.author.id) == get_config("devuser"):
        ch_id = str(ch_id)
        set_config("once_hourly_channel", ch_id)
        await ctx.send("OK")
    else:
        await ctx.send("error: you are not the devuser")

@bot.command()
async def setdev(ctx):
    user = str(ctx.author.id)
    if get_config("devuser") == "None":
        set_config("devuser", user)
        await ctx.send("OK")
    else:
        await ctx.send("error: devuser already exists")

@bot.command()
async def set_modmail_category(ctx, ch_id):
    if str(ctx.author.id) == get_config("devuser"):
        ch_id = str(ch_id)
        set_config("modmail_category_id", ch_id)
        await ctx.send("OK")
    else:
        await ctx.send("Error: you are not the devuser")

@bot.command()
async def set_moderator_role(ctx):
    if str(ctx.author.id) == get_config("devuser"):
        role = ctx.message.role_mentions[0].id
        set_config("mod_role", str(role))
        await ctx.send("OK")
    else:
        await ctx.send("Error: you are not the devuser")

@bot.command()
async def set_at_guild_id(ctx):
    if str(ctx.author.id) == get_config("devuser"):
        set_config("at_guild_id", str(ctx.guild.id))
        await ctx.send("OK")
    else:
        await ctx.send("error: you are not the devuser")

@bot.command()
async def help(ctx, page):
    emb = discord.Embed()
    emb.title = f"Help: {page}"
    try:
        emb.description = man_entries[page]
    except KeyError:
        await ctx.send(f"Error: help page {page} not found")
    emb.color = discord.Color.blue()
    await ctx.send(embed=emb)

@bot.command()
async def modmail(ctx, category, subject):
    await send_modmail(subject, category, ctx.author)
    await ctx.send("Sent.")

@bot.command()
async def modmail_info(ctx, num: int):
    if mod_role in ctx.author.roles:
        try:
            mm_entry = modmail_table.get_raw_entry_from_id(num)
            mm_map = mm_entry.field_map
        except KeyError:
            await ctx.send("Error: that modmail ticket does not exist")
        else:
            emb = discord.Embed()
            emb.title = f"Modmail ticket with ID {num}"
            emb.color = discord.Color.dark_magenta()
            emb.add_field(name="Category", value=mm_map["category"])
            emb.add_field(name="Subject", value=mm_map["subject"])
            emb.add_field(name="User", value=bot.get_user(int(mm_map["opener_id"])))
            await ctx.send(embed=emb)
    else:
        await ctx.send("Only staff members can use this command")

@bot.command()
async def modmail_close(ctx, num: int):
    if mod_role in ctx.author.roles:
        try:
            mm_entry = modmail_table.get_raw_entry_from_id(num)
        except KeyError:
            await ctx.send("Error: a modmail ticket by that id does not exist")
        else:
            chan = bot.get_channel(int(mm_entry.field_map["channel_id"]))
            await chan.delete()
            modmail_table.remove_entry(mm_entry.id)
            await ctx.send("OK!")
    else:
        await ctx.send("You must be a staff member to use this command.")

@bot.command()
async def submit(ctx, name, sheet):
    user_id_str = str(ctx.author.id)
    table = await get_users_character_table(user_id_str)
    char = ATCharacter(name, sheet)
    table.add_entry(name, char.id, "False")
    await char.submit()
    await ctx.send(f"OK, {ctx.author.mention}, your character has been submitted. You will be notified when it has been accepted. Its unique ID is ```{char.id}```.")

#testing only commands
@bot.command()
async def ateval(ctx, expr):
    if testing_mode:
        await ctx.send(str(eval(expr)))
    else:
        pass

@bot.command()
async def testing_disable_mod_check(ctx):
    global mod_role
    if testing_mode:
        mod_role = ctx.author.roles[0]
        await ctx.send("OK")
    else:
        pass

@bot.command()
async def inc_day_c(ctx, amount: int):
    if testing_mode:
        await testing_inc_day(amount)

@bot.command()
async def get_char_dict(ctx, id):
    if testing_mode:
        await ctx.send(str((await get_character(chr_id=id)).__dict__))

@tasks.loop(minutes=10)
async def time_check_loop():
    global now, m_changed
    new_now = datetime.datetime.now()
    if new_now.hour != now.hour:
        await once_hourly_channel.edit(name=h_channel_names[new_now.hour])
    if new_now.day != day_loop_obj.day:
        add_days(1)
        if m_changed:
            m_changed = False
            await once_monthly_channel.edit(name=f"{day_loop_num} {m_channel_names[m_index]}")
            inc_m_index()
        dump_days()
    now = new_now

@bot.event
async def on_ready():
    global once_monthly_channel, once_hourly_channel, mm_channel_category, mod_role, at_guild
    once_monthly_channel = bot.get_channel(int(get_config("once_monthly_channel")))
    once_hourly_channel = bot.get_channel(int(get_config("once_hourly_channel")))
    mm_channel_category = bot.get_channel(int(get_config("modmail_category_id")))
    at_guild = bot.get_guild(int(get_config("at_guild_id")))
    mod_role = utils.get(at_guild.roles, id=int(get_config("mod_role")))
    time_check_loop.start()

async def testing_inc_day(amount):
    global m_changed
    add_days(amount)
    if m_changed:
        m_changed = False
        await once_monthly_channel.edit(name=f"{day_loop_num} {m_channel_names[m_index]}")
        inc_m_index()

async def send_modmail(subject, category, user):
    mm_id = modmail_table.len_entries
    chan = await mm_channel_category.create_text_channel(name=str(mm_id))
    await chan.send(f"Modmail opened: this modmail (ID #{chan.name}) was opened by {user.mention}. The category is {category}, and the subject line is:\n\n\"{subject}\"\n\n{mod_role.mention}")
    await chan.set_permissions(user, read_messages=True, send_messages=True)
    modmail_table.add_entry(str(user.id), subject, category, str(chan.id))
    modmail_table.commit()

def main():
    global testing_mode, man_entries
    if "--testing" in sys.argv:
        testing_mode = True
    for i in os.listdir("static/man"):
        with open(f"static/man/{i}", "r") as f:
            man_entries[i] = f.read()
    with open("static/ch_change_names_m", "r") as f:
        cont = f.read().strip()
        for i in cont.split("\n"):
            m_channel_names.append(i)
    with open("static/ch_change_names_h", "r") as f:
        cont = f.read().strip()
        for i in cont.split("\n"):
            h_channel_names.append(i)
    with open("static/mm_category_list", "r") as f:
        cont = f.read().strip()
        for i in cont.split("\n"):
            mm_category_list.append(i)
    if not os.path.isdir("data"):
        full_setup()
    else:
        init_already_installed()
    with open("static/secret", "r") as f:
        bot.run(f.read().strip())

if __name__ == "__main__":
    main()