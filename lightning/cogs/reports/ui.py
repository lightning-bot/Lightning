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

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo

import discord
import sanctum
from sanctum.exceptions import NotFound

from lightning import GuildContext, LightningBot, lock_when_pressed
from lightning.cache import registry as cache_registry
from lightning.cogs.automod.punishments import PUNISHMENTS, apply_punishment
from lightning.constants import LIGHTNING_COLOR
from lightning.enums import ActionType, AutoModPunishmentType
from lightning.errors import LightningError
from lightning.formatters import truncate_text
from lightning.ui import ExitableMenu, MenuLikeView, UpdateableMenu, _BaseView
from lightning.utils.helpers import dm_user
from lightning.utils.modlogformats import construct_dm_message
from lightning.utils.time import FutureTime, add_tzinfo

if TYPE_CHECKING:
    from lightning.cogs.reports.cog import Reports as ReportsCog


REPORT_PERMISSIONS = discord.Permissions(moderate_members=True, kick_members=True,
                                         ban_members=True)


def has_actionable_permissions(perms: discord.Permissions):
    return perms.value & REPORT_PERMISSIONS.value != 0


def format_message_content(message: discord.Message) -> str:
    """Format message text and media consistently across report views."""
    description = message.content
    if message.attachments:
        attach_urls = [f'[{attachment.filename}]({attachment.url})' for attachment in message.attachments]
        description += '\n\N{BULLET} ' + '\n\N{BULLET} '.join(attach_urls)
    if message.embeds:
        description += "\n \N{BULLET} Message contains an embed(s)"
    return description


class ReasonModal(discord.ui.Modal, title="Message Report"):
    reason = discord.ui.TextInput(label='Reason', style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction[LightningBot], /) -> None:
        return await interaction.response.defer()
        # return await interaction.response.send_message("I got your response!", ephemeral=True)


class ActionOptionsModal(discord.ui.Modal, title="Action Options"):
    duration = discord.ui.TextInput(label="Duration", style=discord.TextStyle.short)
    dt: Optional[FutureTime] = None

    def __init__(self, dashboard: ActionDashboard):
        super().__init__()
        self.dashboard = dashboard

    async def on_submit(self, interaction: discord.Interaction[LightningBot]) -> None:
        tzinfo = await interaction.client.get_user_timezone(interaction.user.id)
        if tzinfo:
            tzinfo = ZoneInfo(tzinfo)
        else:
            tzinfo = timezone.utc

        try:
            dt = FutureTime(self.duration.value, tz=tzinfo)
        except Exception as e:
            await interaction.response.send_message(e, ephemeral=True)
            return

        if dt.dt < (interaction.created_at + timedelta(minutes=5)):
            await interaction.response.send_message(content="The duration must be at least 5 minutes!", ephemeral=True)
            return

        self.dt = dt

        # The dashboard might have timed out while the modal was open, so don't bring it back.
        if self.dashboard.is_finished():
            await interaction.response.defer()
            return

        self.dashboard.duration = dt.dt
        self.dashboard.update_components()
        await interaction.response.edit_message(view=self.dashboard)


action_options = [discord.SelectOption(label="No action", value="no_action"),
                  discord.SelectOption(label="Delete", value="delete", emoji="<:delete:1099772388448673972>"),
                  discord.SelectOption(label="Warn", value="warn", emoji="\N{WARNING SIGN}"),
                  discord.SelectOption(label="Mute", value="mute", emoji="\N{SPEAKER WITH CANCELLATION STROKE}"),
                  discord.SelectOption(label="Kick", value="kick", emoji="\N{WOMANS BOOTS}"),
                  discord.SelectOption(label="Ban", value="ban", emoji="\N{HAMMER}")]


class ActionReasonModal(ReasonModal):
    def __init__(self, dashboard: ActionDashboard):
        super().__init__()
        self.dashboard = dashboard
        self.reason.required = True
        self.reason.default = dashboard.reason

    async def on_submit(self, interaction: discord.Interaction[LightningBot], /) -> None:
        # The dashboard might have timed out while the modal was open, so don't bring it back.
        if self.dashboard.is_finished():
            await interaction.response.defer()
            return

        self.dashboard.reason = self.reason.value
        self.dashboard.update_components()
        await interaction.response.edit_message(view=self.dashboard)


