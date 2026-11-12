"""Discord Secret Santa bot with interactive, per-draw setup."""

import asyncio
import logging
import os
import random
from math import gcd

import discord
from discord.ext import commands
from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO)
load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.all()
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)


class DrawParticipant:
    """A Discord user with the display name chosen for this draw."""

    def __init__(self, user, display_name=None):
        self.user = user
        self.id = user.id
        self.display_name = display_name or user.display_name
        self.bot = user.bot

    async def send(self, message):
        await self.user.send(message)


def _rotate_list(items, step):
    """Return a copy rotated right by step positions."""
    if not items:
        return []
    return [items[(index - step) % len(items)] for index in range(len(items))]


def _make_assignments(participants, exclusions=None, single_cycle=False, max_attempts=2000):
    """Create a valid Secret Santa permutation or return None."""
    participants = list(participants)
    if len(participants) < 2:
        raise ValueError("Need at least 2 participants")

    exclusions = exclusions or set()
    random.shuffle(participants)

    def valid(receivers):
        return all(
            giver.id != receiver.id
            and frozenset((giver.id, receiver.id)) not in exclusions
            for giver, receiver in zip(participants, receivers)
        )

    if single_cycle:
        steps = [step for step in range(1, len(participants)) if gcd(step, len(participants)) == 1]
        random.shuffle(steps)
        for step in steps:
            receivers = _rotate_list(participants, step)
            if valid(receivers):
                return list(zip(participants, receivers))
        return None

    receivers = participants.copy()
    for _ in range(max_attempts):
        random.shuffle(receivers)
        if valid(receivers):
            return list(zip(participants, receivers))
    return None


async def _send_assignments(interaction, assignments, role_name):
    """DM every participant and report any delivery failures."""
    failed = []
    for giver, receiver in assignments:
        message = (
            f"God jul {giver.display_name}! Jag har något att säga till dig — håll det hemligt:\n"
            f"Du har blivit tilldelad att ge en julklapp till {receiver.display_name}."
        )
        try:
            await giver.send(message)
        except discord.HTTPException:
            logging.exception("Failed to send DM to user %s", giver.id)
            failed.append(giver)
        await asyncio.sleep(0.5)

    if failed:
        names = ", ".join(user.display_name for user in failed)
        await interaction.followup.send(
            f"Sent assignments to {len(assignments) - len(failed)} participants; "
            f"failed to DM {len(failed)}: {names}."
        )
    else:
        await interaction.followup.send(
            f"Secret Santa assignments sent by DM to {len(assignments)} participants "
            f"(role: {role_name})."
        )


class ExternalUserModal(discord.ui.Modal, title="Add external participant"):
    user_id = discord.ui.TextInput(
        label="Discord user ID",
        placeholder="Enter the numeric Discord user ID",
        min_length=1,
        max_length=20,
    )
    nickname = discord.ui.TextInput(
        label="Nickname",
        placeholder="Name to use in the draw and DM messages",
        min_length=1,
        max_length=100,
    )

    def __init__(self, setup_view):
        super().__init__()
        self.setup_view = setup_view

    async def on_submit(self, interaction):
        try:
            user_id = int(self.user_id.value.strip())
            user = await bot.fetch_user(user_id)
        except (ValueError, discord.NotFound):
            await interaction.response.send_message(
                "That is not a valid, resolvable Discord user ID.", ephemeral=True
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "Discord could not resolve that user right now.", ephemeral=True
            )
            return

        if user.bot:
            await interaction.response.send_message(
                "Bot accounts cannot participate.", ephemeral=True
            )
            return
        if any(participant.id == user.id for participant in self.setup_view.external_users):
            await interaction.response.send_message(
                "That user is already included.", ephemeral=True
            )
            return

        participant = DrawParticipant(user, self.nickname.value.strip())
        self.setup_view.external_users.append(participant)
        await interaction.response.send_message(
            f"Added external participant: {participant.display_name}.", ephemeral=True
        )
        await self.setup_view.refresh(interaction)


