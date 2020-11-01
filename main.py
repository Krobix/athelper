#!/usr/bin/env python3
import discord
from discord.ext import commands
import os
import pickle

bot = commands.Bot(command_prefix="at.")

config_table = None #data/config.table

class ATHelperTableEntry:
    def __init__(self, id, field_values, table):
        self.id = id
        self.field_values = field_values
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
            if search_value == i.field_map[field].lower():
                return i.field_map + { "id": i.id }
        else:
            return None

    def get_raw_entry_from_id(self, id):
        for i in self.entries:
            if i.id == id:
                return i

    def edit_entry(self, id, field, new_value):
        entry = self.get_raw_entry_from_id(id)
        entry.field_map[field] = new_value
        entry.__init__(id, entry.field_values, self)

    def commit(self):
        with open(self.path, "wb") as f:
            pickle.dump(self, f)

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
    return config_table.get_entry("key", key)

def set_config(key, val):
    id = get_config(key)["id"]
    config_table.edit_entry(id, "value", val)
    config_table.commit()

def full_setup():
    setup_directories()
    setup_tables()

def init_already_installed():
    pass #TODO

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

def main():
    pass #TODO