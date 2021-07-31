"""
Lightning.py - A Discord bot
Copyright (C) 2019-2021 LightSage

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
import contextlib
import logging

import discord

from lightning import ConfigFlags, LightningBot, LightningCog, LightningContext

log: logging.Logger = logging.getLogger(__name__)


class FeaturesListeners(LightningCog):
    """Listeners that handle feature flags (and maybe some misc stuff)."""

    def toggle_feature_flag(self, guild_id, flag):
        return self.bot.get_cog("Config").toggle_feature_flag(guild_id, flag)

    @LightningCog.listener()
    async def on_command_completion(self, ctx: LightningContext) -> None:
        if ctx.guild is None:
            return

        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        if not record or not record.flags.invoke_delete:
            return

        try:
            await ctx.message.delete()
        except discord.Forbidden:
            # Toggle it off
            await self.toggle_feature_flag(ctx.guild.id, ConfigFlags.invoke_delete)
            await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
            return
        except discord.NotFound:
            return

    async def apply_users_roles(self, member: discord.Member, *, reapply=False, punishments_only=True, all=False):
        query = "SELECT roles, punishment_roles FROM roles WHERE guild_id=$1 AND user_id=$2;"
        record = await self.bot.pool.fetchrow(query, member.guild.id, member.id)

        if not record:
            return

        roles = []
        unresolved = []

        def get_and_append(r):
            role = member.guild.get_role(r)
            if role:
                roles.append(role)
            else:
                unresolved.append(role)

        if record['punishment_roles']:
            for role in record['punishment_roles']:
                get_and_append(role)

            if len(unresolved) != 0:
                query = "UPDATE roles SET punishment_roles=$1 WHERE guild_id=$2 AND user_id=$3;"
                log.debug(f"Unable to resolve roles: {unresolved}")
                await self.bot.pool.execute(query, [r.id for r in roles], member.guild.id, member.id)

            await member.add_roles(*roles, reason="Applying previous punishment roles")

            if punishments_only:
                return

        if record['roles'] and reapply:
            for role in record['roles']:
                get_and_append(role)
            await member.add_roles(*roles, reason="Applying old roles back.")

    @LightningCog.listener()
    async def on_member_remove(self, member):
        record = await self.bot.get_guild_bot_config(member.guild.id)

        if not record or not record.flags.role_reapply or len(member.roles) == 0:
            return

        query = """INSERT INTO roles (guild_id, user_id, roles)
                   VALUES ($1, $2, $3::bigint[])
                   ON CONFLICT (guild_id, user_id)
                   DO UPDATE SET roles = EXCLUDED.roles;"""
        await self.bot.pool.execute(query, member.guild.id, member.id,
                                    [r.id for r in member.roles if r is not r.is_default()])

    @LightningCog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        record = await self.bot.get_guild_bot_config(member.guild.id)

        if not record or not record.autorole_id:
            if hasattr(record, 'flags'):
                await self.apply_users_roles(member, reapply=bool(record.flags.role_reapply))
            else:
                await self.apply_users_roles(member)
            return

        role = record.autorole

        if not role:
            await self.apply_users_roles(member, reapply=record.flags.role_reapply)
            # Role is deleted
            await self.remove_config_key(member.guild.id, "autorole")
            await self.bot.get_guild_bot_config.invalidate(member.guild.id)
            return

        await self.apply_users_roles(member, reapply=bool(record.flags.role_reapply))

        if role not in member.roles:
            with contextlib.suppress(discord.Forbidden, discord.HTTPException):
                await member.add_roles(role, reason="Applying configured autorole")


def setup(bot: LightningBot) -> None:
    bot.add_cog(FeaturesListeners(bot))
