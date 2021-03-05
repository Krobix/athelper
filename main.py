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
import traceback

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="at.", intents=intents)

bot.remove_command("help")

config_table = None #data/config.table

modmail_table = None #data/modmail.table

testing_mode = False

VERSION = "1.0.8-angela"

#Discord objects loaded from config table
once_monthly_channel = None

once_hourly_channel = None

mm_channel_category = None

mod_role = None

at_guild = None

char_archive_channel = None

log_channel = None

greetings_channel = None

loaded_testing_char = None
#########################################

m_channel_names = []

h_channel_names = []

mm_category_list = []

watching_users = []

now = datetime.datetime.now()

man_entries = {}

welcome_msg_raw = None

day_loop_obj = None

day_loop_num = 0

m_index = 0

m_changed = False

chr_unapproved_list = []

users_garbage_collection = []

ADMIN_COMMANDS = ("at.approve", "at.ateval", "at.testing_disable_mod_check")

class CharacterNotFoundError(OSError):
    pass

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


class ATBaseObject:
    def __init__(self):
        self.path = "object"
    
    async def commit(self):
        with open(self.path, "wb") as f:
            pickle.dump(self, f)

class ATCharacter(ATBaseObject):
    def __init__(self, name, sheet, owner_id):
        super().__init__()
        self.name = name
        self.sheet = sheet
        self.id = secrets.token_hex(10)
        self.path = f"data/chr/obj/{self.id}"
        self.currency_amount = 0
        self.products_owned = {}
        self.approved_bio = False
        self.approved_stats = False
        self.owner_id = owner_id
        self.approver_ids = []

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
            user = bot.get_user(int(self.owner_id))
            chr_unapproved_list.remove(self.id)
            emb = await get_char_info_embed(self.id)
            await char_archive_channel.send(embed=emb)
            await user.send(f"Your character {self.name} (ID: {self.id}) has beeen approved.")
        with open("data/chr/tables/unapproved.list", "wb") as f:
            pickle.dump(chr_unapproved_list, f)

    async def get_shop_item(self, item_id):
        if item_id in self.products_owned:
            self.products_owned[item_id] += 1
        else:
            self.products_owned[item_id] = 1
        await self.commit()

    async def spend_money(self, amount):
        if amount > self.currency_amount:
            return "ERRAMOUNT"
        else:
            self.currency_amount -= amount
            await self.commit()
            return None

    async def buy(self, pricetag):
        if await self.spend_money(pricetag.price) != "ERRAMOUNT":
            await self.get_shop_item(pricetag.item_id)
            pricetag.shop -= 1
        else:
            return "ERRAMOUNT"

class ATShopItem(ATBaseObject):
    def __init__(self, name, id, description):
        super().__init__()
        self.name = name
        self.id = id
        self.description = description
        self.path = f"data/econ/item/{id}"

class ATShopItemPricetag(ATBaseObject):
    def __init__(self, item, price, stock):
        super().__init__()
        self.item_id = item.id
        self.price = price
        self.stock = stock
        self.path = f"data/econ/0ptag"

class ATShop(ATBaseObject):
    def __init__(self, name, id, description, channel_id):
        super().__init__()
        self.name = name
        self.id = id
        self.item_pricetags = []
        self.description = description
        self.channel_id = channel_id
        self.path = f"data/econ/shop/{id}"

    async def add_pricetag(self, item_id, price, stock):
        pricetag = ATShopItemPricetag(await get_item(item_id), price, stock)
        try:
            old_pricetag = await self.get_pricetag_from_item_id(item_id)
        except KeyError:
            self.item_pricetags.append(pricetag)
        else:
            self.item_pricetags.remove(old_pricetag)
            self.item_pricetags.append(pricetag)
        await self.commit()

    async def get_pricetag_from_item_id(self, item_id):
        """NOTE: returned in format (item, pricetag)"""
        for i in self.item_pricetags:
            if item_id == i.item_id:
                return await get_item(item_id), i
        else:
            raise KeyError("No valid item attached to give pricetag")

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
    if m_index > 19:
        m_index = 0

