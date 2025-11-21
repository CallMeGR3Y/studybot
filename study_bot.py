import re
import discord
from discord.ext import commands
import dateparser
from datetime import datetime

# ==============================
# CONFIG
# ==============================

import os
TOKEN = os.getenv("DISCORD_TOKEN")

GENERAL_CHANNEL_ID = 1437668461471072328  # replace with #general-discussion ID
STUDY_CHANNEL_ID = 1441197907737837590    # replace with #study-group-planning ID

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

TIME_PATTERN = r"\b(\d{1,2}(:\d{2})?\s?(am|pm)|\d{1,2}:\d{2})\b"

def parse_when(text: str):
    """
    Try to pull a date and time out of the message text.
    Example inputs:
      "we should study tomorrow at 4 PM"
      "let's review Saturday at 6"
    Returns a datetime or None.
    """
    parsed = dateparser.parse(
        text,
        settings={
            "PREFER_DATES_FROM": "future",
            "TIMEZONE": "America/New_York",
            "RETURN_AS_TIMEZONE_AWARE": True,
        },
    )
    return parsed

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
            await interaction.followup.send("I could not find the study group channel.", ephemeral=True)
            return

        author = self.original_message.author
        content = self.original_message.content

        when_dt = parse_when(content)
        when_line = ""
        if when_dt is not None:
         # Format like: Friday, November 21, 2025 at 4:00 PM (ET)
        when_str = when_dt.strftime("%A, %B %d, %Y at %-I:%M %p")
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

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_message.author.id:
            await interaction.response.send_message(
                "Only the person who wrote the message can respond.",
                ephemeral=True
            )
            return

        await interaction.response.send_message("No problem. I will ignore that message.", ephemeral=True)

        for child in self.children:
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
    await bot.process_commands(message)

    if message.author.bot:
        return

    if message.channel.id != GENERAL_CHANNEL_ID:
        return

    if looks_like_study_session(message.content):
        view = ConfirmStudyView(message)
        await message.reply(
            "I noticed you might be trying to set up a study session.\n"
            "Do you want me to post this in #study-group-planning?",
            view=view
        )


if __name__ == "__main__":
    bot.run(TOKEN)
