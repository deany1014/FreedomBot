from discord.ext import commands
from discord import app_commands, Interaction
import asyncio

class Developer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    dev_group = app_commands.Group(name="dev", description="Developer commands")
    apollo_group = app_commands.Group(name="apollo", description="Apollo subcommands", parent=dev_group)

    @dev_group.command(name="sync", description="Sync slash commands globally")
    @commands.is_owner()
    async def sync(self, interaction: Interaction):
        synced = await self.bot.tree.sync()
        Load_message = f"Synced {len(synced)} commands globally."
        await interaction.response.send_message(Load_message)
        print(Load_message)

    @dev_group.command(name="stop", description="Stop the bot (owner only)")
    @commands.is_owner()
    async def stop(self, interaction: Interaction):
        await interaction.response.send_message("Shutting down... Bye! 👋")
        print("\n\nBot is shutting down by owner command.\n")
        await self.bot.close()

    @apollo_group.command(name="wip", description="Apollo WIP command")
    @commands.is_owner()
    async def apollo_wip(self, interaction: Interaction):
        await interaction.response.send_message("Apollo feature is a work in progress 🚧")

async def setup(bot):
    await bot.add_cog(Developer(bot))