def setup_directories():
    try_mkdir("data")
    try_mkdir("data/chr")
    try_mkdir("data/chr/tables")
    try_mkdir("data/chr/tables/usr")
    try_mkdir("data/chr/obj")
    try_mkdir("data/econ")
    try_mkdir("data/econ/item")
    try_mkdir("data/econ/shop")

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
    config_table.add_entry("char_arch_id", "None")
    config_table.add_entry("log_channel", "None")
    config_table.add_entry("greetings_channel", "None")
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
    global config_table, modmail_table, day_loop_obj, day_loop_num, m_index, chr_unapproved_list, welcome_msg_raw
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
    with open("./static/on_join_msg", "r") as f:
        welcome_msg_raw = f.read()
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
            try:
                char = table.get_entry("name", name)
                return load_obj(f"data/chr/obj/{char['chr_id']}")
            except OSError:
                raise CharacterNotFoundError
    elif chr_id != None:
        try:
            return load_obj(f"data/chr/obj/{chr_id}")
        except OSError:
            raise CharacterNotFoundError 

async def get_shop(id):
    with open(f"data/econ/shop/{id}", "rb") as f:
        return pickle.load(f)

async def get_shop_by_channel(channel):
    for i in os.listdir("data/econ/shop"):
        shop = await get_shop(i)
        if shop.channel_id == channel.id:
            return shop
    else:
        raise KeyError("Shop not found")

async def get_item(id):
    with open(f"data/econ/item/{id}", "rb") as f:
        return pickle.load(f)

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
async def set_char_archive_channel(ctx):
    if str(ctx.author.id) == get_config("devuser"):
        set_config("char_arch_id", str(ctx.channel.id))
        await ctx.send("OK")
    else:
        await ctx.send("error: you are not the devuser")

@bot.command()
async def set_log_channel(ctx):
    if str(ctx.author.id) == get_config("devuser"):
        set_config("log_channel", str(ctx.channel.id))
        await ctx.send("OK")
    else:
        await ctx.send("error: you are not the devuser")

@bot.command()
async def set_greetings_channel(ctx):
    if str(ctx.author.id) == get_config("devuser"):
        set_config("greetings_channel", str(ctx.channel.id))
        await ctx.send("OK")
    else:
        await ctx.send("error: you are not the devuser")


@bot.command()
async def set_welcome_msg(ctx, msg_id: int):
    msg = await ctx.fetch_message(msg_id)
    await bot_log("Set welcome message command detected")
    if (str(ctx.author.id) == get_config("devuser")) or (mod_role in ctx.author.roles):
        with open("data/welcome_override", "w") as f:
            f.write(msg.content)
            await ctx.send("OK")
    else:
        await bot_log("Setting welcome message override failed")

@bot.command()
async def help(ctx, *args):
    if len(args) >= 1:
        page = args[0]
    else:
        page = "athelper"
    emb = discord.Embed()
    emb.title = f"Help: {page}"
    try:
        emb.description = man_entries[page]
    except KeyError:
        await ctx.send(f"Error: help page {page} not found")
    emb.color = discord.Color.blue()
    await ctx.send(embed=emb)

@bot.command()
async def mm(ctx, category, subject):
    await send_modmail(subject, category, ctx.author)
    await ctx.send("Sent.")

