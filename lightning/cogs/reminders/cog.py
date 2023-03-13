"""
Lightning.py - A Discord bot
Copyright (C) 2019-2023 LightSage

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
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

import asyncpg
import discord
from discord import app_commands
from discord.ext.commands import clean_content, parameter
from sanctum.exceptions import NotFound

from lightning import LightningCog, LightningContext, hybrid_group
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

    def cog_unload(self) -> None:
        self._task.cancel()

    async def get_next_timer(self) -> Optional[Timer]:
        query = """SELECT * FROM timers
                   WHERE "expiry" < (CURRENT_DATE + $1::interval)
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

    async def wait_for_timers(self) -> Optional[Timer]:
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

    async def add_timer(self, event: str, created: datetime, expiry: datetime, *, force_insert: bool = False,
                        **kwargs) -> Union[asyncpg.Record, asyncio.Task]:
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
        created = ltime.strip_tzinfo(created)
        expiry = ltime.strip_tzinfo(expiry)  # Just in case

        delta = (expiry - created).total_seconds()
        if delta <= 60 and force_insert is False:
            # A loop for small timers
            return self.bot.loop.create_task(self.short_timers(delta, Timer(None, event, created, expiry, kwargs)),
                                             name=f"lightning-{event}-timer")

        payload = {"event": event, "created": created.isoformat(), "expiry": expiry.isoformat(), "extra": dict(kwargs)}
        record = await self.bot.api.create_timer(payload)

        if delta <= (86400 * 24):  # 24 days
            self.task_available.set()

        if self._current_task and expiry < self._current_task.expiry:
            # Cancel the task and re-run it
            self.restart_timer_task()

        return record['id']

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

    @hybrid_group(usage="<when>", aliases=["reminder"], invoke_without_command=True, fallback="set")
    @app_commands.describe(when="When to remind you of something, in UTC")
    async def remind(self, ctx: LightningContext, *,
                     when: ltime.UserFriendlyTimeResult =
                     parameter(converter=ltime.UserFriendlyTime(clean_content, default='something'))
                     ) -> None:  # noqa: F821
        """Reminds you of something after a certain date.

        The input can be any direct date (e.g. YYYY-MM-DD), a human readable offset, or a Discord timestamp.

        Examples:
        - "{prefix}remind in 2 days write essay" (2 days)
        - "{prefix}remind 1 hour do dishes" (1 hour)
        - "{prefix}remind 60s clean" (60 seconds)

        Times are in UTC.
        """
        if ctx.interaction:
            channel = None
        else:
            channel = ctx.channel.id

        _id = await self.add_timer("reminder", ctx.message.created_at, when.dt, reminder_text=when.arg,
                                   author=ctx.author.id, channel=channel, message_id=ctx.message.id)

        duration_text = ltime.natural_timedelta(when.dt, source=ctx.message.created_at)

        if type(_id) == int:
            content = f"Ok {ctx.author.mention}, I'll remind you in {'your DMs in ' if not channel else ''}"\
                      f"{duration_text} about {when.arg}. (#{_id})"
        else:
            content = f"Ok {ctx.author.mention}, I'll remind you in {'your DMs in ' if not channel else ''}"\
                      f"{duration_text} about {when.arg}."

        if channel is None:
            embed = discord.Embed().set_footer(text="Make sure to have your DMs open so you can receive your reminder"
                                                    " when it's time!")
            await ctx.send(content, embed=embed, ephemeral=True)
        else:
            await ctx.send(content, ephemeral=True)

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
        await prompt.start()

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
            await ctx.send("Cancelled")
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

        await ctx.send("Cleared all of your reminders.")

    @LightningCog.listener()
    async def on_lightning_reminder_complete(self, timer: Timer) -> None:
        assert timer.extra is not None

        channel = self.bot.get_channel(timer.extra['channel'])
        user = self.bot.get_user(timer.extra['author']) or UserObject(id=timer.extra['author'])

        if not channel and isinstance(user, UserObject):
            # rip
            return

        dt_format = discord.utils.format_dt(ltime.add_tzinfo(timer.created_at), style="R")
        message = f"<@!{user.id}> You asked to be reminded "\
                  f"{dt_format} about {timer.extra['reminder_text']}"
        secret = timer.extra.pop("secret", False)

        # The reminder will be DM'd on one of the following conditions
        # 1. The channel the reminder was made in has been deleted/is not cached.
        # 2. The reminder has been explicitly marked as secret.
        if not channel or secret is True:
            await dm_user(user, message)
            return

        kwargs: Dict[str, Any] = {"allowed_mentions": discord.AllowedMentions(users=[user])}

        if "message_id" in timer.extra:
            _id = channel.guild.id if hasattr(channel, 'guild') else None
            ref = discord.MessageReference(message_id=timer.extra['message_id'], channel_id=channel.id, guild_id=_id,
                                           fail_if_not_exists=False)
            kwargs["reference"] = ref

        await channel.send(message, **kwargs)
