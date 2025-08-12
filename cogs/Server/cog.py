import discord
from discord.ext import commands
from discord import app_commands, Interaction

double_struck_map = {
    # Uppercase
    "A": "𝔸", "B": "𝔹", "C": "ℂ", "D": "𝔻", "E": "𝔼", "F": "𝔽", "G": "𝔾",
    "H": "ℍ", "I": "𝕀", "J": "𝕁", "K": "𝕂", "L": "𝕃", "M": "𝕄", "N": "ℕ",
    "O": "𝕆", "P": "ℙ", "Q": "ℚ", "R": "ℝ", "S": "𝕊", "T": "𝕋", "U": "𝕌",
    "V": "𝕍", "W": "𝕎", "X": "𝕏", "Y": "𝕐", "Z": "ℤ",

    # Lowercase
    "a": "𝕒", "b": "𝕓", "c": "𝕔", "d": "𝕕", "e": "𝕖", "f": "𝕗", "g": "𝕘",
    "h": "𝕙", "i": "𝕚", "j": "𝕛", "k": "𝕜", "l": "𝕝", "m": "𝕞", "n": "𝕟",
    "o": "𝕠", "p": "𝕡", "q": "𝕢", "r": "𝕣", "s": "𝕤", "t": "𝕥", "u": "𝕦",
    "v": "𝕧", "w": "𝕨", "x": "𝕩", "y": "𝕪", "z": "𝕫",

    # Digits
    "0": "𝟘", "1": "𝟙", "2": "𝟚", "3": "𝟛", "4": "𝟜", "5": "𝟝",
    "6": "𝟞", "7": "𝟟", "8": "𝟠", "9": "𝟡",

    # Special mathematical double-struck constants
    "π": "ℼ",  # Double-struck pi
    "γ": "ℽ",  # Euler–Mascheroni constant
    "ℇ": "ℇ",  # Capital double-struck Euler’s number
}

def to_double_struck(text: str) -> str:
    """Convert normal text to mathematical double-struck style with fake spaces."""
    fake_space = "᲼"  # Unicode 'MEDIUM MATHEMATICAL SPACE' U+205F
    return "".join(
        fake_space if c == " " else double_struck_map.get(c, c)
        for c in text
    )

class Server(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    server_group = app_commands.Group(name="server", description="Server management commands")
    channel_group = app_commands.Group(name="channel", description="Channel management commands", parent=server_group)
    category_group = app_commands.Group(name="category", description="Category management commands", parent=server_group)

    @channel_group.command(name="rename", description="Rename a channel")
    @commands.has_permissions(administrator=True)
    async def fancy_rename(self, interaction: Interaction, new_name: str):
        styled_name = to_double_struck(new_name)
        await interaction.channel.edit(name=styled_name)
        await interaction.response.send_message(
            f"Channel renamed to `{styled_name}`", ephemeral=True
        )

    @category_group.command(name="rename", description="Rename a category")
    @commands.has_permissions(administrator=True)
    async def fancy_rename(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        new_name: str
    ):
        styled_name = to_double_struck(new_name)
        await category.edit(name=styled_name)
        await interaction.response.send_message(
            f"Category renamed to `{styled_name}`", ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Server(bot))