class ActionDashboard(_BaseView, discord.ui.LayoutView):
    # We need rows here so the decorated buttons and select can go inside the container.
    select_row = discord.ui.ActionRow()
    options_row = discord.ui.ActionRow()
    confirm_row = discord.ui.ActionRow()

    def __init__(self, message: discord.Message, *, timeout=180):
        self.message = message
        self.action = None
        self.reason = "No reason provided."
        self.notify = False
        self.duration: Optional[datetime] = None
        super().__init__(timeout=timeout)
        # LayoutView adds the rows for us, but we want them inside the container instead.
        self.clear_items()
        self.container = discord.ui.Container(accent_color=LIGHTNING_COLOR)
        self.container.add_item(discord.ui.TextDisplay(
            f"## Report Action · {message.author.mention}\n"
            "-# Select a punishment, then configure any options before confirming."))
        self.container.add_item(discord.ui.Separator())
        self.summary = discord.ui.TextDisplay("")
        self.container.add_item(self.summary)
        self.container.add_item(self.select_row)
        self.container.add_item(self.options_row)
        self.container.add_item(discord.ui.Separator())
        self.container.add_item(self.confirm_row)
        self.add_item(self.container)
        self.update_components()

    def update_components(self) -> None:
        """Keep the controls and summary in sync with the selected punishment."""
        self.confirm_button.disabled = self.action is None
        self.reason_button.disabled = self.action in (None, "no_action")
        self.notify_button.disabled = self.action in (None, "no_action")
        self.duration_button.disabled = self.action not in ("mute", "ban")
        self.notify_button.label = "Don't Notify" if self.notify else "Notify"
        for option in self.select_callback.options:
            option.default = option.value == self.action

        if self.action is None:
            self.summary.content = "### Punishment\nSelect a punishment below."
        elif self.action == "no_action":
            self.summary.content = "### No action\nPress Confirm to complete this report without a punishment."
        else:
            self.summary.content = (
                f"### {self.action.capitalize()}\n**Reason:** {self.reason}\n"
                f"**Notify:** {'Yes' if self.notify else 'No'}")
            if self.action in ("mute", "ban"):
                duration = discord.utils.format_dt(self.duration) if self.duration else "Not set"
                self.summary.content += f"\n**Duration:** {duration}"

    async def complete(self, interaction: discord.Interaction) -> None:
        # We can't use message content with Components v2, so this needs a TextDisplay too.
        self.clear_items()
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay("## Report Action\nSuccessfully completed action!"),
            accent_color=LIGHTNING_COLOR))
        await interaction.response.edit_message(view=self)
        self.stop()

    @select_row.select(options=action_options, min_values=1, max_values=1, placeholder="Select a punishment")
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.action = select.values[0]
        # Only mute and ban take a duration, so clear it if we're switching to something else.
        if self.action not in ("mute", "ban"):
            self.duration = None
        if self.action == "no_action":
            self.notify = False
        self.update_components()
        await interaction.response.edit_message(view=self)

    @options_row.button(label="Reason", disabled=True, emoji="\N{MEMO}")
    async def reason_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ActionReasonModal(self))

    @options_row.button(label="Duration", disabled=True, emoji="\N{HOURGLASS WITH FLOWING SAND}")
    async def duration_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ActionOptionsModal(self))

    @options_row.button(label="Notify", style=discord.ButtonStyle.blurple, disabled=True, emoji="\N{BELL}")
    async def notify_button(self, interaction: discord.Interaction[LightningBot], button: discord.ui.Button):
        self.notify = not self.notify

        if self.notify:
            content = f"{self.message.author.mention} will receive a DM when you press Confirm."
            self.notify_button.label = "Don't Notify"
        else:
            content = f"{self.message.author.mention} will not receive a DM when you press Confirm."
            self.notify_button.label = "Notify"

        self.update_components()
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(content, ephemeral=True)

    def member_unactionable(self):
        return self.message.guild.owner_id == self.message.author.id or \
            self.message.guild.me.top_role <= self.message.author.top_role

    @confirm_row.button(label="Confirm", style=discord.ButtonStyle.green, disabled=True)
    async def confirm_button(self, interaction: discord.Interaction[LightningBot], button: discord.ui.Button):
        if self.action == "no_action":
            await self.complete(interaction)
            return

        if self.member_unactionable():
            await interaction.response.send_message("Unable to action on the message author due to role hierarchy!",
                                                    ephemeral=True)
            return

        punishment = PUNISHMENTS[AutoModPunishmentType[self.action.upper()]]
        if self.notify:
            dm_message = construct_dm_message(self.message.author, punishment.verb, punishment.preposition,
                                              reason=self.reason,
                                              middle=f" due to a message you posted. ({self.message.jump_url})")
            await dm_user(self.message.author, dm_message)

        # The moderator pressing confirm is the one responsible for this action, not the bot.
        try:
            applied = await apply_punishment(interaction.client, punishment.type, self.message, reason=self.reason,
                                             moderator=interaction.user, duration=self.duration)
        except LightningError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        if not applied:
            await interaction.response.send_message("Unable to apply the punishment. Check that the bot has the "
                                                    "required permissions and that a mute role is configured.",
                                                    ephemeral=True)
            return

        await self.complete(interaction)

    @confirm_row.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message()
        await interaction.delete_original_response()
        # The report dashboard checks this to see if we cancelled.
        self.action = None
        self.stop()


