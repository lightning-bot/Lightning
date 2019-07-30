from discord.ext import commands

def is_guild(guild_id):
    async def predicate(ctx):
        if not ctx.guild:
            return False
        if ctx.guild.id == guild_id:
            return True
    return commands.check(predicate)