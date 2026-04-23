import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import utils


class EventsCog(commands.Cog, name="Events"):

    def __init__(self, bot):
        self.bot = bot
        self.event_reminder.start()

    def cog_unload(self):
        self.event_reminder.cancel()

    @tasks.loop(minutes=1)
    async def event_reminder(self):
        try:
            now = datetime.now(timezone.utc)
            for guild in self.bot.guilds:
                remind_channel = discord.utils.get(guild.text_channels, name=utils.NOTIFY_CHANNEL)

                if remind_channel:
                    for event in await guild.fetch_scheduled_events():
                        try:
                            if event.status != discord.EventStatus.scheduled:
                                continue
                            interested = [u async for u in event.users()]
                            mentions   = " ".join(u.mention for u in interested)
                            thirty = event.start_time - timedelta(minutes=30)
                            five   = event.start_time - timedelta(minutes=5)
                            if thirty <= now < thirty + timedelta(minutes=1):
                                await remind_channel.send(f"Reminder! {event.name} starts in 30 minutes! {event.url}\n{mentions}")
                            elif five <= now < five + timedelta(minutes=1):
                                await remind_channel.send(f"Reminder! {event.name} starts in 5 minutes! {event.url}\n{mentions}")
                        except Exception as e:
                            print(f"Error processing event {event.id}: {e}")

                try:
                    for minutes_ahead in [30, 5]:
                        window_start = now + timedelta(minutes=minutes_ahead)
                        window_end   = window_start + timedelta(minutes=1)
                        cal_events   = await utils.pool.fetch("""
                            SELECT ce.title,
                                   array_agg(u.discord_id) FILTER (WHERE u.discord_id IS NOT NULL) AS discord_ids
                            FROM calendar_events ce
                            LEFT JOIN calendar_event_interests cei ON cei.event_id = ce.id
                            LEFT JOIN users u ON u.id = cei.user_id
                            WHERE ce.event_time IS NOT NULL AND ce.event_timezone IS NOT NULL
                            GROUP BY ce.id, ce.title
                            HAVING (ce.event_date + ce.event_time) AT TIME ZONE ce.event_timezone BETWEEN $1 AND $2
                        """, window_start, window_end)
                        rc = discord.utils.get(guild.text_channels, name=utils.NOTIFY_CHANNEL)
                        if not rc:
                            continue
                        for ev in cal_events:
                            mentions = " ".join(
                                m.mention for did in (ev['discord_ids'] or [])
                                if did and (m := guild.get_member(int(did)))
                            )
                            msg = f"Reminder! {ev['title']} starts in {minutes_ahead} minutes!"
                            if mentions:
                                msg += f"\n{mentions}"
                            await rc.send(msg)
                except Exception as e:
                    print(f"Error checking calendar reminders: {e}")
        except Exception as e:
            print(f"Error in event_reminder loop: {e}")

    @event_reminder.before_loop
    async def before_event_reminder(self):
        await self.bot.wait_until_ready()

    @commands.command()
    async def create_event(self, ctx, name: str, description: str, start_time_str: str, duration_minutes: int):
        """Creates a Discord scheduled event.
        Usage: !create_event "Name" "Description" <t:timestamp:F> duration_minutes
        """
        try:
            start_time = utils.parse_discord_timestamp(start_time_str)
            if start_time is None:
                try:
                    start_time = datetime.fromisoformat(start_time_str)
                except ValueError:
                    await ctx.send("Invalid time format. Use `<t:unix_timestamp:F>` or ISO format.")
                    return
            end_time = start_time + timedelta(minutes=duration_minutes)
            await ctx.guild.create_scheduled_event(
                name=name, description=description,
                start_time=start_time, end_time=end_time,
                entity_type=discord.EntityType.external,
                location="BDO",
                privacy_level=discord.PrivacyLevel.guild_only,
            )
            await ctx.send(f'Event "{name}" created!')
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")


async def setup(bot):
    await bot.add_cog(EventsCog(bot))
