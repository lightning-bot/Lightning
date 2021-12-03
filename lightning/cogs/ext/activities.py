"""
Lightning.py - A personal Discord bot
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
import discord

from lightning import LightningBot, LightningCog, LightningContext, command


class Activities(LightningCog):

    @command(aliases=['ytg'])
    async def youtube_together(self, ctx: LightningContext, *, voice_channel: discord.VoiceChannel):
        if not voice_channel.permissions_for(ctx.me).create_instant_invite:
            await ctx.send("Unable to create an invite for YouTube Together.\n"
                           "I need the `Create Invites` permission to do so.")
            return

        invite = await voice_channel.create_invite(max_age=0, target_type=discord.InviteTarget.embedded_application,
                                                   target_application_id=755600276941176913)

        await ctx.send(invite.url)


def setup(bot: LightningBot) -> None:
    bot.add_cog(Activities(bot))
