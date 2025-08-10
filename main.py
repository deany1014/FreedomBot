import os
import asyncio
from dotenv import load_dotenv
import discord
from discord.ext import commands
from fastapi import FastAPI
import uvicorn

# --- Configuration ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN missing in .env")

# --- FastAPI App Definition ---
# Define the app at the top level so uvicorn can find it.
app = FastAPI()

# --- Custom Bot Class ---
class CombinedBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.web_server_task = None
        self.uvicorn_server = None

    async def setup_hook(self):
        """This is called before the bot connects to Discord."""
        # 1. Load Cogs
        print("- - Loading Cogs - -")
        await self.load_cogs()
        print("- - Cogs Loaded - -\n")
        
        # Uncomment if you want to sync slash commands on startup
        # try:
        #     synced = await self.tree.sync()
        #     print(f"Synced {len(synced)} slash commands")
        # except Exception as e:
        #     print(f"Failed to sync slash commands: {e}")

        # 2. Start the FastAPI server in a background task.
        # The '__main__:app' tells uvicorn to look for the 'app' object in the current file.
        config = uvicorn.Config("__main__:app", host="0.0.0.0", port=8000, log_level="info")
        self.uvicorn_server = uvicorn.Server(config)
        
        # Running the server in a background task
        self.web_server_task = asyncio.create_task(self.uvicorn_server.serve())
        print("- - Dashboard started on http://0.0.0.0:8000 - -")

    async def load_cogs(self):
        """Loads all cogs from the ./cogs directory."""
        for folder in os.listdir("./cogs"):
            path = f"./cogs/{folder}"
            if os.path.isdir(path):
                cog_path = f"cogs.{folder}.cog"
                try:
                    await self.load_extension(cog_path)
                    print(f"-> Loaded cog from {cog_path}")
                except Exception as e:
                    print(f"-> Failed to load {cog_path}: {e}")

    async def on_ready(self):
        """Event for when the bot is ready and connected to Discord."""
        print(f"\nLogged in as {self.user} (ID: {self.user.id})")
        print("- - Bot is online and ready! - -")

    async def close(self):
        """Custom close logic to shut down the web server."""
        print("\n- - Closing Bot and Dashboard - -")
        
        # Shut down the web server gracefully
        if self.uvicorn_server:
            self.uvicorn_server.should_exit = True
            # Wait for the server task to finish
            if self.web_server_task:
                await self.web_server_task
        
        # Call the original close method to shut down the bot
        await super().close()

# The status endpoint can now access the bot instance via the request context
# if you pass it in, but a simpler way is just to have it access the global bot variable.
bot_instance = None # Will hold our bot instance

@app.get("/status")
async def status():
    if not bot_instance or not bot_instance.is_ready():
        return {"status": "bot_not_ready"}
    
    return {
        "bot_user": str(bot_instance.user),
        "is_ready": bot_instance.is_ready(),
        "latency": f"{bot_instance.latency * 1000:.2f} ms",
        "guild_count": len(bot_instance.guilds),
    }

# --- Main Execution Block ---
if __name__ == "__main__":
    intents = discord.Intents.default()
    intents.message_content = True

    bot_instance = CombinedBot(command_prefix="!", intents=intents)
    
    try:
        # bot.run() handles the asyncio event loop and gracefully deals
        # with KeyboardInterrupt (Ctrl+C) by calling bot.close().
        bot_instance.run(TOKEN)
    except KeyboardInterrupt:
        # This part is technically redundant because bot.run() handles it,
        # but it's good for clarity.
        print("\n- - Bot stopped by user - -")