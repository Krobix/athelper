#!/usr/bin/env python3
import discord
import sys
import asyncio
import datetime
import pickle
import os
import copy
import traceback
import secrets
from discord.ext import tasks, commands

DEVKEY = secrets.token_hex(5)

bot = commands.Bot(command_prefix="at.")

man_entries = {}

status = None

now = datetime.datetime.now()

m_names = []

h_names = []

FALLBACK_DEV_ID = 229277947733868545

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
    status = ATHelperStatusData(None, None, now.hour, now.month, 0)

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
    if status.devuser == 0:
        status.devuser = ctx.author
        await ctx.send("OK")
    else:
        await ctx.send("error: there is already a devuser")

@bot.command()
async def manual_data_write(ctx):
    await write_data_to_disk()
    await ctx.send("OK")

@bot.command()
async def info(ctx, page):
    if page in man_entries:
        emb = discord.Embed()
        emb.title = f"Help: {page}"
        emb.description = man_entries[page]
        emb.colour = discord.Colour.blue()
        await ctx.send(embed=emb)
    else:
        ctx.send(f"Error: {page} is not a known info page")

@bot.command(name="eval")
async def eval_comm(ctx, key, stmt):
    if key == DEVKEY:
        out = str(eval(stmt))
        await ctx.send(out)
    else:
        pass

async def check_time():
    global now
    while True:
        #print("Running check_time")
        new_now = datetime.datetime.now()
        status.hour_index = h_names[new_now.hour]
        status.month_index = m_names[new_now.month]
        await status.once_monthly_channel.edit(name=status.month_index)
        await status.once_hourly_channel.edit(name=status.hour_index)
        now = new_now
        await asyncio.sleep(600)

@bot.event
async def on_command_error(context, error):
    emb = discord.Embed()
    error = error.original
    #print(sys.exc_info())
    emb.title = "Error"
    emb.colour = discord.Colour.red()
    emb.description = f"An error has occured. Please report it to the developer:\n\n```{''.join(traceback.format_exception(type(error), error, error.__traceback__))}```"
    await context.send(embed=emb)

@bot.event
async def on_ready():
    global status
    await bot.wait_until_ready()
    print(f"devkey={DEVKEY}")
    if not os.path.isdir("data"):
        setup()
    else:
        with open("data/status.bin", "rb") as f:
            status = pickle.load(f)
            print(f"devuser id={status.devuser}")
            status.devuser = bot.get_user(int(status.devuser))
            print(f"DEVUSER DETECTED:\n\n{status.devuser}")
            status.once_hourly_channel = bot.get_channel(int(status.once_hourly_channel))
            status.once_monthly_channel = bot.get_channel(int(status.once_monthly_channel))
            if status.devuser == None:
                status.devuser = bot.get_user(FALLBACK_DEV_ID)
    bot.loop.create_task(check_time())

def main():
    global status, m_names, h_names
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
        with open(f"static/man/{i}", "r") as f:
            man_entries[i] = f.read()
    with open("static/secret", "r") as f:
        bot.run(f.read().strip())

main()