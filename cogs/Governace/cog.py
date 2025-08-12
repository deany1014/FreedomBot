# cogs/Governace/cog.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import traceback

from .db_manager import DBManager
from .ui_components import ProposeButtonView, StatutesView, VotingView, ProposalForm
from . import constants

DB_PATH = constants.DB_PATH

VOTE_DELAY_HOURS = 48
VOTE_DURATION_DAYS = 4  # voting ends 4 days after start

class Governance(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = DBManager(DB_PATH)
        self.scheduled_tasks = {}  # bill_id -> asyncio.Task
        self.base_rules_url = constants.CONSTITUTION_URL if hasattr(constants, "CONSTITUTION_URL") else "https://example.com/constitution"

        # We'll initialize DB on cog load (on_ready)
        # Register persistent views when ready

    governance_group = app_commands.Group(name="governance", description="Governance commands")
    staff_group = app_commands.Group(name="staff", description="Staff commands", parent=governance_group)
    deploy_group = app_commands.Group(name="deploy", description="Deployment commands", parent=governance_group)
    vote_group = app_commands.Group(name="vote", description="Voting commands", parent=governance_group)


    @commands.Cog.listener()
    async def on_ready(self):
        # Ensure DB initialized
        await self.db.initialize()
        # Register the statutes view (persistent)
        try:
            statutes_view = StatutesView(self.bot, self.base_rules_url, self.db)
            self.bot.add_view(statutes_view)  # persistent view registration
        except Exception:
            # Views may not be persistent across restarts without message references; safe ignore
            pass

        # Recover any pending scheduled tasks from DB
        pending = await self.db.get_all_pending_votes()
        for prop in pending:
            bill_id = prop["bill_id"]
            # If vote_start exists and is in future, schedule vote start
            try:
                if prop.get("vote_start"):
                    vote_start = datetime.fromisoformat(prop["vote_start"])
                    if datetime.utcnow() < vote_start:
                        # schedule start
                        self._schedule_vote_start(bill_id, vote_start)
                    elif prop["status"] == "debating" and prop.get("vote_end"):
                        # If start passed but vote_end exists or voting in progress, schedule end
                        vote_end = datetime.fromisoformat(prop["vote_end"]) if prop.get("vote_end") else None
                        if vote_end and datetime.utcnow() < vote_end:
                            self._schedule_vote_end(bill_id, vote_end)
                elif prop["status"] == "voting" and prop.get("vote_end"):
                    vote_end = datetime.fromisoformat(prop["vote_end"])
                    if datetime.utcnow() < vote_end:
                        self._schedule_vote_end(bill_id, vote_end)
            except Exception:
                traceback.print_exc()

    # ---------- Helpers to schedule tasks ----------
    def _schedule_vote_start(self, bill_id: int, vote_start_dt: datetime):
        delay = max((vote_start_dt - datetime.utcnow()).total_seconds(), 0)
        task = self.bot.loop.create_task(self._delayed_start(bill_id, delay))
        self.scheduled_tasks[f"start-{bill_id}"] = task

    def _schedule_vote_end(self, bill_id: int, vote_end_dt: datetime):
        delay = max((vote_end_dt - datetime.utcnow()).total_seconds(), 0)
        task = self.bot.loop.create_task(self._delayed_end(bill_id, delay))
        self.scheduled_tasks[f"end-{bill_id}"] = task

    async def _delayed_start(self, bill_id: int, delay_seconds: float):
        await asyncio.sleep(delay_seconds)
        try:
            await self._post_vote_message(bill_id)
        except Exception:
            traceback.print_exc()

    async def _delayed_end(self, bill_id: int, delay_seconds: float):
        await asyncio.sleep(delay_seconds)
        try:
            await self._tally_votes_and_archive(bill_id)
        except Exception:
            traceback.print_exc()

    # ---------- Utility to send the proposal rules embed + propose button (to PROPOSALS channel) ----------
    @deploy_group.command(name="proposal")
    @commands.has_permissions(manage_guild=True)
    async def deploy_proposal_embed(self, ctx: commands.Context):
        """Deploy the Bill Proposal embed + button into the proposals channel (admin only)."""
        proposals_ch = self.bot.get_channel(constants.PROPOSALS_CHANNEL_ID)
        if not proposals_ch:
            await ctx.reply("Proposals channel not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Bill Proposals — Rules & How to Submit",
            description=(
                "Use the button below to propose a new bill. Your proposal should be clear, concise, and follow the legislative guide."
            ),
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Rules", value="Be civil. Stick to the format. One proposal per author until it's resolved.", inline=False)
        embed.set_footer(text="Proposals will be scheduled for debate, then voting. Voting starts automatically 48 hours after debate and lasts 4 days.")

        view = ProposeButtonView(self.bot, self.db)
        msg = await proposals_ch.send(embed=embed, view=view)
        # Save proposal embed message id? Not strictly necessary
        await ctx.reply("Deployed proposal embed with button.", ephemeral=True)

    # ---------- Deploy Statutes embed ----------
    @deploy_group.command(name="statutes")
    @commands.has_permissions(manage_guild=True)
    async def deploy_statutes_embed(self, ctx: commands.Context):
        """Deploy the Statutes & Acts embed with base rules link and Approved Bills button."""
        statutes_ch = self.bot.get_channel(constants.STATUTES_AND_ACTS_CHANNEL_ID)
        if not statutes_ch:
            await ctx.reply("Statutes & Acts channel not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Statutes & Acts",
            description="Official statutes and approved acts. Use the buttons below to view the Constitution or Approved Bills.",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        view = StatutesView(self.bot, self.base_rules_url, self.db)
        await statutes_ch.send(embed=embed, view=view)
        await ctx.reply("Deployed Statutes & Acts embed.", ephemeral=True)

    # ---------- Public commands ----------
    @vote_group.command(name="start")
    @commands.has_permissions(manage_guild=True)
    async def force_vote_start(self, ctx: commands.Context, bill_id: int):
        """Force the voting to start immediately for a bill."""
        await ctx.defer()
        prop = await self.db.get_proposal_by_id(bill_id)
        if not prop:
            await ctx.reply("Bill not found.", ephemeral=True)
            return
        if prop["status"] in ("voting", "passed", "vetoed", "archived"):
            await ctx.reply(f"Bill is already {prop['status']}.", ephemeral=True)
            return
        # set vote times: start now, end after VOTE_DURATION_DAYS
        vote_start = datetime.utcnow()
        vote_end = vote_start + timedelta(days=VOTE_DURATION_DAYS)
        await self.db.set_vote_times(bill_id, vote_start, vote_end)
        # schedule end
        self._schedule_vote_end(bill_id, vote_end)
        await self._post_vote_message(bill_id)
        await ctx.reply(f"Voting started for bill #{bill_id}. It will end <t:{int(vote_end.timestamp())}:F>.", ephemeral=True)

    @vote_group.command(name="end")
    @commands.has_permissions(manage_guild=True)
    async def force_vote_end(self, ctx: commands.Context, bill_id: int):
        """End voting immediately and tally."""
        await ctx.defer()
        prop = await self.db.get_proposal_by_id(bill_id)
        if not prop:
            await ctx.reply("Bill not found.", ephemeral=True)
            return
        await self._tally_votes_and_archive(bill_id)
        await ctx.reply(f"Voting forcibly ended and tallied for bill #{bill_id}.", ephemeral=True)

    @staff_group.command(name="veto")
    @commands.has_permissions(manage_guild=True)
    async def veto(self, ctx: commands.Context, bill_id: int, *, reason: Optional[str] = None):
        """Veto a bill (staff only). Can be used even after passage."""
        await ctx.defer()
        ok = await self.db.veto_bill(bill_id, reason)
        if not ok:
            await ctx.reply("Bill not found.", ephemeral=True)
            return
        prop = await self.db.get_proposal_by_id(bill_id)
        # post to past legislation channel with veto note
        past_ch = self.bot.get_channel(constants.PAST_LEGISLATION_CHANNEL_ID)
        if past_ch:
            embed = discord.Embed(title=f"Bill #{bill_id}: {prop['title']}", description=prop['text'], color=discord.Color.dark_red(), timestamp=datetime.utcnow())
            embed.set_footer(text="Status: VETOED")
            await past_ch.send(embed=embed)
        await ctx.reply(f"Bill #{bill_id} has been vetoed.", ephemeral=True)

    @staff_group.command(name="remove_bill")
    @commands.has_permissions(manage_guild=True)
    async def remove_bill(self, ctx: commands.Context, bill_id: int):
        """Remove a bill from DB (irreversible)."""
        await ctx.defer()
        await self.db.remove_bill(bill_id)
        await ctx.reply(f"Bill #{bill_id} removed from database.", ephemeral=True)

    # ---------- Internal flow ----------
    async def schedule_debate_and_voting(self, bill_id: int):
        """Set vote start and end (48h and 96h from created_at) in DB and schedule tasks."""
        prop = await self.db.get_proposal_by_id(bill_id)
        if not prop:
            return

        created = datetime.fromisoformat(prop["created_at"])
        vote_start = created + timedelta(hours=VOTE_DELAY_HOURS)
        vote_end = vote_start + timedelta(days=VOTE_DURATION_DAYS)
        await self.db.set_vote_times(bill_id, vote_start, vote_end)
        await self.db.set_status(bill_id, "debating")
        # schedule start and end
        self._schedule_vote_start(bill_id, vote_start)
        self._schedule_vote_end(bill_id, vote_end)

    async def post_to_debate_channel(self, bill_id: int):
        prop = await self.db.get_proposal_by_id(bill_id)
        if not prop:
            return
        debate_ch = self.bot.get_channel(constants.PAST_LEGISLATION_CHANNEL_ID)  # WAIT - we need debate channel id
        # Use the correct debate channel constant (from user's earlier code, it was VOTING_CHANNEL etc.)
        # Let's attempt to get a proper constant name
        try:
            debate_ch = self.bot.get_channel(constants.PAST_LEGISLATION_CHANNEL_ID)  # Fallback
        except Exception:
            debate_ch = None

        # better to use a dedicated debate channel id if set:
        debate_ch = self.bot.get_channel(constants.PAST_LEGISLATION_CHANNEL_ID) if hasattr(constants, "PAST_LEGISLATION_CHANNEL_ID") else None
        # If constants contain a DEBATE channel id, prefer it:
        if hasattr(constants, "DEBATE_CHANNEL_ID"):
            debate_ch = self.bot.get_channel(constants.DEBATE_CHANNEL_ID)
        if not debate_ch:
            # try PROPOSALS channel as fallback
            debate_ch = self.bot.get_channel(constants.PROPOSALS_CHANNEL_ID)

        if not debate_ch:
            print("Debate channel not found; cannot post debate message.")
            return

        # compute timestamps
        created = datetime.fromisoformat(prop["created_at"])
        vote_start = created + timedelta(hours=VOTE_DELAY_HOURS)
        vote_end = vote_start + timedelta(days=VOTE_DURATION_DAYS)

        # embed for debate
        embed = discord.Embed(
            title=f"Bill #{bill_id}: {prop['title']}",
            description=prop['text'],
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Voting Starts", value=f"<t:{int(vote_start.timestamp())}:F>\n<t:{int(vote_start.timestamp())}:R>", inline=True)
        embed.add_field(name="Voting Ends", value=f"<t:{int(vote_end.timestamp())}:F>\n<t:{int(vote_end.timestamp())}:R>", inline=True)
        embed.set_footer(text="Discuss in the thread below — voting will open automatically.")

        debate_message = await debate_ch.send(embed=embed)
        # create thread
        try:
            thread = await debate_message.create_thread(name=f"Debate: Bill #{bill_id}", auto_archive_duration=1440)
        except Exception:
            thread = None

        await self.db.update_proposal_message_ids(bill_id, debate_message_id=debate_message.id)
        # schedule voting times based on created timestamp stored in DB
        await self.schedule_debate_and_voting(bill_id)

    async def _post_vote_message(self, bill_id: int):
        prop = await self.db.get_proposal_by_id(bill_id)
        if not prop:
            return
        voting_ch = self.bot.get_channel(constants.VOTING_CHANNEL_ID)
        if not voting_ch:
            print("Voting channel not found.")
            return

        # vote_start and vote_end must exist in DB
        if not prop.get("vote_start") or not prop.get("vote_end"):
            # set now if missing
            vote_start = datetime.utcnow()
            vote_end = vote_start + timedelta(days=VOTE_DURATION_DAYS)
            await self.db.set_vote_times(bill_id, vote_start, vote_end)
        else:
            vote_start = datetime.fromisoformat(prop["vote_start"])
            vote_end = datetime.fromisoformat(prop["vote_end"])

        embed = discord.Embed(
            title=f"Voting — Bill #{bill_id}: {prop['title']}",
            description=prop['text'],
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Voting Opened", value=f"<t:{int(vote_start.timestamp())}:F>", inline=True)
        embed.add_field(name="Voting Closes", value=f"<t:{int(vote_end.timestamp())}:F>", inline=True)
        embed.set_footer(text="Cast your vote by clicking a button below.")

        view = VotingView(self.bot, bill_id, self.db, vote_end)
        vote_message = await voting_ch.send(embed=embed, view=view)
        await self.db.update_proposal_message_ids(bill_id, vote_message_id=vote_message.id)
        await self.db.set_status(bill_id, "voting")

    async def _tally_votes_and_archive(self, bill_id: int):
        prop = await self.db.get_proposal_by_id(bill_id)
        if not prop:
            return

        counts = await self.db.get_vote_counts(bill_id)
        yes = counts["yes"]
        no = counts["no"]
        abstain = counts["abstain"]

        # Determine outcome - currently simple majority yes > no
        passed = yes > no

        # Update status
        await self.db.set_status(bill_id, "passed" if passed else "failed")

        # If passed, add to laws
        law_id = None
        if passed:
            law_id = await self.db.add_law_from_bill(bill_id)

        # Post summary to past legislation
        past_ch = self.bot.get_channel(constants.PAST_LEGISLATION_CHANNEL_ID)
        embed = discord.Embed(
            title=f"Bill #{bill_id}: {prop['title']}",
            description=prop['text'],
            color=discord.Color.green() if passed else discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Result", value=f"Yes: {yes} | No: {no} | Abstain: {abstain}", inline=False)
        embed.set_footer(text=f"Status: {'PASSED' if passed else 'FAILED'}")

        if past_ch:
            await past_ch.send(embed=embed)

        # If passed, update the Statutes & Acts (laws are already in 'laws' table)
        if passed:
            # Try to edit a central Approved Bills message / or leave as is
            # For simplicity, we rely on StatutesView to fetch from DB when users click "View Approved Bills"
            pass

    # ---------- Event: when a new proposal message is posted to proposals channel ----------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Only act on messages in the proposals channel that were sent by the bot (proposal embeds) OR detect new proposals from users?
        # Instead, we rely on ProposalForm to insert into DB and post to proposals. So we watch bot messages in proposals to trigger debate.
        if message.author != self.bot.user:
            return
        if message.channel.id != constants.PROPOSALS_CHANNEL_ID:
            return
        # try to detect embed with "Bill #"
        if not message.embeds:
            return
        embed = message.embeds[0]
        if not embed.title or not embed.title.startswith("Bill #"):
            return

        # parse bill id from embed title
        try:
            bill_id_str = embed.title.split(":")[0].split("#")[1]
            bill_id = int(bill_id_str)
        except Exception:
            return

        # If DB has no debate_message_id or status 'awaiting', post to debate channel and schedule
        prop = await self.db.get_proposal_by_id(bill_id)
        if not prop:
            return
        if prop["debate_message_id"] or prop["status"] != "awaiting":
            return

        # Post to debate channel and schedule voting
        await self.post_to_debate_channel(bill_id)


# Cog setup
async def setup(bot):
    await bot.add_cog(Governance(bot))
