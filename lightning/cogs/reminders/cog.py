"""
Lightning.py - A Discord bot
Copyright (C) 2019-present LightSage

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation at version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timedelta
from typing import (TYPE_CHECKING, Annotated, Any, Dict, Literal, Optional,
                    Union, overload)
from zoneinfo import ZoneInfo, available_timezones

import asyncpg
import discord
import rapidfuzz
from discord import app_commands
from discord.ext.commands import clean_content, parameter
from sanctum.exceptions import NotFound

from lightning import LightningCog, LightningContext, hybrid_group
from lightning.cogs.reminders.converters import (TimeParseTransformer,
                                                 TimeZoneConverter)
from lightning.cogs.reminders.ui import ReminderEdit, ReminderPaginator
from lightning.formatters import plural
from lightning.models import Timer
from lightning.utils import time as ltime
from lightning.utils.helpers import UserObject, dm_user

if TYPE_CHECKING:
    from lightning import LightningBot

log: logging.Logger = logging.getLogger(__name__)


class Reminders(LightningCog):
    """Commands that remind you something"""

    def __init__(self, bot: LightningBot) -> None:
        super().__init__(bot)

        self.task_available = asyncio.Event()
        self._current_task: Optional[Timer] = None
        self._task = self.bot.loop.create_task(self.handle_timers())

        # Timezones
        self.available_timezones = available_timezones()

    def cog_unload(self) -> None:
        self._task.cancel()

    async def get_next_timer(self) -> Optional[Timer]:
        query = """SELECT * FROM timers
                   WHERE (expiry AT TIME ZONE 'UTC' AT TIME ZONE timezone) < (NOW() + $1::interval)
                   ORDER BY "expiry" LIMIT 1;"""
        record = await self.bot.pool.fetchrow(query, timedelta(days=24))
        return Timer.from_record(record) if record else None

    async def short_timers(self, seconds: float, record: Timer) -> None:
        """A short loop for the bot to process small timers."""
        await asyncio.sleep(seconds)
        self.bot.dispatch(f'lightning_{record.event}_complete', record)

    async def execute_timer(self, record: Timer) -> None:
        self.bot.dispatch(f'lightning_{record.event}_complete', record)
        await self.bot.api.delete_timer(record.id)

    async def wait_for_timers(self) -> Timer:
        record = await self.get_next_timer()

        if not record:
            self.task_available.clear()
            self._current_task = None
            await self.task_available.wait()
            return await self.get_next_timer()

        self.task_available.set()
        return record

    def restart_timer_task(self):
        """Cancels the timer task and recreates the task again"""
        self._task.cancel()
        self._task = self.bot.loop.create_task(self.handle_timers())

    @overload
    async def add_timer(self, event: str, created: datetime, expiry: datetime, *, force_insert: Literal[True],
                        timezone: ZoneInfo, **kwargs: Any) -> dict[str, Any]:
        ...

    @overload
    async def add_timer(self, event: str, created: datetime, expiry: datetime, *, force_insert: Literal[False] = False,
                        timezone: ZoneInfo, **kwarg: Any) -> Union[dict[str, Any], asyncio.Task]:
        ...

    async def add_timer(self, event: str, created: datetime, expiry: datetime, *, force_insert: bool = False,
                        timezone: ZoneInfo, **kwargs) -> Union[dict[str, Any], asyncio.Task]:
        """Adds a pending timer to the timer system

        Parameters
        ----------
        event : str
            The name of the event to trigger.
        created : datetime.datetime
            The creation of the timer.
        expiry : datetime.datetime
            When the job should be done.
        force_insert : bool, optional
            Whether to insert into the database regardless of how long the expiry is. Defaults to False
        **kwargs
            Keyword arguments about the event that are passed to the database
        """
        created = ltime.strip_tzinfo(created.astimezone(ZoneInfo("UTC")))
        expiry = ltime.strip_tzinfo(expiry.astimezone(ZoneInfo("UTC")))

        delta = (expiry - created).total_seconds()
        if delta <= 60 and not force_insert:
            return self.bot.loop.create_task(self.short_timers(delta, Timer(None, event, created, expiry, timezone.key,
                                                                            kwargs)),
                                             name=f"lightning-{event}-timer")

        payload = {"event": event, "created": created.isoformat(), "expiry": expiry.isoformat(),
                   "timezone": timezone.key, "extra": dict(kwargs)}
        record = await self.bot.api.create_timer(payload)

        if delta <= (86400 * 24):  # 24 days
            self.task_available.set()

        if self._current_task and expiry < self._current_task.expiry:
            # Cancel the task and re-run it
            self.restart_timer_task()

        return record

    async def handle_timers(self) -> None:
        await self.bot.wait_until_ready()
        try:
            while not self.bot.is_closed():
                timer = self._current_task = await self.wait_for_timers()
                current_time = datetime.utcnow()
                if timer.expiry >= current_time:
                    tmp = (timer.expiry - current_time).total_seconds()
                    await asyncio.sleep(tmp)
                # Dispatch the job and delete it.
                await self.execute_timer(timer)
        except asyncio.CancelledError:
            raise
        except (discord.ConnectionClosed, asyncpg.PostgresConnectionError):
            self.restart_timer_task()
        except Exception as e:
            exc = "".join(traceback.format_exception(type(e), e, e.__traceback__, chain=False))
            log.error(exc)
            embed = discord.Embed(title="Timer Error", description=f"```{exc}```")
            await self.bot._error_logger.put(embed)

    async def get_user_tzinfo(self, user_id: int) -> ZoneInfo:
        """
        Gets a user's timezone.

        If one is not found, defaults to UTC
        """
        timezone = await self.bot.get_user_timezone(user_id)
        return ZoneInfo(timezone) if timezone else ZoneInfo("UTC")

    @hybrid_group(usage="<when>", aliases=["reminder"], invoke_without_command=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(when="When to remind you of something, in UTC")
    async def remind(self, ctx: LightningContext, *,
                     when: ltime.UserFriendlyTimeResult =
                     parameter(converter=ltime.UserFriendlyTime(clean_content, default='something'))
                     ) -> None:
        """
        Reminds you of something after a certain date.

        The input can be any direct date (e.g. YYYY-MM-DD), a human readable offset, or a Discord timestamp.

        Examples:
        - "{prefix}remind in 2 days write essay" (2 days)
        - "{prefix}remind 1 hour do dishes" (1 hour)
        - "{prefix}remind 60s clean" (60 seconds)
        """
        if ctx.interaction:
            channel = None
        else:
            channel = ctx.channel.id

        timezone = await self.get_user_tzinfo(ctx.author.id)

        if when.dt > ctx.message.created_at + timedelta(days=365 * 10):
            await ctx.send("You cannot set a timer for longer than 10 years!", ephemeral=True)
            return

        _id = await self.add_timer("reminder", ctx.message.created_at, when.dt,
                                   timezone=timezone,
                                   reminder_text=when.arg,
                                   author=ctx.author.id,
                                   channel=channel,
                                   message_id=ctx.message.id)

        if type(_id) is dict:
            content = f"Ok {ctx.author.mention}, I'll remind you{' in your DMs ' if not channel else ''} at"\
                      f" {discord.utils.format_dt(when.dt)} about {when.arg}. (#{_id['id']})"
        else:
            content = f"Ok {ctx.author.mention}, I'll remind you{' in your DMs ' if not channel else ''} at"\
                      f" {discord.utils.format_dt(when.dt)} about {when.arg}."

        if channel is None:
            embed = discord.Embed().set_footer(text="Make sure to have your DMs open so you can receive your reminder"
                                                    " when it's time!")
            await ctx.send(content, embed=embed, ephemeral=True)
        else:
            await ctx.send(content, ephemeral=True)

    @remind.app_command.command(name="set")
    @app_commands.describe(when="When to remind you of something", text="The text to remind you of")
    async def reminder_set_app_command(self, interaction: discord.Interaction,
                                       when: Annotated[datetime, TimeParseTransformer], text: str = "something"):
        """Reminds you of something after a certain date or time"""
        timezone = await self.get_user_tzinfo(interaction.user.id)

        if when < interaction.created_at + timedelta(seconds=59 * 5):
            await interaction.response.send_message("A DM reminder must be at least 5 minutes from now!",
                                                    ephemeral=True)
            return

        if when > interaction.created_at + timedelta(days=365 * 10):
            await interaction.response.send_message("You cannot set a reminder for longer than 10 years!",
                                                    ephemeral=True)
            return

        data = await self.add_timer("reminder", interaction.created_at, when,
                                    timezone=timezone,
                                    reminder_text=text,
                                    author=interaction.user.id,
                                    channel=None,
                                    force_insert=True)

        content = f"Ok {interaction.user.mention}, I'll remind you in your DMs at"\
                  f" {discord.utils.format_dt(when)} about {text}. (#{data['id']})"

        embed = discord.Embed().set_footer(text="Make sure to have your DMs open so you can receive your reminder"
                                                " when it's time!")
        await interaction.response.send_message(content, embed=embed, ephemeral=True)

    @remind.command(name="edit")
    @app_commands.describe(reminder_id="The ID of the reminder")
    async def edit_reminder(self, ctx: LightningContext, reminder_id: int) -> None:
        """Edits a reminder you own"""
        try:
            record = await self.bot.api.get_timer(reminder_id)
        except NotFound:
            await ctx.send("Could not find a reminder with that ID!", ephemeral=True)
            return

        if record['extra']['author'] != ctx.author.id:
            await ctx.send("Could not find a reminder with ID belonging to you!", ephemeral=True)
            return

        prompt = ReminderEdit(reminder_id, context=ctx)
        await prompt.start(wait=False)

    @remind.command(name='list')
    async def listreminders(self, ctx: LightningContext) -> None:
        """Shows up to 25 of your reminders

        This will only show reminders that are longer than one minute."""
        try:
            records = await self.bot.api.get_user_reminders(ctx.author.id, limit=25)
        except NotFound:
            await ctx.send("Seems you haven't set a reminder yet...", ephemeral=True)
            return

        view = ReminderPaginator(records, context=ctx)
        await view.start(wait=False, ephemeral=True)

    @remind.command(name='delete', aliases=['cancel'])
    @app_commands.describe(reminder_id="The reminder's ID you want to delete")
    async def deletereminder(self, ctx: LightningContext, *, reminder_id: int) -> None:
        """Deletes a reminder you own by its ID.

        You can get the ID of a reminder with {prefix}remind list"""
        try:
            await self.bot.api.delete_user_reminder(ctx.author.id, reminder_id)
        except NotFound:
            await ctx.send("I couldn't find a reminder with that ID!")
            return

        if self._current_task and self._current_task.id == reminder_id:
            # Matches current timer, re-run loop as it's gone
            self.restart_timer_task()

        await ctx.send(f"Successfully deleted reminder (ID: {reminder_id})", ephemeral=True)

    @remind.command(name='clear')
    async def clear_reminders(self, ctx: LightningContext) -> None:
        """Clears all of your reminders"""
        queryc = """SELECT COUNT(*)
                    FROM timers
                    WHERE event = 'reminder'
                    AND extra ->> 'author' = $1
                """
        count = await self.bot.pool.fetchval(queryc, str(ctx.author.id))

        if count == 0:
            await ctx.send("You don't have any reminders that I can delete")
            return

        confirm = await ctx.confirm(f"Are you sure you want to remove {plural(count):reminder}?")
        if not confirm:
            await ctx.send("Cancelled", ephemeral=True)
            return

        query = """DELETE FROM timers
                   WHERE event = 'reminder'
                   AND extra ->> 'author' = $1
                   RETURNING id;
                """
        records = await self.bot.pool.fetch(query, str(ctx.author.id))
        ids = [r['id'] for r in records]

        if self._current_task.event == 'reminder' and self._current_task.id in ids:
            # cancel task
            self.restart_timer_task()

        await ctx.send("Cleared all of your reminders.", ephemeral=True)

    @hybrid_group(name="timezone")
    async def reminder_timezone(self, ctx: LightningContext):
        """Commands to manage your timezone in the bot"""
        ...

    @reminder_timezone.command(name='set')
    async def set_reminder_timezone(self, ctx: LightningContext, timezone: Annotated[ZoneInfo, TimeZoneConverter]):
        """
        Sets your timezone in the bot

        When you set your timezone, the bot will use your timezone for timed moderation commands and reminders.
        """
        query = """INSERT INTO user_settings (user_id, timezone)
                   VALUES ($1, $2)
                   ON CONFLICT (user_id)
                   DO UPDATE SET timezone=EXCLUDED.timezone;"""
        await self.bot.pool.execute(query, ctx.author.id, timezone.key)

        await self.bot.redis_pool.set(f"lightning:user_settings:{ctx.author.id}:timezone", timezone.key)
        await ctx.send(f"I set your timezone! IANA key: {timezone.key}", ephemeral=True)

    @set_reminder_timezone.autocomplete('timezone')
    async def set_timezone_autocomplete(self, itx: discord.Interaction, string: str):
        if len(string) == 0:
            # This really doesn't do much...
            string = itx.locale.name

        return [app_commands.Choice(name=x, value=x) for x, y, z in rapidfuzz.process.extract(string,
                                                                                              self.available_timezones,
                                                                                              limit=25,
                                                                                              score_cutoff=60)]

    @reminder_timezone.command(name='get')
    async def get_reminder_timezone(self, ctx: LightningContext):
        """
        Shows your configured timezone
        """
        query = """SELECT * FROM user_settings WHERE user_id=$1;"""
        record = await self.bot.pool.fetchrow(query, ctx.author.id)
        if not record:
            await ctx.send(f"You haven't set a timezone yet!\n> You can set one with {ctx.prefix}timezone set",
                           ephemeral=True)
            return

        dt = discord.utils.utcnow().astimezone(ZoneInfo(record['timezone'])).strftime('%b %d, %Y %I:%M %p')

        await ctx.send(f"Your timezone is {record['timezone']}! "
                       f"The current time for you is {dt}",
                       ephemeral=True)

    @reminder_timezone.command(name='remove')
    async def remove_timezone(self, ctx: LightningContext):
        """Removes your configured timezone"""
        # await self.bot.api.edit_user_settings(ctx.author.id, {"timezone": None})
        query = "UPDATE user_settings SET timezone=NULL WHERE user_id=$1;"
        r = await self.bot.pool.execute(query, ctx.author.id)
        if r == "UPDATE 0":
            await ctx.send("You never had a timezone set!", ephemeral=True)
            return

        await self.bot.redis_pool.delete(f"lightning:user_settings:{ctx.author.id}:timezone")
        await ctx.send("I removed your timezone", ephemeral=True)

    @LightningCog.listener()
    async def on_lightning_reminder_complete(self, timer: Timer) -> None:
        assert timer.extra is not None

        channel = self.bot.get_channel(timer.extra['channel'])
        user = self.bot.get_user(timer.extra['author']) or UserObject(id=timer.extra['author'])

        if not channel and isinstance(user, UserObject):
            # rip
            return

        dt_format = discord.utils.format_dt(ltime.add_tzinfo(timer.created_at), style="R")

        if len(timer.extra['reminder_text']) >= 1800 and "message_id" not in timer.extra:
            paste = await self.bot.api.create_paste(timer.extra['reminder_text'])
            reminder_content = f"This content was too long for me to send. You can see it at {paste['full_url']}"
        else:
            reminder_content = timer.extra['reminder_text'][:1800]

        message = f"<@!{user.id}> You asked to be reminded "\
                  f"{dt_format} about {reminder_content}"
        secret = timer.extra.pop("secret", False)

        # The reminder will be DM'd on one of the following conditions
        # 1. The channel the reminder was made in has been deleted/is not cached.
        # 2. The reminder has been explicitly marked as secret.
        if not channel or secret is True:
            await dm_user(user, message)
            return

        kwargs: Dict[str, Any] = {"allowed_mentions": discord.AllowedMentions(users=[user], roles=False,
                                                                              everyone=False)}

        if "message_id" in timer.extra:
            _id = channel.guild.id if hasattr(channel, 'guild') else None
            ref = discord.MessageReference(message_id=timer.extra['message_id'], channel_id=channel.id, guild_id=_id,
                                           fail_if_not_exists=False)
            kwargs["reference"] = ref

        await channel.send(message, **kwargs)
