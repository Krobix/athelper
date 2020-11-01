#!/usr/bin/env python3
import discord
from discord.ext import commands
import os
import pickle

bot = commands.Bot(command_prefix="at.")

tables = {}

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
                return i.field_map
        else:
            return None

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
    tables["config"] = ATHelperTable("data/config.table", ["key", "value"])
    tables["config"].commit()
    