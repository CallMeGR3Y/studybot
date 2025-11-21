import re
import os
from datetime import datetime, timedelta

import discord
from discord.ext import commands
import dateparser

# ==============================
# CONFIG
# ==============================

TOKEN = os.getenv("DISCORD_TOKEN")

# Use your actual channel IDs here
GENERAL_CHANNEL_ID = 1437668461471072328  # #general-discussion
STUDY_CHANNEL_ID = 1441197907737837590    # #study-group-planning

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==============================
# SMARTER MESSAGE DETECTION
# ==============================

INTENT_KEYWORDS = [
    "study",
    "studying",
    "study together",
    "study group",
    "review",
    "go over",
    "look over",
    "practice",
    "run through",
    "go through",
    "session",
    "meet",
    "meet up",
    "link up",
    "group up",
]

SCHEDULE_KEYWORDS = [
    "today",
    "tomorrow",
    "tonight",
    "later",
    "this weekend",
    "weekend",
    "after class",
    "after lecture",
    "after lab",
    "this afternoon",
    "this evening",
    "morning",
    "afternoon",
    "evening",
    "night",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

# Matches times like: 4pm, 4 pm, 4:00, 16:00, 7:30pm, etc
TIME_PATTERN = r"\b(\d{1,2}(:\d{2})?\s?(am|pm)|\d{1,2}:\d{2})\b"


def parse_when(text: str):
    """
    Try to pull a date and time out of the message text.

    Examples:
      "we should study together tomorrow at 4 PM"
      "let's review saturday at 6"
      "we should study together at 4 PM"

    Returns:
      datetime or None
    """
    # First, let dateparser try on the full text
    parsed = dateparser.parse(
        text,
        settings={
            "PREFER_DATES_FROM": "future",
            "TIMEZONE": "America/New_York",
            "RETURN_AS_TIMEZONE_AWARE": False,  # keep it simple
        },
    )
    if parsed is not None:
        return parsed

    # If that failed but there is a time, assume "next occurrence of that time"
    lowered = text.lower()
    m = re.search(TIME_PATTERN, lowered)
    if not m:
        return None

    time_part = m.group(0)
    time_only = dateparser.parse(time_part)
    if time_only is None:
        return None

    now = datetime.now()
    dt = now.replace(
        hour=time_only.hour,
        minute=time_only.minute,
        second=0,
        microsecond=0,
    )
    # If that time already passed today, move to tomorrow
    if dt <= now:
        dt = dt + timedelta(days=1)

    return dt


def looks_like_study_session(text: str) -> bool:
    """
    Smart detection:
    - Must have at least one intent keyword (study, review, meet up, etc)
    - Must also have:
        - a time (4pm, 18:00, 7:30pm, etc) OR
        - a schedule keyword (tomorrow, saturday, after class, etc)
    """
    lowered = text.lower()

    has_intent = any(kw in lowered for kw in INTENT_KEYWORDS)
    if not has_intent:
        return False

    has_time = re.search(TIME_PATTERN, lowered) is not None
    has_schedule_word = any(kw in lowered for kw in SCHEDULE_KEYWORDS)

    return has_time or has_schedule_word


# ==============================
# CONFIRMATION VIEW (YES / NO)
# ==============================

class ConfirmStudyView(discord.ui.View):
    def __init__(self, original_message: discord.Message):
        super().__init__(timeout=60)
        self.original_message = original_message

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only the original author can confirm
        if interaction.user.id != self.original_message.author.id:
            await interaction.response.send_message(
                "Only the person who wrote the message can confirm this.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Got it. Posting this in #study-group-planning.",
            ephemeral=True
        )

        study_channel = interaction.client.get_channel(STUDY_CHANNEL_ID)
        if study_channel is None:
            await interaction.followup.send(
                "I could not find the study group channel.",
                ephemeral=True
            )
            return

        author = self.original_message.author
        content = self.original_message.content

        when_dt = parse_when(content)
        when_line = ""
        if when_dt is not None:
            # Example: Friday, November 21, 2025 at 04:00 PM (ET)
            when_str = when_dt.strftime("%A, %B %d, %Y at %I:%M %p")
            when_line = f"**When:** {when_str} (ET)\n"

        session_message = await study_channel.send(
            f"📚 **Proposed Study Session**\n"
            f"**From:** {author.mention}\n"
            f"**Details (original):** {content}\n"
            f"{when_line}\n"
            f"React below to RSVP:\n"
            f"✅ Going   ❓ Maybe   ❌ Not going"
        )

        await session_message.add_reaction("✅")
        await session_message.add_reaction("❓")
        await session_message.add_reaction("❌")

        # Disable buttons after use
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only the original author can cancel
        if interaction.user.id != self.original_message.author.id:
            await interaction.response.send_message(
                "Only the person who wrote the message can respond.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "No problem. I will ignore that message.",
            ephemeral=True
        )

        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.message.edit(view=self)


# ==============================
# BOT EVENTS
# ==============================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Bot is ready.")


@bot.event
async def on_message(message: discord.Message):
    # Keep commands working
    await bot.process_commands(message)

    # Ignore other bots
    if message.author.bot:
        return

    # Only watch the general discussion channel
    if message.channel.id != GENERAL_CHANNEL_ID:
        return

    # Detect study session intent
    if looks_like_study_session(message.content):
        view = ConfirmStudyView(message)
        await message.reply(
            "I noticed you might be trying to set up a study session.\n"
            "Do you want me to post this in #study-group-planning?",
            view=view
        )


if __name__ == "__main__":
    bot.run(TOKEN)
