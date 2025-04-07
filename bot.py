import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import asyncio

TOKEN = 'BOT_TOKEN_HERE'

intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True
# intents.scheduled_events = True  # Enable scheduled events intent

bot = commands.Bot(command_prefix='!', intents=intents)
# bot.intents.scheduled_events = True

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.command()
async def create_event(ctx, channel: discord.VoiceChannel, name, description, start_time_str, duration_minutes: int):
    """
    Creates a Discord event in the specified channel.

    Usage:      !create_event #channel "Event Name" "Event Description" <t:1743987610:F> duration_minutes
    Example:    !create_event #testing "Test Event" "" <t:1743987610:F> 30
     !create_event #General "Test Event" "" <t:1743987540:F> 30
    """
    try:
        start_time = parse_discord_timestamp(start_time_str)
        if start_time is None:
            try:
                start_time = datetime.fromisoformat(start_time_str)
            except ValueError:
                await ctx.send("Invalid date/time format. Please use <t:unix_timestamp:F> or ISO format (YYYY-MM-DD HH:MM).")
                return
        end_time = start_time + timedelta(minutes=duration_minutes)

        await channel.guild.create_scheduled_event(
                name=name,
                description=description,
                start_time=start_time,
                end_time=end_time,
                channel=channel,
                entity_type=discord.EntityType.voice,
                privacy_level=discord.PrivacyLevel.guild_only,
            )

        await ctx.send(f'Event "{name}" created in {channel.mention}!')

    except Exception as e:
        await ctx.send(f"An error occurred: {e}")

def parse_discord_timestamp(timestamp_str):
    """Parses a Discord timestamp string like <t:1743987610:F>."""
    try:
        if timestamp_str.startswith('<t:') and timestamp_str.endswith('>'):
            parts = timestamp_str[3:-1].split(':')
            if len(parts) >= 1:
                unix_timestamp = int(parts[0])
                return datetime.fromtimestamp(unix_timestamp, tz=timezone.utc) #important to set timezone to UTC.
        return None
    except (ValueError, IndexError):
        return None

@tasks.loop(minutes=1)
async def event_reminder():
    print('task loop')
    now = datetime.now(timezone.utc)
    for guild in bot.guilds:
        remind_channel = discord.utils.get(guild.text_channels, name='testing')
        if remind_channel:
            events = await guild.fetch_scheduled_events()
            for event in events:
                interested_users = await event.fetch_users()
                thirty_min_before = event.start_time - timedelta(minutes=30)
                five_min_before = event.start_time - timedelta(minutes=5)

                if thirty_min_before <= now < thirty_min_before + timedelta(minutes=1):
                    mentions = " ".join(user.mention for user in interested_users)
                    message = f"Reminder! {event.name} is starting in 30 minutes! {event.url} \n{mentions}"
                    await remind_channel.send(message)
                elif five_min_before <= now < five_min_before + timedelta(minutes=1):
                    mentions = " ".join(user.mention for user in interested_users)
                    message = f"Reminder! {event.name} is starting in 5 minutes! {event.url} \n{mentions}"
                    await remind_channel.send(message)




async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