class ReportDashboard(discord.ui.View):
    def __init__(self, message_id: int, guild_id: int, channel_id: int, *,
                 dashboard_message_id: int = 0, reported_user_id: int = 0):
        self.dismissed = False
        self.actioned = False
        self.message_id = message_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        # This should never be zero
        self.dashboard_message_id = dashboard_message_id
        # Dashboard v2
        self.reported_user_id = reported_user_id
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="View Reported Message",
                                        url=f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}",
                                        row=1))

        self.action_button.custom_id = f"lightning-reportdash-{message_id}:action"
        self.view_reporters_button.custom_id = f"lightning-reportdash-{message_id}:view"
        self.dismiss_button.custom_id = f"lightning-reportdash-{message_id}:dismiss"
        self.view_context_button.custom_id = f"lightning-reportdash-{message_id}:context-lens"

        self.update_buttons()

    @classmethod
    def from_record(cls, record):
        c = cls(record['message_id'], record['guild_id'], record['channel_id'],
                dashboard_message_id=record['report_message_id'],
                reported_user_id=record['reported_user_id'])
        c.dismissed = record['dismissed']
        c.actioned = record['actioned']
        return c

    def update_buttons(self):
        if self.dismissed:
            self.dismiss_button.label = "Re-Open"
            self.dismiss_button.style = discord.ButtonStyle.green
        else:
            self.dismiss_button.label = "Dismiss"
            self.dismiss_button.style = discord.ButtonStyle.red

        self.view_reporters_button.disabled = self.dismissed
        self.action_button.disabled = self.actioned or self.dismissed

    async def interaction_check(self, interaction: discord.Interaction[LightningBot]) -> bool:
        return has_actionable_permissions(interaction.permissions)

    async def fetch_message(self, interaction: discord.Interaction[LightningBot]) -> Optional[discord.Message]:
        channel = interaction.guild.get_channel_or_thread(self.channel_id)
        if not channel:
            return

        return await channel.fetch_message(self.message_id)

    @discord.ui.button(label="Action", style=discord.ButtonStyle.red)
    async def action_button(self, interaction: discord.Interaction[LightningBot], button: discord.ui.Button):
        try:
            msg = await self.fetch_message(interaction)
        except discord.NotFound:
            # Automatically assume it was actioned against.
            self.dismissed = True
            await interaction.client.api.edit_guild_message_report(interaction.guild.id, self.message_id,
                                                                   {"dismissed": self.dismissed})
            self.update_buttons()
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("This message was deleted!", ephemeral=True)
            return

        if not msg:
            await interaction.response.send_message("I was unable to fetch the message", ephemeral=True)
            return

        view = ActionDashboard(msg)
        await interaction.response.send_message(view=view, ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())
        timed_out = await view.wait()
        if timed_out is True or view.action is None:
            return

        self.actioned = True
        await interaction.client.api.edit_guild_message_report(interaction.guild.id, self.message_id,
                                                               {"actioned": True})
        self.update_buttons()
        await interaction.message.edit(view=self)

    async def fetch_message_context(self, interaction: discord.Interaction[LightningBot]) -> Optional[tuple[list[discord.Message], discord.Message, list[discord.Message]]]:
        """Fetch the context of the message, includes messages before and after the reported message.

        Returns a tuple containing:
        - A list of messages before the reported message.
        - The reported message itself.
        - A list of messages after the reported message.

        If the message cannot be fetched, returns None.
        """
        try:
            msg = await self.fetch_message(interaction)

            if not msg:
                return

            before = [m async for m in msg.channel.history(limit=3, before=msg)]
            after = [m async for m in msg.channel.history(limit=3, after=msg)]
        except discord.HTTPException:
            return

        return before, msg, after

    @discord.ui.button(label="View Context", style=discord.ButtonStyle.blurple)
    async def view_context_button(self, interaction: discord.Interaction[LightningBot], button: discord.ui.Button):
        # It's a context lens and provides information on the user who was reported. It helps makes better decisions.
        assert interaction.guild is not None

        # Note to myself: Reported User ID is a Dashboard v2 thing.
        # Old dashboards were not migrated so I don't have to worry about fallbacks.
        desc = [f"## Moderation Context - <@!{self.reported_user_id}>"]
        member = interaction.guild.get_member(self.reported_user_id)
        if member:
            # Data can be made when the member is in the guild, otherwise we don't know.
            # Typehints want to say it's joined_at can be None, but guests can't be reported anyways.
            desc.append(f"**Joined:** {discord.utils.format_dt(member.joined_at)}")
            desc.append(f"**Account Created:** {discord.utils.format_dt(member.created_at)}")
        else:
            desc.append("**Joined:** Unknown")
            desc.append("**Account Created:** Unknown")

        # Dashboard snowflakes encode when the report was created.
        cutoff_snowflake = discord.utils.time_snowflake(discord.utils.utcnow() - timedelta(days=30))
        query = """SELECT COUNT(*) FROM message_reports
                    WHERE guild_id=$1
                    AND reported_user_id=$2
                    AND report_message_id >= $3;"""
        report_count = await interaction.client.pool.fetchval(query, interaction.guild.id,
                                                              self.reported_user_id, cutoff_snowflake)
        # Normally, I would check for the view's version in the record, but old ones are not getting migrated!
        desc.append(f"\n**Reports against the user (last 30 days):** {report_count}")

        container = discord.ui.Container(discord.ui.TextDisplay("\n".join(desc)),
                                         accent_color=LIGHTNING_COLOR)

        try:
            infractions = await interaction.client.api.get_user_infractions(interaction.guild.id,
                                                                            self.reported_user_id)
        except sanctum.NotFound:
            infractions = []

        if infractions:
            # Count matching types and exact stored reasons among the 5 most recent infractions.
            recent = sorted(infractions, key=lambda x: x['created_at'], reverse=True)[:5]
            # Use a collections.Counter to tally occurrences of each (action, reason) pair among the recent infractions.
            counts = Counter((record['action'], record['reason']) for record in recent)
            lines = [
                f"**{str(ActionType(action)).capitalize()}** - {count}x - {reason or 'No reason provided.'}"
                for (action, reason), count in counts.items()
            ]

            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay("### Recent Infractions\n" + "\n".join(lines)))

        # Conversation Context
        context = await self.fetch_message_context(interaction)
        if context:
            before, current, after = context
            container.add_item(discord.ui.Separator())
            conversation = (
                f"### Conversation Context\n### [Jump to the reported message]({current.jump_url})\n" +
                "\n".join(f"{m.author.mention}: {format_message_content(m)}" for m in before) +
                f"\n\N{POLICE CARS REVOLVING LIGHT} **Reported Message:** {format_message_content(current)}\n" +
                "\n".join(f"{m.author.mention}: {format_message_content(m)}" for m in after)
            )
            container.add_item(discord.ui.TextDisplay(truncate_text(conversation, limit=3000)))

        view = discord.ui.LayoutView(timeout=None)
        view.add_item(container)

        await interaction.response.send_message(view=view, ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button(label="View Reporters", style=discord.ButtonStyle.blurple)
    async def view_reporters_button(self, interaction: discord.Interaction[LightningBot], button: discord.ui.Button):
        reporters = await interaction.client.api.get_guild_message_reporters(interaction.guild.id, self.message_id)
        entries = []
        for count, record in enumerate(reporters, start=1):
            # Add UTC timezone to the reported_at timestamp and format it for display
            timestamp = add_tzinfo(datetime.fromisoformat(record['reported_at']))
            timestamp_str = discord.utils.format_dt(timestamp)
            # Dashboard v2 now anonymizes reporters to moderators, but they're still recorded in the database.
            # The philosophy behind this is to prevent potential biases from forming based on the reporter.
            # Helps avoid social pressure or pressure around reporting messages.
            entries.append(f"**Confidential Reporter #{count}** — {timestamp_str}\n"
                           f"{record['reason'] or 'No reason provided.'}")

        container = discord.ui.Container(
            discord.ui.TextDisplay("## Reporters"),
            discord.ui.Separator(),
            discord.ui.TextDisplay("\n\n".join(entries) or "No reporters found."),
            accent_color=LIGHTNING_COLOR,
        )
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(container)

        await interaction.response.send_message(view=view, ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button()
    async def dismiss_button(self, interaction: discord.Interaction[LightningBot], button: discord.ui.Button):
        self.dismissed = not self.dismissed
        await interaction.client.api.edit_guild_message_report(interaction.guild.id, self.message_id,
                                                               {"dismissed": self.dismissed})
        self.update_buttons()
        await interaction.response.edit_message(view=self)


class _SelectSM(discord.ui.ChannelSelect['ChannelSelect']):
    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None

        await interaction.response.defer()

        self.view.stop(interaction=interaction)


class ChannelSelect(MenuLikeView):
    def __init__(self,
                 **kwargs):
        super().__init__(**kwargs)
        select = _SelectSM(max_values=1, channel_types=[discord.ChannelType.text],
                           placeholder="Select a channel")
        self.add_item(select)

        self._select = select

    @property
    def values(self):
        return self._select.values or []

    async def cleanup(self, **kwargs) -> None:
        return


class CogGuildContext(GuildContext):
    cog: ReportsCog


class ReportConfiguration(UpdateableMenu, ExitableMenu):
    ctx: CogGuildContext

    async def format_initial_message(self, ctx: GuildContext):
        try:
            record = await ctx.bot.api.get_guild_moderation_config(ctx.guild.id)
        except NotFound:
            return "You haven't set up message reports yet!"

        if record['message_report_channel_id'] is None:
            return "You haven't set up message reports yet!"

        channel = ctx.guild.get_channel(record['message_report_channel_id'])
        if not channel:
            ...

        return f"**Message Report Configuration**\nReport Channel: <#{record['message_report_channel_id']}>"

    async def update_components(self) -> None:
        try:
            record = await self.ctx.bot.api.get_guild_moderation_config(self.ctx.guild.id)
        except NotFound:
            record = None

        if not record or record["message_report_channel_id"] is None:
            self.set_channel_button.disabled = False
            self.remove_report_channel_button.disabled = True
            return

        if self.ctx.guild.get_channel(record['message_report_channel_id']):
            self.set_channel_button.disabled = True
            self.remove_report_channel_button.disabled = False

    async def invalidate_config(self, guild_id: int):
        if c := cache_registry.get("mod_config"):
            await c.invalidate(str(guild_id))

    @discord.ui.button(label="Set report channel", style=discord.ButtonStyle.blurple)
    @lock_when_pressed
    async def set_channel_button(self, interaction: discord.Interaction[LightningBot], button: discord.ui.Button):
        content = "What channel would you like to use? You can select the channel below."
        view = ChannelSelect(context=self.ctx)
        await interaction.response.send_message(content, view=view, ephemeral=True)
        await view.wait()
        await interaction.delete_original_response()

        if not view.values:
            return

        channel = view.values[0].resolve()
        if not channel:
            channel = await view.values[0].fetch()

        query = """INSERT INTO guild_mod_config (guild_id, message_report_channel_id)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET message_report_channel_id = EXCLUDED.message_report_channel_id;"""
        await interaction.client.pool.execute(query, interaction.guild.id, channel.id)
        await self.invalidate_config(interaction.guild.id)

        await self.update()

    @discord.ui.button(label="Remove report channel", style=discord.ButtonStyle.red)
    @lock_when_pressed
    async def remove_report_channel_button(self, interaction: discord.Interaction[LightningBot],
                                           button: discord.ui.Button):
        record = await self.ctx.bot.api.get_guild_moderation_config(interaction.guild.id)
        channel = interaction.guild.get_channel(record['message_report_channel_id'])
        if not channel:
            await interaction.response.send_message("The configuration has already been removed!")
            return

        await self.ctx.cog.on_guild_channel_delete(channel)

        try:
            await channel.delete(reason="Removing report configuration")
            cd = True
        except discord.HTTPException:
            cd = False

        content = "Removed all configuration and reports!"
        if cd:
            content = "Removed the reports channel, configuration, and reports!"

        await interaction.response.send_message(content, ephemeral=True)
        await self.update()