@bot.command()
async def mmi(ctx, num: int):
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
async def mmc(ctx, num: int):
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
async def submit(ctx, *args):
    if len(args) != 2:
        await ctx.send("Error: you did not give the proper amount of arguments. Note that, if the character's name is more than one word, you must put it in quotes.")
    else:
        name = args[0]
        sheet = args[1]
        user_id_str = str(ctx.author.id)
        table = await get_users_character_table(user_id_str)
        char = ATCharacter(name, sheet, user_id_str)
        table.add_entry(name, char.id, "False")
        table.commit()
        await char.submit()
        await ctx.send(f"OK, {ctx.author.mention}, your character has been submitted. You will be notified when it has been accepted. Its unique ID is: ```{char.id}```")
        if len(chr_unapproved_list) > 5:
            await ctx.send(f"{mod_role.mention}, there are more than five characters waiting for approval!")

@bot.command()
async def approve(ctx, which, chr_id):
    if mod_role in ctx.author.roles:
        char = await get_character(chr_id=chr_id)
        if testing_mode:
            await ctx.send(f"```Testing mode: at.approve: char is {char}```")
        if not (char.approved_bio and char.approved_stats):
            owner_char_table = await get_users_character_table(char.owner_id)
            approved_char_table_entry = owner_char_table.get_entry("chr_id", chr_id)
            await char.approve(which)
            char.approver_ids.append(ctx.author.id)
            await char.commit()
            if char.approved_bio and char.approved_stats:
                owner_char_table.edit_entry(approved_char_table_entry["id"], "approved", "True")
                owner_char_table.commit()
            await ctx.send(f"OK! That character's {which} has been approved.")
        else:
            await ctx.send("That character has already been fully approved.")
    else:
        await ctx.send("You must be a staff member to use that command.")

@bot.command()
async def listc(ctx, user: discord.User):
    await ctx.send(f"Sending a list of {user}'s characters. Use at.character_info (id) to see more info about a specific character.")
    str_user_id = str(user.id)
    async with ctx.typing():
        usr_table = await get_users_character_table(str_user_id)
        for i in usr_table.entries:
            emb = discord.Embed()
            emb.title = "Character"
            emb.add_field(name="Character Name", value=i.field_map["name"], inline=False)
            emb.add_field(name="Is fully approved?", value=i.field_map["approved"], inline=False)
            emb.add_field(name="Character's ID", value=i.field_map["chr_id"], inline=False)
            await ctx.send(embed=emb)
    await ctx.send("Done.")

@bot.command()
async def chari(ctx, chr_id):
    async with ctx.typing():
        emb = await get_char_info_embed(chr_id)
        await ctx.send(embed=emb)

@bot.command()
async def listwa(ctx):
    await ctx.send("Please wait a moment while I retrieve the list; it may be long...")
    async with ctx.typing():
        await asyncio.sleep(2)
        for i in chr_unapproved_list:
            await ctx.send(embed=await get_char_info_embed(i))
    await ctx.send("Done.")

@bot.command()
async def charse(ctx, name):
    async with ctx.typing():
        try:
            char = await get_character(user_id=str(ctx.author.id), name=name)
        except KeyError:
            await ctx.send("No character with that name was found.")
        else:
            await ctx.send(char.id)

@bot.command()
async def chardel(ctx, chr_id):
    char = await get_character(chr_id=chr_id)
    if (int(char.owner_id) == ctx.author.id) or (mod_role in ctx.author.roles):
        await delete_character(chr_id)
        await ctx.send("OK")
    else:
        await ctx.send("You do not have the vaid permissions to delete that character.")

@bot.command()
async def charrename(ctx, chr_id, new_name):
    char = await get_character(chr_id=chr_id)
    if int(char.owner_id) == ctx.author.id:
        char.name = new_name 
        await char.commit()
        await ctx.send("OK")
    else:
        await ctx.send("You do not own that character.")

@bot.command()
async def shop_create(ctx, name, id, description, channel: discord.TextChannel):
    if mod_role in ctx.author.roles:
        shop = ATShop(name=name, id=id, description=description, channel_id=channel.id)
        await shop.commit()
        await ctx.send("OK!")
    else:
        await ctx.send("That command is for moderators only")

