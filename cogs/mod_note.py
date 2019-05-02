import discord
from discord.ext import commands
from discord.ext.commands import Cog
from db.user_log import userlog
import db.mod_check

# Robocop-ng's Note Cog, but slightly adapted. Robocop-ng's note cog is under the MIT License.
# https://github.com/reswitched/robocop-ng/blob/master/cogs/mod_note.py
class ModNote(Cog):
    def __init__(self, bot):
        """Note cog for adding a note to user. 
        Useful for not taking moderation action on a user."""
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')

    @commands.guild_only()
    @db.mod_check.check_if_at_least_has_staff_role("Helper")
    @commands.command(aliases=["addnote"])
    async def note(self, ctx, target: discord.Member, *, note: str = ""):
        """Adds a note to a user, staff only."""
        userlog(ctx.guild, target.id, ctx.author, note,
                "notes", target.name)
        await ctx.send(f"{ctx.author.mention}: noted {target}!")

    @commands.guild_only()
    @db.mod_check.check_if_at_least_has_staff_role("Helper")
    @commands.command(aliases=["addnoteid"])
    async def noteid(self, ctx, target: int, *, note: str = ""):
        """Adds a note to a user by userid, staff only."""
        userlog(ctx.guild, target, ctx.author, note,
                "notes")
        await ctx.send(f"ID {target} was noted!")


def setup(bot):
    bot.add_cog(ModNote(bot))
