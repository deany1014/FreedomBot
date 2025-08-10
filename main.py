import os
import asyncio
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()  # Load .env variables

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    # try:
    #     synced = await bot.tree.sync()
    #     print(f"Synced {len(synced)} slash commands")
    # except Exception as e:
    #     print(f"Failed to sync slash commands: {e}")

async def load_cogs():
    for folder in os.listdir("./cogs"):
        path = f"./cogs/{folder}"
        if os.path.isdir(path):
            cog_path = f"cogs.{folder}.cog"
            try:
                await bot.load_extension(cog_path)
                print(f"Loaded cog from {cog_path}")
            except Exception as e:
                print(f"Failed to load {cog_path}: {e}")

async def main():
    async with bot:
        print(f"- - Loading Cogs - -")
        await load_cogs()
        print(f"- - Cogs Loaded - -")
        print(f"\n- - Starting Bot - -")
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("- - Bot Stopped - -")