@bot.command()
async def shop_item_create(ctx, name, id, description):
    if mod_role in ctx.author.roles:
        item = ATShopItem(name=name, id=id, description=description)
        await item.commit()
        await ctx.send("OK!")
    else:
        await ctx.send("That command is for moderators only")

@bot.command()
async def add_item_to_shop(ctx, shop_id, item_id, price: int, stock: int):
    if mod_role in ctx.author.roles:
        shop = await get_shop(shop_id)
        await shop.add_pricetag(item_id, price, stock)
        await ctx.send("OK")
    else:
        await ctx.send("Only staff can use that command.")

@bot.command()
async def shopi(ctx):
    try:
        shop = await get_shop_by_channel(ctx.channel)
    except KeyError:
        await ctx.send("There is no shop in this channel")
    else:
        emb = discord.Embed()
        emb.title = f"Shop info: {shop.name}"
        emb.add_field(name="Shop name", value=shop.name, inline=False)
        emb.add_field(name="Shop ID", value=shop.id, inline=False)
        emb.add_field(name="Description", value=shop.description, inline=False)
        emb.add_field(name="Stock", value=len(shop.item_pricetags), inline=False)
        emb.color = discord.Color.green()
        await ctx.send(embed=emb)

@bot.command()
async def itemls(ctx):
    try:
        shop = await get_shop_by_channel(ctx.channel)
    except KeyError:
        await ctx.send("There is no shop in this channel")
    else:
        async with ctx.typing():
            for i in shop.item_pricetags:
                emb = await get_item_info_embed(i.item_id)
                emb.add_field(name="Price", value=str(i.price), inline=False)
                emb.add_field(name="Stock", value=str(i.stock), inline=False)
                await ctx.send(embed=emb)
        await ctx.send("Done!")

@bot.command()
async def ownedls(ctx, chr_id):
    try:
        char = await get_character(chr_id=chr_id)
    except OSError:
        await ctx.send("Error: that character does not exist.")
    else:
        await ctx.send("Please wait while I retrieve the list; it may be long...")
        async with ctx.typing():
            for i in char.products_owned.keys():
                emb = await get_item_info_embed(i)
                emb.add_field(name="Amount Owned", value=str(char.products_owned[i]), inline=False)
                await ctx.send(embed=emb)
        await ctx.send("Done!")

@bot.command()
async def buy(ctx, chr_id, item_id):
    #TODO: make this get shop from current channel and fetch pricetag
    try:
        char = await get_character(chr_id=chr_id)
    except OSError:
        await ctx.send("Error: no character with the given ID was found.")
    else:
        if not (char.approved_bio and char.approved_stats and (int(char.owner_id) == ctx.author.id)):
            await ctx.send("Error: that character is not fully approved or is not yours.")
        else:
            try:
                shop = await get_shop_by_channel(ctx.channel)
                item, pricetag = await shop.get_pricetag_from_item_id(item_id)
                err = await char.buy(pricetag)
            except OSError:
                await ctx.send("The item that you have requested to buy is nonexistent.")
            else:
                if err == "ERRAMOUNT":
                    await ctx.send(f"Error: that character does not have enough money to purchase 1 {item.name}")
                else:
                    if pricetag.stock <= 0:
                        shop.item_pricetags.remove(item.id)
                    await shop.commit()
                    await ctx.send("Success")

@bot.command()
async def bank_give(ctx, amount: int, chr_id):
    if mod_role in ctx.author.roles:
        async with ctx.typing():
            char = await get_character(chr_id=chr_id)
            if char == None:
                await ctx.send("Error: that character does not exist")
            else:
                char.currency_amount += amount
                await char.commit()
                await ctx.send("OK!")
    else:
        await ctx.send("Error: you must be staff to use that command")

