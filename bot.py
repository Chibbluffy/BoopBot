import discord, asyncio, os, json
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone

TOKEN = '<BOT_TOKEN>'
NOTIFY_CHANNEL = 'testing'

intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

CHEST_INFO_CHANNEL_ID = <CHANNEL_ID>
CHEST_INFO_MESSAGE_ID = None # OR <MESSAGE_ID>

GEAR_DATA_FILE = 'user_gear.json'

# Store the next chest event times for each server
next_chest_events = {
    "Arsha(PVP)": None,  
    "ArshaAnon": None,  
    "Balenos1": None, 
    "Balenos2": None, 
    "Balenos3": None, 
    "Balenos4": None, 
    "Balenos5": None, 
    "Balenos6": None, 
    "Calpheon1": None, 
    "Calpheon2": None, 
    "Calpheon3": None, 
    "Calpheon4": None, 
    "Calpheon5": None, 
    "Calpheon6": None, 
    "Serendia1": None, 
    "Serendia2": None, 
    "Serendia3": None, 
    "Serendia4": None, 
    "Serendia5": None, 
    "Serendia6": None, 
    "Kamasylvia1": None, 
    "Kamasylvia2": None, 
    "Kamasylvia3": None, 
    "Kamasylvia4": None, 
    "Valencia1": None, 
    "Valencia2": None, 
    "Valencia3": None, 
    "Valencia4": None, 
    "Valencia5": None, 
    "Valencia6": None, 
    "Mediah1": None, 
    "Mediah2": None, 
    "Mediah3": None, 
    "Mediah4": None, 
    "Mediah5": None, 
    "Mediah6": None, 
    "Velia1": None, 
    "Velia2": None, 
    "Velia3": None, 
    "Velia4": None, 
    "Velia5": None, 
    "Velia6": None
}


################# EVENTS #################

