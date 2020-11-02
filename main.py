#!/usr/bin/env python3
import discord
import asyncio
from discord.ext import commands, tasks
import os
import pickle
import copy
import sys
import datetime

bot = commands.Bot(command_prefix="at.")

config_table = None #data/config.table

testing_mode = False

once_monthly_channel = None

once_hourly_channel = None

m_channel_names = []

h_channel_names = []

now = datetime.datetime.now()

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
            return None

    def get_raw_entry_from_id(self, id):
        for i in self.entries:
            if i.id == id:
                return i

    def edit_entry(self, id, field, new_value):
        entry = self.get_raw_entry_from_id(id)
        pos = self.fields.index(field)
        entry.field_values[pos] = new_value
        entry.__init__(id, entry.field_values, self)

    def commit(self):
        with open(self.path, "wb") as f:
            pickle.dump(self, f)

def load_table(path):
    with open(path, "rb") as f:
        return pickle.load(f)

def try_mkdir(dir):
    if not os.path.isdir(dir):
        os.mkdir(dir)

def setup_directories():
    try_mkdir("data")
    try_mkdir("data/chr")
    try_mkdir("data/chr/tables")
    try_mkdir("data/chr/obj")

def setup_tables():
    global config_table
    #Config table
    config_table = ATHelperTable("data/config.table", ["key", "value"])
    config_table.add_entry("once_monthly_channel", "None")
    config_table.add_entry("once_hourly_channel", "None")
    config_table.add_entry("devuser", "None")
    config_table.commit()

def get_config(key):
    return config_table.get_entry("key", key)["value"]

def set_config(key, val):
    id = config_table.get_entry("key", key)["id"]
    if testing_mode:
        print(f"set_config: id is {id}")
    config_table.edit_entry(id, "value", val)
    config_table.commit()

def full_setup():
    setup_directories()
    setup_tables()

def init_already_installed():
    global config_table
    config_table = load_table("data/config.table")

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
async def ateval(ctx, expr):
    if testing_mode:
        await ctx.send(str(eval(expr)))
    else:
        pass

@tasks.loop(minutes=10)
async def time_check_loop():
    global now
    new_now = datetime.datetime.now()
    if new_now.hour != now.hour:
        await once_monthly_channel.edit(name=m_channel_names[new_now.month])
        await once_hourly_channel.edit(name=h_channel_names[new_now.hour])
    now = new_now

@bot.event
async def on_ready():
    global once_monthly_channel, once_hourly_channel
    once_monthly_channel = bot.get_channel(int(get_config("once_monthly_channel")))
    once_hourly_channel = bot.get_channel(int(get_config("once_hourly_channel")))
    time_check_loop.start()

def main():
    global testing_mode
    if "--testing" in sys.argv:
        testing_mode = True
    with open("static/ch_change_names_m", "r") as f:
        cont = f.read().strip()
        for i in cont.split("\n"):
            m_channel_names.append(i)
    with open("static/ch_change_names_h", "r") as f:
        cont = f.read().strip()
        for i in cont.split("\n"):
            h_channel_names.append(i)
    if not os.path.isdir("data"):
        full_setup()
    else:
        init_already_installed()
    with open("static/secret", "r") as f:
        bot.run(f.read().strip())

main()