@bot.command()
async def givem(ctx, amount: int, chr_id1, chr_id2):
    try:
        char1 = await get_character(chr_id=chr_id1)
    except OSError:
        await ctx.send("A character was not found with the first ID given.")
    else:
        if int(char1.owner_id) == ctx.author.id:
            try:
                char2 = await get_character(chr_id=chr_id2)
            except OSError:
                await ctx.send("A character was not found with the second ID given.")
            else:
                err = await char1.spend_money(amount)
                if err == "ERRAMOUNT":
                    await ctx.send("That character does not have enough money to give that amount!")
                else:
                    char2.currency_amount += amount
                    await char1.commit()
                    await char2.commit()
                    await ctx.send("OK")
        else:
            await ctx.send("Error: that character is not yours!")

@bot.command()
async def status(ctx):
    emb = discord.Embed()
    emb.title = "Bot Status"
    emb.add_field(name="ATHelper version", value=VERSION, inline=False)
    emb.add_field(name="Bot is running in testing mode", value=str(testing_mode), inline=False)
    emb.color = discord.Color.magenta()
    await ctx.send(embed=emb)

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

@bot.command()
async def load_testing_char(ctx, id):
    global loaded_testing_char
    if testing_mode:
        loaded_testing_char = await get_character(chr_id=id)
        await ctx.send("OK")

@tasks.loop(minutes=10)
async def time_check_loop():
    global now, m_changed, day_loop_obj
    await bot_log("Checking time and date.")
    new_now = datetime.datetime.now()
    if new_now.hour != now.hour:
        await once_hourly_channel.edit(name=h_channel_names[new_now.hour])
    await bot_log(f"The current day is {new_now.day} and the stored day is {day_loop_num}")
    while new_now.date() > day_loop_obj.date():
        await bot_log("The day has changed.")
        add_days(1)
        if m_changed:
            inc_m_index()
            m_changed = False
        day_loop_obj += datetime.timedelta(days=1)
    await once_monthly_channel.edit(name=f"{day_loop_num} {m_channel_names[m_index]}")
    dump_days()
    now = new_now
    day_loop_obj = now
    await bot_log("Check completed.")

@tasks.loop(hours=24)
async def data_garbage_collection():
    await bot_log("Now, garbage collection will begin. Any character data that has been scheduled for deletion will be deleted.")
    for i in users_garbage_collection:
        for j in (await get_users_character_table(i).entries):
            await delete_character(j.field_map["chr_id"])
    await bot_log("Garbage collection has finished.")

@bot.event
async def on_member_join(member): 
    welcome_msg = welcome_msg_raw.format(member.mention)
    await greetings_channel.send(welcome_msg)

@bot.event
async def on_member_remove(member):
    await bot_log(f"The member with the ID {member.id} has left. If they have any characters, they will be scheduled for deletion.")
    if os.path.exists(f"data/chr/tables/usr/{member.id}.table"):
        await bot_log(f"Character list for {member.id} found...")
        users_garbage_collection.append(member.id)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.UserInputError):
        await ctx.send("Error: there was an error with the command. That command may not exist or an argument you gave may be invalid. For more info, see at.help error.")
    elif hasattr(error, "original"):
        if isinstance(error.original, CharacterNotFoundError):
            await ctx.send("Error: that character was not found.")
        error = error.original
        emb = discord.Embed()
        emb.title = "Fatal Error"
        emb.color = discord.Color.red()
        emb.description = f"A fatal error has occurred. Please report it to the developer:\n\n```{''.join(traceback.format_exception(type(error), error, error.__traceback__))}```"
        await ctx.send(embed=emb)

