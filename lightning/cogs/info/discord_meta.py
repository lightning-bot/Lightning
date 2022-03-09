"""
Lightning.py - A Discord bot
Copyright (C) 2019-2022 LightSage

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

import collections
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from lightning import LightningCog, command
from lightning.converters import GuildorNonGuildUser
from lightning.utils.helpers import Emoji
from lightning.utils.time import natural_timedelta

if TYPE_CHECKING:
    from lightning import LightningContext


class DiscordMeta(LightningCog):
    @command(aliases=['avy'])
    async def avatar(self, ctx: LightningContext, *, member: GuildorNonGuildUser = commands.default.Author) -> None:
        """Displays a user's avatar"""
        parts = []
        if hasattr(member, 'guild_avatar') and member.guild_avatar:
            parts.append(f"[Link to guild avatar]({member.guild_avatar.with_static_format('png')})")
        if member.avatar:
            parts.append(f"[Link to avatar]({member.avatar.with_static_format('png')})")
        if member.default_avatar:
            parts.append(f"[Link to default avatar]({member.default_avatar.url})")
        embed = discord.Embed(color=discord.Color.blue(), description='\n'.join(parts))
        embed.set_author(name=f"{member.name}\'s Avatar")
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    def _determine_activity(self, activity: discord.ActivityType) -> str:
        if isinstance(activity, discord.Spotify):
            artists = ', '.join(activity.artists)
            return f"Listening to [{activity.title}]"\
                f"(https://open.spotify.com/track/{activity.track_id}) by {artists}"
        elif isinstance(activity, discord.Streaming):
            return f"Streaming [{activity.name}]({activity.url})"
        elif isinstance(activity, discord.CustomActivity):
            act_name = activity.name if activity.name is not None else ""
            return f"{activity.emoji} {act_name}" if activity.emoji else act_name
        else:
            return activity.name

    @command(aliases=['ui'])
    async def userinfo(self, ctx: LightningContext, *, member: GuildorNonGuildUser = commands.default.Author) -> None:
        """Gives information about a member or a user"""
        embed = discord.Embed(title=member, color=member.colour)
        desc = [f"**ID**: {member.id}",
                f"**Account Creation**: {discord.utils.format_dt(member.created_at)} "
                f"({natural_timedelta(member.created_at, accuracy=3)})"]
        embed.set_thumbnail(url=member.display_avatar.url)

        if member == self.bot.user:
            desc.append(f"**Shared Servers**: {len(self.bot.guilds)}")
        else:
            desc.append(f"**Shared Servers**: {len(member.mutual_guilds)}")

        if not isinstance(member, discord.Member):
            embed.set_footer(text='This member is not in this server.')

        activities = getattr(member, 'activities', None)
        if activities is not None:
            activities_fmt = '\N{BULLET} '.join([f"{self._determine_activity(a)}\n" for a in activities])
            desc.append(f"**Activities**: {activities_fmt.strip()}")

        if hasattr(member, 'joined_at'):
            desc.append(f"**Joined**: {discord.utils.format_dt(member.joined_at)} "
                        f"({natural_timedelta(member.joined_at, accuracy=3)})")

        if hasattr(member, 'roles'):
            if roles := [x.mention for x in member.roles if not x.is_default()]:
                revrole = reversed(roles)
                embed.add_field(name=f"Roles [{len(roles)}]",
                                value=" ".join(revrole) if len(roles) < 10 else "Cannot show all roles",
                                inline=False)

        if member.bot:
            desc.append("\nThis user is a bot.")

        embed.description = "\n".join(desc)
        await ctx.send(embed=embed)

    @command()
    @commands.guild_only()
    async def roleinfo(self, ctx: LightningContext, *, role: discord.Role) -> None:
        """Gives information for a role"""
        em = discord.Embed(title=role.name, color=role.color)
        desc = [f"**Creation**: {natural_timedelta(role.created_at, accuracy=3)}",
                f"**Color**: {role.color}", f"**ID**: {role.id}", f"{len(role.members)} members have this role."]

        allowed = []
        for name, value in role.permissions:
            name = name.replace('_', ' ').replace('guild', 'server').title()
            if value:
                allowed.append(name)
        em.add_field(name="Permissions",
                     value=f"**Value**: {role.permissions.value}\n\n" + ", ".join(allowed),
                     inline=False)

        if role.managed:
            desc.append("This role is managed by an integration of some sort.")

        em.description = "\n".join(desc)
        await ctx.send(embed=em)

    @command()
    async def spotify(self, ctx: LightningContext, member: discord.Member = commands.default.Author) -> None:
        """Tells you what someone is listening to on Spotify"""
        if member.status is discord.Status.offline:
            await ctx.send(f"{member} needs to be online in order for me to check their Spotify status.")
            return

        activity = None
        for act in member.activities:
            if isinstance(act, discord.Spotify):
                activity = act
                break

        if not activity:
            await ctx.send(f"{member} is not listening to Spotify with Discord integration."
                           " If that is wrong, then blame Discord's API.")
            return

        embed = discord.Embed(title=activity.title, color=0x1DB954)
        embed.set_thumbnail(url=activity.album_cover_url)
        embed.set_author(name=member, icon_url=member.avatar.url)
        embed.add_field(name="Artist", value=', '.join(activity.artists))
        embed.add_field(name="Album", value=activity.album, inline=False)

        duration_m, duration_s = divmod(activity.duration.total_seconds(), 60)
        current_m, current_s = divmod((discord.utils.utcnow() - activity.start).seconds, 60)
        embed.description = f"{'%d:%02d' % (current_m, current_s)} - {'%d:%02d' % (duration_m, duration_s)}"

        await ctx.send(embed=embed)

    @commands.guild_only()
    @command(aliases=['guildinfo'], usage='')
    async def serverinfo(self, ctx: LightningContext, guild: discord.Guild = commands.default.CurrentGuild) -> None:
        """Shows information about the server"""
        guild = guild if await self.bot.is_owner(ctx.author) else ctx.guild

        embed = discord.Embed(title=guild.name)
        embed.description = f"**ID**: {guild.id}\n**Owner**: {str(guild.owner)}\n**Creation**: "\
                            f"{discord.utils.format_dt(guild.created_at)} ("\
                            f"{natural_timedelta(guild.created_at, accuracy=3)})"

        if guild.icon:
            if guild.icon.is_animated():
                icon_url = guild.icon.with_format("gif")
            else:
                icon_url = guild.icon.with_static_format("png")
            embed.description += f"\n**Icon**: [Link]({icon_url})"

            embed.set_thumbnail(url=icon_url)

        member_by_status = collections.Counter()
        for m in guild.members:
            member_by_status[str(m.status)] += 1
            if m.bot:
                member_by_status["bots"] += 1
        fmt = f'{Emoji.online} {member_by_status["online"]} ' \
              f'{Emoji.idle} {member_by_status["idle"]} ' \
              f'{Emoji.do_not_disturb} {member_by_status["dnd"]} ' \
              f'{Emoji.offline}{member_by_status["offline"]}\n' \
              f'<:bot_tag:596576775555776522> {member_by_status["bots"]}\n'\
              f'Total: {guild.member_count}'
        embed.add_field(name="Members", value=fmt, inline=False)

        features = {"VIP_REGIONS": "VIP Voice Servers",
                    "DISCOVERABLE": "Server Discovery",
                    "PARTNERED": "Partnered",
                    "VERIFIED": "Verified",
                    "COMMUNITY": "Community Server",
                    "WELCOME_SCREEN_ENABLED": "Welcome Screen",
                    "INVITE_SPLASH": "Invite Splash",
                    "ANIMATED_ICON": "Animated Server Icon",
                    "BANNER": "Banner",
                    "VANITY_URL": "Vanity Invite URL",
                    "NEWS": "News Channels",
                    "MEMBER_VERIFICATION_GATE_ENABLED": "Membership Screening",
                    "THREADS_ENABLED": "Threads",
                    "PRIVATE_THREADS": "Private Threads",
                    "ROLE_ICONS": "Role Icons"}
        if guild_features := [
            value for key, value in features.items() if key in guild.features
        ]:
            embed.add_field(name="Features",
                            value=', '.join(guild_features),
                            inline=False)

        if guild.premium_subscription_count:
            boosts = f"Tier: {guild.premium_tier}\n"\
                     f"{guild.premium_subscription_count} boosts."
            embed.add_field(name="Server Boost", value=boosts)

        await ctx.send(embed=embed)

    async def show_channel_permissions(self, channel: discord.TextChannel, member: discord.Member,
                                       ctx: LightningContext) -> None:
        perms = channel.permissions_for(member)
        embed = discord.Embed(title="Channel Permissions", color=member.color)
        allowed = []
        denied = []
        for name, value in perms:
            name = name.replace('_', ' ').replace('guild', 'server').title()
            if value:
                allowed.append(name)
            else:
                denied.append(name)
        if allowed:
            embed.add_field(name='Allowed', value='\n'.join(allowed))
        if denied:
            embed.add_field(name='Denied', value='\n'.join(denied))
        await ctx.send(embed=embed)

    @command()
    async def permissions(self, ctx: LightningContext, member: discord.Member = commands.default.Author,
                          channel: discord.TextChannel = commands.default.CurrentChannel) -> None:
        """Shows channel permissions for a member"""
        await self.show_channel_permissions(channel, member, ctx)
