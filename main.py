# main.py

import os
import asyncio
from dotenv import load_dotenv
import discord
from discord.ext import commands
import uvicorn

# Import the FastAPI app instance from your dashboard module
# The 'as dashboard_app' alias is used to avoid name conflicts.
from dashboard.app import app as dashboard_app

# --- Configuration ---
# Load environment variables from a .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN is missing from your .env file!")

# --- Custom Bot Class ---
class CombinedBot(commands.Bot):
    """
    A custom bot class that integrates a FastAPI web server.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.web_server_task = None
        self.uvicorn_server = None

    async def setup_hook(self):
        """
        This special method is called by discord.py after login but before
        connecting to the gateway. It's the ideal place for async setup tasks.
        """
        # --- 1. Load Cogs ---
        print("- - - - - - - - - - - - - - - -")
        print("Loading Cogs...")
        # Example cog loading logic (customize for your project)
        for folder in os.listdir("./cogs"):
            path = f"./cogs/{folder}"
            if os.path.isdir(path):
                cog_path = f"cogs.{folder}.cog"
                try:
                    await bot.load_extension(cog_path)
                    print(f"Loaded cog from {cog_path}")
                except Exception as e:
                    print(f"Failed to load {cog_path}: {e}")
        print("Cogs loaded successfully.")
        print("- - - - - - - - - - - - - - - -")

        # --- 2. Share Bot Instance with FastAPI ---
        # This makes the 'bot' object available in your FastAPI routes
        # via 'request.app.state.bot'.
        dashboard_app.state.bot = self
        print("Bot instance shared with FastAPI app.")

        # --- 3. Start the Uvicorn Web Server ---
        # We run the web server in a background task.
        config = uvicorn.Config(
            "dashboard.app:app",  # Points to the 'app' object in 'dashboard/app.py'
            host="0.0.0.0",
            port=8000,
            log_level="info"
        )
        self.uvicorn_server = uvicorn.Server(config)
        
        # Start the server
        self.web_server_task = asyncio.create_task(self.uvicorn_server.serve())
        print(f"Dashboard started on http://0.0.0.0:8000")
        print("- - - - - - - - - - - - - - - -")

    async def on_ready(self):
        """
        Event fired when the bot is fully connected and ready.
        """
        print(f"\nLogged in as: {self.user.name} (ID: {self.user.id})")
        print(f"Discord.py Version: {discord.__version__}")
        print("Bot is online and ready! 🚀")
        print("- - - - - - - - - - - - - - - -")

    async def close(self):
        """
        Custom cleanup function to gracefully shut down the bot and web server.
        """
        print("\nClosing down...")
        
        # First, shut down the Uvicorn server
        if self.uvicorn_server:
            self.uvicorn_server.should_exit = True
            # Wait for the server task to finish
            if self.web_server_task:
                await asyncio.wait([self.web_server_task], timeout=5.0)
        
        # Then, call the original close method to shut down the bot
        await super().close()
        print("Bot and dashboard have been closed.")


# --- Main Execution Block ---
if __name__ == "__main__":
    # Define the bot's intents
    intents = discord.Intents.default()
    intents.message_content = True  # Enable message content for text commands
    intents.members = True          # Enable member tracking if needed

    # Create an instance of our custom bot
    bot = CombinedBot(command_prefix="!", intents=intents)
    
    # The bot.run() method handles the entire application lifecycle,
    # including catching KeyboardInterrupt (Ctrl+C) and calling bot.close().
    bot.run(TOKEN)