@bot.event
async def on_ready():
    global once_monthly_channel, once_hourly_channel, mm_channel_category, mod_role, at_guild, char_archive_channel, log_channel, greetings_channel, welcome_msg_raw
    ###CHANNEL LOADING
    once_monthly_channel = bot.get_channel(int(get_config("once_monthly_channel")))
    once_hourly_channel = bot.get_channel(int(get_config("once_hourly_channel")))
    mm_channel_category = bot.get_channel(int(get_config("modmail_category_id")))
    char_archive_channel = bot.get_channel(int(get_config("char_arch_id")))
    log_channel = bot.get_channel(int(get_config("log_channel")))
    greetings_channel = bot.get_channel(int(get_config("greetings_channel")))
    ##################
    at_guild = bot.get_guild(int(get_config("at_guild_id")))
    mod_role = utils.get(at_guild.roles, id=int(get_config("mod_role")))
    await bot.change_presence(activity=discord.Game(name="at.help athelper"))
    time_check_loop.start()
    data_garbage_collection.start()
    await bot_log("The bot is now running.")
    await fix_waiting_approval_list()
    if os.path.exists("data/welcome_override"):
        with open("data/welcome_override", "r") as f:
            welcome_msg_raw =  f.read()
    if testing_mode:
        await bot_log("The bot is running in testing mode.")

@bot.event
async def on_message(message):
    await security_check(message)
    await bot.process_commands(message)

async def security_check(message):
    if message.content.startswith("at."):
        if message.author.id in watching_users:
            await bot_log(f"The watched user {message.author.mention} has used the command '{message.content}'")
        else:
            comm_name = message.content.split(" ")[0]
            if (comm_name in ADMIN_COMMANDS) and ((str(message.author.id) != get_config("devuser")) and (not (mod_role in message.author.roles))):
                warnmsg = f"Warning: The user {message.author.mention} has tried to use the command '{message.content}', but they do not have the proper permissions. All of the commands they use until the bot restarts will be logged,"
                devuser = bot.get_user(int(get_config("devuser")))
                await devuser.send(warnmsg)
                await bot_log(warnmsg)
                watching_users.append(message.author.id)

async def delete_character(chr_id):
    char = await get_character(chr_id=chr_id)
    table = await get_users_character_table(char.owner_id)
    chr_entry_id = int(table.get_entry(field="chr_id", search_value=chr_id)["id"])
    table.remove_entry(chr_entry_id)
    os.remove(char.path)
    if char.id in chr_unapproved_list:
        chr_unapproved_list.remove(char.id)

async def fix_waiting_approval_list():
    for i in os.listdir("data/chr/obj"):
        char = await get_character(chr_id=i)
        if (not (char.approved_bio and char.approved_stats)) and (not(char.id in chr_unapproved_list)):
            await bot_log("The unapproved character list has been detected as corrupt; This issue will be fixed automatically.")
            chr_unapproved_list.append(char.id)
    with open("data/chr/tables/unapproved.list", "wb") as f:
        pickle.dump(chr_unapproved_list, f)

async def get_char_info_embed(chr_id):
    char = await get_character(chr_id=chr_id)
    emb = discord.Embed()
    emb.title = f"Character info: {char.name}"
    emb.color = discord.Color.blurple()
    emb.add_field(name="Character name", value=char.name, inline=False)
    emb.add_field(name="Character ID", value=char.id, inline=False)
    emb.add_field(name="Currency Amount", value=char.currency_amount, inline=False)
    emb.add_field(name="Approved bio?", value=char.approved_bio, inline=False)
    emb.add_field(name="Approved stats?", value=char.approved_stats, inline=False)
    emb.add_field(name="Character's sheet", value=char.sheet, inline=False)
    emb.add_field(name="Character's Owner", value=bot.get_user(int(char.owner_id)).mention, inline=False)
    return emb

async def get_item_info_embed(item_id):
    item = await get_item(item_id)
    emb = discord.Embed()
    emb.title = f"Shop Item: {item.name}"
    emb.add_field(name="Name", value=item.name, inline=False)
    emb.add_field(name="ID", value=item.id, inline=False)
    emb.add_field(name="Description", value=item.description, inline=False)
    return emb

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

async def bot_log(message):
    emb = discord.Embed()
    emb.title = f"Log: {datetime.datetime.now()}"
    emb.description = message
    await log_channel.send(embed=emb)

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