@bot.command()
async def create_event(ctx, channel: discord.VoiceChannel, name, description, start_time_str, duration_minutes: int):
    """
    Creates a Discord event in the specified channel.

    Usage:      !create_event #channel "Event Name" "Event Description" <t:1743987610:F> duration_minutes
    Example:    !create_event #testing "Test Event" "" <t:1743987610:F> 30
     !create_event #General "Test Event" "" <t:1744592340:F> 30
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
    try:
        now = datetime.now(timezone.utc)
        for guild in bot.guilds:
            remind_channel = discord.utils.get(guild.text_channels, name=NOTIFY_CHANNEL)
            if remind_channel:
                events = await guild.fetch_scheduled_events()
                for event in events:
                    try:
                        interested_users = []
                        async for user in event.users():
                            interested_users.append(user)

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
                    except Exception as e:
                        print(f"Error processing event {event.id}: {e}")
    except Exception as e:
        print(f"Error in event_reminder loop: {e}")


################# CHESTS #################

@tasks.loop(minutes=1)
async def update_chest_info():
    now = datetime.now(timezone.utc)
    info_channel = bot.get_channel(CHEST_INFO_CHANNEL_ID)
    if info_channel:
        try:
            info_message = await info_channel.fetch_message(CHEST_INFO_MESSAGE_ID)
            updated_events = {}
            for server, last_event_time in next_chest_events.items():
                if last_event_time is not None and now >= last_event_time:
                    next_event_time = last_event_time + timedelta(hours=3, minutes=13)
                    next_chest_events[server] = next_event_time
                    updated_events[server] = next_event_time

            if updated_events:
                print(f"Chest event times updated: {updated_events}")

            # Format the updated information string
            info_string = "Next chest event\n"
            for server, event_time in sorted(next_chest_events.items()):
                if event_time:
                    timestamp = int(event_time.timestamp())
                    info_string += f"{server}: <t:{timestamp}:F>\n"
                else:
                    info_string += f"{server}: Not Set\n"

            await info_message.edit(content=info_string)

        except discord.NotFound:
            print(f"Error: Info message with ID {CHEST_INFO_MESSAGE_ID} not found in channel {CHEST_INFO_CHANNEL_ID}")
            update_chest_info.stop()
        except discord.Forbidden:
            print(f"Error: Bot does not have permission to access channel {CHEST_INFO_CHANNEL_ID} or message {CHEST_INFO_MESSAGE_ID}")
            update_chest_info.stop()
        except Exception as e:
            print(f"Error in update_chest_info loop: {e}")

@bot.command(name="chest")
async def chest_command(ctx, server: str, time_str: str):
    """Manually sets the next chest event time for a specific server.
    Usage: !chest <ServerName> <t:unix_timestamp:F> or None
    Example: !chest Serendia4 <t:1744592340:F>
    Example: !chest Serendia1 None
    """
    if server in next_chest_events:
        if time_str.lower() == "none":
            next_chest_events[server] = None
            await update_chest_info()
        else:
            parsed_time = parse_discord_timestamp(time_str)
            if parsed_time:
                next_chest_events[server] = parsed_time
                timestamp = int(parsed_time.timestamp())
                await update_chest_info()
            else:
                await ctx.send("Invalid Discord timestamp format. Please use <t:unix_timestamp:F> or 'None'.")
    else:
        await ctx.send(f"Server '{server}' not found.")


################# GEAR #################

def load_gear_data():
    """Loads user gear data from the JSON file."""
    if os.path.exists(GEAR_DATA_FILE):
        with open(GEAR_DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_gear_data(gear_data):
    """Saves user gear data to the JSON file."""
    with open(GEAR_DATA_FILE, 'w') as f:
        json.dump(gear_data, f, indent=4)

@bot.command()
async def Gear(ctx, target_user: discord.Member = None, image_url: str = None):
    """Saves, updates, or retrieves a gear image URL for a specific user.
    Can also save an attached image if no URL is provided.
    """
    user_id_requesting = str(ctx.author.id)
    gear_data = load_gear_data()
    attached_image_url = None

    if ctx.message.attachments:
        # If there's an attachment, use the first one's URL
        attached_image_url = ctx.message.attachments[0].url

    if image_url:
        # Save or update the URL provided as text
        gear_data[user_id_requesting] = image_url
        save_gear_data(gear_data)
        await ctx.send(f"Gear image URL saved/updated for {ctx.author.name}.")
    elif attached_image_url:
        # Save or update the URL of the attached image
        gear_data[user_id_requesting] = attached_image_url
        save_gear_data(gear_data)
        await ctx.send(f"Gear image from attachment saved/updated for {ctx.author.name}.")
    elif target_user:
        # Retrieve the URL for the mentioned user
        target_user_id = str(target_user.id)
        if target_user_id in gear_data:
            saved_url = gear_data[target_user_id]
            await ctx.reply(f"{saved_url}")
        else:
            await ctx.reply(f"{target_user.name} has not saved a gear image URL yet.")
    else:
        # Retrieve the URL for the command sender if no arguments are provided
        if user_id_requesting in gear_data:
            saved_url = gear_data[user_id_requesting]
            await ctx.reply(f"{saved_url}")
        else:
            await ctx.reply("You have not saved a gear image URL yet. Use `!Gear <image_url>` or attach an image to save one.")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)
    if not event_reminder.is_running():
        event_reminder.start()
    if not update_chest_info.is_running():
        info_channel = bot.get_channel(CHEST_INFO_CHANNEL_ID)
        global CHEST_INFO_MESSAGE_ID

        if info_channel and CHEST_INFO_MESSAGE_ID is None:
            # Create the initial info message
            info_string = "Next chest event\n"
            for server in sorted(next_chest_events.keys()):
                info_string += f"{server}: Not Set\n"
            try:
                initial_message = await info_channel.send(info_string)
                CHEST_INFO_MESSAGE_ID = initial_message.id
                print(f"Initial chest info message created with ID: {CHEST_INFO_MESSAGE_ID}")
                update_chest_info.start()  # Start the update task after creating the message
            except discord.Forbidden:
                print(f"Error: Bot does not have permission to send messages in channel {CHEST_INFO_CHANNEL_ID}")
            except Exception as e:
                print(f"Error creating initial info message: {e}")
        elif info_channel and CHEST_INFO_MESSAGE_ID is not None:
            update_chest_info.start()  # Start the update task if the message ID is already set
        elif not info_channel:
            print(f"Error: Info channel with ID {INFO_CHANNEL_ID} not found.")

async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
