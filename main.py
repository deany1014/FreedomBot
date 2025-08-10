import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

# Load cogs dynamically from cogs/<folder>/cog.py
for folder in os.listdir("./cogs"):
    path = f"./cogs/{folder}"
    if os.path.isdir(path):
        cog_path = f"cogs.{folder}.cog"
        try:
            bot.load_extension(cog_path)
            print(f"Loaded cog from {cog_path}")
        except Exception as e:
            print(f"Failed to load {cog_path}: {e}")

bot.run("YOUR_BOT_TOKEN_HERE")
