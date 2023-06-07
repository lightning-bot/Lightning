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

from typing import Union

import discord
from discord import app_commands
from discord.ext import commands

from lightning import (GuildContext, LightningCog, LightningContext, command,
                       hybrid_command)
from lightning.cogs.info.converters import ReadableChannel
from lightning.converters import GuildorNonGuildUser
from lightning.utils.checks import no_threads
from lightning.utils.time import natural_timedelta

query_member = commands.Author.replace(annotation=GuildorNonGuildUser)


class DiscordMeta(LightningCog):
    @command(aliases=['avy'])
    async def avatar(self, ctx: LightningContext, *,
                     member: Union[discord.Member, discord.User] = query_member) -> None:
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
    async def userinfo(self, ctx: LightningContext, *,
                       member: Union[discord.User, discord.Member] = query_member) -> None:
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
            embed.set_footer(text='This user is not in this server.')

        activities = getattr(member, 'activities', None)
        if activities:
            activities_fmt = '\N{BULLET} '.join([f"{self._determine_activity(a)}\n" for a in activities])
            desc.append(f"**Activities**: {activities_fmt.strip()}")

        if hasattr(member, 'joined_at'):
            desc.append(f"**Joined**: {discord.utils.format_dt(member.joined_at)} "
                        f"({natural_timedelta(member.joined_at, accuracy=3)})")

        if hasattr(member, 'roles'):
            if roles := [x.mention for x in member.roles if not x.is_default()]:
                revrole = reversed(roles[:10])
                if len(roles) > 10:
                    fmt = " ".join(revrole) + f" (and {len(roles) - 10} other roles)"
                else:
                    fmt = " ".join(revrole)

                embed.add_field(name=f"Roles [{len(roles)}]",
                                value=fmt,
                                inline=False)

        if member.bot:
            desc.append("\nThis user is a bot.")

        embed.description = "\n".join(desc)
        await ctx.send(embed=embed)

    @hybrid_command()
    @commands.guild_only()
    @app_commands.guild_only()
    async def roleinfo(self, ctx: GuildContext, *, role: discord.Role) -> None:
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

    @commands.guild_only()
    @command(aliases=['guildinfo'], usage='')
    async def serverinfo(self, ctx: GuildContext, guild: discord.Guild = commands.CurrentGuild) -> None:
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

        if guild.chunked is False:
            await guild.chunk()

        embed.add_field(name="Members",
                        value=f'Total: {guild.member_count} ({sum(m.bot for m in guild.members)} bots)',
                        inline=False)

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
    async def permissions(self, ctx: LightningContext, member: discord.Member = commands.Author,
                          channel: discord.TextChannel = commands.CurrentChannel) -> None:
        """Shows channel permissions for a member"""
        await self.show_channel_permissions(channel, member, ctx)

    @command()
    @no_threads()
    @commands.guild_only()
    async def topic(self, ctx: LightningContext, *,
                    channel: ReadableChannel = commands.CurrentChannel) -> None:
        """Quotes a channel's topic"""
        if channel.topic is None or channel.topic == "":
            await ctx.send(f"{channel.mention} has no topic set!")
            return

        await ctx.send(f"**Topic for {channel.mention}**:\n{channel.topic}")
