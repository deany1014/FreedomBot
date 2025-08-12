# cogs/Governace/ui_components.py
import discord
from discord.ui import Modal, TextInput, View, Button
from datetime import datetime
from typing import Optional

from .db_manager import DBManager
from . import constants

# Constants alias (to match user's constants file)
PROPOSALS_CHANNEL_ID = constants.PROPOSALS_CHANNEL_ID
VOTING_CHANNEL_ID = constants.VOTING_CHANNEL_ID
ANNOUNCEMENTS_CHANNEL_ID = constants.ANNOUNCEMENTS_CHANNEL_ID
PAST_LEGISLATION_CHANNEL_ID = constants.PAST_LEGISLATION_CHANNEL_ID
STATUTES_AND_ACTS_CHANNEL_ID = constants.STATUTES_AND_ACTS_CHANNEL_ID
PROPOSER_ROLE_ID = constants.PROPOSER_ROLE_ID
STAFF_ROLE_ID = getattr(constants, "STAFF_ROLE_ID", None)  # optional


class ProposalForm(Modal, title='Submit a Bill Proposal'):
    title_input = TextInput(
        label='Bill Title',
        placeholder='e.g., The New Member Onboarding Act',
        min_length=5,
        max_length=100,
        required=True
    )

    text_input = TextInput(
        label='Bill Text',
        placeholder='Write the full text of your proposed law here. Be clear and concise.',
        style=discord.TextStyle.paragraph,
        min_length=20,
        max_length=2000,
        required=True
    )

    def __init__(self, bot_instance: discord.Client, db_manager: DBManager):
        super().__init__()
        self.bot = bot_instance
        self.db_manager = db_manager

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        proposals_channel = self.bot.get_channel(PROPOSALS_CHANNEL_ID)
        if not proposals_channel:
            await interaction.followup.send("Error: proposals channel not found. Contact an admin.", ephemeral=True)
            return

        # Insert into DB
        bill_id = await self.db_manager.insert_proposal(
            self.title_input.value,
            self.text_input.value,
            interaction.user.id
        )

        # Embed for proposals channel (intro / rules)
        embed = discord.Embed(
            title=f"Bill #{bill_id}: {self.title_input.value}",
            description=self.text_input.value,
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        avatar_url = interaction.user.display_avatar.url if interaction.user else None
        embed.set_author(name=f"Proposed by {interaction.user.display_name}", icon_url=avatar_url)
        embed.set_footer(text=f"Status: Awaiting debate schedule")

        try:
            proposal_message = await proposals_channel.send(embed=embed)
            await self.db_manager.update_proposal_message_ids(bill_id, proposal_message_id=proposal_message.id)
            await interaction.followup.send(
                f"Your proposal for **Bill #{bill_id}: \"{self.title_input.value}\"** has been posted in {proposals_channel.mention}. It will be scheduled for debate and voting automatically.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send("There was an error creating the proposal message. Contact an admin.", ephemeral=True)


class ProposeButtonView(View):
    def __init__(self, bot_instance: discord.Client, db_manager: DBManager):
        super().__init__(timeout=None)
        self.bot = bot_instance
        self.db_manager = db_manager

    @discord.ui.button(label="Propose New Bill", style=discord.ButtonStyle.primary, custom_id="propose_bill_button")
    async def propose_button(self, interaction: discord.Interaction, button: Button):
        # role check
        if PROPOSER_ROLE_ID:
            proposer_role = discord.utils.get(interaction.user.roles, id=PROPOSER_ROLE_ID)
            if not proposer_role:
                return await interaction.response.send_message("You do not have permission to propose bills.", ephemeral=True)

        await interaction.response.send_modal(ProposalForm(self.bot, self.db_manager))


class VotingView(View):
    def __init__(self, bot_instance: discord.Client, bill_id: int, db_manager: DBManager, end_time_dt: datetime):
        super().__init__(timeout=None)
        self.bot = bot_instance
        self.bill_id = bill_id
        self.db_manager = db_manager
        self.end_time_dt = end_time_dt

    async def _handle_vote(self, interaction: discord.Interaction, vote_type: str):
        await interaction.response.defer(ephemeral=True)

        if datetime.utcnow() >= self.end_time_dt:
            await interaction.followup.send("Voting for this bill has already ended.", ephemeral=True)
            return

        recorded = await self.db_manager.record_vote(interaction.user.id, self.bill_id, vote_type)
        if recorded:
            await interaction.followup.send(f"You have cast your vote: **{vote_type.capitalize()}**.", ephemeral=True)
        else:
            existing = await self.db_manager.get_user_vote(interaction.user.id, self.bill_id)
            if existing:
                await interaction.followup.send(f"You've already voted on this bill (your current vote: **{existing.capitalize()}**).", ephemeral=True)
            else:
                await interaction.followup.send("You have already voted on this bill.", ephemeral=True)

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success, custom_id="vote_yes_button")
    async def yes_button(self, interaction: discord.Interaction, button: Button):
        await self._handle_vote(interaction, "yes")

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger, custom_id="vote_no_button")
    async def no_button(self, interaction: discord.Interaction, button: Button):
        await self._handle_vote(interaction, "no")

    @discord.ui.button(label="Abstain", style=discord.ButtonStyle.secondary, custom_id="vote_abstain_button")
    async def abstain_button(self, interaction: discord.Interaction, button: Button):
        await self._handle_vote(interaction, "abstain")


class StatutesView(View):
    def __init__(self, bot_instance: discord.Client, base_rules_url: str, db_manager: DBManager):
        super().__init__(timeout=None)
        self.bot = bot_instance
        self.db_manager = db_manager
        # Link button - no custom_id allowed on link buttons
        self.add_item(Button(label="Base Rules (Constitution)", style=discord.ButtonStyle.link, url=base_rules_url))
        # Add a callback button for viewing approved bills
        self.add_item(Button(label="View Approved Bills", style=discord.ButtonStyle.primary, custom_id="view_approved_bills"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only intercept the approved bills button; link button handled by Discord
        if interaction.data.get("custom_id") == "view_approved_bills":
            await self.show_approved_bills(interaction)
            return False
        return True

    async def show_approved_bills(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        laws = await self.db_manager.get_all_approved_laws()
        if not laws:
            await interaction.followup.send("There are currently no approved bills.", ephemeral=True)
            return

        approved_text = ""
        for law in laws:
            enacted = law["enacted_at"].split(".")[0]
            approved_text += f"**Act #{law['law_id']} (Bill #{law['bill_id']}): {law['title']}**\n{law['text']}\n*(Enacted: {enacted})*\n\n"

        # chunking to avoid >2000 characters
        chunks = [approved_text[i:i + 1900] for i in range(0, len(approved_text), 1900)]
        for i, chunk in enumerate(chunks):
            await interaction.followup.send(f"__**Approved Bills (Part {i+1}):**__\n{chunk}", ephemeral=True)
