#!/usr/bin/env python3
import discord
import sys
import asyncio
import datetime
import pickle
import os
import copy
import traceback
from discord.ext import tasks, commands

bot = commands.Bot(command_prefix="at.")

man_entries = {}

status = None

now = datetime.datetime.now()

m_names = []

h_names = []

class ATHelperStatusData:
    def __init__(self, mchannel, hchannel, hindex, mindex, devuser):
        self.once_monthly_channel = mchannel
        self.once_hourly_channel = hchannel
        self.hour_index = hindex
        self.month_index = mindex
        self.devuser = devuser

def setup():
    global status
    os.mkdir("data")
    os.mkdir("data/channel.d")
    os.mkdir("data/chr")
    os.mkdir("data/chr/tables")
    os.mkdir("data/chr/obj")
    status = ATHelperStatusData(None, None, now.hour, now.month, None)

async def write_data_to_disk():
    nstatus = copy.copy(status)
    with open("data/status.bin", "wb") as f:
        nstatus.devuser = status.devuser.id
        nstatus.once_hourly_channel = status.once_hourly_channel.id
        nstatus.once_monthly_channel = status.once_monthly_channel.id
        pickle.dump(nstatus, f)

@bot.command()
async def set_once_monthly(ctx):
    global status
    if ctx.author == status.devuser:
        channel = ctx.message.raw_channel_mentions[0]
        status.once_monthly_channel = bot.get_channel(channel)
        await ctx.send("OK")
    else:
        await ctx.send("error: you are not the developer")

@bot.command()
async def set_once_hourly(ctx):
    global status
    if ctx.author == status.devuser:
        channel = ctx.message.raw_channel_mentions[0]
        status.once_hourly_channel = bot.get_channel(channel)
        await ctx.send("OK")
    else:
        await ctx.send("error: you are not the developer.")

@bot.command()
async def setdev(ctx):
    global status
    if status.devuser == None:
        status.devuser = ctx.author
        await ctx.send("OK")
    else:
        await ctx.send("error: there is already a devuser")

@bot.command()
async def manual_data_write(ctx):
    await write_data_to_disk()
    await ctx.send("OK")

@bot.command()
async def help(ctx, page):
    if os.path.isfile(f"static/man/{page}"):
        with open(f"static/man/{page}", "r") as f:
            emb = discord.Embed()
            emb.title = f"Help: {page}"
            emb.description = f.read()
            emb.colour = discord.Colour.blue()

@tasks.loop(minutes=10.0)
async def check_time():
    global now
    print("Running check_time")
    new_now = datetime.datetime.now()
    status.hour_index = h_names[new_now.hour]
    status.month_index = m_names[new_now.month]
    status.once_monthly_channel.edit(name=status.month_index)
    status.once_hourly_channel.edit(name=status.hour_index)
    now = new_now

@bot.event
async def on_command_error(context, error):
    emb = discord.Embed()
    error = error.original
    #print(sys.exc_info())
    emb.title = "Error"
    emb.colour = discord.Colour.red()
    emb.description = f"An error has occured. Please report it to the developer:\n\n```{''.join(traceback.format_exception(type(error), error, error.__traceback__))}```"
    await context.send(embed=emb)

def main():
    global status, m_names, h_names
    if not os.path.isdir("data"):
        setup()
    else:
        with open("data/status.bin", "rb") as f:
            status = pickle.load(f)
            status.devuser = bot.get_user(status.devuser)
            status.once_hourly_channel = bot.get_channel(status.once_hourly_channel)
            status.once_monthly_channel = bot.get_channel(status.once_monthly_channel)
    with open("static/ch_change_names_h", "r") as f:
        h_names = f.read()
        h_names = h_names.strip("\n")
        h_names = h_names.strip(" ")
        h_names = h_names.split("\n")
    with open("static/ch_change_names_m", "r") as f:
        m_names = f.read()
        m_names = m_names.strip("\n")
        m_names = m_names.strip(" ")
        m_names = m_names.split("\n")
    for i in os.listdir("static/man"):
        with open(f"static/man/{i}", r) as f:
            man_entries[i] = f.read()
    with open("static/secret", "r") as f:
        bot.run(f.read().strip())

main()