class ExclusionPairView(discord.ui.View):
    def __init__(self, setup_view):
        super().__init__(timeout=300)
        self.setup_view = setup_view
        participants = setup_view.all_participants
        self.user_select = discord.ui.Select(
            placeholder="Select two participants",
            min_values=2,
            max_values=2,
            options=[
                discord.SelectOption(
                    label=participant.display_name[:100],
                    value=str(participant.id),
                )
                for participant in participants[:25]
            ],
        )
        self.user_select.callback = self.pair_selected
        self.add_item(self.user_select)

    async def pair_selected(self, interaction):
        first, second = (int(value) for value in self.user_select.values)
        pair = frozenset((first, second))
        if pair in self.setup_view.exclusions:
            await interaction.response.send_message(
                "That exclusion pair already exists.", ephemeral=True
            )
            return

        self.setup_view.exclusions.add(pair)
        await interaction.response.edit_message(
            content="Exclusion pair added.", view=None
        )
        await self.setup_view.refresh(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(
            content="Exclusion pair selection cancelled.", view=None
        )


class DrawSetupView(discord.ui.View):
    def __init__(self, owner_id, role, participants, single_cycle=False):
        super().__init__(timeout=600)
        self.owner_id = owner_id
        self.role = role
        self.participants = list(participants)
        self.external_users = []
        self.exclusions = set()
        self.single_cycle = single_cycle
        self.message = None

    @property
    def all_participants(self):
        return self.participants + self.external_users

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the person who started this setup can use it.", ephemeral=True
            )
            return False
        return True

    def summary(self):
        external = ", ".join(user.display_name for user in self.external_users) or "none"
        pairs = ", ".join(
            f"{first} ↔ {second}" for first, second in self.exclusions
        ) or "none"
        mode = "single circle" if self.single_cycle else "normal draw"
        return (
            f"**Role:** {self.role.name}\n"
            f"**Participants:** {len(self.participants) + len(self.external_users)}\n"
            f"**External users:** {external}\n"
            f"**Exclusions:** {pairs}\n"
            f"**Mode:** {mode}\n\n"
            "Add external users and exclusions, then start the draw."
        )

    async def refresh(self, interaction):
        if self.message:
            await self.message.edit(content=self.summary(), view=self)

    @discord.ui.button(label="Add external user", style=discord.ButtonStyle.primary)
    async def add_external(self, interaction, button):
        await interaction.response.send_modal(ExternalUserModal(self))

    @discord.ui.button(label="Add exclusion pair", style=discord.ButtonStyle.secondary)
    async def add_exclusion(self, interaction, button):
        if len(self.all_participants) > 25:
            await interaction.response.send_message(
                "Discord can only show 25 participants in this selector. "
                "Reduce the role size before adding exclusions.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            "Select the two participants who must not be assigned to each other.",
            view=ExclusionPairView(self),
            ephemeral=True,
        )

    @discord.ui.button(label="Start draw", style=discord.ButtonStyle.success)
    async def start_draw(self, interaction, button):
        await interaction.response.defer()
        participants = self.participants + self.external_users
        assignments = _make_assignments(
            participants, exclusions=self.exclusions, single_cycle=self.single_cycle
        )
        if assignments is None:
            await interaction.followup.send(
                "No valid assignment exists with these participants and exclusions."
            )
            return
        self.stop()
        await interaction.followup.send("The draw is starting; assignments will be sent privately.")
        await _send_assignments(interaction, assignments, self.role.name)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction, button):
        self.stop()
        await interaction.response.edit_message(
            content="Secret Santa setup cancelled.", view=None
        )


class RoleSelectionView(discord.ui.View):
    def __init__(self, owner_id, single_cycle=False):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.single_cycle = single_cycle
        self.role_select = discord.ui.RoleSelect(
            placeholder="Choose the participant role",
            min_values=1,
            max_values=1,
        )
        self.role_select.callback = self.role_selected
        self.add_item(self.role_select)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the person who started this setup can use it.", ephemeral=True
            )
            return False
        return True

    async def role_selected(self, interaction):
        role = self.role_select.values[0]
        if role.is_default() or role.managed:
            await interaction.response.send_message(
                "Choose a normal user role, not @everyone or a managed role.",
                ephemeral=True,
            )
            return

        participants = [member for member in role.members if not member.bot]
        if len(participants) < 2:
            await interaction.response.send_message(
                "That role must contain at least two non-bot members.",
                ephemeral=True,
            )
            return

        setup = DrawSetupView(
            interaction.user.id, role, participants, single_cycle=self.single_cycle
        )
        await interaction.response.edit_message(content=setup.summary(), view=setup)
        setup.message = await interaction.original_response()


async def _start_setup(interaction, single_cycle=False):
    view = RoleSelectionView(interaction.user.id, single_cycle=single_cycle)
    mode = "single-circle" if single_cycle else "normal"
    await interaction.response.send_message(
        f"Choose a participant role to configure a {mode} Secret Santa draw.",
        view=view,
        ephemeral=True,
    )


@bot.event
async def setup_hook():
    await bot.tree.sync()


@bot.event
async def on_ready():
    logging.info("Connected to Discord as %s", bot.user)


@bot.tree.command(name="secretsanta", description="Configure and start a Secret Santa draw")
@discord.app_commands.guild_only()
async def secretsanta(interaction: discord.Interaction):
    await _start_setup(interaction)


@bot.tree.command(name="circle", description="Configure and start a single-circle draw")
@discord.app_commands.guild_only()
async def circle(interaction: discord.Interaction):
    await _start_setup(interaction, single_cycle=True)


if __name__ == "__main__" and DISCORD_BOT_TOKEN:
    bot.run(DISCORD_BOT_TOKEN)
